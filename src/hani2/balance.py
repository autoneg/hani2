"""How balanced a study's assignment came out: ``hani2 study balance <project>/<study>``.

The report is built from what actually happened (each participant's ``results.csv``) and from the
plans kept in ``assignments.json``. Its Solo part covers one human per negotiation:

* totals per Assistant and per opponent (counted negotiations);
* Assistant × position (the counted negotiation 1, 2, …);
* pair co-occurrence: how many humans used both Assistants of a pair;
* the crossing: Assistant × opponent, and Assistant × scenario type;
* humans who got one Assistant more than once, humans who completed all K;
* the crossing rule each human was given (``cross``) and the warnings about the files.

Only the counted humans are included: the people in ``assignments.json`` (not admins, playground
sessions or simulated participants).

A negotiation is *counted* by the same rule as a Prolific study: not a practice round, and with at
least one action by the human (or an opponent that failed). :func:`study_balance` returns a plain
dict (``--json``); :func:`render` turns it into text.
"""

from __future__ import annotations

import csv
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Any

from hani2 import assignment, projects, scheduling

#: the result rows of human-opponent negotiations; the Solo tables leave them out
_HUMAN_KINDS = ("human", "human+assistant")


def _truthy(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "t", "1.0")


def counted_row(row: dict[str, Any]) -> bool:
    """Whether a result row is a counted negotiation (the rule of ``ProlificStudy.counted``)."""
    if _truthy(row.get("practice")):
        return False
    if row.get("status") == "agent_failed":
        return True
    try:
        return int(float(row.get("n_human_actions") or 0)) > 0
    except ValueError:
        return True


