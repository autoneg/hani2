"""Information splits: the human and the Assistant know different things (hani2.information).

The leak tests serialise everything each party gets and check that it holds only
that party's share."""

import json

import pytest

from hani2 import information as info
from hani2 import projects
from hani2.testing import make_session

SPLIT = {
    "past_negotiations": {"count": 6, "human_share": 0.5},
    "preferences": {"human": "weights", "assistant": "values", "reserved_value": "assistant"},
    "market_research": {"audience": "assistant"},
}


def session_with(information, scenario="Trade", **kw):
    s = make_session(load=False, **kw)
    s.admin_prefs["information"] = information
    s.load(scenario)
    return s


def tool(s, name):
    return next(t for t in s.tools if t.name == name)


def available_names(s):
    return [t["name"] for t in s.snapshot()["tools"]]


def render(s, name):
    out = s.render_tool(s.tool_state(tool(s, name))["id"])
    return out["view"] if out else None


def dump(x) -> str:
    return json.dumps(x, default=str)


def titles(view) -> list[str]:
    found = []

    def walk(c):
        if isinstance(c, dict):
            if c.get("title"):
                found.append(str(c["title"]))
            for v in c.values():
                walk(v)
        elif isinstance(c, list):
            for v in c:
                walk(v)

    walk(view)
    return found


# --------------------------------------------------------------------------- #
# Default: nothing is split                                                    #
# --------------------------------------------------------------------------- #
def test_default_splits_nothing():
    s = make_session()
    s.start()
    s.wait_for_turn()
    s.play_counters(1)
    snap = s.snapshot()
    assert not s.information.split
    assert snap["information"] is None
    assert snap["draft"]["utility"] is not None and snap["reserved_value"] is not None
    assert any("utility" in h for h in snap["history"] if h.get("kind") == "offer")
    assert "Past Negotiations" not in available_names(s) and "Market Research" not in available_names(s)
    assert "Utility Plot" in available_names(s)
    names = [f["function"]["name"] for f in s.support_agent.dispatcher.schemas()]
    assert "get_private_information" not in names
    assert "information" not in s.context()
    assert s.support_agent.read_tool("Preferences")["ok"]


def test_settings_are_checked():
    s = info.resolve_settings({"past_negotiations": {"count": "x", "human_share": 7, "preferences": "odd"},
                               "preferences": {"human": "bogus"}, "market_research": {"audience": "all"}})
    assert s["past_negotiations"]["count"] == 0 and s["past_negotiations"]["human_share"] == 1.0
    assert s["past_negotiations"]["preferences"] == "similar"
    assert s["preferences"]["human"] == "full" and s["market_research"]["audience"] == "none"


# --------------------------------------------------------------------------- #
# Past negotiations                                                            #
# --------------------------------------------------------------------------- #
def test_past_negotiations_are_shared_out():
    s = session_with({"past_negotiations": {"count": 6, "human_share": 0.5}})
    st = s.information
    assert len(st.past) == 6 and st.past_source == "simulated"
    assert len(st.human_past) == 3 and len(st.assistant_past) == 3
    assert not set(st.human_past) & set(st.assistant_past)
    assert "Past Negotiations" in available_names(s)
    view = dump(render(s, "Past Negotiations"))
    for pid in st.human_past:
        assert f'"{pid}"' in view
    for pid in st.assistant_past:
        assert f'"{pid}"' not in view  # the human sees only their own records
    assert "has 3 more" in view
    # the Assistant sees its own, not the human's
    sa = s.support_agent
    names = [f["function"]["name"] for f in sa.dispatcher.schemas()]
    assert {"get_private_information", "show_past_negotiation"} <= set(names)
    priv = sa.dispatcher.execute("get_private_information", {})
    assert priv["ok"]
    assert [r["id"] for r in priv["past_negotiations_you_hold"]] == st.assistant_past
    assert priv["past_negotiations_the_participant_holds"] == st.human_past
    one = sa.dispatcher.execute("show_past_negotiation", {"id": st.assistant_past[0]})
    assert one["ok"] and one["negotiation"]["offers"]
    refused = sa.dispatcher.execute("show_past_negotiation", {"id": st.human_past[0]})
    assert not refused["ok"] and "participant" in refused["error"]
    assert not sa.read_tool("Past Negotiations")["ok"]  # the human's own records
    assert s.context()["information"]["past_negotiations_the_participant_holds"] == st.human_past


