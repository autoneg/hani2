"""A small seeded project for the leaderboard pages: five Assistants, a few dozen games, people and AI.

Run with ``HANI2_HOME`` set: ``python tests/e2e/board_seed.py`` (the e2e fixture does this after
``hani2 setup``, and the docs' screenshots use it too). Each game is a placeholder recording plus the
evaluation-cache entry a finished game would have (:mod:`hani2.evaluation.eval_cache`), so boards read
it without evaluating anything.

* ``LB`` (HI, 2027): studies ``play`` (Mixed: AI games and Paired matches) and ``lab`` (Solo).
  The project board is **public**, sorts by ``utility`` (default), ``hi_team`` or ``agreement``
  (each has another leader), offers the ``games`` and ``stratum`` switches but **not** ``window``,
  and ranks entrants with at least 5 games by 3 players (Ember has 3 games: not ranked yet).
* ``LB/play``'s own board is for signed-in **participants**; ``LB/lab``'s is for **admins** only.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone

from hani2 import projects
from hani2.evaluation import eval_cache
from hani2.projects import StudyRef

PROJECT = "LB"
ASSISTANTS = {  # spec, entrant id, strengths (utility, hi_team, agreement)
    "Aurora": ("team_aurora.assistant:Aurora", "sub_aurora", (0.92, 0.55, 0.85)),
    "Birch": ("team_birch.assistant:Birch", "sub_birch", (0.62, 0.95, 0.80)),
    "Cobalt": ("team_cobalt.assistant:Cobalt", "sub_cobalt", (0.45, 0.50, 1.00)),
    "Delta": ("team_delta.assistant:Delta", "sub_delta", (0.40, 0.35, 0.55)),
    "Ember": ("team_ember.assistant:Ember", "sub_ember", (0.70, 0.70, 0.90)),
}
BOARD = {
    "track": "hi",
    "studies": ["play", "lab"],
    "sort_options": ["utility", "hi_team", "agreement"],
    "default_sort": "utility",
    "columns": ["utility", "hi_team", "agreement", "games", "participants"],
    "user_options": {"games": ["all", "people", "ai"], "stratum": ["combined", "solo", "paired"]},
    "defaults": {"games": "all", "stratum": "combined"},
    "visibility": "public",
    "rules": {"min_games": 5, "min_participants": 3, "adjust": "relative", "ci": 0.95},
}


def _row(rng, user, name, *, day, scenario, opponent, **kw):
    spec, entrant, (u, t, a) = ASSISTANTS[name]
    deal = rng.random() < a
    adv = max(0.0, min(1.0, rng.gauss(u, 0.12))) if deal else 0.0
    return {
        "id": "", "user": user, "scenario": scenario, "scenario_type": scenario, "opponent": opponent,
        "support_agent": spec, "assistant": spec, "assistant_entrant": entrant, "status": "success",
        "agreement": 1.0 if deal else 0.0, "human_advantage": adv,
        "welfare_optimality": max(0.0, min(1.0, rng.gauss(t, 0.1))) if deal else 0.0,
        "irrational_accept": 1.0 if rng.random() > t else 0.0, "always_follows": max(0.0, min(1.0, rng.gauss(1 - t, 0.1))),
        "started": (datetime.now(timezone.utc) - timedelta(days=day, hours=rng.randint(0, 20))).isoformat(),
        "practice": False, "counted": True, "mode": None, "own_assistant": False, **kw,
    }


def _write(ref: StudyRef, rows: list[dict]) -> None:
    root = eval_cache.results_dir(ref)
    for i, r in enumerate(rows):
        rid = f"{ref.study}-{i:03d}"
        r["id"] = rid
        d = root / r["user"]
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{rid}.hrec"
        f.write_bytes(b"placeholder recording for the seeded leaderboard\n")
        eval_cache._write_entry(ref, rid, {"version": eval_cache.VERSION, "id": rid, "recording": f"{r['user']}/{f.name}",
                                           "file": f.name, "size": f.stat().st_size, "complete": True, "row": r,
                                           "errors": [], "judged": {}, "updated": r["started"]})


def seed() -> None:
    rng = random.Random(7)
    projects.create_project(PROJECT, kind="assistant", year=2027)
    pf = projects.project_dir(PROJECT) / projects.PROJECT_FILE
    d = projects.read_yaml(pf)
    d.update(full_name="Demo league 2027", leaderboard=BOARD)
    projects.write_yaml(pf, d)
    for study, block in (("play", {"visibility": "participants"}), ("lab", {"visibility": "admins"})):
        ref = StudyRef(PROJECT, study)
        projects.create_study(ref, type="online")
        sf = projects.study_dir(ref) / projects.STUDY_FILE
        s = projects.read_yaml(sf)
        s.update(leaderboard=block, study_mode="mixed" if study == "play" else "solo")
        projects.write_yaml(sf, s)
    scenarios, opponents = ["Trade", "Job", "Supplier"], ["Boulware", "Conceder", "Linear"]
    play: list[dict] = []
    lab: list[dict] = []
    n = 0
    for name in ("Aurora", "Birch", "Cobalt", "Delta"):  # AI games: 10 each, by 6 people
        for k in range(10):
            n += 1
            row = _row(rng, f"p{(n % 14) + 1:02d}", name, day=rng.randint(0, 50), scenario=scenarios[k % 3],
                       opponent=opponents[(k + n) % 3], opponent_kind="agent", study_mode="mixed")
            (play if k % 2 else lab).append(row)
    names = ["Aurora", "Birch", "Cobalt", "Delta"]
    for m in range(14):  # Paired matches: two rows each, two people with their own Assistants
        a, b = rng.sample(names, 2)
        ua, ub = f"p{rng.randint(1, 14):02d}", f"q{rng.randint(1, 14):02d}"
        common = dict(match_id=f"m{m:02d}", opponent_kind="human+assistant", study_mode="paired",
                      opponent="human", pairing="cells")
        day, scen = rng.randint(0, 50), scenarios[m % 3]
        play.append(_row(rng, ua, a, day=day, scenario=scen, side=0, opponent_user=ub, **common))
        play.append(_row(rng, ub, b, day=day, scenario=scen, side=1, opponent_user=ua, **common))
    for k in range(3):  # Ember: too few games to be ranked
        play.append(_row(rng, f"e{k}", "Ember", day=3, scenario=scenarios[k], opponent="Boulware", opponent_kind="agent",
                         study_mode="mixed"))
    _write(StudyRef(PROJECT, "play"), play)
    _write(StudyRef(PROJECT, "lab"), lab)
    print(json.dumps({"project": PROJECT, "games": len(play) + len(lab)}))


if __name__ == "__main__":
    seed()
