"""Scenario pictures: lookup rules and the Scenario Info tool."""

from __future__ import annotations

from pathlib import Path

from hani2 import scenario_pictures as pics
from hani2.config import DEFAULT_SCENARIOS
from hani2.testing import make_session

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 1"><rect width="2" height="1"/></svg>'


def _write(folder: Path, name: str, text: str = SVG) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text)
    return folder / name


def test_every_bundled_scenario_has_a_light_and_dark_picture():
    for d in sorted(p for p in DEFAULT_SCENARIOS.iterdir() if p.is_dir()):
        found = pics.find(None, d.name)
        assert found.get("light") == d / "picture.svg", d.name
        assert found.get("dark") == d / "picture_dark.svg", d.name


def test_single_picture_serves_both_themes(tmp_path):
    _write(tmp_path, "picture.png", "x")
    light, dark = pics.sources(tmp_path, None)
    assert light and light.startswith("data:image/png;base64,") and dark is None


def test_light_and_dark_files_and_info_override(tmp_path):
    _write(tmp_path, "picture_light.svg")
    _write(tmp_path, "picture_dark.svg")
    found = pics.find(tmp_path, None)
    assert found == {"light": tmp_path / "picture_light.svg", "dark": tmp_path / "picture_dark.svg"}
    _write(tmp_path, "day.svg")
    found = pics.find(tmp_path, None, {"picture": {"light": "day.svg", "dark": "https://x.org/n.png"}})
    assert found == {"light": tmp_path / "day.svg", "dark": "https://x.org/n.png"}
    # paths may not leave the folder
    assert pics._ref(tmp_path, "../../etc/passwd") is None


def test_picture_false_turns_off_the_bundled_fallback(tmp_path):
    assert pics.find(tmp_path, "UsedCar")  # falls back to the bundled UsedCar picture
    assert pics.find(tmp_path, "UsedCar", {"picture": False}) == {}


def test_category_folder_picture_is_used_for_its_scenarios(tmp_path, monkeypatch):
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path))
    cat = tmp_path / "Harbour"
    _write(cat / "s1", "Harbour.yml", "x")
    pic = _write(cat, "picture.svg")
    assert pics.find(cat / "s1", "Harbour")["light"] == pic


def test_scenario_info_tool_shows_picture_with_switch():
    s = make_session(scenario_type="UsedCar")
    tool = s.tool_controller.find("Scenario Info")
    comps = tool.view()
    flat = list(_all(comps))
    img = next(c for c in flat if c["type"] == "image")
    assert img["src"].startswith("data:image/svg+xml;base64,")
    assert img["dark_src"].startswith("data:image/svg+xml;base64,") and img["dark_src"] != img["src"]
    sw = next(c for c in flat if c["type"] == "switch")
    assert sw["name"] == "show_picture" and sw["value"] is True
    tool.on_input("show_picture", False)
    assert not any(c["type"] == "image" for c in _all(tool.view()))
    s.load()  # the choice is kept for the next scenario
    tool = s.tool_controller.find("Scenario Info")
    assert not any(c["type"] == "image" for c in _all(tool.view()))


def _all(comps):
    for c in comps:
        yield c
        yield from _all(c.get("children", []))
        if c.get("image"):
            yield c["image"]


def test_scenario_info_picture_styles():
    s = make_session(scenario_type="UsedCar")
    tool = s.tool_controller.find("Scenario Info")
    comps = tool.view()
    sel = next(c for c in _all(comps) if c.get("name") == "picture_style")
    assert sel["value"] == "small" and {o["value"] for o in sel["options"]} == {"small", "large", "watermark"}
    fig = next(c for c in comps if c["type"] == "figure")  # small (the default): beside the story
    assert fig["placement"] == "side" and fig["image"]["type"] == "image"
    assert fig["children"][0]["type"] == "markdown"
    tool.on_input("picture_style", "watermark")
    fig = next(c for c in tool.view() if c["type"] == "figure")
    assert fig["placement"] == "watermark" and fig["children"][0]["type"] == "markdown"
    tool.on_input("picture_style", "large")
    comps = tool.view()
    assert not any(c["type"] == "figure" for c in comps)
    assert any(c["type"] == "image" for c in comps)
    s.load()  # the style is kept for the next scenario
    tool = s.tool_controller.find("Scenario Info")
    assert not any(c["type"] == "figure" for c in tool.view())
    tool.on_input("show_picture", False)
    comps = tool.view()
    assert not any(c.get("name") == "picture_style" for c in _all(comps))
    assert not any(c["type"] in ("image", "figure") for c in comps)


def test_scenario_picture_style_default_from_info():
    s = make_session(scenario_type="UsedCar")
    tool = s.tool_controller.find("Scenario Info")
    s.scenario.info = {**(s.scenario.info or {}), "picture_style": "watermark"}
    assert next(c for c in tool.view() if c["type"] == "figure")["placement"] == "watermark"


