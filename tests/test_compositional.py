"""Compositional scenarios: factors, balanced sampling, composition, verification, the bluffing
opponent, running a pool and the per-factor report."""

import copy
from collections import Counter
from itertools import combinations

import numpy as np
import pytest
from negmas import SAOMechanism, opposition_level

from hani2.compositional import (FACTORS, Cell, all_cells, compose, factor_report, format_report, generate_pool,
                                 parse_levels, pool_scenarios, run_pool, sample_cells, verify)
from hani2.helpers.deceptive import DeceptiveTBNegotiator, HonestTBNegotiator
from hani2.scenario_store import _load_dir, assign_human


def test_factor_catalog_and_level_parsing():
    assert {f.kind for f in FACTORS.values()} == {"scenario", "episode"}
    assert parse_levels(["issues=2,4", "zopa=narrow"]) == {"issues": ["2", "4"], "zopa": ["narrow"]}
    with pytest.raises(ValueError):
        parse_levels(["colour=red"])
    with pytest.raises(ValueError):
        parse_levels(["zopa=huge"])
    assert len(all_cells()) == np.prod([len(f.levels) for f in FACTORS.values()])


def test_sampling_is_balanced_over_levels_and_pairs():
    cells = sample_cells(48, seed=3)
    assert len(cells) == len(set(cells)) == 48
    for name, f in FACTORS.items():
        counts = Counter(c.get(name) for c in cells)
        assert set(counts) == set(f.levels) and max(counts.values()) - min(counts.values()) <= 1, (name, counts)
    pairs = Counter(p for c in cells for p in combinations(c.levels, 2))
    for a, b in combinations(FACTORS, 2):
        n = [pairs[((a, x), (b, y))] for x in FACTORS[a].levels for y in FACTORS[b].levels]
        assert max(n) - min(n) <= 4, (a, b, n)
    # whole copies of the factorial first
    full = sample_cells(2 * len(all_cells()), seed=0)
    assert set(Counter(full).values()) == {2}
    assert sample_cells(48, seed=3) == cells  # reproducible


def _utils(s):
    hi = assign_human(s, "auto", 1)
    outs = list(s.outcome_space.enumerate())
    return hi, outs, np.array([s.ufuns[hi](o) for o in outs]), np.array([s.ufuns[1 - hi](o) for o in outs])


def test_every_scenario_cell_composes_and_verifies():
    for cell in all_cells({"deception": ["honest"], "time_pressure": ["tight"]}):
        c = compose(cell, "t", seed=5)
        assert c.scenario is not None, (cell.code, c.error)
        v = verify(c.scenario)
        assert v.ok, (cell.code, v.problems)


def test_composition_is_reproducible_and_replicates_differ():
    cell = Cell.of(issues="4", opposition="high", zopa="narrow")
    a, b, c = compose(cell, "x", 1), compose(cell, "x", 1), compose(cell, "x", 1, replicate=1)
    ua, ub, uc = (_utils(x.scenario)[2] for x in (a, b, c))
    assert np.allclose(ua, ub) and not np.allclose(ua, uc)


def test_measured_factors_match_the_cell():
    cell = Cell.of(issues="2", opposition="low", zopa="narrow", constraint="none", time_pressure="tight",
                   deception="deceptive")
    s = compose(cell, "x", 0).scenario
    hi, outs, uh, uo = _utils(s)
    assert s.ufuns[hi].name == "Buyer" and len(s.outcome_space.issues) == 2
    # negmas' opposition level of the preferences alone (no reservation values: independent of the ZOPA)
    free = [copy.deepcopy(u) for u in s.ufuns]
    for u in free:
        u.reserved_value = float("-inf")
    opp = opposition_level(free, outcome_space=s.outcome_space, max_utils=(1.0, 1.0))
    assert abs(opp - s.info["composition"]["measured"]["opposition"]) < 1e-3
    assert FACTORS["opposition"].levels["low"][0] <= opp <= FACTORS["opposition"].levels["low"][1]
    zopa = (uh >= s.ufuns[hi].reserved_value) & (uo >= s.ufuns[1 - hi].reserved_value)
    lo, hi_ = FACTORS["zopa"].levels["narrow"]
    assert lo <= zopa.mean() <= hi_ and zopa.sum() >= 3
    comp = s.info["composition"]
    assert comp["episode"] == {"opponent": "helpers.DeceptiveTBNegotiator", "n_steps": 8}
    assert "8 rounds" in s.info["long_description"]
    # the target is the Nash point of the ZOPA
    t = tuple(comp["target"]["outcome"][i.name] for i in s.outcome_space.issues)
    assert t in [o for o, z in zip(outs, zopa) if z]


