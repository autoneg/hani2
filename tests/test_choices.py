"""The human choosing the scenario, opponent and Assistant of a negotiation (hani2.choices)."""

import json

from conftest import write_settings

from hani2 import assignment, choices, groups, projects
from hani2.testing import make_session

OPP_A, OPP_B = "BoulwareTBNegotiator", "ConcederTBNegotiator"


def _session(**kw):
    kw.setdefault("load", False)
    s = make_session(**kw)
    s.admin_prefs["allow_scenario_selection"] = False  # make_session turns the old switch on
    return s


def _write_env(folder, data):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "env.json").write_text(json.dumps(data), encoding="utf-8")


def test_nothing_is_allowed_by_default(hani2_home):
    s = _session()
    assert choices.policy(s) == {"scenario": False, "opponent": False, "assistant": False}
    s.load("Trade")
    assert s.snapshot()["choices"] is None
    assert s.choose("opponent", OPP_A)["ok"] is False


def test_playground_choices_from_the_settings_folder(hani2_home):
    write_settings(hani2_home, "env.json", {"playground": {"choices": {"opponent": [OPP_A, OPP_B], "scenario": True}}})
    s = _session()
    s.load("Trade")
    state = s.snapshot()["choices"]
    assert [o["value"] for o in state["opponent"]["options"]] == [OPP_A, OPP_B]
    assert state["opponent"]["current"] is None  # HANI2's own pick until the human chooses
    assert state["scenario"]["options"]
    assert state["assistant"]["options"] == []
    assert s.choose("opponent", "SomethingElse")["ok"] is False
    assert s.choose("opponent", "file:/tmp/evil.py")["ok"] is False
    assert s.choose("opponent", OPP_B)["ok"] is True
    assert s.snapshot()["choices"]["opponent"]["current"] == OPP_B
    assert s.choose_partner() == OPP_B
    assert s.choose("opponent", None)["ok"] is True  # back to HANI2's own pick
    assert s.chosen_opponent is None


def test_the_chosen_opponent_is_recorded_and_lasts_one_negotiation(hani2_home):
    write_settings(hani2_home, "env.json", {"playground": {"choices": {"opponent": True}}})
    s = _session(partner=None, opponent=None)
    s.load("Trade")
    pool = [o["value"] for o in s.snapshot()["choices"]["opponent"]["options"]]
    assert pool  # true: the session's own opponent pool
    assert s.choose("opponent", pool[-1])["ok"]
    s.start()
    assert s.ss["opponent_scheduling"] == "user"
    s.end()
    s.wait(lambda: s.phase not in ("running", "starting"))
    s.load("Trade")
    assert s.chosen_opponent is None


def test_scenario_choice_is_limited_to_the_allowed_types(hani2_home):
    write_settings(hani2_home, "env.json", {"playground": {"choices": {"scenario": ["Island"]}}})
    s = _session()
    s.load()
    assert s.can_choose_scenario()
    assert s.snapshot()["choices"]["scenario"]["options"] == ["Island"]
    plan = s.round_plan
    s.load("Trade")  # not allowed: nothing is loaded
    assert s.round_plan is plan
    s.load("Island", "no-such-scenario")
    assert s.round_plan is plan
    s.load("Island")
    assert s.ss["scenario_type"] == "Island"
    assert s.round_plan["scenario_scheduling"] == "user"


def test_the_old_switch_still_allows_choosing_the_scenario(hani2_home):
    s = _session()
    s.admin_prefs["allow_scenario_selection"] = True
    assert choices.policy(s)["scenario"] is True


def test_settings_folder_choices_never_reach_a_study(hani2_home):
    write_settings(hani2_home, "env.json", {"playground": {"choices": {"opponent": True}},
                                            "choices": {"opponent": True}})
    projects.create_project("P")
    projects.create_study("P/online", type="online")
    projects.create_study("default/legacy", type="online")
    for ref in ("P/online", "default/legacy"):
        s = _session(study=ref)
        assert choices.policy(s)["opponent"] is False, ref