def test_installed_example_copy_without_pictures_uses_bundled_one(tmp_path):
    copy = tmp_path / "Examples" / "Lease"  # an Examples folder installed before pictures existed
    _write(copy, "Lease.yml", "x")
    assert pics.find(copy, "Examples")["dark"] == DEFAULT_SCENARIOS / "Lease" / "picture_dark.svg"
    assert pics.find(tmp_path / "Mine" / "s1", "Mine", {"story": "Island"})["light"] == \
        DEFAULT_SCENARIOS / "Island" / "picture.svg"


# --------------------------------------------------------------------------- #
# Layered settings: picture shown and full description opened                  #
# --------------------------------------------------------------------------- #
def _flat(comps):
    return list(_all(comps))


def _info_view(s):
    return _flat(s.tool_controller.find("Scenario Info").view())


def _desc(s):
    return next(c for c in _info_view(s) if c["type"] == "card" and c.get("title") == "Full description")


def test_defaults_picture_on_description_closed():
    s = make_session(scenario_type="UsedCar")
    assert any(c["type"] == "image" for c in _info_view(s))
    assert _desc(s)["collapsed"] is True
    assert s.set_pref("open_scenario_description", True)
    assert _desc(s)["collapsed"] is False  # the tool is re-rendered at once
    old = _desc(s)["id"]
    s.load()
    assert _desc(s)["collapsed"] is False and _desc(s)["id"] != old  # a new card: starts opened


def test_project_and_study_layers_set_the_defaults(hani2_home):
    import json

    from hani2 import projects

    projects.create_project("P")
    projects.create_study("P/s1")
    projects.create_study("P/s2")
    (projects.project_dir("P") / "env.json").write_text(json.dumps(
        {"interface": {"prefs": {"show_scenario_picture": False, "open_scenario_description": True}}}))
    (projects.study_dir(projects.StudyRef("P", "s1")) / "env.json").write_text(json.dumps(
        {"interface": {"prefs": {"show_scenario_picture": True}}}))
    s1, s2 = make_session(study="P/s1"), make_session(study="P/s2")
    assert any(c["type"] == "image" for c in _info_view(s1))  # the study beats its project
    assert not any(c["type"] == "image" for c in _info_view(s2))  # the project's default
    assert _desc(s1)["collapsed"] is False and _desc(s2)["collapsed"] is False


def test_admin_can_lock_the_settings_for_participants(hani2_home):
    import json

    from hani2 import projects

    projects.create_project("P")
    projects.create_study("P/locked")
    (projects.study_dir(projects.StudyRef("P", "locked")) / "env.json").write_text(json.dumps({"interface": {
        "participant_settings": {"show_scenario_picture": False, "open_scenario_description": False},
        "prefs": {"show_scenario_picture": False}}}))
    s = make_session(study="P/locked")
    ui = s.snapshot()["interface"]["participant_settings"]
    assert ui["show_scenario_picture"] is False and ui["open_scenario_description"] is False
    assert not any(c["type"] in ("image", "switch") for c in _info_view(s))  # no picture, no switch
    assert not s.set_pref("show_scenario_picture", True)  # refused by the server
    assert not s.set_pref("open_scenario_description", True)
    s.tool_controller.find("Scenario Info").on_input("show_picture", True)  # nor through the tool
    assert s.prefs["show_scenario_picture"] is False
    a = make_session(study="P/locked", is_admin=True)  # administrators may change everything
    assert a.set_pref("show_scenario_picture", True)
    assert {"show_scenario_picture", "open_scenario_description"} <= set(a.snapshot()["interface"]["hidden_from_participants"])


def test_picture_style_is_a_layered_participant_setting(hani2_home):
    import json

    from hani2 import projects

    projects.create_project("P")
    projects.create_study("P/wm")
    projects.create_study("P/locked")
    (projects.study_dir(projects.StudyRef("P", "wm")) / "env.json").write_text(json.dumps(
        {"interface": {"prefs": {"scenario_picture_style": "watermark"}}}))
    (projects.study_dir(projects.StudyRef("P", "locked")) / "env.json").write_text(json.dumps({"interface": {
        "prefs": {"scenario_picture_style": "large"},
        "participant_settings": {"scenario_picture_style": False}}}))
    s = make_session(study="P/wm")
    assert next(c for c in _info_view(s) if c["type"] == "figure")["placement"] == "watermark"
    assert s.set_pref("scenario_picture_style", "small")  # the participant's own choice
    assert next(c for c in _info_view(s) if c["type"] == "figure")["placement"] == "side"
    assert not s.set_pref("scenario_picture_style", "huge")  # unknown styles are refused
    s.tool_controller.find("Scenario Info").on_input("picture_style", "large")  # the menu writes the pref
    assert s.prefs["scenario_picture_style"] == "large"
    locked = make_session(study="P/locked")
    view = _info_view(locked)
    assert not any(c.get("name") == "picture_style" for c in view)  # no menu
    assert any(c["type"] == "image" for c in view) and not any(c["type"] == "figure" for c in view)  # large
    assert not locked.set_pref("scenario_picture_style", "watermark")
    locked.tool_controller.find("Scenario Info").on_input("picture_style", "watermark")
    assert locked.prefs["scenario_picture_style"] == "large"
