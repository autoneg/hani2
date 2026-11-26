#!/usr/bin/env python3
"""Generate a pool of scenarios, optionally with cached utility inverses.

This is a self-contained scenario-pool generator. It depends only on
the built-in scenario makers and negmas -- never on any external project. Each slot is
written as a negmas ``Scenario`` directory (``<Type>.yml`` + per-role ufuns +
``_info.yml``) under ``<base>/<Type>/NNNN<Type>/``, which is exactly what the server
loads at serve time.

When ``--cache-inverter`` is on (the default), an initialised inverse of the
served human ufun is pickled next to each scenario as ``inverter_h<idx>.pkl`` so
the Utility-based Selector starts instantly instead of recomputing. The cache
is purely an optimisation: it is validated against the live ufun on load and
recomputes on any mismatch or load failure, so a missing/stale pickle is always
safe (see ``hani2.tools.builtin.UtilitySelectorTool``).

CLI::

    hani2 generate                       # all types x50 into the default pool
    hani2 generate --type Trade -n 20    # 20 Trade scenarios
    hani2 generate --no-cache-inverter   # skip the inverse pickles
    hani2 generate --rebuild-inverses    # only (re)write inverses for existing scenarios
"""
from __future__ import annotations

import pickle
import random
import time
from pathlib import Path
from typing import Annotated, Optional

import typer
from negmas import opposition_level
from negmas.inout import Scenario

from hani2.config import scenarios_dir  # noqa: F401 - kept for callers importing it from here
from hani2.scenarios import registry

app = typer.Typer(add_completion=False)

#: ``{type: maker}`` of every registered generator (a live view of the registry).
MAKER_MAP = registry.MAKERS

# The participant is negotiator 1 by default (the server default).
DEFAULT_HUMAN_INDEX = 1
DEFAULT_COUNT = 50
# Opposition band: ~0 means a win-win exists (little to negotiate over), higher
# means genuine tradeoffs. Keep real-but-not-hopeless conflict in every slot.
DEFAULT_MIN_OPPOSITION = 0.35
DEFAULT_MAX_OPPOSITION = 0.90
# Small disagreement (reservation) values, on the ufuns' normalized [0,1] scale.
DEFAULT_USER_RESERVED_MAX = 0.10
DEFAULT_AGENT_RESERVED_MAX = 0.20
DEFAULT_MAX_TRIES = 60


def inverter_filename(human_index: int) -> str:
    return f"inverter_h{human_index}.pkl"


def scenario_opposition(scenario: Scenario) -> float:
    """opposition_level of a scenario's (normalized) ufuns."""
    n = len(scenario.ufuns)
    return float(
        opposition_level(
            scenario.ufuns,
            outcome_space=scenario.outcome_space,
            max_utils=tuple(1.0 for _ in range(n)),
        )
    )


def set_reservation_values(scenario: Scenario, human_index: int, rng: random.Random,
                           user_max: float, agent_max: float, simple: bool = False) -> tuple[float, float]:
    """Set small disagreement values on the ufuns' [0,1] scale: the human at or
    below ``user_max``, every other (agent) negotiator at or below ``agent_max``
    (``simple``: rounded to 5%). Returns (human_reserved, agent_reserved)."""
    human_r = round(rng.uniform(0.0, user_max), 4)
    agent_r = round(rng.uniform(0.0, agent_max), 4)
    if simple:
        from hani2.scenarios.simple import snap_reserved

        human_r, agent_r = snap_reserved(human_r), snap_reserved(agent_r)
    for i, uf in enumerate(scenario.ufuns):
        try:
            uf.reserved_value = human_r if i == human_index else agent_r
        except Exception:
            pass
    return human_r, agent_r


def slot_seed(seed: int | str, scenario_type: str, slot: int) -> str:
    """The seed of one pool slot: the same ``(seed, type, slot)`` always gives
    the same scenario, whatever other slots or types are generated."""
    return f"{seed}:{scenario_type}:{slot}"