def test_past_negotiations_are_deterministic_and_the_share_is_per_participant():
    from hani2.scenarios import registry

    sc = registry.MAKERS["Lease"](0)
    settings = {"past_negotiations": {"count": 8}}
    a = info.build_state(sc, human_index=1, settings=settings, scenario_dir="/pool/Lease/0001", assign_seed="alice|0")
    info._CACHE.clear()
    b = info.build_state(sc, human_index=1, settings=settings, scenario_dir="/pool/Lease/0001", assign_seed="alice|0")
    c = info.build_state(sc, human_index=1, settings=settings, scenario_dir="/pool/Lease/0001", assign_seed="bob|0")
    assert a.past == b.past == c.past  # the same records for the same scenario (strict studies stay comparable)
    assert a.human_past == b.human_past  # the same share for the same participant and round
    assert len(c.human_past) == 4


@pytest.mark.parametrize("share,human,assistant", [(1.0, 4, 0), (0.0, 0, 4)])
def test_all_or_nothing(share, human, assistant):
    s = session_with({"past_negotiations": {"count": 4, "human_share": share}})
    assert (len(s.information.human_past), len(s.information.assistant_past)) == (human, assistant)
    assert ("Past Negotiations" in available_names(s)) == bool(human)


def test_shared_gives_both_everything():
    s = session_with({"past_negotiations": {"count": 3, "shared": True}})
    assert s.information.human_past == s.information.assistant_past == ["P1", "P2", "P3"]


@pytest.mark.parametrize("mode", ["same", "similar", "different"])
def test_preference_modes(mode):
    from hani2.scenarios import registry

    sc = registry.MAKERS["Lease"](0)
    import numpy as np

    rng = np.random.default_rng(1)
    u = sc.ufuns[0]
    v = info.perturb_ufun(u, mode, 0.3, rng)
    outcomes = list(sc.outcome_space.enumerate_or_sample(max_cardinality=200))
    diff = max(abs(float(u(o)) - float(v(o))) for o in outcomes)
    if mode == "same":
        assert v is u
    else:
        assert diff > 0


def test_scenario_file_wins(tmp_path):
    from hani2.scenario_store import save_scenario
    from hani2.scenarios import registry

    sc = registry.MAKERS["Trade"](0)
    folder = tmp_path / "Trade" / "0000Trade"
    save_scenario(sc, folder)
    recs = info.simulate_past_negotiations(sc, {**info.DEFAULTS["past_negotiations"], "count": 2})
    recs[0]["notes"] = "Written by the scenario author"
    info.write_past_file(folder, recs)
    assert info.load_past_file(folder)[0]["notes"] == "Written by the scenario author"
    st = info.build_state(sc, human_index=1, settings={"past_negotiations": {"count": 5, "human_share": 1}},
                          scenario_dir=str(folder))
    assert st.past_source == "scenario" and len(st.past) == 2
    # a past-negotiations file is not a utility function: the folder still loads as before
    from hani2.scenario_store import _load_dir

    assert _load_dir(folder) is not None