def test_hidden_constraint_bites_and_is_told_only_to_the_participant():
    cell = Cell.of(issues="4", opposition="medium", zopa="wide", constraint="hidden")
    s = compose(cell, "x", 2).scenario
    cons = s.info["composition"]["constraint"]
    hi, outs, uh, uo = _utils(s)
    j = [i.name for i in s.outcome_space.issues].index(cons["issue"])
    viol = np.array([o[j] == cons["value"] for o in outs])
    assert viol.any() and np.all(uh[viol] < s.ufuns[hi].reserved_value)
    assert viol[int(np.argmax(uo))]  # the opponent's ideal deal breaks it
    assert "Hard limit (private)" in s.info["hints"]["Buyer"]
    assert "Hard limit (private)" not in s.info["hints"]["Supplier"]


def test_verify_catches_a_broken_scenario():
    s = compose(Cell.of(zopa="narrow"), "x", 0).scenario
    s.ufuns[0].reserved_value = 0.0
    s.ufuns[1].reserved_value = 0.0
    v = verify(s)
    assert not v.ok and not v.checks["zopa"]
    s.info["composition"]["episode"]["opponent"] = "no.such.Negotiator"
    assert not verify(s).checks["episode"]


@pytest.mark.parametrize("cls", [HonestTBNegotiator, DeceptiveTBNegotiator])
def test_bluffing_opponent(cls):
    s = compose(Cell.of(issues="4", opposition="medium", zopa="wide"), "x", 0).scenario
    hi = assign_human(s, "auto", 1)
    m = SAOMechanism(outcome_space=s.outcome_space, n_steps=30)
    me = HonestTBNegotiator(name="me")
    opp = cls(name="opp")
    negs = [None, None]
    negs[hi], negs[1 - hi] = me, opp
    for n, u in zip(negs, s.ufuns):
        m.add(n, ufun=u)
    m.run()
    texts = [r[7] if len(r) > 7 else None for r in m.extended_trace] if hasattr(m, "extended_trace") else []
    texts = [t for t in texts if t] or [str(x) for x in m.full_trace]
    joined = " ".join(map(str, texts))
    weights = s.ufuns[1 - hi].weights
    names = [i.name for i in s.outcome_space.issues]
    top, bottom = names[int(np.argmax(weights))], names[int(np.argmin(weights))]
    if cls is DeceptiveTBNegotiator:
        assert f"{bottom} is what matters most" in joined and "final offer" in joined
    else:
        assert f"{top} is our most important issue" in joined and "final offer" not in joined
    if m.agreement is not None:  # it accepts only by its true utility
        assert s.ufuns[1 - hi](m.agreement) >= s.ufuns[1 - hi].reserved_value


def test_generate_run_and_report(hani2_home, tmp_path):
    m = generate_pool(tmp_path / "pool", 6, seed=4, log=lambda *a: None)
    assert len(m["scenarios"]) == 6 and not m["failed"]
    folder = tmp_path / "pool" / "Compositional"
    assert (folder / "_composition.json").exists() and len(pool_scenarios(folder)) == 6
    for p in pool_scenarios(folder):
        assert verify(_load_dir(p)).ok
    res = run_pool(folder, hani2_home, driver="ConcederTBNegotiator", timeout=60, log=lambda *a: None)
    assert len(res) == 6 and all(r["done"] for r in res)

    from hani2.evaluation import evaluate_paths

    rows = evaluate_paths([hani2_home], metrics=["outcome", "factors"])["rows"]
    assert len(rows) == 6
    by_name = {e["name"]: e for e in m["scenarios"]}
    assert all(e["measured"] for e in m["scenarios"])
    for r in rows:
        cell = by_name[r["scenario"]]["cell"]
        assert all(r[f"factor_{k}"] == v for k, v in cell.items()), (r, cell)
        assert r["target_attainment"] is not None
        assert r["agreement"] == 0 or r["target_attainment"] > -1e-9  # the baseline never accepts below its reservation
        assert (r.get("constraint_violated") is None) == (cell["constraint"] == "none")
    rep = factor_report(rows)
    g = rep["groups"]["all"]
    assert g["n"] == 6 and set(g["factors"]) == set(FACTORS)
    assert sorted(g["ranking"]) == sorted(k for k in FACTORS if g["factors"][k]["effects"])
    text = format_report(rep)
    assert "Target attainment" in text and "Where it fails" in text

    from typer.testing import CliRunner

    from hani2.cli import app

    out = CliRunner().invoke(app, ["compose", "report", str(hani2_home), "-o", str(tmp_path / "r.json")])
    assert out.exit_code == 0, out.output
    assert "Target attainment" in out.output and (tmp_path / "r.json").exists()
    out = CliRunner().invoke(app, ["compose", "verify", str(folder)])
    assert out.exit_code == 0 and "6/6 verified" in out.output