def make_in_band(scenario_type: str, slot: int,
                 min_opp: float, max_opp: float, max_tries: int, seed: int | str | None = None,
                 simple: bool = False):
    """Draw scenarios from the (random) maker until opposition_level falls in
    [min_opp, max_opp]. Returns (scenario, opposition, tries). Raises after
    max_tries with the closest-to-band attempt so we never write nothing.

    With ``seed`` the draws are reproducible: Python's random generator (which
    every built-in maker uses) is seeded from :func:`slot_seed` first. ``simple``
    generates simple scenarios (see :mod:`hani2.scenarios.simple`)."""
    if seed is None:
        return _make_in_band(scenario_type, slot, min_opp, max_opp, max_tries, simple)
    state = random.getstate()
    random.seed(slot_seed(seed, scenario_type, slot))
    try:
        return _make_in_band(scenario_type, slot, min_opp, max_opp, max_tries, simple)
    finally:
        random.setstate(state)


def _make_in_band(scenario_type: str, slot: int, min_opp: float, max_opp: float, max_tries: int,
                  simple: bool = False):
    from hani2.scenario_store import make_scenario

    best = None  # (distance_outside_band, scenario, opp)
    for attempt in range(1, max_tries + 1):
        scenario = make_scenario(scenario_type, slot, simple)
        opp = scenario_opposition(scenario)
        if min_opp <= opp <= max_opp:
            return scenario, opp, attempt
        dist = (min_opp - opp) if opp < min_opp else (opp - max_opp)
        if best is None or dist < best[0]:
            best = (dist, scenario, opp)
    assert best is not None
    raise RuntimeError(
        f"no in-band scenario after {max_tries} tries "
        f"(closest opp={best[2]:.3f}, band=[{min_opp},{max_opp}])"
    )


def write_inverter(out_dir: Path, human_index: int) -> str:
    """Pickle the initialised inverse of the *served* human ufun next to a
    scenario dir, returning a short status note.

    CRITICAL: invert the ufun exactly as the server will serve it -- reloaded from
    disk -- not an in-memory one. ``Scenario.load()`` can reorder ufuns by role
    name (e.g. Trade comes back ``[Buyer, Seller]`` although make_trade_scenario
    builds them ``[Seller, Buyer]``), so an in-memory ``ufuns[human_index]`` is a
    *different* negotiator than the reloaded ``ufuns[human_index]`` the
    participant gets. Inverting the in-memory ufun pickles the WRONG negotiator's
    inverse, which makes the Utility-based Selector return outcomes outside the
    requested range. ``.init()`` forces the presort so the pickle is
    ready-to-query. The inverse is an optimisation, never a dependency, so we
    never raise."""
    inv_path = out_dir / inverter_filename(human_index)
    try:
        served = Scenario.load(out_dir)
        if served is None:
            raise ValueError(f"could not reload scenario from {out_dir}")
        inverter = served.ufuns[human_index].invert()
        if hasattr(inverter, "init"):
            inverter.init()
        with inv_path.open("wb") as fh:
            pickle.dump(inverter, fh, protocol=pickle.HIGHEST_PROTOCOL)
        return f"+inv({inv_path.stat().st_size}B)"
    except Exception as e:  # never fail generation over the optional cache
        return f"+inv FAILED: {e!r}"


