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