# --------------------------------------------------------------------------- #
# Preferences split                                                            #
# --------------------------------------------------------------------------- #
def test_weights_to_the_human_values_to_the_assistant():
    s = session_with({"preferences": {"human": "weights", "assistant": "values"}})
    s.start()
    s.wait_for_turn()
    s.play_counters(2)
    snap = s.snapshot()
    # the human: no deal values anywhere
    assert snap["information"]["totals_hidden"]
    assert snap["draft"]["utility"] is None
    assert snap["partner_offer"] is None or snap["partner_offer"]["utility"] is None
    assert all("utility" not in h and "below_reserved" not in h for h in snap["history"])
    for name in ("Utility Plot", "Negotiation Plot", "Trace"):
        assert name not in available_names(s)
    pref = render(s, "Preferences")
    t = titles(pref)
    assert any("Issue weights" in x for x in t) and not any("Value of each option" in x for x in t)
    assert "your Assistant" in dump(pref)
    draft_msgs = s.hub.of_type("draft")
    assert all(m["utility"] is None for m in draft_msgs)
    # the Assistant: values but no weights, no deal values
    sa = s.support_agent
    ctx = s.context()
    assert ctx["draft_offer_utility"] is None and ctx["partner_offer_utility"] is None
    assert all(h["utility"] is None for h in ctx["history"])
    state = sa.dispatcher.execute("get_negotiation_state", {})
    assert state["draft_offer_utility"] is None
    priv = sa.dispatcher.execute("get_private_information", {})
    part = priv["participant_preferences_you_know"]
    assert part["part"] == "values" and "values" in part and "weights" not in part
    assert not sa.read_tool("Preferences")["ok"]
    listed = {t["name"] for t in s.tool_controller.list_tools()}
    assert "Utility Plot" not in listed and "Trace" not in listed
    added = sa.add_tool("Trace")
    assert not added.get("ok", False) or "Trace" not in available_names(s)


def test_values_to_the_human_hides_hints_and_weights():
    s = session_with({"preferences": {"human": "values", "assistant": "weights"}}, scenario="Grocery")
    pref = render(s, "Preferences")
    t = titles(pref)
    assert any("Value of each option" in x for x in t) and not any("Issue weights" in x for x in t)
    view = dump(render(s, "Scenario Info"))
    assert "Most Important Item" not in view  # hints come from the weights
    priv = s.support_agent.dispatcher.execute("get_private_information", {})
    assert "weights" in priv["participant_preferences_you_know"]
    # the Assistant does not see the hints either (they are the full picture for neither)
    assert "Most Important Item" not in s.support_agent.read_tool("Scenario Info")["text"]


def test_human_full_assistant_values_keeps_hints_from_the_assistant():
    s = session_with({"preferences": {"human": "full", "assistant": "values"}}, scenario="Grocery")
    s.start()
    s.wait_for_turn()
    assert "Most Important Item" in dump(render(s, "Scenario Info"))
    assert "Most Important Item" not in s.support_agent.read_tool("Scenario Info")["text"]
    assert s.snapshot()["draft"]["utility"] is not None  # the human still sees deal values
    assert s.context()["draft_offer_utility"] is None  # the Assistant does not


def test_reserved_value_to_the_assistant_only():
    s = session_with({"preferences": {"reserved_value": "assistant"}})
    assert s.snapshot()["reserved_value"] is None
    assert "Unknown" in dump(render(s, "Preferences"))
    assert s.context()["reserved_value"] is not None
    assert "participant_value_on_disagreement" in s.support_agent.private_information()


def test_show_totals_to_partial():
    s = session_with({"preferences": {"human": "weights", "assistant": "values", "show_totals_to_partial": True}})
    s.start()
    s.wait_for_turn()
    assert s.snapshot()["draft"]["utility"] is not None and s.context()["draft_offer_utility"] is not None


# --------------------------------------------------------------------------- #
# Market research                                                              #
# --------------------------------------------------------------------------- #
def test_market_research_for_the_assistant():
    s = session_with({"market_research": {"audience": "assistant"}}, scenario="Lease")
    assert "Market Research" not in available_names(s)
    mr = s.support_agent.private_information()["market_research"]
    opp = mr["opponent"]
    assert set(opp["issue_weights"]) == {i.name for i in s.issues}
    assert opp["issues_by_importance"] and opp["likely_best_deal"]
    assert "your_side" not in mr  # default: only about the opponent


