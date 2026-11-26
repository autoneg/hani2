"""The admin console API: layers, settings per layer, pools, balance and scenario details, and
the console's flows through the library API (``/api/admin/library``: upload, link, remove, sets)."""

import io
import json
import stat
import sys
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from hani2 import projects
from hani2 import scenario_store as store


@pytest.fixture
def client(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c
    hub.sessions.clear()


@pytest.fixture
def admin(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    assert r.status_code == 200
    return client


@pytest.fixture
def studies(hani2_home):
    projects.create_project("HI2027", full_name="Human-AI 2027", kind="assistant", defaults={"n_required": 2})
    projects.create_study("HI2027/hi-01", type="prolific", title="January")
    return hani2_home


def make_scenario(folder: Path, name: str = "Zebra", n_roles: int = 2, info=True) -> Path:
    from negmas import Scenario
    from negmas.outcomes import make_issue, make_os
    from negmas.preferences import LinearAdditiveUtilityFunction as U

    os_ = make_os([make_issue(["a", "b", "c"], "x"), make_issue(5, "y")], name=name)
    ufs = tuple(U.random(os_, reserved_value=0.1, normalized=True, name=n) for n in ("buyer", "seller")[:n_roles])
    s = Scenario(outcome_space=os_, ufuns=ufs, info={"title": f"{name} deal", "short_description": "s",
                                                     "long_description": "l"} if info else {})
    store.save_scenario(s, folder)
    return folder


def zip_dir(root: Path, prefix: str = "") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for f in sorted(root.rglob("*")):
            if f.is_file():
                zf.write(f, prefix + str(f.relative_to(root)))
    return buf.getvalue()


def zip_of(entries: dict, symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, c in entries.items():
            zf.writestr(n, c)
        if symlink:
            zi = zipfile.ZipInfo(symlink)
            zi.create_system = 3
            zi.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(zi, "/etc/passwd")
    return buf.getvalue()


def up(c, url, data):
    return c.post(url, content=data, headers={"content-type": "application/octet-stream"})


# --------------------------------------------------------------------------- #
# Access                                                                       #
# --------------------------------------------------------------------------- #
ADMIN_GETS = ["/api/admin/layers", "/api/admin/settings/env?layer=settings", "/api/admin/pools/opponent",
              "/api/admin/scenarios/Trade", "/api/admin/projects/default/studies/x/balance",
              "/api/admin/library/scenarios/default", "/api/admin/scheduling-methods"]


def test_admin_only(client):
    for u in ADMIN_GETS:
        assert client.get(u).status_code == 401, u
    assert client.patch("/api/admin/settings/env?layer=settings", json={}).status_code == 401
    assert client.delete("/api/admin/settings/env?layer=settings").status_code == 401
    assert client.put("/api/admin/pools/opponent", json={"items": []}).status_code == 401
    assert client.put("/api/admin/library/scenarios/default", json={"default": None}).status_code == 401
    assert client.post("/api/admin/library/opponents/describe", json=[]).status_code == 401
    client.post("/api/auth/register", json={"username": "bob", "password": "bobpass1"})
    client.post("/api/auth/login", json={"username": "bob", "password": "bobpass1"})
    for u in ADMIN_GETS:
        assert client.get(u).status_code == 403, u


# --------------------------------------------------------------------------- #
# Layers and settings                                                          #
# --------------------------------------------------------------------------- #
def test_layers(admin, studies, monkeypatch):
    r = admin.get("/api/admin/layers").json()
    ids = [x["id"] for x in r["layers"]]
    assert ids == ["settings", "project:HI2027", "study:HI2027/hi-01"]
    by = {x["id"]: x for x in r["layers"]}
    assert by["settings"]["label"] == "All projects (settings folder)" and by["settings"]["kind"] == "settings"
    assert by["project:HI2027"]["label"] == "Project HI2027" and by["project:HI2027"]["project"] == "HI2027"
    assert by["study:HI2027/hi-01"]["label"] == "Study HI2027/hi-01" and by["study:HI2027/hi-01"]["study"] == "hi-01"
    assert by["study:HI2027/hi-01"]["path"].replace("\\", "/").endswith("projects/HI2027/studies/hi-01")
    assert r["bound"] is None and r["default_study"] is None
    assert admin.get("/s/HI2027/hi-01/api/admin/layers").json()["bound"] == "study:HI2027/hi-01"
    monkeypatch.setenv("HANI2_STUDY", "HI2027/hi-01")
    assert admin.get("/api/admin/layers").json()["default_study"] == "HI2027/hi-01"


def test_layer_param_errors(admin, studies):
    assert admin.get("/api/admin/settings/env?layer=nonsense").status_code == 400
    assert admin.get("/api/admin/settings/env?layer=project:../x").status_code == 400
    assert admin.get("/api/admin/settings/env?layer=project:NOPE").status_code == 404
    assert admin.get("/api/admin/settings/env?layer=study:HI2027/none").status_code == 404
    assert admin.get("/api/admin/settings/env?layer=study:../../x").status_code in (400, 404)
    assert admin.get("/api/admin/settings/bogus?layer=settings").status_code == 404
    # project:default is the settings layer
    assert admin.get("/api/admin/settings/env?layer=project:default").json()["layer"] == "settings"


def test_layer_explicit_saves(admin, studies):
    home = studies
    base = "/api/admin/settings/llm"
    assert admin.patch(f"{base}?layer=project:HI2027", json={"model": "m-proj", "extra": {"a": 1}}).json()["own"] \
        == {"model": "m-proj", "extra": {"a": 1}}
    assert admin.patch(f"{base}?layer=project:HI2027", json={"extra": {"b": 2}}).json()["own"] \
        == {"model": "m-proj", "extra": {"a": 1, "b": 2}}
    assert not (home / "settings" / "llm_settings.json").exists()
    assert not (home / "projects/HI2027/studies/hi-01/llm_settings.json").exists()
    assert admin.put(f"{base}?layer=study:HI2027/hi-01", json={"temperature": 0.9}).json() == {"ok": True}
    st = json.loads((home / "projects/HI2027/studies/hi-01/llm_settings.json").read_text(encoding="utf-8"))
    assert st == {"temperature": 0.9}
    g = admin.get(f"{base}?layer=study:HI2027/hi-01").json()
    assert g["layer"] == "study:HI2027/hi-01" and g["own"] == {"temperature": 0.9}
    assert g["effective"]["model"] == "m-proj" and g["effective"]["temperature"] == 0.9
    assert g["inherited"]["model"] == "m-proj" and g["inherited"]["temperature"] != 0.9
    # settings layer: inherited is the bundled defaults
    admin.patch(f"{base}?layer=settings", json={"model": "m-settings"})
    s = admin.get(f"{base}?layer=settings").json()
    assert s["own"] == {"model": "m-settings"} and s["effective"]["model"] == "m-settings"
    assert s["inherited"]["model"] != "m-settings"
    p = admin.get(f"{base}?layer=project:HI2027").json()
    assert p["inherited"]["model"] == "m-settings" and p["effective"]["model"] == "m-proj"
    # DELETE a dotted key, then the whole file
    assert admin.delete(f"{base}?layer=project:HI2027&key=extra.a").json() == {"ok": True}
    assert admin.get(f"{base}?layer=project:HI2027").json()["own"] == {"model": "m-proj", "extra": {"b": 2}}
    assert admin.delete(f"{base}?layer=project:HI2027&key=extra.b").json() == {"ok": True}
    assert admin.get(f"{base}?layer=project:HI2027").json()["own"] == {"model": "m-proj"}
    assert admin.delete(f"{base}?layer=project:HI2027&key=nope").status_code == 404
    assert admin.delete(f"{base}?layer=project:HI2027").json() == {"ok": True}
    assert not (home / "projects/HI2027/llm_settings.json").exists()
    assert admin.get(f"{base}?layer=project:HI2027").json()["own"] == {}
    assert json.loads((home / "settings/llm_settings.json").read_text(encoding="utf-8")) == {"model": "m-settings"}
    assert admin.patch("/api/admin/settings/consent?layer=settings", json={"x": 1}).status_code == 400


def test_effective_under_layer_not_request_binding(admin, studies):
    admin.patch("/api/admin/settings/llm?layer=study:HI2027/hi-01", json={"model": "m-study"})
    admin.patch("/api/admin/settings/llm?layer=settings", json={"model": "m-set"})
    r = admin.get("/s/HI2027/hi-01/api/admin/settings/llm?layer=settings").json()
    assert r["effective"]["model"] == "m-set"
    r = admin.get("/s/HI2027/hi-01/api/admin/settings/llm?layer=project:HI2027").json()
    assert r["effective"]["model"] == "m-set"
    r = admin.get("/api/admin/settings/llm?layer=study:HI2027/hi-01").json()
    assert r["effective"]["model"] == "m-study"


def test_409_when_bound_without_layer(admin, studies):
    pre = "/s/HI2027/hi-01/api/admin/settings/llm"
    for call in (lambda u: admin.put(u, json={"model": "x"}), lambda u: admin.patch(u, json={"model": "x"}),
                 lambda u: admin.delete(u)):
        r = call(pre)
        assert r.status_code == 409
        assert r.json()["detail"] == ("This console is open in study HI2027/hi-01; say which layer to save to "
                                      "(?layer=settings, ?layer=project:HI2027 or ?layer=study:HI2027/hi-01)")
    assert not (studies / "settings/llm_settings.json").exists()
    assert admin.put(pre + "?layer=settings", json={"model": "x"}).status_code == 200
    assert json.loads((studies / "settings/llm_settings.json").read_text(encoding="utf-8")) == {"model": "x"}
    # unbound: back-compatible write of the settings folder
    assert admin.put("/api/admin/settings/llm", json={"model": "y"}).status_code == 200
    assert json.loads((studies / "settings/llm_settings.json").read_text(encoding="utf-8")) == {"model": "y"}
    assert admin.put("/api/admin/settings/consent?study=HI2027/hi-01", json={"text": "t"}).status_code == 200


def test_text_settings_layers(admin, studies):
    home = studies
    (home / "settings").mkdir(exist_ok=True)
    (home / "settings/consent.md").write_text("settings consent", encoding="utf-8")
    r = admin.get("/api/admin/settings/consent?layer=study:HI2027/hi-01").json()
    assert r["text"] == "" and r["exists"] is False and r["effective"] == "settings consent"
    assert r["source"] == "settings" and r["source_path"].replace("\\", "/").endswith("settings/consent.md")
    assert admin.put("/api/admin/settings/consent?layer=project:HI2027", json={"text": "project consent"}).json()["ok"]
    r = admin.get("/api/admin/settings/consent?layer=study:HI2027/hi-01").json()
    assert r["effective"] == "project consent" and r["source"] == "project:HI2027"
    r = admin.get("/api/admin/settings/consent?layer=project:HI2027").json()
    assert r["text"] == "project consent" and r["exists"] and r["source"] == "project:HI2027"
    admin.delete("/api/admin/settings/consent?layer=project:HI2027")
    assert admin.get("/api/admin/settings/consent?layer=project:HI2027").json()["exists"] is False
    (home / "settings/consent.md").unlink()
    r = admin.get("/api/admin/settings/consent?layer=settings").json()
    assert r["source"] == "bundled" and r["effective"]
    # old shape without layer
    assert set(admin.get("/api/admin/settings/consent").json()) == {"text"}
    assert set(admin.get("/api/admin/settings/consent?project=HI2027").json()) == {"text", "exists", "effective"}


def test_template_preview_with_layer(admin, studies):
    t = {"text": "{{project_name}}|{{study_name}}|{{n_required}}|{{project_full_name}}"}
    r = admin.post("/api/admin/templates/preview", json={**t, "layer": "study:HI2027/hi-01"}).json()
    assert r["rendered"] == "HI2027|hi-01|2|Human-AI 2027" and r["layer"] == "study:HI2027/hi-01"
    r = admin.post("/api/admin/templates/preview", json={**t, "layer": "project:HI2027"}).json()
    assert r["rendered"] == "HI2027||2|Human-AI 2027" and r["layer"] == "project:HI2027"
    r = admin.post("/api/admin/templates/preview", json={**t, "layer": "settings"}).json()
    assert r["rendered"].startswith("default||") and r["study"] is None
    assert admin.post("/api/admin/templates/preview", json={**t, "layer": "bogus"}).status_code == 400
    r = admin.post("/api/admin/templates/preview", json={"text": "{{study_name}}", "study": "HI2027/hi-01"}).json()
    assert r["rendered"] == "hi-01"


def test_study_info_results_rows(admin, studies):
    d = studies / "projects/HI2027/studies/hi-01/results"
    (d / "u1").mkdir(parents=True)
    (d / "u1/results.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    (d / "u2").mkdir()
    (d / "u2/results.csv").write_text("a,b\n5,6\n", encoding="utf-8")
    r = admin.get("/api/admin/projects/HI2027/studies/hi-01").json()
    assert r["participants"] == 2 and r["results_rows"] == 3
    assert "results_rows" not in admin.get("/api/admin/projects/HI2027/studies/hi-01").json()["overrides"]
    # what the GET adds is dropped on PUT, so the console can send back what it read
    r = admin.get("/api/admin/projects/HI2027/studies/hi-01").json()
    assert admin.put("/api/admin/projects/HI2027/studies/hi-01", json={"data": r}).status_code == 200
    sdata = yaml.safe_load((studies / "projects/HI2027/studies/hi-01/study.yaml").read_text(encoding="utf-8"))
    assert not {"results_rows", "participants", "links", "scheduling_effective", "errors"} & set(sdata)


def test_study_scheduling_round_trip(admin, studies):
    m = admin.get("/api/admin/scheduling-methods").json()
    assert set(m["dimensions"]) == {"opponents", "assistants", "scenarios"}
    assert all(o["details"] for o in m["dimensions"]["opponents"])
    url = "/api/admin/projects/HI2027/studies/hi-01"
    r = admin.get(url).json()
    data = {k: v for k, v in r.items() if k not in ("name", "project")}
    data["scheduling"] = {"opponents": "random"}
    assert admin.put(url, json={"data": data}).status_code == 200
    r = admin.get(url).json()
    assert r["scheduling"] == {"opponents": "random"} and r["scheduling_effective"]["opponents"] == "random"
    data = {k: v for k, v in r.items() if k not in ("name", "project")}
    data["scheduling"] = {}
    assert admin.put(url, json={"data": data}).status_code == 200  # inherit again
    r = admin.get(url).json()
    assert r["scheduling"] == {} and r["scheduling_effective"]["opponents"] == m["defaults"]["opponents"]
    bad = dict(data, scheduling={"opponents": "nope"})
    assert admin.put(url, json={"data": bad}).status_code == 400


# --------------------------------------------------------------------------- #
# Pools and balance                                                            #
# --------------------------------------------------------------------------- #
def test_pools_read_modify_write(admin, studies):
    home = studies
    pf = home / "projects/HI2027/project.yaml"
    admin.put("/api/admin/pools/opponent?layer=settings", json={"items": [":template"]})
    s = admin.get("/api/admin/pools/opponent?layer=settings").json()
    assert s["items"] == [":template"] and s["key"] == "opponents" and s["file"].replace("\\", "/").endswith("settings/env.json")
    assert s["editable"] and len(s["effective"]) > 3
    assert json.loads((home / "settings/env.json").read_text(encoding="utf-8")) == {"opponents": [":template"]}
    g = admin.put("/api/admin/pools/opponent?layer=project:HI2027",
                  json={"items": ["BoulwareTBNegotiator", "LinearTBNegotiator"]}).json()
    assert g["key"] == "defaults.opponents" and g["items"] == ["BoulwareTBNegotiator", "LinearTBNegotiator"]
    assert g["inherited"] == [":template"] and g["effective"] == ["BoulwareTBNegotiator", "LinearTBNegotiator"]
    data = yaml.safe_load(pf.read_text(encoding="utf-8"))
    assert data["defaults"] == {"n_required": 2, "opponents": ["BoulwareTBNegotiator", "LinearTBNegotiator"]}
    assert data["full_name"] == "Human-AI 2027" and data["kind"] == "assistant"
    admin.put("/api/admin/projects/HI2027/studies/hi-01", json={"data": {"type": "online", "title": "T", "wave": 3}})
    st = admin.put("/api/admin/pools/opponents?layer=study:HI2027/hi-01", json={"items": ["LinearTBNegotiator"]}).json()
    assert st["key"] == "overrides.opponents" and st["inherited"] == ["BoulwareTBNegotiator", "LinearTBNegotiator"]
    sdata = yaml.safe_load((home / "projects/HI2027/studies/hi-01/study.yaml").read_text(encoding="utf-8"))
    assert sdata["overrides"] == {"opponents": ["LinearTBNegotiator"]} and sdata["title"] == "T" and sdata["wave"] == 3
    # empty list removes the key (and the empty container)
    admin.put("/api/admin/pools/opponent?layer=study:HI2027/hi-01", json={"items": []})
    sdata = yaml.safe_load((home / "projects/HI2027/studies/hi-01/study.yaml").read_text(encoding="utf-8"))
    assert "overrides" not in sdata and sdata["title"] == "T"
    admin.put("/api/admin/pools/opponent?layer=project:HI2027", json={"items": []})
    assert yaml.safe_load(pf.read_text(encoding="utf-8"))["defaults"] == {"n_required": 2}
    assert admin.put("/api/admin/pools/opponent?layer=settings", json={"items": "x"}).status_code == 400
    assert admin.get("/api/admin/pools/bogus?layer=settings").status_code == 400


def test_assistant_pool(admin, studies):
    s = admin.get("/api/admin/pools/assistant?layer=settings").json()
    assert s["editable"] is False and "agent_class" in s["note"] and s["items"] == ["hani2.assistant:Assistant"]
    assert admin.put("/api/admin/pools/assistant?layer=settings", json={"items": []}).status_code == 400
    p = admin.put("/api/admin/pools/assistant?layer=project:HI2027", json={"items": [":tutorial"]}).json()
    assert p["key"] == "defaults.assistants" and p["effective"] == p["effective"] and p["items"] == [":tutorial"]
    assert p["inherited"] == ["hani2.assistant:Assistant"]
    st = admin.get("/api/admin/pools/assistant?layer=study:HI2027/hi-01").json()
    assert st["items"] == [] and st["inherited"] == [":tutorial"] and st["effective"] == p["effective"]


def test_balance(admin, studies):
    from hani2 import assignment

    admin.put("/api/admin/pools/assistant?layer=project:HI2027",
              json={"items": ["level1_hello:HelloAgent", "level2_rules:RulesAgent"]})
    ref = projects.StudyRef("HI2027", "hi-01")
    path = assignment.store_path(ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, "next_index": 2, "humans": {
        "u1": {"index": 0, "first_seen": "t0", "assistant": "level1_hello:HelloAgent", "assistant_group": "",
               "assigned_at": "t1"},
        "u2": {"index": 1, "first_seen": "t2"}}}), encoding="utf-8")
    r = admin.get("/api/admin/projects/HI2027/studies/hi-01/balance").json()
    assert r["pool"] == ["level1_hello:HelloAgent", "level2_rules:RulesAgent"] and r["source"] == "project"
    assert r["counts"] == {"level1_hello:HelloAgent": 1, "level2_rules:RulesAgent": 0} and r["humans"] == 2
    assert {a["user"] for a in r["assignments"]} == {"u1", "u2"}
    a1 = next(a for a in r["assignments"] if a["user"] == "u1")
    assert a1 == {"user": "u1", "index": 0, "assistant": "level1_hello:HelloAgent", "assistant_group": "",
                  "assigned_at": "t1", "first_seen": "t0"}
    assert admin.get("/api/admin/projects/HI2027/studies/none/balance").status_code == 404
    admin.put("/api/admin/pools/assistant?layer=study:HI2027/hi-01", json={"items": [":tutorial"]})
    r = admin.get("/api/admin/projects/HI2027/studies/hi-01/balance").json()
    assert r["source"] == "study" and r["group"] == "tutorial" and len(r["pool"]) == 10
    admin.put("/api/admin/pools/assistant?layer=study:HI2027/hi-01", json={"items": []})
    admin.put("/api/admin/pools/assistant?layer=project:HI2027", json={"items": []})
    r = admin.get("/api/admin/projects/HI2027/studies/hi-01/balance").json()
    assert r["source"] == "settings" and r["pool"] == ["hani2.assistant:Assistant"]


# --------------------------------------------------------------------------- #
# Scenarios: details, and the console's flows through the library API          #
# --------------------------------------------------------------------------- #
LIB = "/api/admin/library"


def test_scenario_details_builtin(admin, studies):
    d = admin.get("/api/admin/scenarios/Lease?layer=settings").json()
    assert d["generated"] is True and d["kind"] == "story" and len(d["roles"]) == 2 and d["issues"]
    assert sum(1 for x in d["roles"] if x["human"]) == 1 and d["sample"] and len(d["sample"]) <= 8
    assert set(d["sample"][0]) == {"outcome", "utilities"} and d["n_outcomes"]
    assert set(d["issues"][0]) == {"name", "type", "n_values", "values", "description"}
    d2 = admin.get("/api/admin/scenarios/Lease?layer=settings&generate=3").json()
    assert d2["generated"] and d2["title"] == d["title"]
    assert admin.get("/api/admin/scenarios/Nope").status_code == 404
    assert admin.get("/api/admin/scenarios/Lease?scenario=x&generate=abc").status_code == 422


def test_scenario_details_plot(admin, studies):
    """The outcome space as negmas's 2D utility plot: one Plotly figure, axes named by role."""
    d = admin.get("/api/admin/scenarios/Lease?layer=settings").json()
    assert "plots" not in d and d["plot_token"]  # the plot is fetched apart, not to delay the page
    pl = admin.get(f"/api/admin/scenarios/plot/{d['plot_token']}").json()
    assert len(pl["plots"]) == 1 and pl["plot_note"] == ""
    fig = pl["plots"][0]["figure"]
    names = [t["name"] for t in fig["data"]]
    assert "Outcomes" in names and "Pareto frontier" in names and "Nash Point" in names
    roles = {r["name"] for r in d["roles"]}
    assert not roles & set(names)  # no empty offer traces: no negotiation ran
    outcomes = next(t for t in fig["data"] if t["name"] == "Outcomes")
    assert len(outcomes["x"]) == d["n_outcomes"]
    human = next(r["name"] for r in d["roles"] if r["human"])
    assert fig["layout"]["xaxis"]["title"]["text"] == f"{human} utility"
    assert admin.get("/api/admin/scenarios/plot/nope").status_code == 404


def test_scenario_generation_rules(admin, studies):
    """Any generation rule can be drawn by, whatever the layer's own rule (simple by default)."""
    d = admin.get("/api/admin/scenarios/Lease?layer=settings").json()
    assert {r["value"] for r in d["rules"]} == {"simple", "random"} and d["layer_rule"] == "simple"
    assert d["rule"] == "simple" and d["simple"] is True
    for _ in range(3):  # a random draw is almost never simple by chance; one of three surely is not
        r = admin.get("/api/admin/scenarios/Lease?layer=settings&generate=2&rule=random").json()
        assert r["rule"] == "random"
        if not r["simple"]:
            break
    else:
        raise AssertionError("rule=random kept giving simple scenarios")
    s = admin.get("/api/admin/scenarios/Lease?layer=settings&generate=2&rule=simple").json()
    assert s["rule"] == "simple" and s["simple"] is True
    assert admin.get("/api/admin/scenarios/Lease?layer=settings&rule=nope").status_code == 400


def test_scenario_summaries_picture_and_preferences(admin, studies):
    """Every role's summary, the picture and the Preferences tool as each role sees it."""
    d = admin.get("/api/admin/scenarios/Lease?layer=settings").json()
    assert [x["role"] for x in d["summaries"]] == [r["name"] for r in d["roles"]]
    assert all(x["summary"] for x in d["summaries"])
    pic = admin.get(f"/api/admin/scenarios/picture/{d['plot_token']}?layer=settings").json()
    assert set(pic) == {"light", "dark"} and (pic["light"] or "").startswith("data:image/")
    for i, role in enumerate(d["roles"]):
        p = admin.post(f"/api/admin/scenarios/preferences/{d['plot_token']}", json={"role": i}).json()
        comps = p["components"]
        assert p["role"] == role["name"] and p["human"] == role["human"]
        assert not [c for c in comps if c.get("type") == "alert" and c.get("kind") in ("error", "warning")]
        assert comps[0]["title"] == "In short" and comps[0]["children"][0]["text"] == d["summaries"][i]["summary"]
    assert admin.post(f"/api/admin/scenarios/preferences/{d['plot_token']}", json={"role": 9}).status_code == 404
    assert admin.post("/api/admin/scenarios/preferences/nope", json={"role": 0}).status_code == 404


def test_scenario_plots_bounded_and_per_pair():
    from negmas import Scenario, make_issue, make_os
    from negmas.preferences import LinearAdditiveUtilityFunction as L

    from hani2.admin_scenarios import PLOT_MAX_OUTCOMES, _plots

    os_ = make_os([make_issue(30, f"i{k}") for k in range(4)])  # 810000 outcomes
    big = Scenario(outcome_space=os_, ufuns=tuple(L.random(os_, name=n, reserved_value=0.0) for n in "ab"))
    figs, note = _plots(big, 0)
    names = [t["name"] for t in figs[0]["figure"]["data"]]
    pts = next(t for t in figs[0]["figure"]["data"] if t["name"] == "Outcomes")
    assert len(pts["x"]) <= PLOT_MAX_OUTCOMES and "sample" in note and "Nash Point" in names
    os2 = make_os([make_issue((0.0, 1.0), "price"), make_issue(5, "q")])  # continuous
    three = Scenario(outcome_space=os2, ufuns=tuple(L.random(os2, name=n) for n in "xyz"))
    figs, _ = _plots(three, 1)
    assert [f["title"] for f in figs] == ["y vs x", "y vs z"]
    one = Scenario(outcome_space=os2, ufuns=(L.random(os2, name="solo"),))
    assert _plots(one, 0)[0] == []


def make_zip_scenario(tmp, name="Zebra", wrap=None):
    d = make_scenario(tmp / "src" / name, name)
    return zip_dir(d, prefix=f"{wrap}/" if wrap else "")


def lib_upload(c, kind, layer, filename, data, **fields):
    return c.post(f"{LIB}/{kind}/upload", data={"layer": layer, **{k: str(v) for k, v in fields.items()}},
                  files={"file": (filename, data, "application/octet-stream")})


def test_scenario_upload_details_and_layers(admin, studies, tmp_path):
    home = studies
    r = lib_upload(admin, "scenarios", "settings", "z.zip", make_zip_scenario(tmp_path), name="Zebra")
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["path"] == str(home / "settings/scenarios/Zebra")
    items = {i["name"]: i for i in admin.get(f"{LIB}/scenarios?layer=settings").json()["items"]}
    assert items["Zebra"]["source"] == "uploaded" and items["Zebra"]["removable"] and items["Zebra"]["title"] == "Zebra deal"
    pz = {i["name"]: i for i in admin.get(f"{LIB}/scenarios?layer=project:HI2027").json()["items"]}["Zebra"]
    assert pz["layer"] == "settings" and pz["removable"] is False
    d = admin.get("/api/admin/scenarios/Zebra?layer=settings").json()
    assert d["generated"] is False and d["kind"] == "folder" and d["pool"] == ["Zebra"]
    assert d["loaded_from"].replace("\\", "/").endswith("scenarios/Zebra")
    assert [r["name"] for r in d["roles"]] == ["buyer", "seller"] and d["issues"][0]["values"] == ["a", "b", "c"]
    assert admin.get("/api/admin/scenarios/Zebra?layer=settings&generate=1").status_code == 400
    assert admin.get("/api/admin/scenarios/Zebra?layer=settings&scenario=zzz").status_code == 404
    # a category uploaded to a study: seen there with the settings' categories, not elsewhere
    cat = tmp_path / "cat"
    for n in ("Quokka", "Numbat"):
        make_scenario(cat / "Marsupials" / n, n)
    r = lib_upload(admin, "scenarios", "study:HI2027/hi-01", "m.zip", zip_dir(cat))
    assert r.status_code == 200, r.text
    d = admin.get("/api/admin/scenarios/Marsupials?layer=study:HI2027/hi-01").json()
    assert d["pool"] == ["Numbat", "Quokka"]
    assert admin.get("/api/admin/scenarios/Marsupials?layer=settings").status_code == 404
    with projects.use_study("HI2027/hi-01"):
        assert {"Zebra", "Marsupials"} <= set(store.available_types())
    # a link is described as one
    ext = tmp_path / "ext"
    make_scenario(ext / "Dingo", "Dingo")
    r = admin.post(f"{LIB}/scenarios/link?layer=project:HI2027", json={"target": str(ext / "Dingo")})
    assert r.status_code == 200, r.text
    links = yaml.safe_load((home / "projects/HI2027/scenario_links.yaml").read_text(encoding="utf-8"))
    assert links == {"links": {"Dingo": str((ext / "Dingo").resolve())}}
    d = admin.get("/api/admin/scenarios/Dingo?layer=study:HI2027/hi-01").json()
    assert d["kind"] == "link" and d["loaded_from"] == str((ext / "Dingo").resolve())
    # removing from the console: the upload goes to .trash, the link only is removed
    r = admin.delete(f"{LIB}/scenarios/items/Zebra?layer=settings").json()
    assert r["how"] == "deleted" and ".trash" in r["trash"] and not (home / "settings/scenarios/Zebra").exists()
    assert admin.delete(f"{LIB}/scenarios/items/Dingo?layer=project:HI2027").json()["how"] == "unlinked"
    assert (ext / "Dingo").is_dir()


def test_scenario_sets_and_default_set(admin, studies):
    home = studies
    (home / "settings").mkdir(exist_ok=True)
    (home / "settings/scenario_sets.yaml").write_text("sets:\n  Mine: [Lease, Chores]\n", encoding="utf-8")
    L = "?layer=study:HI2027/hi-01"
    r = admin.put(f"{LIB}/scenarios/groups/Wide{L}", json=["@Mine", "Energy", "Nonexistent", "@Ghost"]).json()
    assert r["expanded"] == ["Lease", "Chores", "Energy", "Nonexistent"]
    w = " ".join(r["warnings"])
    assert "Nonexistent" in w and "Ghost" in w and "Energy" not in w
    admin.put(f"{LIB}/scenarios/groups/Loop{L}", json=["@Loop2"])
    r = admin.put(f"{LIB}/scenarios/groups/Loop2{L}", json=["@Loop"]).json()
    assert any("cycle" in x for x in r["warnings"])
    g = {x["name"]: x for x in admin.get(f"{LIB}/scenarios/groups{L}").json()["groups"]}
    assert g["Wide"]["editable"] and g["Mine"]["layer"] == "settings" and not g["Mine"]["editable"]
    # the default set, per layer
    d = admin.get(f"{LIB}/scenarios/default{L}").json()
    assert d["here"] is None and d["effective"] and "Wide" in d["sets"]
    d = admin.put(f"{LIB}/scenarios/default{L}", json={"default": "wide"}).json()
    assert d["here"] == "Wide" and d["effective"] == "Wide"
    sf = yaml.safe_load((home / "projects/HI2027/studies/hi-01/scenario_sets.yaml").read_text(encoding="utf-8"))
    assert sf["default"] == "Wide" and sf["sets"]["Wide"][0] == "@Mine"
    assert admin.get(f"{LIB}/scenarios/default?layer=settings").json()["here"] is None
    assert admin.put(f"{LIB}/scenarios/default{L}", json={"default": "Nope"}).status_code == 404
    assert admin.put(f"{LIB}/scenarios/default{L}", json={"default": 3}).status_code == 400
    d = admin.put(f"{LIB}/scenarios/default{L}", json={"default": None}).json()
    assert d["here"] is None
    assert "default" not in yaml.safe_load((home / "projects/HI2027/studies/hi-01/scenario_sets.yaml").read_text(encoding="utf-8"))
    assert admin.put(f"{LIB}/scenarios/groups/Custom{L}", json=["Lease"]).status_code == 409


# --------------------------------------------------------------------------- #
# Opponents and Assistants through the library                                 #
# --------------------------------------------------------------------------- #
OPP_CODE = """
from negmas.sao import SAONegotiator


class AdmFirst(SAONegotiator):
    \"\"\"A first test opponent.

    More text.
    \"\"\"
"""


@pytest.fixture(autouse=True)
def _clean_modules():
    before = list(sys.path)
    mods = set(sys.modules)
    yield
    sys.path[:] = before
    for m in set(sys.modules) - mods:
        if m.startswith("adm_"):
            del sys.modules[m]


def test_opponent_upload_group_describe_and_remove(admin, studies):
    home = studies
    r = lib_upload(admin, "opponents", "project:HI2027", "adm_opp.py", OPP_CODE.encode(), group="mine")
    assert r.status_code == 200, r.text
    assert r.json()["notice"] and r.json()["items"][0]["name"] == "AdmFirst"
    items = {i["name"]: i for i in admin.get(f"{LIB}/opponents?layer=project:HI2027").json()["items"]}
    assert items["AdmFirst"]["groups"] == ["mine"] and items["AdmFirst"]["description"].startswith("A first")
    g = json.loads((home / "projects/HI2027/groups/mine.json").read_text(encoding="utf-8"))
    assert g["agents"] == [items["AdmFirst"]["spec"]]
    d = {x["entry"]: x for x in admin.post(f"{LIB}/opponents/describe?layer=project:HI2027",
                                          json=["AdmFirst", "@mine", ":llm", "no.such.Thing", "@ghost"]).json()["entries"]}
    assert d["AdmFirst"]["kind"] == "item" and d["AdmFirst"]["ok"]
    assert d["@mine"]["kind"] == "group" and d["@mine"]["n"] == 1
    assert d[":llm"]["kind"] == "group"
    assert d["no.such.Thing"]["ok"] is False and d["no.such.Thing"]["error"]
    assert d["@ghost"]["ok"] is False
    r = admin.put(f"{LIB}/opponents/groups/mine?layer=project:HI2027", json=["AdmFirst", "no.such.Thing"]).json()
    assert any("no.such.Thing" in w for w in r["warnings"])
    r = admin.delete(f"{LIB}/opponents/items/AdmFirst?layer=project:HI2027").json()
    assert r["how"] == "deleted" and ".trash" in r["trash"]
    assert not (home / "projects/HI2027/library/opponents/adm_opp").exists()


def test_describe_many_builtins_fast_and_cached(admin):
    import time

    specs = [i["spec"] for i in admin.get(f"{LIB}/opponents").json()["items"] if i["source"] == "builtin"][:150]
    t = time.time()
    r = admin.post(f"{LIB}/opponents/describe", json=specs).json()["entries"]
    first = time.time() - t
    assert len(r) == len(specs) and all(x["kind"] == "item" for x in r)
    t = time.time()
    admin.post(f"{LIB}/opponents/describe", json=specs)
    assert time.time() - t <= max(1.0, first)


def test_pools_store_library_items_as_specs(admin, studies):
    lib_upload(admin, "opponents", "project:HI2027", "adm_pool.py", OPP_CODE.encode(), group="fin")
    spec = {i["name"]: i for i in admin.get(f"{LIB}/opponents?layer=project:HI2027").json()["items"]}["AdmFirst"]["spec"]
    r = admin.put("/api/admin/pools/opponent?layer=study:HI2027/hi-01", json={"items": ["AdmFirst", "@fin"]}).json()
    assert r["items"] == [spec, "@fin"] and r["effective"] == [spec]
    from hani2.agents import get_agent_type

    with projects.use_study("HI2027/hi-01"):
        assert get_agent_type(r["effective"][0]).__name__ == "AdmFirst"
    admin.put("/api/admin/pools/assistant?layer=study:HI2027/hi-01", json={"items": ["@tutorial"]})
    b = admin.get("/api/admin/projects/HI2027/studies/hi-01/balance").json()
    assert b["group"] == "tutorial" and len(b["pool"]) == 10


def test_compact_preferences_and_layout_settings_round_trip(admin, studies):
    """The forced value on disagreement (0 is a value), the weights chart, the start view and the
    simple view's tools side, saved through the admin API, read back and taking effect."""
    from hani2.testing import make_session

    r = admin.get("/api/admin/projects/HI2027/studies/hi-01").json()
    r["overrides"] = {**(r.get("overrides") or {}), "force_reserved_value": 0}
    assert admin.put("/api/admin/projects/HI2027/studies/hi-01", json={"data": r}).status_code == 200
    back = admin.get("/api/admin/projects/HI2027/studies/hi-01").json()
    assert back["overrides"]["force_reserved_value"] == 0
    body = {"tools": {"weights_chart": "bar"}, "interface": {"view": "full", "simple_tools_side": "left"}}
    assert admin.patch("/api/admin/settings/env?study=HI2027/hi-01", json=body).status_code == 200
    s = make_session(study="HI2027/hi-01")
    assert all(float(u.reserved_value) == 0.0 for u in s.scenario.ufuns)
    assert s.layout["view"] == "full" and s.snapshot()["layout"]["tools_side"] == "left"
    with projects.use_study("HI2027/hi-01"):
        from hani2.tools.ufun_views import weights_chart

        assert weights_chart() == "bar"
