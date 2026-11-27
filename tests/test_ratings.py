"""Leaderboard update rules (hani2.ratings) and their use by the boards: pooled, latest tournament and
continuous (recency-weighted, change-flagging) ratings."""

import json
import random
import subprocess
import sys

import pytest

from hani2 import ratings
from hani2.ratings import Observation as O

DAY = ratings.DAY


def _series(entrant, days, mean, sd=0.05, seed=0, **kw):
    rng = random.Random(f"{entrant}{seed}")
    return [O(entrant, d * DAY, rng.gauss(mean(d) if callable(mean) else mean, sd), **kw) for d in days]


def test_module_is_pure():
    """scmlweb can import it: no HANI2 or web modules come with it."""
    code = ("import sys, hani2.ratings; bad = [m for m in sys.modules if m.startswith(('fastapi', 'negmas', "
            "'starlette', 'numpy', 'hani2.session', 'hani2.projects'))]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
    assert out == "[]"


def test_pooled_weighs_every_game_the_same():
    obs = [O("a", 0, 0.2), O("a", 10 * DAY, 0.8), O("b", 0, 0.4), O("b", DAY, 0.4)]
    est = ratings.method_from_config("pooled").estimate(obs)
    assert est["a"].mean == pytest.approx(0.5) and est["a"].n == 2
    assert est["b"].mean == pytest.approx(0.4) and est["b"].sd == pytest.approx(0.0)
    ranked = ratings.rank(est, by="mean")
    assert [e.entrant for e in ranked] == ["a", "b"] and ranked[0].rank == 1


def test_latest_tournament_replaces_the_board():
    obs = [O("a", 0, 0.9, tournament="t1"), O("b", 0, 0.1, tournament="t1"),
           O("b", 5 * DAY, 0.7, tournament="t2"), O("c", 6 * DAY, 0.3, tournament="t2")]
    m = ratings.method_from_config({"mode": "latest"})
    assert m.latest(obs) == "t2"
    est = m.estimate(obs)
    assert set(est) == {"b", "c"}  # a did not play the newest tournament
    assert est["b"].mean == pytest.approx(0.7)


def test_continuous_uses_every_score_with_recency():
    """An entrant that improved recently ranks above one with the same overall mean that got worse."""
    obs = (_series("improving", range(30), lambda d: 0.3 if d < 15 else 0.7) +
           _series("declining", range(30), lambda d: 0.7 if d < 15 else 0.3))
    pooled = ratings.method_from_config("pooled").estimate(obs)
    assert pooled["improving"].mean == pytest.approx(pooled["declining"].mean, abs=0.05)
    for method in ("kalman", "decayed"):
        est = ratings.method_from_config({"mode": "continuous", "method": method,
                                          "half_life_days": 7}).estimate(obs, now=30 * DAY)
        assert est["improving"].mean > 0.55 > 0.45 > est["declining"].mean, method
        # every game is used (none is dropped by a window)
        assert est["improving"].n == 30


def test_kalman_flags_a_probable_new_version_and_relearns():
    obs = _series("x", range(60), lambda d: 0.4 if d < 40 else 0.8) + _series("y", range(60), 0.6)
    est = ratings.method_from_config({"mode": "continuous"}).estimate(obs, now=60 * DAY)
    cps = est["x"].changes
    assert cps and cps[0].kind == "cusum"
    t = ratings._ts(cps[0].time) / DAY
    assert 40 <= t <= 46  # detected within a few games of the change
    assert est["x"].mean == pytest.approx(0.8, abs=0.06)  # re-learnt: not stuck halfway
    assert not est["y"].changes
    # without the reset the estimate lags behind
    lag = ratings.KalmanLocalLevel(reset_on_change=False, change_h=0).estimate(obs, now=60 * DAY)
    assert lag["x"].mean < est["x"].mean


def test_declared_version_is_a_hint_not_a_split():
    obs = [O("x", d * DAY, 0.5, version="1.0" if d < 5 else "2.0") for d in range(10)]
    est = ratings.method_from_config({"mode": "continuous"}).estimate(obs, now=10 * DAY)
    assert list(est) == ["x"]  # one entrant, whatever it declared
    assert est["x"].versions == ["1.0", "2.0"]
    assert [c.kind for c in est["x"].changes] == ["version"]
    off = ratings.method_from_config({"mode": "continuous", "version_hint": False}).estimate(obs, now=10 * DAY)
    assert off["x"].changes == []


def test_few_games_and_idle_entrants_are_uncertain_and_rank_by_the_lower_bound():
    obs = [O("veteran", d * DAY / 2, 0.51 if d % 2 else 0.81) for d in range(120)] + [O("newcomer", 59 * DAY, 0.70)]
    est = ratings.method_from_config({"mode": "continuous"}).estimate(obs, now=60 * DAY)
    assert est["newcomer"].sd > 1.4 * est["veteran"].sd
    assert est["newcomer"].mean < 0.70  # shrunk toward the field
    ranked = ratings.rank(est, by="lower")
    assert ranked[0].entrant == "veteran"
    assert ratings.rank(est, by="mean")[0].entrant == "newcomer"
    # an entrant that stopped playing grows uncertain
    later = ratings.method_from_config({"mode": "continuous"}).estimate(obs, now=400 * DAY)
    assert later["veteran"].sd > est["veteran"].sd


def test_rank_direction_lower_is_better():
    est = ratings.method_from_config("pooled").estimate([O("a", 0, 10), O("a", 1, 12), O("b", 0, 20), O("b", 1, 22)])
    assert [e.entrant for e in ratings.rank(est, direction="lower")] == ["a", "b"]


def test_config_checks():
    assert ratings.check_config(None) == [] and ratings.check_config("continuous") == []
    assert ratings.check_config("weekly")
    assert any("unknown key" in p for p in ratings.check_config({"mode": "continuous", "speed": 1}))
    assert any("method" in p for p in ratings.check_config({"mode": "continuous", "method": "elo"}))
    assert any("drift_sd" in p for p in ratings.check_config({"drift_sd": -1}))
    with pytest.raises(ValueError):
        ratings.method_from_config({"mode": "nope"})


def test_command_line_reads_json_lines():
    lines = "\n".join(json.dumps({"entrant": e, "time": f"2026-11-{d:02d}T00:00:00Z", "value": v})
                      for e, v in (("a", 0.8), ("b", 0.2)) for d in range(1, 6))
    out = subprocess.run([sys.executable, "-m", "hani2.ratings", '{"mode": "continuous"}', "2026-11-06T00:00:00Z"],
                         input=lines, capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    assert [e["entrant"] for e in data["entries"]] == ["a", "b"] and data["entries"][0]["rank"] == 1


# --------------------------------------------------------------------------- #
# On the boards                                                               #
# --------------------------------------------------------------------------- #
from test_boards import RULES0, hi, names, row, set_board  # noqa: E402,F401  (fixture re-used)

from hani2 import projects  # noqa: E402
from hani2.evaluation import boards  # noqa: E402

A, B = "teamA.helper:Helper", "teamB.coach:Coach"


def test_board_latest_keeps_only_the_newest_study(hi):
    projects.create_study("HI/round2", type="online")
    set_board({"sort_options": ["utility"], "rules": RULES0, "update": "latest"})
    hi["HI/play"] = [row("u1", A, 0.9, day=1), row("u2", B, 0.1, day=1)]
    hi["HI/round2"] = [row("u3", B, 0.8, day=9), row("u4", B, 0.6, day=9)]
    out = boards.board("HI", None, {}, n_boot=20)
    assert names(out) == [B]
    assert out["excluded"]["earlier tournament"] == 2
    assert any("latest" in n and "HI/round2" in n for n in out["notes"])
    # the default (pooled) board ranks both
    set_board({"sort_options": ["utility"], "rules": RULES0})
    assert set(names(boards.board("HI", None, {}, n_boot=20))) == {A, B}


def test_board_latest_ignores_games_that_do_not_count(hi):
    """A newer study with only a practice or a failed game is not the latest tournament."""
    projects.create_study("HI/round2", type="online")
    set_board({"sort_options": ["utility"], "rules": RULES0, "update": "latest"})
    hi["HI/play"] = [row("u1", A, 0.9, day=1), row("u2", B, 0.1, day=1)]
    hi["HI/round2"] = [row("u3", B, 0.8, day=9, practice=True), row("u4", B, 0.8, day=9, status="erred")]
    out = boards.board("HI", None, {}, n_boot=20)
    assert set(names(out)) == {A, B} and any("HI/play" in n for n in out["notes"])


def test_board_continuous_ranks_recent_form_and_flags_changes(hi):
    from datetime import datetime, timezone

    set_board({"sort_options": ["utility"], "rules": {**RULES0, "adjust": "balanced"},
               "update": {"mode": "continuous"}})
    rows = []
    for d in range(1, 29):
        rows.append(row(f"u{d}", A, 0.3 if d < 15 else 0.8, day=d))   # improved (a new version)
        rows.append(row(f"v{d}", B, 0.6, day=d))                      # steady
    hi["HI/play"] = rows
    out = boards.board("HI", None, {}, n_boot=0, now=datetime(2027, 3, 29, tzinfo=timezone.utc))
    assert names(out) == [A, B]  # pooled, B would lead (0.6 > 0.53)
    a = out["entries"][0]
    assert a["rating"]["changes"] and a["rating"]["sd"] > 0
    assert a["values"]["utility"]["mean"] == pytest.approx(a["rating"]["mean"])
    assert any("continuous" in n for n in out["notes"]) and any("probable change" in n for n in out["notes"])
    set_board({"sort_options": ["utility"], "rules": {**RULES0, "adjust": "balanced"}})
    assert names(boards.board("HI", None, {}, n_boot=0)) == [B, A]


def test_board_block_checks_update(hi):
    assert boards.check_block({"update": "continuous"}) == []
    assert boards.check_block({"update": {"mode": "continuous", "method": "glicko"}})
    assert boards.check_block({"update": "sometimes"})