def test_market_research_for_the_human_with_author_notes():
    s = make_session(load=False)
    s.admin_prefs["information"] = {"market_research": {"audience": "human", "sides": "both"}}
    s.load("Lease")
    s.scenario.info["market_research"] = "Landlords in this city rarely move on rent."  # _info.yaml text
    st = info.build_state(s.scenario, human_index=s.human_index, settings=s.admin_prefs["information"])
    assert st.market["notes"].startswith("Landlords")
    assert "Market Research" in available_names(s)
    view = dump(render(s, "Market Research"))
    assert "Parties like your opponent" in view and "Parties in your role" in view
    assert "market_research" not in s.support_agent.private_information()
    assert not s.support_agent.read_tool("Market Research")["ok"]


def test_capability_off_hides_the_functions():
    s = session_with(SPLIT, assistant_settings={"capabilities": {"private_info": False}})
    names = [f["function"]["name"] for f in s.support_agent.dispatcher.schemas()]
    assert "get_private_information" not in names
    assert not s.support_agent.private_information()["ok"]


# --------------------------------------------------------------------------- #
# Leaks: everything each party gets                                            #
# --------------------------------------------------------------------------- #
def test_no_leaks_either_way():
    s = session_with(SPLIT, scenario="Lease")
    s.start()
    s.wait_for_turn()
    s.play_counters(3)
    st = s.information
    sa = s.support_agent
    ufun = s.human_ufun
    weights = [round(float(w), 3) for w in ufun.weights]

    # the human: snapshot, every tool render and every pushed message
    snap = s.snapshot()
    renders = dump([s.render_tool(s.tool_state(t)["id"]) for t in s.tools])
    human_side = dump(snap) + renders + dump(s.hub.messages)
    assert snap["reserved_value"] is None
    for pid in st.assistant_past:
        assert f'"{pid}"' not in dump([render(s, "Past Negotiations")])
    assert "Market Research" not in available_names(s)
    assert '"utility": 0.' not in human_side.replace('"utility": null', "")
    assert "Value of each option" not in renders  # (the tool's help text names it; the data is not shown)

    # the Assistant: context, every read function and every tool it can read
    a_side = dump(s.context()) + dump(sa.dispatcher.execute("get_negotiation_state", {}))
    a_side += dump(sa.dispatcher.execute("get_private_information", {}))
    a_side += dump(sa.dispatcher.execute("list_tools", {}))
    for t in s.tool_controller.tools:
        a_side += dump(sa.read_tool(t.name))
    for pid in st.human_past:
        assert sa.past_negotiation(pid)["ok"] is False
    assert '"weights": {' not in a_side and "Issue weights" not in a_side  # no weight data (the split names the part)
    assert "draft_offer_utility\": null" in a_side
    for issue, w in zip(s.issues, weights):  # nor as "issue": weight pairs
        assert f'"{issue.name}": {w}' not in a_side
    # and the check would catch them: the Assistant of the opposite split does see such pairs
    other = session_with({"preferences": {"human": "values", "assistant": "weights"}}, scenario="Lease")
    shown = dump(other.support_agent.private_information())
    assert any(f'"{i.name}": {round(float(w), 3)}' in shown for i, w in zip(other.issues, other.human_ufun.weights))


def test_results_and_recording_carry_the_split():
    s = session_with(SPLIT)
    s.start()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    import csv

    rows = list(csv.DictReader(open(s.ss["user_path"] / "results.csv")))
    assert rows[-1]["information_split"] == "True"
    assert rows[-1]["info_human_preferences"] == "weights"
    assert set(rows[-1]["info_assistant_past"].split(",")) == set(s.information.assistant_past)


def test_study_setting(hani2_home):
    projects.create_project("SPLIT", defaults={"information": {"past_negotiations": {"count": 2, "human_share": 1}}})
    projects.create_study("SPLIT/s1")
    s = make_session(study="SPLIT/s1")
    assert s.information.human_past == ["P1", "P2"]
    projects.create_study("SPLIT/s2", information={"preferences": {"human": "weights"}})
    s2 = make_session(study="SPLIT/s2")
    assert not s2.information.past and s2.information.human_prefs == "weights"  # a study's block replaces the project's


