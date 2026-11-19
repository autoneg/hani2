"""Ablations: the opponent_utility oracle, the no-Assistant arm, conditions and the ablation report."""

import pytest
from conftest import write_settings

from hani2 import projects
from hani2.evaluation.ablation import ablation_report, condition_of
from hani2.projects import StudyRef
from hani2.support_agent.capabilities import Capability
from hani2.testing import make_session

HELLO = "level1_hello:HelloAgent"


# --------------------------------------------------------------------------- #
# The oracle capability                                                        #
# --------------------------------------------------------------------------- #
def test_oracle_off_by_default(hani2_home):
    s = make_session()
    sa = s.support_agent
    assert not sa.capabilities.has(Capability.OPPONENT_UTILITY)
    assert "get_opponent_utility" not in [f["function"]["name"] if "function" in f else f.get("name")
                                          for f in sa.dispatcher.schemas()]
    assert "opponent" not in sa.context()
    assert sa.opponent_view()["ok"] is False
    assert s.ablation_condition()["oracle"] is False


def _names(sa):
    return [f["function"]["name"] if "function" in f else f.get("name") for f in sa.dispatcher.schemas()]


def test_oracle_gives_the_opponent_utility(hani2_home):
    s = make_session(assistant_settings={"capabilities": {"opponent_utility": True}})
    sa = s.support_agent
    assert sa.capabilities.has(Capability.OPPONENT_UTILITY)
    assert "get_opponent_utility" in _names(sa)
    assert "OPPONENT KNOWLEDGE" in sa.messages[0]["content"]
    ctx = sa.context()
    prefs = ctx["opponent"]["opponent_preferences"]
    assert "reserved_value" in prefs and (prefs.get("issues") or prefs.get("best_outcomes"))
    # score an offer for both sides
    o = next(iter(s.scenario.outcome_space.enumerate_or_sample(max_cardinality=10)))
    offer = s.outcome_to_dict(o)
    v = sa.opponent_view(offer)
    assert v["ok"] and v["offer"]["opponent_utility"] == pytest.approx(float(s.opponent_ufun(o)))
    assert v["offer"]["your_utility"] == pytest.approx(float(s.human_ufun(o)))
    assert sa.dispatcher._get_opponent_utility({"offer": {"nope": 1}})["ok"] is False
    assert s.ablation_condition()["oracle"] is True


def test_oracle_is_admin_only(hani2_home):
    s = make_session(assistant_settings={"capabilities": {"opponent_utility": True}})
    sa = s.support_agent
    # never shown to the participant, and the participant cannot switch it off
    assert "opponent_utility" not in [c["key"] for c in sa.client_state()["capabilities"]]
    sa.capabilities.set_user_capability("opponent_utility", False)
    assert sa.capabilities.has(Capability.OPPONENT_UTILITY)
    # nor on: the admin grant decides
    s2 = make_session()
    s2.support_agent.capabilities.set_user_capability("opponent_utility", True)
    assert not s2.support_agent.capabilities.has(Capability.OPPONENT_UTILITY)


# --------------------------------------------------------------------------- #
# The no-Assistant arm                                                         #
# --------------------------------------------------------------------------- #
@pytest.fixture
def study(hani2_home):
    projects.create_project("HI", kind="assistant")
    projects.create_study("HI/s1", type="prolific")
    ref = StudyRef("HI", "s1")
    f = projects.study_dir(ref) / projects.STUDY_FILE
    d = projects.read_yaml(f)
    d["assistants"] = [HELLO, "none"]
    projects.write_yaml(f, d)
    return ref


def test_none_is_a_balanced_no_assistant_arm(study):
    got = {}
    for i in range(4):
        s = make_session(user=f"prolific_P{i}", mode="guest", partner=None, study=study, query={"noautostart": "1"})
        got[s.user] = s.assistant_choice.spec
        if s.assistant_choice.spec == "none":
            assert s.support_agent is None and not s.__dict__.get("assistant_error")
            assert s.ablation_condition()["assistant"] == "none"
            assert s.assistant_attribution()["assistant"] == "none"
        else:
            assert type(s.support_agent).__name__ == "HelloAgent"
            assert s.ablation_condition()["assistant"] == "on"
    assert sorted(got.values()) == sorted([HELLO, HELLO, "none", "none"])