def generate_one(scenario_type: str, index: int, type_dir: Path, human_index: int,
                 force: bool, cache_inverter: bool, rng: random.Random,
                 min_opp: float, max_opp: float, set_reservations: bool,
                 user_max: float, agent_max: float, max_tries: int,
                 seed: int | str | None = None, simple: bool = False) -> tuple[bool, str]:
    """Generate (or skip) one scenario directory, optionally caching its inverse.

    Returns (wrote, message)."""
    out_dir = type_dir / f"{index:04d}{scenario_type}"
    scenario_yml = out_dir / f"{scenario_type}.yml"
    inv_path = out_dir / inverter_filename(human_index)

    # Idempotency: a complete slot is left alone unless --force. "Complete" means
    # the scenario yml exists, and (only when caching) the inverse exists too --
    # so --no-cache-inverter still skips already-generated scenarios.
    if not force and scenario_yml.is_file() and (not cache_inverter or inv_path.is_file()):
        return False, f"skip {out_dir.name} (exists)"

    scenario, opp, tries = make_in_band(
        scenario_type, index, min_opp, max_opp, max_tries, seed, simple
    )
    if seed is not None:
        rng = random.Random(slot_seed(seed, scenario_type, index) + ":reserved")
    res_note = ""
    if set_reservations:
        # the participant's side under the default role rule (a role named
        # human, the story's suggested role, else --human-index)
        from hani2.scenario_store import assign_human

        human_r, agent_r = set_reservation_values(
            scenario, assign_human(scenario, "auto", human_index), rng, user_max, agent_max, simple
        )
        res_note = f" res h={human_r}/a={agent_r}"
    # <Type>.yml / per-role ufuns / _info.yml, including the reservation values we just set
    from hani2.scenario_store import save_scenario

    save_scenario(scenario, out_dir)

    # Cache the inverse for every role: the role-assignment rule decides at
    # serve time which one the participant plays.
    inv_note = (" ".join(write_inverter(out_dir, i) for i in range(len(scenario.ufuns)))
                if cache_inverter else "")

    card = scenario.outcome_space.cardinality
    return True, (f"wrote {out_dir.name} (card={card} opp={opp:.3f}{res_note} "
                  f"tries={tries}) {inv_note}".rstrip())


def rebuild_inverses(base: Path, types: list[str], count: int,
                     human_index: int) -> tuple[int, int]:
    """Rewrite the cached inverse next to every *existing* scenario without
    regenerating the scenarios themselves. Repairs a pool whose pickles were
    cached from a mis-ordered in-memory ufun (see write_inverter). Returns
    (rebuilt, missing)."""
    rebuilt = missing = 0
    for scenario_type in types:
        type_dir = base / scenario_type
        for index in range(count):
            out_dir = type_dir / f"{index:04d}{scenario_type}"
            if not (out_dir / f"{scenario_type}.yml").is_file():
                missing += 1
                continue
            note = write_inverter(out_dir, human_index)
            rebuilt += 1
            if "FAILED" in note or index % 10 == 0 or index == count - 1:
                print(f"  [{scenario_type}] rebuilt {out_dir.name} {note}")
        print(f"  {scenario_type}: rebuilt inverses -> {type_dir}")
    return rebuilt, missing