def test_cli_writes_past_negotiations(tmp_path):
    from typer.testing import CliRunner

    from hani2.cli import app
    from hani2.scenario_store import save_scenario
    from hani2.scenarios import registry

    folder = tmp_path / "Lease" / "0000Lease"
    save_scenario(registry.MAKERS["Lease"](0), folder)
    r = CliRunner().invoke(app, ["scenario", "past", str(tmp_path / "Lease"), "--count", "3"])
    assert r.exit_code == 0, r.output
    assert len(info.load_past_file(folder)) == 3
    r = CliRunner().invoke(app, ["scenario", "past", str(folder), "--count", "1"])
    assert "skip" in r.output and len(info.load_past_file(folder)) == 3  # kept without --force


def test_preferences_stay_readable_when_only_records_are_split():
    s = session_with({"past_negotiations": {"count": 4}})
    assert s.information.split
    assert s.support_agent.read_tool("Preferences")["ok"]  # the Assistant knows them as fully as the human
    assert not s.support_agent.read_tool("Past Negotiations")["ok"]
    shared = session_with({"past_negotiations": {"count": 2, "shared": True}})
    assert shared.support_agent.read_tool("Past Negotiations")["ok"]  # nothing in it the Assistant lacks


def test_past_utilities_hidden_from_a_side_without_totals():
    s = session_with({"past_negotiations": {"count": 4, "preferences": "same", "utilities": "both"},
                      "preferences": {"human": "weights", "assistant": "full"}})
    view = dump(render(s, "Past Negotiations"))
    assert "Your side got" not in view and "Worth to your side" not in view and "utility_" not in view
    pid = s.information.assistant_past[0]
    rec = s.support_agent.past_negotiation(pid)["negotiation"]
    assert "your_side" in rec["final_utilities"]  # the Assistant sees totals, so it gets them
    s2 = session_with({"past_negotiations": {"count": 4}, "preferences": {"human": "full", "assistant": "values"}})
    rec2 = s2.support_agent.past_negotiation(s2.information.assistant_past[0])["negotiation"]
    assert rec2["final_utilities"] == {} and all(not any(k.startswith("utility_") for k in o) for o in rec2["offers"])
    rows = s2.support_agent.private_information()["past_negotiations_you_hold"]
    assert all("your_side_utility" not in r for r in rows)


def test_market_research_describes_the_population_not_the_opponent():
    import numpy as np

    s = session_with({"market_research": {"audience": "assistant", "samples": 60}}, scenario="Grocery")
    mr = s.information.market
    assert mr["source"] == "generator" and mr["samples"] == 60
    opp = s.information.opponent_role
    est = mr["roles"][opp]["issue_weights"]
    u = next(x for x in s.scenario.ufuns if x.name == opp)
    w = np.array([float(x) for x in u.weights])
    w = w / w.sum()
    # Grocery draws every item's value from the same range: the typical weights are close to equal,
    # whatever this opponent's are
    means = np.array([est[i.name]["mean"] for i in s.issues])
    assert np.all(np.abs(means - 0.25) < 0.08)
    assert np.abs(means - w).max() > 0.02 or np.abs(w - 0.25).max() < 0.05


def test_write_paths_leak_nothing():
    s = session_with(SPLIT, scenario="Lease")
    s.start()
    s.wait_for_turn()
    sa = s.support_agent
    out = dump(sa.dispatcher.execute("set_offer", {"outcome": {i.name: list(i.all)[0] for i in s.issues}}))
    out += dump(sa.use_tool("Value Histogram"))
    assert '"utility": 0' not in out and "draft_offer_utility\": 0" not in out
    res = s.send_counter()
    assert "utility" not in dump(res) or '"utility": null' in dump(res)


def test_admin_project_save_keeps_the_block(hani2_home):
    block = {"preferences": {"human": "weights", "assistant": "values"}, "past_negotiations": {"count": 3}}
    projects.create_project("SAVE", defaults={"information": block})
    assert projects.get_project(projects.StudyRef("SAVE", "x")).defaults["information"] == block


# --------------------------------------------------------------------------- #
# Dual control: private briefings, hidden constraints, human-only decisions    #
# --------------------------------------------------------------------------- #
LIMIT = {"briefing": [{"text": "Your manager will not approve a price above 120.",
                       "constraints": [{"issue": "Price", "max": 120}]}]}


