"""A different look for the Assistant and the opponent in each negotiation (interface.vary_appearance)."""

import json

from hani2 import appearance, projects
from hani2.testing import make_session


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _play_one(s):
    s.start()
    s.wait_for_turn()
    look = s.snapshot()["interface"]["appearance"]
    s.end()
    assert s.wait_until_done()
    return look


def test_flags():
    assert appearance.vary_flags(None) == {"assistant": False, "opponent": False}
    assert appearance.vary_flags(True) == {"assistant": True, "opponent": True}
    assert appearance.vary_flags("yes") == {"assistant": True, "opponent": True}
    assert appearance.vary_flags({"opponent": True}) == {"assistant": False, "opponent": True}


def test_looks_are_stable_distinct_and_disjoint():
    flags = {"assistant": True, "opponent": True}
    seq = [appearance.look_for("P/s|alice", i, flags) for i in range(12)]
    assert seq == [appearance.look_for("P/s|alice", i, flags) for i in range(12)]  # deterministic
    for a, b in zip(seq, seq[1:]):  # consecutive negotiations never look the same
        for who in ("assistant", "opponent"):
            assert a[who]["color"] != b[who]["color"] and a[who]["icon"] != b[who]["icon"]
    assert not set(appearance.ASSISTANT_COLORS) & set(appearance.OPPONENT_COLORS)
    # another participant walks the looks in another order
    other = [appearance.look_for("P/s|bob", i, flags) for i in range(12)]
    assert other != seq
    assert appearance.look_for("x", 0, {"assistant": False, "opponent": False}) is None


def test_off_by_default(hani2_home):
    s = make_session()
    assert s.snapshot()["interface"]["appearance"] is None
    s.start()
    s.wait_for_turn()
    assert s.snapshot()["interface"]["appearance"] is None
    s.end()


def test_each_negotiation_gets_its_own_look(hani2_home):
    _write(hani2_home / "settings" / "env.json", {"interface": {"vary_appearance": {"assistant": True, "opponent": True}}})
    s = make_session(user="alice")
    before = s.snapshot()["interface"]["appearance"]
    first = _play_one(s)
    assert before == first and first["index"] == 0  # announced before the start, kept while it runs
    assert s.snapshot()["interface"]["appearance"] == first  # still this negotiation's after the end
    s.load()
    second = _play_one(s)
    assert second["index"] == 1
    assert second["assistant"] != first["assistant"] and second["opponent"] != first["opponent"]
    # a new browser session of the same participant continues the count
    s2 = make_session(user="alice")
    assert s2.snapshot()["interface"]["appearance"]["index"] == 2


def test_layers_global_project_study(hani2_home):
    _write(hani2_home / "settings" / "env.json", {"interface": {"vary_appearance": {"assistant": True}}})
    projects.create_project("P")
    projects.create_study("P/s1")
    projects.create_study("P/s2")
    projects.create_study("P/s3")
    _write(projects.project_dir("P") / "env.json", {"interface": {"vary_appearance": {"opponent": True}}})
    _write(projects.study_dir(projects.StudyRef("P", "s1")) / "env.json",
           {"interface": {"vary_appearance": {"assistant": True, "opponent": False}}})
    _write(projects.study_dir(projects.StudyRef("P", "s3")) / "env.json", {"interface": {"vary_appearance": {"assistant": False, "opponent": False}}})

    def look(study=None):
        return make_session(study=study, load=False).snapshot()["interface"]["appearance"]

    g = look()  # the settings folder (global)
    assert g["assistant"] and g["opponent"] is None
    p = look("P/s2")  # the project adds the opponent; the Assistant's comes from the settings folder (key by key)
    assert p["opponent"] and p["assistant"]
    s1 = look("P/s1")  # the study's own value wins
    assert s1["assistant"] and s1["opponent"] is None
    assert look("P/s3") is None  # switched off in the study
