"""How scenarios show offers: text, history, the offer on the table and the controls."""

import json

from negmas import Scenario

from hani2 import scenario_store as store
from hani2.display import DefaultOutcomeDisplay, OfferContext, OfferDisplay
from hani2.scenarios.story import StoryOutcomeDisplay
from hani2.testing import make_session
from hani2.tools import ui


def _trade() -> Scenario:
    s, _, _ = store.load_scenario("Trade", 0, load_existing=False)
    return s


def _offer(s: Scenario) -> dict:
    o = next(iter(s.outcome_space.enumerate_or_sample(max_cardinality=3)))
    return dict(zip([i.name for i in s.outcome_space.issues], o))


def test_default_text_uses_template_formats_and_labels():
    s = _trade()
    q, p = (i.name for i in s.outcome_space.issues)
    offer = {q: 3, p: 120}
    d = OfferDisplay()
    assert d.text(offer, OfferContext(s)) == f"{q}: 3, {p}: 120"
    assert d.text(None, OfferContext(s)) == "❓"
    s.info = dict(s.info or {}, issue_format={p: "${:,}"}, value_labels={q: {3: "three"}})
    assert d.text(offer, OfferContext(s)) == f"{q}: three, {p}: $120"
    s.info["offer_template"] = "{%s} units for {%s}" % (q, p)
    assert d.text(offer, OfferContext(s)) == "three units for $120"
    s.info["offer_template"] = "{Missing}"  # a broken template falls back to the default
    assert d.text(offer, OfferContext(s)) == f"{q}: three, {p}: $120"
    assert d.history(offer, OfferContext(s)) is None and d.on_table(offer, OfferContext(s)) is None
    assert d.controls(offer, OfferContext(s)) is None


def test_old_display_interface_still_works():
    class Old(DefaultOutcomeDisplay):
        def str(self, outcome, scenario, is_done, from_human):
            if outcome is None:
                return super().str(outcome, scenario, is_done, from_human)
            return f"{outcome[0]} at {outcome[1]} ({'me' if from_human else 'them'})"

    s = _trade()
    offer = _offer(s)
    o = tuple(offer.values())
    assert Old().text(offer, OfferContext(s, from_human=True)) == f"{o[0]} at {o[1]} (me)"
    assert Old().str(None, s, False, False) == "❓"
    assert DefaultOutcomeDisplay().text(offer, OfferContext(s)).startswith(f"{s.outcome_space.issues[0].name}: ")
    # every display still answers the old call
    assert store.display_for(s).str(o, s, False, True) == f"{o[0]} items at {o[1]}$"


def test_display_file_prefers_its_own_class(tmp_path):
    f = tmp_path / "display.py"
    f.write_text(
        "from hani2.scenarios.story import StoryOutcomeDisplay\n"
        "class Mine(StoryOutcomeDisplay):\n"
        "    def text(self, offer, ctx):\n"
        "        return 'mine'\n", encoding="utf-8"
    )
    assert type(store.load_display_file(f)).__name__ == "Mine"
    f.write_text("from hani2.display import OfferDisplay\n"
                 "class _Base(OfferDisplay):\n    pass\n"
                 "display = _Base()\n", encoding="utf-8")
    assert type(store.load_display_file(f)).__name__ == "_Base"
    f.write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    assert store.load_display_file(f) is None