def test_generate_refuses_to_mix_pools(tmp_path):
    generate_pool(tmp_path, 2, seed=0, log=lambda *a: None)
    with pytest.raises(FileExistsError):
        generate_pool(tmp_path, 2, seed=1, log=lambda *a: None)
    m = generate_pool(tmp_path, 3, seed=1, force=True, log=lambda *a: None)
    assert len(pool_scenarios(tmp_path / "Compositional")) == 3 == len(m["scenarios"])
    # names are opaque: the browser shows them, so they must not give the cell away
    assert all(e["name"].endswith("Compositional") and "deceptive" not in e["name"] for e in m["scenarios"])


def test_target_is_reached_in_play_even_under_time_pressure():
    for cell in all_cells({"zopa": ["narrow"], "time_pressure": ["tight"], "issues": ["6"]}):
        v = verify(compose(cell, "x", 3).scenario)
        assert v.checks["target_reached_in_play"], cell.code


def test_assistant_driver_runs_a_pool(hani2_home, tmp_path, scripted):
    generate_pool(tmp_path / "pool", 1, levels={"time_pressure": ["tight"]}, seed=0, log=lambda *a: None)
    scripted(*([("submit_counter_offer", {"message": "auto"})] * 40))
    res = run_pool(tmp_path / "pool" / "Compositional", hani2_home, driver="Assistant", timeout=60,
                   log=lambda *a: None)
    assert len(res) == 1 and res[0]["done"]
    from hani2.evaluation import evaluate_paths

    rows = evaluate_paths([hani2_home], metrics=["outcome", "factors"])["rows"]
    assert len(rows) == 1 and rows[0]["factor_time_pressure"] == "tight"


def test_factors_metric_constraint_violation():
    from types import SimpleNamespace

    from hani2.evaluation.factors import factors

    comp = {"cell": Cell.of(constraint="hidden").as_dict(), "target": {"human_utility": 0.6},
            "constraint": {"issue": "Price", "value": 120}}
    ctx = SimpleNamespace(scenario={"info": {"composition": comp}, "issue_names": ["Price", "Delivery"]},
                          rec=SimpleNamespace(start={"opponent": "DeceptiveTBNegotiator", "n_steps": 12}),
                          agreement=[120, 4], point_of=lambda a: np.array([-0.3, 0.9]),
                          disagreement=np.array([0.2, 0.1]), has_scenario=True, summary={})
    row = factors(ctx, {})
    assert row["constraint_violated"] == 1 and row["reached_target"] == 0
    assert row["target_attainment"] == pytest.approx((-0.3 - 0.2) / (0.6 - 0.2))
    assert row["factor_deception"] == "deceptive" and row["factor_time_pressure"] == "steps=12"
    ctx.agreement = {"Price": 100, "Delivery": 4}
    assert factors(ctx, {})["constraint_violated"] == 0


def test_report_names_only_reliable_failures():
    rows = []
    for i in range(20):
        cell = sample_cells(20, seed=0)[i].as_dict()
        att = 1.0 - (0.8 if cell["zopa"] == "narrow" else 0.0) + 0.01 * (i % 3)
        rows.append({**{f"factor_{k}": v for k, v in cell.items()}, "target_attainment": att, "agreement": 1})
    rep = factor_report(rows)["groups"]["all"]
    assert rep["failures"] == ["zopa"] and rep["ranking"][0] == "zopa"
    assert "**zopa**" in format_report(factor_report(rows))