def test_project_choices_are_inherited_and_a_study_overrides_them(hani2_home):
    projects.create_project("P")
    projects.create_study("P/a", type="online")
    projects.create_study("P/b", type="lab")
    _write_env(projects.project_dir("P"), {"choices": {"opponent": [OPP_A], "assistant": True}})
    _write_env(projects.study_dir(projects.StudyRef("P", "b")), {"choices": {"opponent": False}})
    assert choices.policy(_session(study="P/a"))["opponent"] == [OPP_A]
    pol_b = choices.policy(_session(study="P/b"))
    assert pol_b["opponent"] is False and pol_b["assistant"] is True


def test_prolific_studies_never_allow_choosing(hani2_home):
    projects.create_project("P")
    projects.create_study("P/pro", type="prolific")
    _write_env(projects.study_dir(projects.StudyRef("P", "pro")), {"choices": {"opponent": True, "scenario": True}})
    s = _session(study="P/pro")
    assert choices.policy(s) == {"scenario": False, "opponent": False, "assistant": False}
    assert not s.can_choose_scenario()
    p = _session(study="P/pro", user="prolific_X", mode="guest", partner=None, query={"noautostart": "1"})
    p.admin_prefs["allow_scenario_selection"] = True
    assert choices.policy(p) == {"scenario": False, "opponent": False, "assistant": False}
    assert not p.can_choose_scenario()


def test_the_old_switch_still_works_in_a_study_of_the_default_type(hani2_home):
    projects.create_project("P")
    projects.create_study("P/s")  # type: prolific (the default), a signed-in user
    s = make_session(study="P/s", scenario_type="Island")
    assert s.can_choose_scenario()
    assert s.ss["scenario_type"] == "Island"


def test_a_participant_link_session_gets_its_picks(hani2_home):
    projects.create_project("P")
    projects.create_study("P/on", type="online")
    _write_env(projects.study_dir(projects.StudyRef("P", "on")),
               {"choices": {"scenario": ["Island"], "opponent": [OPP_B], "assistant": ["none"]}})
    s = _session(study="P/on", user="participant_x", mode="guest", partner=None, query={"noautostart": "1"})
    s.load()
    state = s.snapshot()["choices"]
    assert state is not None and state["scenario"]["options"] == ["Island"]
    s.load("Island")
    assert s.ss["scenario_type"] == "Island" and s.round_plan["scenario_scheduling"] == "user"
    assert s.choose("opponent", OPP_B)["ok"] and s.choose("assistant", "none")["ok"]
    s.start()
    assert s.ss["last_partner_type"] == OPP_B and s.ss["opponent_scheduling"] == "user"
    assert assignment.is_no_assistant(s.assistant_choice.spec)
    s.end()


def test_choosing_the_assistant_is_used_as_given_and_not_recorded(hani2_home):
    projects.create_project("P")
    projects.create_study("P/a", type="online")
    s = _session(study="P/a", user="alice")
    default = groups.default_assistant_spec(s.assistant_settings)
    _write_env(projects.project_dir("P"), {"choices": {"assistant": [default, "none"]}})
    s.load("Trade")
    before = assignment.read_assignments(s.study_ref)
    opts = [o["value"] for o in s.snapshot()["choices"]["assistant"]["options"]]
    assert opts == [default, "none"]
    assert s.choose("assistant", "SomeOtherAssistant")["ok"] is False
    assert s.choose("assistant", "none")["ok"] is True
    assert s.support_agent is None
    assert s.assistant_choice.source == "user"
    assert s.assistant_attribution()["assistant_scheduling"] == "user"
    s.refresh_assistant(s.round_plan)  # a reconnect keeps the human's pick
    assert assignment.is_no_assistant(s.assistant_choice.spec)
    assert assignment.read_assignments(s.study_ref) == before
    s.start()
    s.end()
    s.wait(lambda: s.phase not in ("running", "starting"))
    s.refresh_assistant(s.round_plan)  # a reload before the next load keeps this negotiation's Assistant
    assert assignment.is_no_assistant(s.assistant_choice.spec)
    s.load("Trade")
    assert s.chosen_assistant is None  # the next negotiation starts from HANI2's own pick again
    assert s.assistant_choice.spec == default and s.support_agent is not None