def test_split_story_views():
    s, _, _ = store.load_scenario("Estate", 0, load_existing=False)
    d = store.display_for(s)
    assert isinstance(d, StoryOutcomeDisplay)
    names = [i.name for i in s.outcome_space.issues]
    offer = {n: 1 for n in names}
    ctx = OfferContext(s, role="human", from_human=True)
    assert d.text(offer, ctx).startswith("You get 1 ")
    hist = d.history(offer, ctx)
    assert [c["label"] for c in hist[0]["children"]] == ["You get", "Your opponent gets"]
    controls = d.controls(offer, OfferContext(s, surface="controls", role="human"))
    issues = [c for c in controls[0]["children"] if c["type"] == "issue"]
    assert [c["name"] for c in issues] == names
    totals = s.info["split"]["totals"]
    assert d.on_action("split_evenly", {}, offer, ctx) == {k: t // 2 for k, t in totals.items()}
    # a participant playing the other role edits their own share through on_input
    flipped = OfferContext(s, surface="controls", role="agent")
    first = names[0]
    c = d.controls({n: 0 for n in names}, flipped)[0]["children"][0]
    assert c["name"] == f"mine:{first}" and c["value"] == totals[first]
    assert d.on_input(f"mine:{first}", 1, offer, flipped) == {first: totals[first] - 1}
    assert d.text({n: 0 for n in names}, OfferContext(s, role="agent")).startswith("You get " + str(totals[first]))


def test_session_sends_custom_views_and_routes_control_events():
    s = make_session(scenario_type="Estate")
    snap = s.snapshot()
    assert snap["draft"]["controls"] and snap["draft"]["controls"][0]["type"] == "grid"
    names = [i["name"] for i in snap["scenario"]["issues"]]
    assert all(i.get("widget") is None for i in snap["scenario"]["issues"])  # no hints in the template
    s.start()
    assert s.wait_for_turn()
    snap = s.snapshot()
    po = snap["partner_offer"]
    if po is not None:
        assert po["view"][0]["type"] == "row"
    assert any(h.get("view") for h in snap["history"] if h.get("kind") == "offer")
    json.dumps(snap)
    totals = s.scenario.info["split"]["totals"]
    s.hub.messages.clear()
    r = s.draft_action("split_evenly", {})
    assert r["ok"] and s.draft == {k: t // 2 for k, t in totals.items()}
    msg = s.hub.of_type("draft")[-1]
    assert msg["controls"] and msg["draft"] == s.draft
    s.draft_input(names[0], 0)  # an input named after an issue sets it
    assert s.draft[names[0]] == 0
    assert s.draft_action("nothing", {})["applied"] == {}


def test_broken_display_falls_back_to_defaults():
    class Broken(OfferDisplay):
        def text(self, offer, ctx):
            raise ValueError("no")

        def controls(self, draft, ctx):
            raise ValueError("no")

        def history(self, offer, ctx):
            return "not components"

    s = make_session()
    s.ss["outcome_display"] = Broken()
    snap = s.snapshot()
    assert snap["draft"]["controls"] is None
    o = tuple(i.min_value if hasattr(i, "min_value") else list(i.all)[0] for i in s.issues)
    assert ":" in s.outcome_str(o)
    assert s.offer_view("history", o) is None


def test_custom_controls_and_widgets_in_a_session():
    class Picker(OfferDisplay):
        widgets = {"Price": "slider"}

        def controls(self, draft, ctx):
            return [ui.issue("Quantity"), ui.button("Cheapest", action="cheap"), ui.select("pkg", ["a", "b"], "a")]

        def on_action(self, action, payload, draft, ctx):
            return {"Price": min(ctx.issues[1].all)} if action == "cheap" else None

        def on_input(self, name, value, draft, ctx):
            return {"Quantity": 2} if (name, value) == ("pkg", "b") else None

    s = make_session()
    s.ss["outcome_display"] = Picker()
    snap = s.snapshot()
    assert [i.get("widget") for i in snap["scenario"]["issues"]] == [None, "slider"]
    assert snap["draft"]["controls"][0] == {"type": "issue", "name": "Quantity"}
    s.draft_action("cheap", {})
    assert s.draft["Price"] == min(s.issues[1].all)
    s.draft_input("pkg", "b")
    assert s.draft["Quantity"] == 2


def test_scenario_check_exercises_the_display(tmp_path):
    s = _trade()
    p = tmp_path / "Trade"
    store.save_scenario(s, p)
    (p / "display.py").write_text(
        "from hani2.display import OfferDisplay\n"
        "class D(OfferDisplay):\n"
        "    def controls(self, draft, ctx):\n"
        "        raise RuntimeError('broken controls')\n", encoding="utf-8"
    )
    _, errors, _ = store.check_scenario(p)
    assert any("broken controls" in e for e in errors)


def test_template_folder_display_is_used_for_generated_scenarios(tmp_path):
    import shutil

    from hani2.config import DEFAULT_SCENARIOS
    from hani2.scenarios import iago, registry
    from hani2.scenarios.story import Story

    folder = tmp_path / "MyEstate"
    shutil.copytree(DEFAULT_SCENARIOS / "Estate", folder)
    (folder / "display.py").write_text(
        "from hani2.display import OfferDisplay\n"
        "class EstateText(OfferDisplay):\n"
        "    def text(self, offer, ctx):\n"
        "        return 'estate:' + ','.join(str(v) for v in offer.values())\n", encoding="utf-8"
    )
    story = Story.from_folder(folder, roles=dict(iago.ESTATE_STORY.roles), setup=iago.ESTATE_STORY.setup)
    assert type(story.display).__name__ == "EstateText"
    registry.register_story(story)
    try:
        s, _, sdir = store.load_scenario("MyEstate", 0, load_existing=False)
        d = store.display_for(s, sdir)
        assert type(d).__name__ == "EstateText"
        assert d.text(_offer(s), OfferContext(s)).startswith("estate:")
    finally:
        registry.unregister("MyEstate")


def test_labels_match_float_values():
    s = make_session()  # the generated Trade type stores prices as floats
    s.scenario.info = dict(s.scenario.info or {}, issue_format={"Price": "${:,}"})
    price = next(i for i in s.snapshot()["scenario"]["issues"] if i["name"] == "Price")
    v = price["values"][0]
    assert isinstance(v, float) and price["labels"][str(int(v))] == f"${int(v):,}"
    s.scenario.info["value_labels"] = {"Price": {int(v): "cheap"}}
    assert OfferDisplay().text({"Quantity": 1, "Price": v}, OfferContext(s.scenario)) == "Quantity: 1, Price: cheap"