def test_constraints_are_checked():
    cons = [{"issue": "Price", "max": 120}, {"issue": "Lease length", "forbidden": ["2 years"]}]
    assert info.check_constraints(cons, {"Price": 110, "Lease length": "1 year"}) == (1, [])
    met, bad = info.check_constraints(cons, {"Price": 200, "Lease length": "2 years"})
    assert met == 0 and len(bad) == 2 and "at most 120" in bad[0]
    assert info.check_constraints(cons, None) == (None, [])
    assert info.constraint_text({"issue": "Rent", "min": 1, "max": 3}) == "Rent must be between 1 and 3."


def test_private_briefing_for_the_human():
    s = session_with(LIMIT)
    st = s.information
    assert st.split and st.briefings[0]["to"] == "human" and st.constraints
    assert "Briefing" in available_names(s)
    assert "manager" in dump(render(s, "Briefing"))
    s.start()
    s.wait_for_turn()
    assert any("manager" in p["text"] for p in s.snapshot()["pins"])
    sa = s.support_agent
    a_side = dump(s.context()) + dump(sa.private_information()) + dump(sa.read_tool("Briefing"))
    a_side += dump(sa.read_tool("Scenario Info")) + dump(sa.dispatcher.execute("list_tools", {}))
    assert "manager" not in a_side and "at most 120" not in a_side
    assert s.context()["information"]["participant_has_private_briefings"] == 1
    assert "Ask them" in sa.private_information()["participant_briefing_hint"]
    sa.unpin_message()  # the Assistant cannot remove (or overwrite) it
    assert sa.pin_message("x", pin_id="briefing-B1")["ok"] is False
    assert any("manager" in p["text"] for p in s.pins)


def test_briefing_redirected_to_the_assistant():
    s = session_with({"briefing": [{**LIMIT["briefing"][0], "to": "assistant"}]})
    assert "Briefing" not in available_names(s)
    mine = s.support_agent.private_information()["briefings_for_you"]
    assert "manager" in mine[0]["text"] and mine[0]["constraints"] == ["Price must be at most 120."]


def test_scenario_briefing_from_info_yaml(hani2_home):
    from hani2.scenario_store import save_scenario, write_info
    from hani2.scenarios import registry

    sc = registry.MAKERS["Lease"](0)
    folder = hani2_home / "settings" / "scenarios" / "Lease" / "0000Lease"
    save_scenario(sc, folder)
    sc.info["briefing"] = {"Tenant": {"text": "Your partner insists on a 1 year lease.",
                                      "constraints": [{"issue": "Lease length", "allowed": ["1 year"]}]},
                           "Landlord": "The bank needs the rent to be at least 3000."}
    write_info(sc.info, folder / "_info.yml")  # the file save_scenario wrote
    s = make_session(load=False)
    s.admin_prefs["information"] = {}
    s.admin_prefs["role_rule"] = "roles"
    s.admin_prefs["human_roles"] = ["Tenant"]
    s.load("Lease")
    assert [b["text"] for b in s.information.briefings] == ["Your partner insists on a 1 year lease."]
    flip = make_session(load=False)
    flip.admin_prefs.update(information={"briefing_audience": "assistant"}, role_rule="roles", human_roles=["Tenant"])
    flip.load("Lease")
    assert flip.information.briefings[0]["to"] == "assistant"  # the study gives the scenario's briefing to the Assistant
    off = make_session(load=False)
    off.admin_prefs["information"] = {"use_scenario_briefing": False}
    off.load("Lease")
    assert not off.information.briefings and not off.information.split


