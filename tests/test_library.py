"""The library: shared group composition, items of every kind (upload, link,
remove), groups per layer, tool groups, per-view tool placement, API and CLI."""

from __future__ import annotations

import io
import json
import textwrap
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from hani2 import composition, groups, library, projects, scenario_sets, tool_groups
from hani2.library import LibraryError
from hani2.projects import StudyRef
from hani2.testing import make_session

OPPONENT_PY = textwrap.dedent('''
    from negmas.sao import BoulwareTBNegotiator

    class LibBoulware(BoulwareTBNegotiator):
        """A Boulware opponent uploaded to the library."""
''')

ASSISTANT_PY = textwrap.dedent('''
    from hani2.support_agent.runtime import SupportAgent

    class LibCoach(SupportAgent):
        """An Assistant uploaded to the library."""
''')

TOOL_PY = textwrap.dedent('''
    from hani2.tools import Tool, ui

    class LibCounter(Tool):
        name = "Lib Counter"
        description = "Counts offers"
        pane = "side"
        groups = ("information",)

        def view(self):
            return [ui.stat("Offers", len(self.trace()))]
''')


@pytest.fixture
def study(hani2_home):
    projects.create_project("P1", kind="opponent")
    projects.create_study("P1/s1", type="online")
    return StudyRef("P1", "s1")