def test_no_assistant_arm_has_no_assistant_autopilot(study, hani2_home):
    write_settings(hani2_home, "autopilot_settings.json",
                   {"allowed": True, "driver": "Assistant", "allowed_drivers": ["Assistant"], "step_delay": 0})
    for i in range(2):
        s = make_session(user=f"prolific_Q{i}", mode="guest", partner=None, study=study, query={"noautostart": "1"})
        if s.assistant_choice.spec == "none":
            s.start()
            s.wait_for_turn()
            assert not s.set_autopilot(True)["ok"]
            assert not s.autopilot_active
            return
    pytest.fail("no session got the no-Assistant arm")


# --------------------------------------------------------------------------- #
# Conditions                                                                   #
# --------------------------------------------------------------------------- #
def _acts(*actors):
    return [{"type": "offer", "actor": a} for a in actors]


@pytest.mark.parametrize("cond, acts, events, label", [
    ({"assistant": "on", "oracle": False}, _acts("human", "agent"), [], "team"),
    ({"assistant": "on", "oracle": True}, _acts("human"), [], "oracle_team"),
    ({"assistant": "none"}, _acts("human", "human"), [], "human_alone"),
    ({"assistant": "on"}, _acts("autopilot", "autopilot"), [{"type": "autopilot", "active": True, "driver": "Assistant"}],
     "no_human"),
    ({"assistant": "on", "oracle": True}, _acts("autopilot"), [{"type": "autopilot", "active": True, "driver": "Assistant"}],
     "oracle_no_human"),
    ({"assistant": "on"}, _acts("autopilot"), [{"type": "autopilot", "active": True, "driver": "ConcederTBNegotiator"}],
     "negotiator_autopilot"),
    ({"assistant": "on"}, _acts("human", "autopilot"), [{"type": "autopilot", "active": True, "driver": "Assistant"}],
     "mixed"),
    ({"assistant": "off"}, _acts("human"), [], "assistant_off"),
    (None, _acts("human"), [], "unknown"),
])
def test_condition_labels(cond, acts, events, label):
    start = {"condition": cond} if cond is not None else {}
    assert condition_of(start, acts, events)["condition"] == label


def test_report_matches_cells_instead_of_pooling():
    rows = []

    def add(cond, scenario, value, n=1, **kw):
        for _ in range(n):
            rows.append(dict(condition=cond, scenario=scenario, opponent="B", human_advantage=value, **kw))

    # the team played mostly the easy cell, humans alone mostly the hard one: pooled means would
    # exaggerate the added value; matched cells give +0.1 in both
    add("team", "easy", 0.9, 5, assistant="A1")
    add("team", "hard", 0.3, 1, assistant="A1")
    add("human_alone", "easy", 0.8, 1)
    add("human_alone", "hard", 0.2, 5)
    add("no_human", "easy", 1.0)
    add("team", "only_team", 0.5, assistant="A2")
    add("team", "easy", 0.0, practice=True, assistant="A1")  # practice: left out
    add("team", "easy", 0.0, opponent_info_tools=1, assistant="A1")  # saw the opponent: left out
    rep = ablation_report(rows)
    gaps = {g["gap_name"]: g for g in rep["gaps"]}
    av = gaps["added_value"]
    assert av["cells"] == 2 and av["gap"] == pytest.approx(0.1) and av["cells_a_only"] == 1
    assert av["n_a"] == 6 and av["n_b"] == 6
    assert gaps["through_human_loss"]["gap"] == pytest.approx(0.1) and gaps["through_human_loss"]["cells"] == 1
    assert gaps["information_gain"]["gap"] is None
    assert rep["dropped"] == {"practice": 1, "opponent_info_tools": 1}
    rows.append(dict(condition="assistant_off", scenario="only_team", opponent="B", human_advantage=0.1))
    assert {g["gap_name"]: g["cells"] for g in ablation_report(rows)["gaps"]}["added_value"] == 2
    assert {g["gap_name"]: g["cells"] for g in ablation_report(rows, off_is_control=True)["gaps"]}["added_value"] == 3
    by = [g for g in ablation_report(rows, by="assistant")["gaps"] if g["gap_name"] == "added_value"]
    assert {g["group"]: g["cells"] for g in by} == {"A1": 2, "A2": 0}