def test_constraints_met_in_results():
    s = session_with({"briefing": [{"text": "Keep the price low.", "constraints": [{"issue": "Price", "max": 100}]}]})
    s.start()
    s.wait_for_turn()
    price = s.outcome_to_dict(s.partner_offer())["Price"]
    s.accept()
    s.wait_until_done()
    import csv

    row = list(csv.DictReader(open(s.ss["user_path"] / "results.csv")))[-1]
    assert row["constraints_met"] == ("1" if float(price) <= 100 else "0")
    assert row["info_briefings"] == "B1:human" and "Keep the price low" not in open(s.ss["user_path"] / "results.csv").read()
    from hani2.evaluation import evaluate_recording
    from hani2.recording.format import Recording

    r = Recording.load(s.recorder.finalize())
    m = evaluate_recording(r, ["dual_control"])["row"]
    assert m["information_split"] == 1 and m["constraints_met"] == (1 if float(price) <= 100 else 0)


def test_human_only_issues_and_actions():
    from hani2.recording.recorder import acting

    s = session_with({"control": {"human_only_issues": ["price"], "human_only_actions": ["accept", "send"]}})
    st = s.information
    assert st.human_only_issues == ["Price"] and "Briefing" in available_names(s)
    s.start()
    s.wait_for_turn()
    sa = s.support_agent
    before = s.draft["Price"]
    other = next(v for v in s.issues[1].all if v != before)
    with acting("agent"):
        res = sa.dispatcher.execute("set_offer", {"outcome": {"Price": other, "Quantity": 3}})
    assert res["human_only"] == ["Price"] and s.draft["Price"] == before and s.draft["Quantity"] == 3
    s.set_draft({"Price": other})  # the participant may
    assert s.draft["Price"] == other
    with acting("agent"):
        acc = sa.dispatcher.execute("accept_offer", {})
        sent = sa.dispatcher.execute("submit_counter_offer", {})
        assert s.accept() is False and s.send_counter()["ok"] is False  # the session refuses it too
    assert acc["executed"] is False and "Only the participant" in acc["note"]
    assert sent["submitted"] is False and s.phase == "running"
    issue = next(i for i in s.context()["issues"] if i["name"] == "Price")
    assert issue["only_the_participant_may_set"]
    assert any("Only you can" in p["text"] for p in s.pins)
    assert "Only the participant may" in sa.private_information()["control_hint"]
    with acting("autopilot"):  # the participant handed control to the autopilot
        assert sa.dispatcher._human_only("accept") is False



def test_human_only_issue_without_an_actor_and_send_accept_become_suggestions():
    import threading

    s = session_with({"control": {"human_only_issues": ["Price"]}})
    s.start()
    s.wait_for_turn()
    sa = s.support_agent
    before = s.draft["Price"]
    other = next(v for v in s.issues[1].all if v != before)
    out = {}
    t = threading.Thread(target=lambda: out.update(  # a bare thread: no actor bound (e.g. a harness callback)
        set=sa.dispatcher.execute("set_offer", {"outcome": {"Price": other}}),
        send=sa.dispatcher.execute("submit_counter_offer", {"outcome": {"Price": other}}),
        acc=sa.dispatcher.execute("accept_offer", {})))
    t.start()
    t.join()
    assert out["set"]["human_only"] == ["Price"] and s.draft["Price"] == before
    assert out["send"]["submitted"] is False and out["acc"]["executed"] is False
    assert s.phase == "running"


def test_private_keys_leave_the_scenario():
    s = make_session(load=False)
    s.admin_prefs["information"] = {}
    s.load("Lease")
    s.scenario.info["briefing"] = "x"  # (as if it came from _info.yaml) a new round takes it out again
    s._build_information(s.scenario, s.human_index, None, {})
    assert "briefing" not in s.scenario.info and s.information.briefings


def test_role_named_human_is_a_role():
    from hani2.scenarios import registry

    sc = registry.MAKERS["Island"](0)  # roles are "agent" and "human"
    sc.info["briefing"] = {"human": "for the human role", "agent": "for the agent role"}
    as_agent = info.build_state(sc, human_index=[u.name for u in sc.ufuns].index("agent"), settings={})
    assert [b["text"] for b in as_agent.briefings] == ["for the agent role"]
    sc2 = registry.MAKERS["Lease"](0)
    sc2.info["briefing"] = {"assistant": "only for the Assistant"}  # not a role of Lease: an audience
    st = info.build_state(sc2, human_index=1, settings={})
    assert st.briefings[0]["to"] == "assistant"
