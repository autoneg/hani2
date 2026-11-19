"""``hani2 compose``: compositional scenarios built from difficulty factors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

compose_app = typer.Typer(add_completion=False, no_args_is_help=True,
                          help="Compositional scenarios: generate a balanced, verified set from difficulty factors, "
                               "play it and report scores per factor.")

LevelOpt = Annotated[Optional[list[str]], typer.Option(
    "--factor", "-f", help="Restrict a factor's levels, e.g. -f issues=2,4 -f zopa=narrow (repeatable).")]


def _levels(specs):
    from hani2.compositional import parse_levels

    try:
        return parse_levels(specs)
    except ValueError as e:
        typer.echo(str(e))
        raise typer.Exit(code=2)


@compose_app.command("factors")
def factors_cmd() -> None:
    """List the difficulty factors and their levels."""
    from hani2.compositional import FACTORS

    for f in FACTORS.values():
        typer.echo(f"{f.name} ({f.kind}): {f.title}")
        for lv, v in f.levels.items():
            typer.echo(f"    {lv:<10} {v}")
        typer.echo(f"    {f.description}\n")


@compose_app.command("generate")
def generate_cmd(
    count: Annotated[int, typer.Option("-n", "--count", help="Scenarios to generate")] = 48,
    base: Annotated[Optional[Path], typer.Option(help="Pool root (default: the scenarios directory)")] = None,
    category: Annotated[str, typer.Option(help="Category folder under the pool root")] = "Compositional",
    seed: Annotated[int, typer.Option(help="Seed: the same seed and options give the same pool")] = 0,
    factor: LevelOpt = None,
    force: Annotated[bool, typer.Option("--force", help="Remove the category's old scenarios first")] = False,
) -> None:
    """Generate a balanced set of verified scenarios (every level, and every pair of levels, about
    equally often). Cells that cannot be composed or fail verification are listed, not dropped silently."""
    from hani2.compositional import generate_pool

    if base is None:
        from hani2.scenario_store import base_dir

        base = base_dir()
    typer.echo(f"Pool: {Path(base).expanduser() / category}")
    try:
        m = generate_pool(base, count, _levels(factor), seed=seed, category=category, force=force, log=typer.echo)
    except FileExistsError as e:
        typer.echo(f"{e} — pass --force or --category.")
        raise typer.Exit(code=2)
    typer.echo(f"Done: {len(m['scenarios'])} scenarios, {len(m['failed'])} infeasible or failed.")
    if m["failed"]:
        raise typer.Exit(code=1)


@compose_app.command("verify")
def verify_cmd(folder: Annotated[Path, typer.Argument(help="A category folder (or one scenario folder)")]) -> None:
    """Re-verify every scenario of a pool (or one scenario)."""
    from hani2.compositional import pool_scenarios, verify
    from hani2.scenario_store import _load_dir

    folder = folder.expanduser()
    paths = [folder] if any(folder.glob("_info.y*ml")) else pool_scenarios(folder)
    bad = 0
    for p in paths:
        s = _load_dir(p)
        v = verify(s) if s is not None else None
        if v is None or not v.ok:
            bad += 1
            typer.echo(f"FAIL {p.name}: {'; '.join(v.problems) if v else 'cannot load'}")
        else:
            typer.echo(f"ok   {p.name} {v.measured}")
    typer.echo(f"{len(paths) - bad}/{len(paths)} verified")
    if bad:
        raise typer.Exit(code=1)


@compose_app.command("run")
def run_cmd(
    folder: Annotated[Path, typer.Argument(help="The pool's category folder")],
    home: Annotated[Path, typer.Option(help="Where the runs (settings, recordings) are written")],
    driver: Annotated[str, typer.Option(
        help="Who plays the participant's seat: 'Assistant' (the configured Assistant, through the autopilot) "
             "or a negotiator class (a baseline without a language model)")] = "Assistant",
    agent_class: Annotated[Optional[str], typer.Option(help="The Assistant class (module:Class)")] = None,
    settings: Annotated[Optional[Path], typer.Option(help="An assistant_settings JSON file to use")] = None,
    repeats: Annotated[int, typer.Option(help="Negotiations per scenario")] = 1,
    limit: Annotated[Optional[int], typer.Option(help="Only the first N scenarios")] = None,
    timeout: Annotated[float, typer.Option(help="Seconds allowed per negotiation")] = 600.0,
) -> None:
    """Play every scenario of a pool with the opponent and step limit of its episode factors."""
    from hani2.compositional import run_pool

    extra = json.loads(settings.read_text()) if settings else None
    res = run_pool(folder, home, driver=driver, agent_class=agent_class, assistant_settings=extra, repeats=repeats,
                   timeout=timeout, limit=limit, log=typer.echo)
    deals = sum(1 for r in res if r["agreement"])
    typer.echo(f"Done: {len(res)} negotiations, {deals} deals. Report: hani2 compose report {home}")


@compose_app.command("report")
def report_cmd(
    paths: Annotated[list[Path], typer.Argument(help="Run folders or recordings; several folders are compared")],
    by: Annotated[Optional[str], typer.Option(
        help="Report separately per value of this row field (default: per folder when several are given)")] = None,
    output: Annotated[Optional[Path], typer.Option("--output", "-o", help="Also write the report (.md or .json)")] = None,
) -> None:
    """Scores per factor level (target attainment, agreement, advantage, constraint violations) and the
    factors ranked by how much they hurt."""
    from hani2.compositional import factor_report, format_report
    from hani2.evaluation import evaluate_paths

    rows: list[dict] = []
    for p in paths:
        ev = evaluate_paths([p], metrics=["outcome", "factors"])
        for r in ev["rows"]:
            r["label"] = p.name
        rows += ev["rows"]
    if by is None and len(paths) > 1:
        by = "label"
    rep = factor_report(rows, by=by)
    text = format_report(rep)
    typer.echo(text if rep["groups"] else "No recordings of compositional scenarios found.")
    if output:
        output.write_text(json.dumps(rep, indent=1) if output.suffix == ".json" else text)
