"""With a support agent, "human" and "agent" values are shown as "You" and "Partner"."""

import json

from hani2.naming import relabel_components, relabel_text
from hani2.testing import make_session
from hani2.tools import ui


M = {"human": "You", "agent": "Partner"}


def test_relabel_helpers():
    assert relabel_text("Compass=agent, Food = human; agentic", M) == "Compass=Partner, Food = You; agentic"
    comps = [ui.card(ui.table([{"Compass": "agent", "U": 0.5}], on_select="pick"),
                     ui.select("who", ["agent", "human"], "agent"), ui.stat("Holder", "human"),
                     ui.button("Go", "agent"))]
    out = relabel_components(comps, M)
    card = out[0]["children"]
    assert card[0]["rows"][0]["Compass"] == "Partner"
    assert [o["label"] for o in card[1]["options"]] == ["Partner", "You"]
    assert [o["value"] for o in card[1]["options"]] == ["agent", "human"] and card[1]["value"] == "agent"
    assert card[2]["value"] == "You" and card[3]["action"] == "agent"
    assert comps[0]["children"][0]["rows"][0]["Compass"] == "agent"  # input untouched


def test_island_with_support_agent_shows_you_and_partner(hani2_home):
    s = make_session(scenario_type="Island")
    assert s.labels == M
    snap = s.snapshot()
    issue = snap["scenario"]["issues"][0]
    assert issue["values"] == ["agent", "human"] and issue["labels"] == {"agent": "Partner", "human": "You"}
    assert snap["scenario"]["role"] == ""
    s.start()
    s.wait_for_turn()
    first = s.issues[0].name
    assert s.set_draft({first: "Partner"})["ok"] and s.draft[first] == "agent"  # labels map back
    ctx = s.context()
    assert set(ctx["issues"][0]["values"]) == {"Partner", "You"} and "names" in ctx
    assert all(v in ("You", "Partner") for v in (ctx["partner_offer"] or {}).values())
    sel = next(t for t in s.tools if t.name == "Utility-based Selector")
    view = json.dumps(s.render_tool(s.tool_state(sel)["id"]))
    assert '"agent"' not in view.replace('"value": "agent"', "") and "Partner" in view
    s.end()
    s.wait_until_done()
    import csv

    rows = list(csv.DictReader(open(hani2_home / "db" / "tester" / "results.csv")))
    assert "Partner" not in rows[-1].get("agreement", "") and "You" not in rows[-1].get("agreement", "")


def test_no_relabelling_without_a_support_agent(hani2_home):
    s = make_session(scenario_type="Island", support_settings={"mode": "off"})
    assert s.support_agent is None and s.labels == {}
    assert "labels" not in s.snapshot()["scenario"]["issues"][0]


def test_names_can_be_configured(hani2_home):
    env = hani2_home / "settings" / "env.json"
    data = json.loads(env.read_text()) if env.exists() else {}
    data["names"] = {"apply": "always", "self": "Me", "opponent": "Them"}
    env.parent.mkdir(parents=True, exist_ok=True)
    env.write_text(json.dumps(data))
    s = make_session(scenario_type="Island", support_settings={"mode": "off"})
    assert s.labels == {"human": "Me", "agent": "Them"}