@pytest.fixture
def client(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c
    hub.sessions.clear()


def _zip(files: dict[str, str], *, symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, t in files.items():
            z.writestr(n, t)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def _scenario_files(tmp_path: Path, name: str = "Rent") -> Path:
    """A small valid scenario folder written by HANI2 itself."""
    from negmas import make_issue
    from negmas.inout import Scenario
    from negmas.outcomes import make_os
    from negmas.preferences import LinearAdditiveUtilityFunction as U

    from hani2.scenario_store import save_scenario

    os_ = make_os([make_issue(["low", "high"], "price"), make_issue(3, "months")], name=name)
    u1 = U.random(os_, reserved_value=0.0, normalized=True)
    u2 = U.random(os_, reserved_value=0.0, normalized=True)
    u1.name, u2.name = "tenant", "owner"
    s = Scenario(outcome_space=os_, ufuns=(u1, u2))
    s.info = {"title": "Renting a flat", "short_description": "Agree on a rent", "long_description": "Rent it."}
    folder = tmp_path / "src" / name
    save_scenario(s, folder)
    return folder


def _zip_folder(folder: Path, prefix: str | None = None, extra: dict[str, str] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for f in folder.rglob("*"):
            if f.is_file():
                z.write(f, str(Path(prefix or folder.name) / f.relative_to(folder)))
        for n, t in (extra or {}).items():
            z.writestr(n, t)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# The shared algorithm                                                         #
# --------------------------------------------------------------------------- #
def test_composition_expands_in_place_without_duplicates_and_case_insensitively():
    raw = {"A": ["x", "@b", "y"], "B": ["y", "z", "x"], "C": ["@A", ":b", "w"]}
    out = composition.expand_groups(raw)
    assert out["A"] == ["x", "y", "z"]
    assert out["C"] == ["x", "y", "z", "w"]
    # a bare entry naming a group is that group; its own name is an item
    assert composition.expand_groups({"Trade": ["Trade", "b"], "B": ["q"]})["Trade"] == ["Trade", "q"]


def test_composition_reports_and_breaks_cycles(capsys):
    out = composition.expand_groups({"A": ["a", "@B"], "B": ["b", "@A"], "S": ["@S", "s"]}, label="set")
    assert out["A"] == ["a", "b"] and out["B"] == ["b", "a"] and out["S"] == ["s"]
    err = capsys.readouterr().out
    assert "set cycle" in err and err.count("A -> B -> A") == 1


def test_composition_unknown_reference_is_skipped(capsys):
    assert composition.expand_groups({"A": ["@missing", "x"]})["A"] == ["x"]
    assert "unknown group 'missing'" in capsys.readouterr().out


def test_scenario_sets_use_the_shared_algorithm():
    assert scenario_sets.expand({"X": ["Trade", "@y"], "Y": ["Island", "Trade"]})["X"] == ["Trade", "Island"]


# --------------------------------------------------------------------------- #
# Opponent and Assistant groups: composition and the token rule                #
# --------------------------------------------------------------------------- #
def _gfile(home: Path, sub: str, key: str, data) -> Path:
    p = home / "settings" / sub / f"{key}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data))
    return p


def test_opponent_groups_compose_and_cycles_terminate(hani2_home, capsys):
    from hani2.agents import _expand_agent_items, resolve_agent_group

    _gfile(hani2_home, "groups", "base", ["BoulwareTBNegotiator", "ConcederTBNegotiator"])
    _gfile(hani2_home, "groups", "Mixed", {"agents": ["@base", ":notext", "LinearTBNegotiator"]})
    _gfile(hani2_home, "groups", "loop", ["@loop2", "A1"])
    _gfile(hani2_home, "groups", "loop2", [":loop", "A2"])
    mixed = resolve_agent_group("mixed")  # case-insensitive
    assert mixed[:2] == ["BoulwareTBNegotiator", "ConcederTBNegotiator"]
    assert "HybridNegotiator" in mixed and mixed.count("LinearTBNegotiator") == 1
    assert _expand_agent_items([":loop"]) == ["A2", "A1"]
    assert "cycle" in capsys.readouterr().out
    # a bare spec that is no group stays a spec
    assert _expand_agent_items(["helpers.CUHKAgent"]) == ["helpers.CUHKAgent"]


def test_assistant_groups_compose(hani2_home):
    _gfile(hani2_home, "assistant_groups", "coaches", {"assistants": ["level1_hello:HelloAgent"]})
    _gfile(hani2_home, "assistant_groups", "all", {"assistants": ["@coaches", ":default", "level2_rules:RulesAgent"]})
    out = groups.expand_assistants(["all"])
    assert out[0] == "level1_hello:HelloAgent" and out[-1] == "level2_rules:RulesAgent"
    assert groups.DEFAULT_ASSISTANT_SPEC in out
    assert groups.expand_members("assistant", "@all") == out


# --------------------------------------------------------------------------- #
# Layers                                                                       #
# --------------------------------------------------------------------------- #
def test_layers(study, hani2_home):
    assert library.parse_layer(None).name == "settings"
    assert library.parse_layer("project:default").level == "settings"
    assert library.parse_layer("project:P1").dir == projects.project_dir("P1")
    la = library.parse_layer("study:P1/s1")
    assert [x.name for x in la.chain()] == ["settings", "project:P1", "study:P1/s1"]
    for bad in ("project:../x", "study:P1/../x", "project:missing", "nonsense:x"):
        with pytest.raises(LibraryError):
            library.parse_layer(bad)


# --------------------------------------------------------------------------- #
# Opponents, Assistants, tools: upload, link, remove                           #
# --------------------------------------------------------------------------- #
def test_upload_opponent_py_and_use_it_in_a_session(study, hani2_home):
    r = library.add_upload("opponents", "mine.py", OPPONENT_PY.encode(), "project:P1", group="lib")
    assert r["ok"] and r["items"][0]["name"] == "LibBoulware" and "server" in r["notice"]
    spec = r["items"][0]["spec"]
    assert spec.startswith("file:")
    items = {i["name"]: i for i in library.list_items("opponents", "study:P1/s1")}
    assert items["LibBoulware"]["source"] == "uploaded" and items["LibBoulware"]["layer"] == "project:P1"
    assert items["LibBoulware"]["groups"] == ["lib"]
    assert not items["LibBoulware"]["removable"]  # added at the project, not at this study
    assert library.list_items("opponents", "project:P1")[0]["source"] == "builtin"
    # the group file holds the spec, so it works without the library
    data = json.loads((projects.project_dir("P1") / "groups" / "lib.json").read_text())
    assert data["agents"] == [spec]
    with projects.use_study(study):
        from hani2.agents import get_agent_type, resolve_agent_group

        assert resolve_agent_group("lib") == [spec]
        assert get_agent_type(spec).__name__ == "LibBoulware"
    s = make_session(partner=spec, study="P1/s1")
    s.start()
    s.wait_for_turn()
    assert "LibBoulware" in str(s.ss.get("last_partner_type"))
    # names are unique
    with pytest.raises(LibraryError) as e:
        library.add_upload("opponents", "mine.py", OPPONENT_PY.encode(), "project:P1")
    assert e.value.status == 409
    with pytest.raises(LibraryError, match="already exists"):  # another upload, same class name
        library.add_upload("opponents", "other.py", OPPONENT_PY.encode(), "project:P1")
    assert library.add_upload("opponents", "other.py", OPPONENT_PY.encode(), "project:P1", name="Other")["ok"]
    out = library.remove_item("opponents", "LibBoulware", "project:P1")
    assert out["how"] == "deleted" and not (projects.project_dir("P1") / "library" / "opponents" / "mine").exists()


def test_upload_assistant_zip_package(study, hani2_home):
    z = _zip({"coachpkg_lib/__init__.py": "", "coachpkg_lib/coach.py": ASSISTANT_PY})
    r = library.add_upload("assistants", "coachpkg_lib.zip", z, "settings", group="mine")
    assert r["items"][0]["spec"] == "coachpkg_lib.coach:LibCoach"
    assert groups.expand_assistants([":mine"]) == ["coachpkg_lib.coach:LibCoach"]
    data = json.loads((hani2_home / "settings" / "assistant_groups" / "mine.json").read_text())
    assert data["syspath"] and Path(data["syspath"][0]).is_dir()
    with pytest.raises(LibraryError):
        library.remove_item("assistants", "LibCoach", "project:P1")
    assert library.remove_item("assistants", "LibCoach")["how"] == "deleted"


def test_broken_code_and_unsafe_archives_are_refused(hani2_home):
    with pytest.raises(LibraryError) as e:
        library.add_upload("opponents", "bad.py", b"import does_not_exist_xyz\n")
    assert e.value.status == 422 and "does_not_exist_xyz" in str(e.value)
    with pytest.raises(LibraryError):
        library.add_upload("opponents", "none.py", b"x = 1\n")
    with pytest.raises(LibraryError, match="unsafe path"):
        library.add_upload("tools", "evil.zip", _zip({"../evil.py": TOOL_PY}))
    with pytest.raises(LibraryError, match="unsafe path"):
        library.add_upload("tools", "evil.zip", _zip({"/abs/evil.py": TOOL_PY}))
    with pytest.raises(LibraryError, match="symbolic link"):
        library.add_upload("tools", "evil.zip", _zip({"ok.py": TOOL_PY}, symlink="link.py"))
    with pytest.raises(LibraryError, match="not a valid"):
        library.add_upload("tools", "x.zip", b"not a zip")
    with pytest.raises(LibraryError, match="clashes"):
        library.add_upload("opponents", "json.zip", _zip({"json/__init__.py": OPPONENT_PY}))
    with pytest.raises(LibraryError, match="not a .* subclass|cannot load"):
        library.add_link("opponents", "collections:OrderedDict")
    assert not (hani2_home / "evil.py").exists()


def test_link_opponent_spec_and_folder(tmp_path, hani2_home):
    pkg = tmp_path / "ext"
    (pkg / "extneg_lib").mkdir(parents=True)
    (pkg / "extneg_lib" / "__init__.py").write_text("")
    (pkg / "extneg_lib" / "agent.py").write_text(OPPONENT_PY)
    r = library.add_link("opponents", str(pkg))
    assert r["items"][0]["spec"] == "extneg_lib.agent.LibBoulware"
    assert library.remove_item("opponents", "LibBoulware")["how"] == "unlinked"
    assert (pkg / "extneg_lib" / "agent.py").exists()  # unlinking leaves the target alone
    r = library.add_link("opponents", "negmas.sao.ConcederTBNegotiator", name="Conceder2")
    assert r["items"][0]["name"] == "Conceder2"
    with pytest.raises(LibraryError):
        library.add_link("opponents", "/does/not/exist.py")


def test_tool_upload_link_and_registry(study, hani2_home, tmp_path):
    from hani2.tools.registry import tool_specs

    r = library.add_upload("tools", "counter.py", TOOL_PY.encode(), "study:P1/s1")
    assert r["items"][0]["name"] == "Lib Counter"
    assert "Lib Counter" not in [s.name for s in tool_specs()]  # only the study sees it
    with projects.use_study(study):
        spec = next(s for s in tool_specs() if s.name == "Lib Counter")
        assert "information" in spec.groups
    items = {i["name"]: i for i in library.list_items("tools", "study:P1/s1")}
    assert items["Lib Counter"]["source"] == "uploaded" and items["Lib Counter"]["removable"]
    assert items["Preferences"]["source"] == "builtin"
    assert "information" in items["Lib Counter"]["groups"]
    with pytest.raises(LibraryError):  # same tool name again
        library.add_upload("tools", "counter2.py", TOOL_PY.encode(), "study:P1/s1")
    library.remove_item("tools", "Lib Counter", "study:P1/s1")
    f = tmp_path / "linked_tool.py"
    f.write_text(TOOL_PY)
    assert library.add_link("tools", str(f))["items"][0]["source"] == "linked"
    assert "Lib Counter" in [s.name for s in tool_specs()]


# --------------------------------------------------------------------------- #
# Scenarios                                                                    #
# --------------------------------------------------------------------------- #
def test_scenario_upload_link_and_remove(study, hani2_home, tmp_path):
    from hani2 import scenario_store

    folder = _scenario_files(tmp_path, "Rent")
    r = library.add_upload("scenarios", "Rent.zip", _zip_folder(folder), "project:P1", group="MySet")
    assert r["items"][0]["name"] == "Rent" and r["items"][0]["source"] == "uploaded"
    with projects.use_study(study):
        assert "Rent" in scenario_store.available_types()
        s, info, _ = scenario_store.load_scenario("Rent", 0)
        assert info["load_path"].startswith(str(projects.project_dir("P1")))
        assert scenario_sets.set_types("MySet") == ["Rent"]
    items = {i["name"]: i for i in library.list_items("scenarios", "project:P1")}
    assert items["Rent"]["groups"] == ["MySet"] and items["Rent"]["layer"] == "project:P1"
    assert items["Trade"]["source"] == "builtin"
    assert "Rent" not in {i["name"] for i in library.list_items("scenarios")}
    assert library.remove_item("scenarios", "Rent", "project:P1")["how"] == "deleted"
    # link instead
    r = library.add_link("scenarios", str(folder), name="RentLinked")
    assert r["items"][0]["source"] == "linked"
    assert "RentLinked" in scenario_store.available_types()
    assert {i["name"]: i for i in library.list_items("scenarios")}["RentLinked"]["source"] == "linked"
    assert scenario_store.load_scenario("RentLinked", 0)[1]["load_path"] == str(folder.resolve())
    assert library.remove_item("scenarios", "RentLinked")["how"] == "unlinked" and folder.is_dir()


def test_settings_pools_stay_visible_when_a_project_has_scenarios(study, hani2_home, tmp_path):
    from hani2 import scenario_store

    folder = _scenario_files(tmp_path, "Flat")
    pool = hani2_home / "settings" / "scenarios" / "Shared" / "Flat"
    import shutil

    shutil.copytree(folder, pool)
    library.add_upload("scenarios", "Rent.zip", _zip_folder(folder, "Rentals"), "project:P1")
    with projects.use_study(study):
        assert {"Shared", "Rentals"} <= set(scenario_store.available_types())
        assert scenario_store.list_scenarios("Shared") == ["Flat"]


def test_folders_the_library_did_not_add_are_not_removed(hani2_home, tmp_path):
    import shutil

    folder = _scenario_files(tmp_path, "Flat")
    shutil.copytree(folder, hani2_home / "settings" / "scenarios" / "Examples" / "Flat")
    items = {i["name"]: i for i in library.list_items("scenarios")}
    assert items["Examples"]["source"] == "registered" and not items["Examples"]["removable"]
    with pytest.raises(LibraryError):
        library.remove_item("scenarios", "Examples")
    assert (hani2_home / "settings" / "scenarios" / "Examples").is_dir()


def test_reupload_and_replace_code(hani2_home):
    z = _zip({"coachpkg_re/__init__.py": "", "coachpkg_re/coach.py": ASSISTANT_PY})
    library.add_upload("assistants", "coachpkg_re.zip", z)
    library.remove_item("assistants", "LibCoach")
    assert library.add_upload("assistants", "coachpkg_re.zip", z)["ok"]
    changed = ASSISTANT_PY.replace('"""An Assistant uploaded to the library."""', 'VERSION = 2')
    z2 = _zip({"coachpkg_re/__init__.py": "", "coachpkg_re/coach.py": changed})
    assert library.add_upload("assistants", "coachpkg_re.zip", z2, replace=True)["ok"]
    from hani2.support_agent.runtime import load_class

    assert load_class("coachpkg_re.coach:LibCoach").VERSION == 2
    library.add_upload("assistants", "single.py", ASSISTANT_PY.encode(), name="Single")
    r = library.add_upload("assistants", "single.py", changed.encode(), name="Single", replace=True)
    assert load_class(r["items"][0]["spec"]).VERSION == 2


def test_scenario_upload_refusals(hani2_home, tmp_path):
    folder = _scenario_files(tmp_path, "Rent")
    with pytest.raises(LibraryError, match="registered scenario type"):
        library.add_upload("scenarios", "Trade.zip", _zip_folder(folder, "Trade"))
    with pytest.raises(LibraryError, match="start alike"):
        library.add_upload("scenarios", "x.zip", _zip_folder(folder), name="TradeExtra")
    with pytest.raises(LibraryError, match="start alike"):
        library.add_upload("scenarios", "x.zip", _zip_folder(folder), name="Tra")
    with pytest.raises(LibraryError, match="Python files"):
        library.add_upload("scenarios", "Rent.zip", _zip_folder(folder, extra={"Rent/display.py": "x = 1"}))
    with pytest.raises(LibraryError, match="no scenario folder"):
        library.add_upload("scenarios", "junk.zip", _zip({"junk/readme.txt": "hi"}))
    bad = tmp_path / "bad" / "Broken"
    bad.mkdir(parents=True)
    (bad / "Broken.yml").write_text("type: NotADomain\n")
    with pytest.raises(LibraryError):
        library.add_link("scenarios", str(bad))
    library.add_upload("scenarios", "Rent.zip", _zip_folder(folder))
    with pytest.raises(LibraryError) as e:
        library.add_upload("scenarios", "Rent.zip", _zip_folder(folder))
    assert e.value.status == 409
    assert library.add_upload("scenarios", "Rent.zip", _zip_folder(folder), replace=True)["ok"]


# --------------------------------------------------------------------------- #
# Groups per layer                                                             #
# --------------------------------------------------------------------------- #
def test_scenario_set_edits_per_layer(study, hani2_home):
    library.put_group("scenarios", "Base", ["Trade", "Island"])
    r = library.put_group("scenarios", "More", ["@base", "Grocery"], "project:P1")
    assert r["expanded"] == ["Trade", "Island", "Grocery"]
    sets = {g["name"]: g for g in library.list_groups("scenarios", "study:P1/s1")}
    assert sets["More"]["layer"] == "project:P1" and not sets["More"]["editable"]
    assert sets["HAN2026"]["source"] == "builtin"
    with pytest.raises(LibraryError) as e:
        library.delete_group("scenarios", "More", "study:P1/s1")
    assert e.value.status == 409
    with pytest.raises(LibraryError):
        library.delete_group("scenarios", "HAN2026")
    with pytest.raises(LibraryError):
        library.put_group("scenarios", "Custom", ["Trade"])
    library.put_group("scenarios", "Most", ["@More"], "project:P1", rename_from="More")
    names = {g["name"] for g in library.list_groups("scenarios", "project:P1")}
    assert "Most" in names and "More" not in names
    assert library.delete_group("scenarios", "most", "project:P1")["ok"]


def test_opponent_group_edits_keep_other_fields(study, hani2_home):
    d = projects.project_dir("P1") / "groups"
    d.mkdir(parents=True)
    (d / "test_x.json").write_text(json.dumps({"syspath": ["/tmp"], "agents": ["A"], "support_agent": "pkg:Coach"}))
    library.put_group("opponents", "test_x", ["A", "@llm"], "project:P1")
    data = json.loads((d / "test_x.json").read_text())
    assert data["agents"] == ["A", "@llm"] and data["syspath"] == ["/tmp"] and data["assistant"] == "pkg:Coach"
    g = next(x for x in library.list_groups("opponents", "project:P1") if x["name"] == "test_x")
    assert g["expanded"][0] == "A" and "LLMHybridNegotiator" in g["expanded"] and g["assistant"] == "pkg:Coach"
    # the outside system's results folder wins and is read-only here
    res = projects.study_dir(study) / "results" / "groups"
    res.mkdir(parents=True)
    (res / "test_x.json").write_text(json.dumps(["B"]))
    gs = [x for x in library.list_groups("opponents", "study:P1/s1") if x["name"] == "test_x"]
    assert gs[0]["layer"] == "results" and gs[0]["active"] and not gs[1]["active"]
    with pytest.raises(LibraryError):
        library.delete_group("opponents", "test_x", "study:P1/s1")
    library.put_group("opponents", "renamed", ["A"], "project:P1", rename_from="test_x")
    assert not (d / "test_x.json").exists() and (d / "renamed.json").exists()
    assert library.delete_group("opponents", "renamed", "project:P1")["ok"]
    with pytest.raises(LibraryError):
        library.put_group("opponents", "../evil", ["A"])


# --------------------------------------------------------------------------- #
# Tool groups, offer and placement                                             #
# --------------------------------------------------------------------------- #
def test_builtin_tool_groups(hani2_home):
    from hani2.tools.registry import tool_specs

    g = tool_groups.builtin_groups(tool_specs())
    assert {"Preferences", "Scenario Info", "My Results"} <= set(g["information"])
    assert {"Utility Plot", "Outcome Plot", "Value Histogram"} <= set(g["visualization"])
    assert {"Utility-based Selector", "LLM", "Random"} <= set(g["recommendation"])
    assert {"All Results", "Negotiation Plot", "Opponent Preferences"} <= set(g["admin"])
    assert g["assistant"] == []
    from hani2.tools.registry import builtin_tool_classes

    assert all(c.groups for c in builtin_tool_classes())


def test_tool_offer_filters_built_and_addable_tools(study, hani2_home):
    from hani2.tools.registry import addable_tool_specs

    library.put_group("tools", "core", ["@information", "Utility-based Selector"], "project:P1")
    library.put_offer(["@core", "Trace"], "study:P1/s1")
    s = make_session(study="P1/s1", is_admin=True)
    names = {t.name for t in s.tools}
    assert "Preferences" in names and "Utility Plot" not in names
    s.start()
    names = {t.name for t in s.tools}
    assert {"Utility-based Selector", "Trace"} <= names and "Value Histogram" not in names
    assert "Utility Plot" not in {x.name for x in addable_tool_specs(s)}
    assert "Trace" not in {x.name for x in addable_tool_specs(s)}  # already there
    # elsewhere every tool is offered (the default)
    s2 = make_session()
    s2.start()
    assert "Value Histogram" in {t.name for t in s2.tools}
    off = library.get_offer("study:P1/s1")
    assert off["here"] == ["@core", "Trace"] and "Trace" in off["tools"]
    library.put_offer(None, "study:P1/s1")
    assert library.get_offer("study:P1/s1")["effective"] is None


def test_placement_per_view_in_sessions(hani2_home, monkeypatch):
    from hani2.tools.builtin import ValueHistogramTool

    monkeypatch.setattr(ValueHistogramTool, "placement", {"simple": {"pane": "upper", "visible": False}},
                        raising=False)
    library.put_placement({"Trace": {"simple": {"pane": "side"}, "full": {"order": 3}}})
    s = make_session()
    s.start()
    st = {t.name: s.tool_state(t) for t in s.tools}
    assert st["Value Histogram"]["pane"] == "lower" and st["Value Histogram"]["visible"]
    assert st["Trace"]["pane"] == "lower"
    s.set_layout(view="simple")
    st = {t.name: s.tool_state(t) for t in s.tools}
    assert st["Value Histogram"]["pane"] == "upper" and not st["Value Histogram"]["visible"]
    assert st["Trace"]["pane"] == "side"
    # a move in the simple view is remembered for that view only
    s.tool_controller.move_tool("Trace", pane="upper")
    s.set_layout(view="full")
    st = {t.name: s.tool_state(t) for t in s.tools}
    assert st["Value Histogram"]["visible"] and st["Trace"]["pane"] == "lower"
    s.set_layout(view="simple")
    assert s.tool_state(s.tool_controller.find("Trace"))["pane"] == "upper"
    # a session opened in the simple view starts there
    s2 = make_session(query={"view": "simple"})
    s2.start()
    assert not s2.tool_state(s2.tool_controller.find("Value Histogram"))["visible"]


def test_no_placement_means_no_change_on_view_switch(hani2_home):
    s = make_session()
    s.start()
    s.tool_controller.set_tool_visible("Trace", False)
    s.tool_controller.move_tool("Value Histogram", pane="side")
    before = {t.name: (s.tool_state(t)["pane"], s.tool_state(t)["order"], s.tool_state(t)["visible"]) for t in s.tools}
    s.set_layout(view="simple")
    s.set_layout(view="focus")
    after = {t.name: (s.tool_state(t)["pane"], s.tool_state(t)["order"], s.tool_state(t)["visible"]) for t in s.tools}
    assert before == after
    s.set_layout(view="full")
    assert not s.tool_state(s.tool_controller.find("Trace"))["visible"]
    assert s.tool_state(s.tool_controller.find("Value Histogram"))["pane"] == "side"


def test_offer_applies_from_the_first_tools(hani2_home):
    library.put_offer(["Preferences", "@visualization"])
    s = make_session()
    assert "My Results" not in {t.name for t in s.tools} and "Preferences" in {t.name for t in s.tools}


def test_placement_validation_and_layers(study, hani2_home):
    with pytest.raises(LibraryError):
        library.put_placement({"Trace": {"simple": {"pane": "nowhere"}}})
    with pytest.raises(LibraryError):
        library.put_placement({"Trace": {"bogus": 1}})
    library.put_placement({"Trace": {"pane": "side"}})
    library.put_placement({"Trace": {"simple": {"visible": False}}}, "study:P1/s1")
    pl = library.get_placement("study:P1/s1")["tools"]["Trace"]
    assert pl["effective"]["full"]["pane"] == "side" and not pl["effective"]["simple"]["visible"]
    assert pl["here"] == {"simple": {"visible": False}}
    library.put_placement({"Trace": None}, "study:P1/s1")
    assert library.get_placement("study:P1/s1")["tools"]["Trace"]["here"] is None


def test_tool_groups_compose_and_builtins_are_read_only(hani2_home):
    library.put_group("tools", "plots", ["visualization"])
    library.put_group("tools", "mine", ["@plots", "Trace", "@mine"])
    g = {x["name"]: x for x in library.list_groups("tools")}
    assert g["mine"]["expanded"][-1] == "Trace" and "Utility Plot" in g["mine"]["expanded"]
    assert g["admin"]["source"] == "builtin"
    with pytest.raises(LibraryError):
        library.put_group("tools", "admin", ["Trace"])
    with pytest.raises(LibraryError):
        library.delete_group("tools", "information")
    assert yaml.safe_load((hani2_home / "settings" / "tools.yaml").read_text())["groups"]["plots"] == ["visualization"]


# --------------------------------------------------------------------------- #
# API                                                                          #
# --------------------------------------------------------------------------- #
def test_removed_and_replaced_uploads_go_to_trash(study, hani2_home, tmp_path):
    from hani2.config import settings_dir

    folder = _scenario_files(tmp_path, "Rent")
    library.add_upload("scenarios", "Rent.zip", _zip_folder(folder))
    library.add_upload("scenarios", "Rent.zip", _zip_folder(folder), replace=True)
    trash = settings_dir() / "scenarios" / library.TRASH
    assert [p.name.startswith("Rent-") for p in trash.iterdir()] == [True]
    r = library.remove_item("scenarios", "Rent")
    assert r["how"] == "deleted" and Path(r["trash"]).parent == trash and len(list(trash.iterdir())) == 2
    # a .trash folder is never served as a category
    from hani2 import scenario_store

    assert library.TRASH not in scenario_store.available_types()
    library.add_upload("opponents", "mine.py", OPPONENT_PY.encode(), "project:P1")
    r = library.remove_item("opponents", "LibBoulware", "project:P1")
    assert r["how"] == "deleted" and (Path(r["trash"]) / "mine.py").is_file()
    assert not (projects.project_dir("P1") / "library/opponents/mine").exists()


def test_broken_files_are_not_overwritten(hani2_home, tmp_path):
    from hani2.config import settings_dir

    sd = settings_dir()
    sd.mkdir(parents=True, exist_ok=True)
    folder = _scenario_files(tmp_path, "Rent")
    (sd / "scenario_links.yaml").write_text("links: [unclosed\n")
    with pytest.raises(LibraryError) as e:
        library.add_link("scenarios", str(folder), name="Rent")
    assert e.value.status == 409 and "scenario_links.yaml" in str(e.value)
    assert (sd / "scenario_links.yaml").read_text() == "links: [unclosed\n"
    (sd / "scenario_links.yaml").unlink()
    (sd / "library.yaml").write_text("opponents: {a: [1, 2\n")
    with pytest.raises(LibraryError) as e:
        library.add_upload("opponents", "mine.py", OPPONENT_PY.encode())
    assert e.value.status == 409 and (sd / "library.yaml").read_text().startswith("opponents: {a")
    assert not (sd / "library/opponents/mine").exists()
    (sd / "scenario_sets.yaml").write_text("- not\n- a mapping\n")
    with pytest.raises(LibraryError) as e:
        library.put_group("scenarios", "Mine", ["Trade"])
    assert e.value.status == 409
    with pytest.raises(LibraryError):
        library.put_default_set("HAN2026")


def test_archive_size_limit(hani2_home, tmp_path, monkeypatch):
    monkeypatch.setattr(library, "MAX_ZIP_BYTES", 1000)
    z = tmp_path / "a.zip"
    z.write_bytes(_zip({"a/x.txt": "x" * 600, "a/y.txt": "y" * 600}))
    with pytest.raises(LibraryError, match="more than"):
        library.safe_extract(z, tmp_path / "out")
    z.write_bytes(_zip({"a/x.txt": "x" * 600}))
    assert (library.safe_extract(z, tmp_path / "ok") / "x.txt").read_text() == "x" * 600


def test_group_warnings_unknown_entries_and_cycles(study, hani2_home):
    r = library.put_group("scenarios", "Wide", ["Trade", "Nonexistent", "@Ghost", "@HAN2026"])
    w = " ".join(r["warnings"])
    assert "Nonexistent" in w and "Ghost" in w and "Trade" not in w and "HAN2026" not in w
    library.put_group("scenarios", "A", ["@B"])
    r = library.put_group("scenarios", "B", ["@A", "Island"])
    assert any("cycle" in x for x in r["warnings"])
    r = library.put_group("tools", "mine", ["Preferences", "Nope tool", "@visualization"])
    assert r["warnings"] == ["mine: 'Nope tool' is no known tool or group"]
    r = library.put_group("opponents", "odd", ["BoulwareTBNegotiator", "no.such.Class", ":llm"], "project:P1")
    assert len(r["warnings"]) == 1 and "no.such.Class" in r["warnings"][0]


def test_default_set_per_layer(study, hani2_home):
    library.put_group("scenarios", "Pilot", ["Trade"], "project:P1")
    d = library.put_default_set("pilot", "project:P1")
    assert d["here"] == "Pilot" and d["effective"] == "Pilot"
    with projects.use_study(study):
        assert scenario_sets.active_set() == "Pilot"
    assert library.get_default_set("settings")["here"] is None
    assert library.get_default_set("study:P1/s1")["effective"] == "Pilot"
    with pytest.raises(LibraryError) as e:
        library.put_default_set("Nope", "project:P1")
    assert e.value.status == 404
    assert library.put_default_set(None, "project:P1")["here"] is None
    f = projects.project_dir("P1") / "scenario_sets.yaml"
    assert "default" not in yaml.safe_load(f.read_text()) and "Pilot" in yaml.safe_load(f.read_text())["sets"]


def test_describe_entries(study, hani2_home):
    library.add_upload("opponents", "mine.py", OPPONENT_PY.encode(), "project:P1", group="lib")
    d = {x["entry"]: x for x in library.describe("opponents", ["LibBoulware", "@lib", "lib", "nope.Nope", "@ghost",
                                                                "BoulwareTBNegotiator"], "project:P1")}
    assert d["LibBoulware"]["kind"] == "item" and d["LibBoulware"]["description"].startswith("A Boulware")
    assert d["@lib"]["kind"] == "group" and d["@lib"]["n"] == 1 and d["lib"]["kind"] == "group"
    assert d["nope.Nope"]["ok"] is False and "nope.Nope" in d["nope.Nope"]["error"]
    assert d["@ghost"]["kind"] == "unknown" and d["BoulwareTBNegotiator"]["ok"]
    t = {x["entry"]: x for x in library.describe("tools", ["Preferences", "@visualization", "Nope"])}
    assert t["Preferences"]["kind"] == "item" and t["@visualization"]["kind"] == "group" and not t["Nope"]["ok"]
    with pytest.raises(LibraryError):
        library.describe("tools", "Preferences")


def test_an_empty_offer_offers_nothing(study, hani2_home):
    assert library.put_offer([], "project:P1")["here"] == []
    assert library.get_offer("study:P1/s1")["tools"] == []
    assert library.put_offer(None, "project:P1")["here"] is None
    assert library.get_offer("study:P1/s1")["tools"]


def test_copying_a_group_into_a_layer_keeps_its_fields(study, hani2_home):
    from hani2.config import settings_dir

    d = settings_dir() / "groups"
    d.mkdir(parents=True, exist_ok=True)
    (d / "base.json").write_text(json.dumps({"agents": ["BoulwareTBNegotiator"], "description": "Base",
                                             "syspath": ["/srv/x"], "assistant": "hani2.assistant:Assistant"}))
    r = library.put_group("opponents", "base", ["BoulwareTBNegotiator", "LinearTBNegotiator"], "project:P1")
    data = json.loads(Path(r["path"]).read_text())
    assert data["agents"] == ["BoulwareTBNegotiator", "LinearTBNegotiator"]
    assert data["description"] == "Base" and data["syspath"] == ["/srv/x"] and data["assistant"] == "hani2.assistant:Assistant"
    assert json.loads((d / "base.json").read_text())["agents"] == ["BoulwareTBNegotiator"]


def test_a_broken_tools_yaml_is_not_overwritten(hani2_home):
    from hani2.config import settings_dir

    f = settings_dir() / "tools.yaml"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text("offer: [a\n")
    for call in (lambda: library.put_offer(["Trace"]), lambda: library.put_placement({"Trace": {"pane": "side"}}),
                 lambda: library.put_group("tools", "mine", ["Trace"])):
        with pytest.raises(LibraryError) as e:
            call()
        assert e.value.status == 409
    assert f.read_text() == "offer: [a\n"


def test_api_is_admin_only(client):
    assert client.get("/api/admin/library/tools").status_code == 401
    client.post("/api/auth/login", json={"username": "user", "password": "userpass"})
    assert client.get("/api/admin/library/tools").status_code == 403
    assert client.post("/api/admin/library/tools/upload", files={"file": ("t.py", TOOL_PY)}).status_code == 403


def test_api_flow(client, study, tmp_path):
    client.post("/api/auth/login", json={"username": "admin", "password": "adminpass"})
    assert client.get("/api/admin/library").json()["kinds"] == list(library.KINDS)
    assert client.get("/api/admin/library/bogus").status_code == 400
    r = client.post("/api/admin/library/opponents/upload?layer=project:P1",
                    files={"file": ("mine.py", OPPONENT_PY)}, data={"group": "lib"})
    assert r.status_code == 200, r.text
    assert r.json()["items"][0]["name"] == "LibBoulware"
    items = client.get("/api/admin/library/opponents?layer=project:P1").json()["items"]
    assert next(i for i in items if i["name"] == "LibBoulware")["groups"] == ["lib"]
    gs = client.get("/api/admin/library/opponents/groups?layer=project:P1").json()["groups"]
    assert next(g for g in gs if g["name"] == "lib")["editable"]
    r = client.put("/api/admin/library/opponents/groups/both?layer=project:P1",
                   json={"entries": ["@lib", ":notext"], "description": "two pools"})
    assert r.status_code == 200 and "HybridNegotiator" in r.json()["expanded"]
    assert client.delete("/api/admin/library/opponents/groups/llm?layer=project:P1").status_code == 409
    assert client.delete("/api/admin/library/opponents/groups/both?layer=project:P1").json()["ok"]
    assert client.delete("/api/admin/library/opponents/items/LibBoulware?layer=project:P1").json()["ok"]
    assert client.delete("/api/admin/library/opponents/items/LibBoulware?layer=project:P1").status_code == 404
    assert client.get("/api/admin/library/opponents?layer=study:P1/../x").status_code in (400, 404)
    r = client.post("/api/admin/library/tools/upload", files={"file": ("evil.zip", _zip({"../e.py": TOOL_PY}))})
    assert r.status_code == 400
    folder = _scenario_files(tmp_path, "Rent")
    r = client.post("/api/admin/library/scenarios/link", json={"target": str(folder), "group": "Rentals"})
    assert r.status_code == 200, r.text
    assert "Rent" in [g for g in client.get("/api/admin/library/scenarios/groups").json()["groups"]
                      if g["name"] == "Rentals"][0]["expanded"]
    pl = client.put("/api/admin/library/tools/placement", json={"Trace": {"simple": {"visible": False}}})
    assert pl.status_code == 200 and pl.json()["tools"]["Trace"]["effective"]["simple"]["visible"] is False
    assert client.get("/api/admin/library/tools/placement").json()["views"] == ["full", "simple", "focus"]
    assert client.put("/api/admin/library/tools/offer", json=["@information"]).json()["here"] == ["@information"]
    assert client.get("/api/admin/library/tools/offer").json()["effective"] == ["@information"]
    tools = client.get("/api/admin/library/tools").json()["items"]
    assert next(t for t in tools if t["name"] == "Trace")["offered"] is True


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def test_cli(hani2_home, tmp_path):
    from typer.testing import CliRunner

    from hani2.cli import app

    f = tmp_path / "counter.py"
    f.write_text(TOOL_PY)
    run = CliRunner().invoke
    r = run(app, ["library", "add", "tools", str(f), "--group", "extras"])
    assert r.exit_code == 0, r.output
    assert "Lib Counter" in r.output and "server" in r.output
    r = run(app, ["library", "list", "tools"])
    assert r.exit_code == 0 and "Lib Counter" in r.output and "uploaded" in r.output
    r = run(app, ["library", "group-set", "tools", "core", "@extras", "Trace"])
    assert r.exit_code == 0, r.output
    r = run(app, ["library", "groups", "tools", "--expanded"])
    assert "core" in r.output and "Lib Counter" in r.output
    r = run(app, ["library", "add", "tools", str(f), "--link", "--layer", "project:none"])
    assert r.exit_code != 0
    r = run(app, ["library", "group-delete", "tools", "core"])
    assert r.exit_code == 0
    r = run(app, ["library", "remove", "tools", "Lib Counter"])
    assert r.exit_code == 0, r.output
    r = run(app, ["library", "placement", "Trace", "--view", "simple", "--hidden"])
    assert r.exit_code == 0, r.output
    assert yaml.safe_load((hani2_home / "settings" / "tools.yaml").read_text())["placement"]["Trace"] == \
        {"simple": {"visible": False}}