@app.command()
def generate(
    types: Annotated[Optional[list[str]], typer.Option(
        "--type", "-t",
        help="Scenario type(s) to generate (repeatable). Default: the types of the "
        "active scenario set (see --set).")] = None,
    count: Annotated[int, typer.Option(
        "-n", "--count", help="Scenarios per type")] = DEFAULT_COUNT,
    base: Annotated[Optional[Path], typer.Option(
        help="Base directory for the pool (default: the scenarios directory)")] = None,
    human_index: Annotated[int, typer.Option(
        help="Negotiator index whose inverse to cache")] = DEFAULT_HUMAN_INDEX,
    cache_inverter: Annotated[bool, typer.Option(
        "--cache-inverter/--no-cache-inverter",
        help="Pickle the served human ufun's inverse next to each scenario "
        "(an optimisation that is validated and can always be recomputed).")] = True,
    rebuild_inverses_only: Annotated[bool, typer.Option(
        "--rebuild-inverses",
        help="Do NOT regenerate scenarios; only (re)write the cached inverse "
        "next to every existing scenario, from the served (reloaded) ufun.")] = False,
    min_opposition: Annotated[float, typer.Option(
        help="Reject scenarios below this opposition_level")] = DEFAULT_MIN_OPPOSITION,
    max_opposition: Annotated[float, typer.Option(
        help="Reject scenarios above this opposition_level")] = DEFAULT_MAX_OPPOSITION,
    set_reservations: Annotated[bool, typer.Option(
        "--set-reservations/--no-set-reservations",
        help="Override ufun reservation values with small random ones")] = True,
    user_reserved_max: Annotated[float, typer.Option(
        help="Max human reservation value, [0,1] scale")] = DEFAULT_USER_RESERVED_MAX,
    agent_reserved_max: Annotated[float, typer.Option(
        help="Max agent reservation value, [0,1] scale")] = DEFAULT_AGENT_RESERVED_MAX,
    max_tries: Annotated[int, typer.Option(
        help="Max maker draws per slot to hit the opposition band")] = DEFAULT_MAX_TRIES,
    seed: Annotated[int, typer.Option(
        help="Seed: the same seed, type and slot always give the same scenario (default 0)")] = 0,
    force: Annotated[bool, typer.Option(
        "--force", help="Regenerate even if the scenario dir already exists")] = False,
    scenario_set: Annotated[Optional[str], typer.Option(
        "--set", help="Generate the types of this scenario set (default: the active set).")] = None,
    simple: Annotated[Optional[bool], typer.Option(
        "--simple/--no-simple",
        help="Simple scenarios: round numbers, linear and symmetric preferences (default: the "
        "simple_scenarios setting of the current project/study, else of env.json; on unless switched off). Existing slots are "
        "kept unless --force.")] = None,
):
    """Generate a pool of scenarios, optionally with cached utility inverses."""
    from hani2 import scenario_sets

    registry.load_plugins()
    if types:
        chosen = list(types)
    else:
        if scenario_set and not scenario_sets.resolve(scenario_set):
            typer.echo(f"Unknown scenario set {scenario_set!r}. Available: {scenario_sets.set_names()}")
            raise typer.Exit(code=2)
        chosen = [t for t in scenario_sets.set_types(scenario_set) if t in MAKER_MAP]
    unknown = [t for t in chosen if t not in MAKER_MAP]
    if unknown:
        typer.echo(f"Unknown type(s): {unknown}. Available: {list(MAKER_MAP)}")
        raise typer.Exit(code=2)

    if base is None:
        from hani2.scenario_store import base_dir

        base = base_dir()
    base = base.expanduser()
    rng = random.Random(seed)
    print(f"Scenario base : {base}")
    print(f"Types         : {', '.join(chosen)}")
    print(f"Human index   : {human_index}")

    if rebuild_inverses_only:
        print("Mode          : rebuild inverses only (scenarios untouched)")
        print("-" * 60)
        t0 = time.perf_counter()
        rebuilt, missing = rebuild_inverses(base, chosen, count, human_index)
        print("-" * 60)
        print(f"Done in {time.perf_counter() - t0:.1f}s: rebuilt {rebuilt} "
              f"inverses, {missing} scenario slots missing")
        return

    print(f"Count/type    : {count}")
    print(f"Opposition    : [{min_opposition}, {max_opposition}]")
    print(f"Cache inverter: {cache_inverter}")
    print(f"Reservations  : {'set' if set_reservations else 'maker defaults'}"
          + (f" (user<={user_reserved_max} agent<={agent_reserved_max})"
             if set_reservations else ""))
    if simple is None:
        from hani2.scenario_store import simple_scenarios

        simple = simple_scenarios()
    print(f"Simple        : {simple}")
    print(f"Force rewrite : {force}")
    print("-" * 60)

    t0 = time.perf_counter()
    total_wrote = total_skip = total_err = 0
    for scenario_type in chosen:
        type_dir = base / scenario_type
        type_dir.mkdir(parents=True, exist_ok=True)
        wrote = skip = 0
        for i in range(count):
            try:
                did_write, msg = generate_one(
                    scenario_type, i, type_dir, human_index, force, cache_inverter,
                    rng, min_opposition, max_opposition, set_reservations,
                    user_reserved_max, agent_reserved_max, max_tries, seed, bool(simple),
                )
            except Exception as e:
                total_err += 1
                print(f"  [{scenario_type} {i:04d}] ERROR: {e!r}")
                continue
            if did_write:
                wrote += 1
                if "FAILED" in msg:
                    total_err += 1
            else:
                skip += 1
            if did_write and (i % 10 == 0 or i == count - 1):
                print(f"  [{scenario_type}] {msg}")
        total_wrote += wrote
        total_skip += skip
        print(f"  {scenario_type}: wrote {wrote}, skipped {skip} -> {type_dir}")

    dt = time.perf_counter() - t0
    print("-" * 60)
    print(f"Done in {dt:.1f}s: wrote {total_wrote}, skipped {total_skip}, "
          f"errors {total_err}")
    if total_err:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