# --------------------------------------------------------------------------- #
# The No-Human runner, end to end                                              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("oracle", [False, True])
def test_no_human_runs_are_recorded_and_evaluated(hani2_home, scripted, oracle):
    from hani2.ablation import run_no_human
    from hani2.evaluation import evaluate_paths

    scripted(*([("submit_counter_offer", {"message": "auto"})] * 40))
    runs = run_no_human(scenario_types=["Trade"], opponents=["ConcederTBNegotiator"], reps=1, n_steps=4,
                        oracle=oracle, timeout=60)
    assert len(runs) == 1 and runs[0]["ok"], runs
    assert runs[0]["recording"]
    # the settings file was not touched
    assert not (hani2_home / "settings" / "autopilot_settings.json").exists()
    ev = evaluate_paths([runs[0]["recording"]], ["outcome", "condition"])
    row = ev["rows"][0]
    assert row["condition"] == ("oracle_no_human" if oracle else "no_human"), row
    assert row["autopilot_share"] == 1.0 and row["autopilot_driver"] == "Assistant"
    assert row["oracle"] == (1 if oracle else 0)
    assert row["human_advantage"] is not None


def test_by_splits_every_assistant_condition():
    rows = [dict(condition=c, scenario="s", opponent="B", human_advantage=v, assistant=a)
            for c, v, a in [("team", 0.5, "A1"), ("team", 0.7, "A2"), ("no_human", 0.9, "A1"), ("no_human", 0.6, "A2"),
                            ("human_alone", 0.4, "none")]]
    gaps = ablation_report(rows, by="assistant")["gaps"]
    loss = {g["group"]: g["gap"] for g in gaps if g["gap_name"] == "through_human_loss"}
    assert loss == {"A1": pytest.approx(0.4), "A2": pytest.approx(-0.1)}  # each Assistant against itself
    av = {g["group"]: g["gap"] for g in gaps if g["gap_name"] == "added_value"}
    assert av == {"A1": pytest.approx(0.1), "A2": pytest.approx(0.3)}  # a shared human-alone baseline


def test_none_passes_the_command_line_check(hani2_home):
    from hani2.cli import _check_assistants

    assert _check_assistants(f"{HELLO},none") == f"{HELLO},none"


def test_stalled_autopilot_counts_as_no_deal(hani2_home, scripted):
    from hani2.ablation import run_no_human

    llm = scripted(*(["I am just chatting"] * 60))
    runs = run_no_human(opponents=["BoulwareTBNegotiator"], n_steps=30, timeout=60)
    assert runs[0]["ok"] and runs[0]["note"] == "autopilot disengaged", runs
    assert runs[0]["result"] is not None and not runs[0]["result"].get("agreement")
    # no oracle: the function is never offered, even with autopilot's full autonomy
    assert llm.calls and all("get_opponent_utility" not in c["tools"] for c in llm.calls)
    from hani2.evaluation import evaluate_paths

    row = evaluate_paths([runs[0]["recording"]], ["outcome", "condition"])["rows"][0]
    assert row["condition"] == "no_human" and row["human_advantage"] == pytest.approx(0.0)


def test_three_arms_share_cells(study, hani2_home, scripted):
    """A team, a human alone and the No-Human run of the same study meet in the same cells, and the
    runner neither takes a participant slot nor changes the scheduled opponents."""
    import json

    from hani2.ablation import cells_of, run_no_human
    from hani2.assignment import store_path
    from hani2.evaluation import ablation_report, evaluate_paths

    scripted(*([("submit_counter_offer", {"message": "auto"})] * 40))
    arms = set()
    for i in range(2):
        s = make_session(user=f"u{i}", study=study, opponent="ConcederTBNegotiator", n_steps=4,
                         query={"noautostart": "1"})
        arms.add(s.assistant_choice.spec)
        s.start()
        s.play_counters(6)
        assert s.wait_until_done(timeout=30)
        s.recorder.finalize()
        s.close()
    assert arms == {HELLO, "none"}
    before = json.loads(store_path(study).read_text())
    cells = cells_of([hani2_home])
    assert cells and all(c["opponent"] == "ConcederTBNegotiator" for c in cells)
    runs = run_no_human(cells=cells, study=study, n_steps=4, timeout=60)
    assert runs and all(r["ok"] and r["assistant"] == HELLO for r in runs), runs
    assert json.loads(store_path(study).read_text()) == before  # no participant slot taken
    ev = evaluate_paths([hani2_home], ["outcome", "condition"])
    assert {r["condition"] for r in ev["rows"]} == {"team", "human_alone", "no_human"}
    assert all(r["opponent"] == "ConcederTBNegotiator" for r in ev["rows"])
    gaps = {g["gap_name"]: g for g in ablation_report(ev["rows"])["gaps"]}
    assert gaps["added_value"]["cells"] >= 1 and gaps["through_human_loss"]["cells"] >= 1