def _rows(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open(newline="", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except (OSError, csv.Error):
        return []


def _simulated(user: str, rows: list[dict[str, Any]]) -> bool:
    return user.startswith(("sim_", "guest_")) or any(str(r.get("mode") or "") == "simulated" for r in rows)


def _spread(values: list[int]) -> int:
    return (max(values) - min(values)) if values else 0


def _pool(ref: projects.StudyRef) -> list[str]:
    from hani2 import groups

    raw = projects.setting("assistants", None, ref=ref)
    if raw is None:
        return []
    try:
        with projects.use_study(ref):
            return groups.expand_assistants(raw, ref)
    except Exception:  # noqa: BLE001
        return []


def study_balance(ref: "projects.StudyRef | str") -> dict[str, Any]:
    """The Solo balance report of study ``ref`` as a dict (see the module docs)."""
    from hani2.config import results_root

    r = projects.parse_ref(ref) if isinstance(ref, str) else ref
    if r is None:
        raise ValueError("a study is needed (project/study)")
    methods, explicit, errors = scheduling.resolve(r)
    options = scheduling.options_for(r)
    k = int(projects.setting("n_required", 5, env="PROLIFIC_N_REQUIRED", cast=int, ref=r) or 5)
    data = assignment.read_assignments(r)
    with projects.use_study(r):
        root = results_root()
    # the counted humans are the ones assignments.json knows (a study from before it existed: everyone)
    counted_humans = set(data.get("humans", {}))
    people: dict[str, list[dict[str, Any]]] = {}
    paired_rows = 0
    if root.is_dir():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            rows = _rows(d / "results.csv")
            if not rows or _simulated(d.name, rows):
                continue
            if counted_humans and d.name not in counted_humans:
                continue  # admins, playground sessions: never assigned, never counted
            counted = [x for x in rows if counted_row(x)]
            solo = [x for x in counted if str(x.get("opponent_kind") or "agent") not in _HUMAN_KINDS]
            paired_rows += len(counted) - len(solo)
            if counted:
                people[d.name] = solo
    pool = _pool(r)
    totals: Counter = Counter()
    opp_totals: Counter = Counter()
    positions: dict[str, Counter] = {}
    pairs: Counter = Counter()
    crossing: dict[str, Counter] = {}
    scen: dict[str, Counter] = {}
    repeats: dict[str, list[str]] = {}
    for user, rows in people.items():
        used = []
        for pos, row in enumerate(rows):
            a = str(row.get("assistant") or "") or "(none)"
            o = str(row.get("agent_type") or "")
            t = str(row.get("scenario_type") or "")
            used.append(a)
            totals[a] += 1
            opp_totals[o] += 1
            positions.setdefault(a, Counter())[pos] += 1
            crossing.setdefault(a, Counter())[o] += 1
            scen.setdefault(a, Counter())[t] += 1
        twice = sorted(a for a, n in Counter(used).items() if n > 1)
        if twice:
            repeats[user] = twice
        for x, y in combinations(sorted(set(used)), 2):
            pairs[(x, y)] += 1
    assistants = sorted(set(pool) | set(totals), key=lambda a: (a not in pool, pool.index(a) if a in pool else 0, a))
    opponents = sorted(opp_totals)
    types = sorted({t for c in scen.values() for t in c})
    width = max([k] + [max(c) + 1 for c in positions.values() if c])
    humans = data.get("humans", {})
    pos_table = {a: [positions.get(a, Counter())[p] for p in range(width)] for a in assistants}
    cross_table = {a: {o: crossing.get(a, Counter())[o] for o in opponents} for a in assistants}
    pair_list = [{"a": x, "b": y, "n": pairs[(x, y)]} for x, y in combinations(assistants, 2)]
    return {
        "study": str(r),
        "methods": methods,
        "explicit": explicit,
        "options": options,
        "k": k,
        "assistants": assistants,
        "assistant_pool": pool,
        "opponents": opponents,
        "scenario_types": types,
        "participants": len(people),
        "completed": sum(1 for rows in people.values() if len(rows) >= k),
        "negotiations": sum(totals.values()),
        "paired_negotiations": paired_rows,
        "totals": {a: totals[a] for a in assistants},
        "opponent_totals": {o: opp_totals[o] for o in opponents},
        "positions": pos_table,
        "pairs": pair_list,
        "crossing": cross_table,
        "scenarios": {a: {t: scen.get(a, Counter())[t] for t in types} for a in assistants},
        "spread": {
            "totals": _spread([totals[a] for a in assistants]),
            "positions": _spread([n for row in pos_table.values() for n in row[:k]]),
            "pairs": _spread([p["n"] for p in pair_list]),
            "crossing": _spread([n for row in cross_table.values() for n in row.values()]),
        },
        "repeats": repeats,
        "cross_rules": dict(Counter(str(h.get("cross") or "none") for h in humans.values())),
        "plans": sum(1 for h in humans.values() if isinstance(h.get("assistant_plan"), list)),
        "warnings": list(dict.fromkeys([*errors, *scheduling.study_repeat_problems(r)])),
    }


def _short(spec: str) -> str:
    """A spec's class name (``pkg.mod:Class`` → ``Class``) for narrow tables."""
    return str(spec).split(":")[-1].split(".")[-1] or str(spec)


def _grid(title: str, rows: list[str], cols: list[str], cell) -> list[str]:
    if not rows or not cols:
        return []
    names = [_short(x) for x in rows]
    heads = [_short(c) for c in cols]
    w0 = max(len(n) for n in names + [""])
    ws = [max(len(h), 3) for h in heads]
    out = [title, "  " + " " * w0 + "  " + "  ".join(h.rjust(w) for h, w in zip(heads, ws))]
    for name, row in zip(names, rows):
        out.append("  " + name.ljust(w0) + "  " + "  ".join(str(cell(row, c)).rjust(w) for c, w in zip(cols, ws)))
    return out


def render(rep: dict[str, Any]) -> str:
    """The report as text (``hani2 study balance``)."""
    m = rep["methods"]
    lines = [f"Study {rep['study']}: Solo balance",
             f"  methods: assistants {m['assistants']}, opponents {m['opponents']}, scenarios {m['scenarios']}"
             f"; cross: {rep['options'].get('cross', scheduling.CROSS_DEFAULT + ' (default)')}"
             f"; assistant_repeats: {rep['options'].get('assistant_repeats', 'unset')}",
             f"  K = {rep['k']} counted negotiations per person; N = {len(rep['assistant_pool']) or '?'} Assistants",
             f"  participants: {rep['participants']} ({rep['completed']} completed all {rep['k']}); "
             f"Solo negotiations: {rep['negotiations']}"
             + (f"; with a person: {rep['paired_negotiations']} (not in these tables)" if rep["paired_negotiations"] else ""),
             "  crossing rule of the people in assignments.json: "
             + (", ".join(f"{k} {v}" for k, v in sorted(rep["cross_rules"].items())) or "-")
             + (f"; stored Assistant plans: {rep['plans']}" if rep["plans"] else "")]
    for w in rep["warnings"]:
        lines.append(f"  WARNING: {w}")
    if not rep["negotiations"]:
        lines.append("  (no counted Solo negotiations yet)")
        return "\n".join(lines)
    sp = rep["spread"]
    lines.append("")
    lines += _grid(f"Totals per Assistant (spread {sp['totals']})", rep["assistants"], ["n"],
                   lambda a, _c: rep["totals"][a])
    lines.append("")
    k = rep["k"]
    cols = [str(p + 1) for p in range(len(next(iter(rep["positions"].values()), [])))]
    lines += _grid(f"Assistant x position (spread over positions 1..{k}: {sp['positions']})", rep["assistants"], cols,
                   lambda a, c: rep["positions"][a][int(c) - 1])
    if len(rep["assistants"]) > 1:
        lines.append("")
        pairs = {(p["a"], p["b"]): p["n"] for p in rep["pairs"]}
        lines += _grid(f"Pair co-occurrence: people who used both (spread {sp['pairs']})", rep["assistants"],
                       rep["assistants"],
                       lambda a, b: "-" if a == b else pairs.get((a, b), pairs.get((b, a), 0)))
    lines.append("")
    lines += _grid(f"Assistant x opponent (spread {sp['crossing']})", rep["assistants"], rep["opponents"],
                   lambda a, o: rep["crossing"][a][o])
    if len(rep["scenario_types"]) > 1:
        lines.append("")
        lines += _grid("Assistant x scenario type", rep["assistants"], rep["scenario_types"],
                       lambda a, t: rep["scenarios"][a][t])
    if rep["repeats"]:
        lines.append("")
        lines.append(f"People who got one Assistant more than once: {len(rep['repeats'])}")
        for u, a in sorted(rep["repeats"].items()):
            lines.append(f"  {u}: {', '.join(_short(x) for x in a)}")
    return "\n".join(lines)
