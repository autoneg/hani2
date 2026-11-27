"""The score builder's preview (``POST /api/admin/scores/preview``, :func:`hani2.evaluation.boards.preview`):
an unsaved score on the current board data, with the weights in effect after coverage, the dropped parts,
the distribution over the games and the top entrants; it ranks as the saved score would, writes nothing,
and is for admins only."""

import itertools

import pytest
from fastapi.testclient import TestClient

from hani2 import projects
from hani2.evaluation import boards, scores as S
from hani2.projects import StudyRef

A, B, C = "teamA.helper:Helper", "teamB.coach:Coach", "teamC.pal:Pal"
_ids = itertools.count()


def row(user, spec, adv, agree=1.0, **kw):
    return {"id": f"r{next(_ids)}", "user": user, "scenario": "s1", "opponent": "Boulware", "support_agent": spec,
            "assistant": spec, "status": "success", "agreement": agree, "human_advantage": adv,
            "started": "2027-03-01T10:00:00+00:00", "practice": False, "counted": True, "mode": None, **kw}


@pytest.fixture
def hi(hani2_home, monkeypatch):
    projects.create_project("HI", kind="assistant", year=2027)
    projects.create_study("HI/play", type="online")
    # A leads on human_advantage, C on agreement; only A and B have welfare_optimality
    rows = [row(f"a{i}", A, 0.9, 0.4, welfare_optimality=0.5) for i in range(4)] + \
           [row(f"b{i}", B, 0.5, 0.6, welfare_optimality=0.5) for i in range(4)] + \
           [row(f"c{i}", C, 0.2, 1.0) for i in range(4)]

    def fake(ref):
        return ([dict(r, _study=str(ref)) for r in rows] if str(ref) == "HI/play" else []), {"games": 0}

    monkeypatch.setattr(boards, "study_rows", fake)
    f = projects.project_dir("HI") / projects.PROJECT_FILE
    d = projects.read_yaml(f)
    d["leaderboard"] = {"rules": {"min_games": 1, "min_participants": 1}}
    projects.write_yaml(f, d)
    return rows


def draft(w_adv, w_agree, **kw):
    return {"title": "Draft", "track": "hi", "components": [
        {"criterion": "human_advantage", "weight": w_adv}, {"criterion": "agreement", "weight": w_agree}], **kw}


def test_the_top_entrant_follows_the_weights(hi):
    adv = boards.preview("HI", None, draft(0.9, 0.1), "mix")
    agree = boards.preview("HI", None, draft(0.1, 0.9), "mix")
    assert adv["problems"] == [] and adv["entries"][0]["label"] == "Helper"
    assert agree["entries"][0]["label"] == "Pal"
    assert adv["weights_in_effect"] == {"human_advantage": 0.9, "agreement": 0.1}
    assert adv["games"] == 12 and sum(b["count"] for b in adv["histogram"]) == 12
    assert len(adv["histogram"]) == 10 and adv["histogram"][0]["lo"] == 0 and adv["histogram"][-1]["hi"] == 1


def test_the_preview_ranks_as_the_saved_score(hi):
    """The regression: the preview equals the board of the same score once it is saved."""
    d = draft(0.6, 0.4)
    pre = boards.preview("HI", None, d, "mix", n_boot=200)
    S.save_score("HI", None, "mix", d)
    out = boards.board("HI", None, {"sort": "mix"}, admin=True, n_boot=200)
    assert [e["entrant"] for e in pre["entries"]] == [e["entrant"] for e in out["entries"]][:5]
    assert [e["mean"] for e in pre["entries"]] == [e["values"]["mix"]["mean"] for e in out["entries"]][:5]
    assert pre["weights_in_effect"] == out["scores"]["mix"]["weights_in_effect"]


def test_coverage_drops_a_part_for_everyone(hi):
    d = {"track": "hi", "components": [{"criterion": "human_advantage", "weight": 0.5},
                                       {"criterion": "welfare_optimality", "weight": 0.5}]}
    out = boards.preview("HI", None, d)
    assert out["dropped"] == ["welfare_optimality"]
    assert out["weights_in_effect"] == {"human_advantage": 1.0}
    assert out["key"] == boards.PREVIEW_KEY  # no key yet: the stand-in


def test_weights_that_do_not_sum_to_one_are_rescaled_with_a_note(hi):
    out = boards.preview("HI", None, draft(30, 30), "mix")
    assert out["problems"] == []
    assert out["weights_in_effect"] == {"human_advantage": 0.5, "agreement": 0.5}
    assert any("rescaled to 100 %" in n for n in out["notes"])


def test_problems_come_back_without_a_board(hi):
    out = boards.preview("HI", None, {"components": [{"criterion": "no_such_column", "weight": 1}]}, "x")
    assert out["problems"] and "unknown criterion" in out["problems"][0]
    assert "entries" not in out


def test_a_study_preview_uses_the_study_and_writes_nothing(hi):
    f = projects.study_dir(StudyRef("HI", "play")) / projects.STUDY_FILE
    before = f.read_text(encoding="utf-8")
    out = boards.preview("HI", "play", draft(0.5, 0.5), "mix")
    assert out["games"] == 12
    assert f.read_text(encoding="utf-8") == before
    assert "mix" not in S.resolve("HI", "play").scores


def test_the_endpoint_is_for_admins(hi):
    from hani2.server import app

    with TestClient(app) as c:
        body = {"key": "mix", "score": draft(0.9, 0.1)}
        assert c.post("/api/admin/scores/preview?project=HI", json=body).status_code in (401, 403)
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        r = c.post("/api/admin/scores/preview?project=HI", json=body)
        assert r.status_code == 200, r.text
        assert r.json()["entries"][0]["label"] == "Helper"
        r = c.post("/api/admin/scores/preview?study=HI/play", json=body)
        assert r.status_code == 200 and r.json()["games"] == 12
        assert c.post("/api/admin/scores/preview?project=NOPE", json=body).status_code == 404
        assert c.post("/api/admin/scores/preview", json=body).status_code == 400
