"""``hani2 ablation``: run the No-Human ablation (the Assistant on autopilot) and report the gaps between
conditions (team, human alone, autopilot, oracle); see :mod:`hani2.ablation` and
:mod:`hani2.evaluation.ablation`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

ablation_app = typer.Typer(help="Ablations as diagnostics: the Assistant on autopilot (No-Human), with the opponent's "
                                "utility function (Oracle), and the added value over humans alone.")


def _split(v: Optional[str]) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


@ablation_app.command("run")
def ablation_run(
    scenario_types: Annotated[str, typer.Option("--scenario-types", "-s", help="Comma-separated scenario types.")] = "Trade",
    opponents: Annotated[str, typer.Option("--opponents", "-p", help="Comma-separated opponent negotiators.")] = "BoulwareTBNegotiator",
    like: Annotated[Optional[list[Path]], typer.Option("--like", help="Run on the cells (scenario, opponent, side) of the team and human-alone recordings under this path, instead of --scenario-types × --opponents.")] = None,
    reps: Annotated[int, typer.Option(help="Negotiations per cell and Assistant.")] = 1,
    oracle: Annotated[bool, typer.Option("--oracle", help="Give the Assistant the opponent's utility function.")] = False,
    assistants: Annotated[Optional[str], typer.Option("--assistants", help="Comma-separated Assistant classes (default: the study's pool without none, else the configured one).")] = None,
    n_steps: Annotated[int, typer.Option(help="Rounds per negotiation.")] = 20,
    study: Annotated[Optional[str], typer.Option(help="Record in this study (project/study; default: the current one).")] = None,
    timeout: Annotated[float, typer.Option(help="Seconds to wait for one negotiation before ending it as no deal.")] = 900.0,
):
    """Run the Assistant on autopilot on every cell (the No-Human condition)."""
    from hani2.ablation import cells_of, run_no_human

    cells = cells_of(like) if like else None
    if like and not cells:
        typer.secho("no team or human-alone recordings found there", fg="red", err=True)
        raise typer.Exit(1)

    def show(r: dict) -> None:
        res = r.get("result") or {}
        what = f"{r.get('scenario_name') or r.get('scenario_type')} vs {r['opponent']}"
        who = f" [{r['assistant']}]" if r.get("assistant") else ""
        msg = (f"{what}{who} #{r['rep']}{' (oracle)' if r['oracle'] else ''}: "
               + (f"{res.get('status', 'done')} utility={res.get('human_utility')}"
                  + (f" ({r['note']}: ended as no deal)" if r.get("note") else "") if r["ok"] else f"ERROR {r['error']}"))
        typer.secho(msg, fg=None if r["ok"] else "red", err=not r["ok"])

    runs = run_no_human(scenario_types=_split(scenario_types), opponents=_split(opponents), cells=cells, reps=reps,
                        oracle=oracle, assistants=assistants, n_steps=n_steps, study=study, timeout=timeout,
                        progress=show)
    ok = sum(r["ok"] for r in runs)
    typer.echo(f"{ok}/{len(runs)} negotiations finished; evaluate them with `hani2 ablation report`.")
    if ok < len(runs):
        raise typer.Exit(1)


@ablation_app.command("report")
def ablation_report_cmd(
    paths: Annotated[Optional[list[Path]], typer.Argument(help="Recording files or folders (default: every recording in the results folder).")] = None,
    value: Annotated[str, typer.Option(help="The column compared (any evaluation column).")] = "human_advantage",
    cell: Annotated[str, typer.Option(help="Comma-separated fields that make a cell.")] = "scenario,opponent,human_index",
    by: Annotated[Optional[str], typer.Option(help="Split the team side by this field, e.g. assistant.")] = None,
    practice: Annotated[bool, typer.Option("--practice", help="Include practice rounds.")] = False,
    opponent_info: Annotated[bool, typer.Option("--opponent-info", help="Include sessions whose tools showed the opponent's utilities.")] = False,
    off_is_control: Annotated[bool, typer.Option("--off-is-control", help="Count sessions with the Assistant switched off in the settings (e.g. a separate --no-assistant study) as human alone.")] = False,
    cells: Annotated[bool, typer.Option("--cells", help="Also print every cell of every gap.")] = False,
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="Write the full report as JSON.")] = None,
):
    """The conditions and the gaps between them, matched cell by cell (added value = team − human alone)."""
    from hani2.cli import _paths, _write_table
    from hani2.evaluation import ablation_report, evaluate_paths

    metrics = ["outcome", "condition"]
    ev = evaluate_paths(_paths(paths), metrics if value in ("human_advantage", "human_utility", "agreement", "welfare",
                                                             "opponent_advantage", "opponent_utility") else None)
    for k, errs in ev["errors"].items():
        typer.secho(f"{k}: {errs}", fg="yellow", err=True)
    rep = ablation_report(ev["rows"], value=value, cell=_split(cell), by=by, include_practice=practice,
                          include_opponent_info=opponent_info, off_is_control=off_is_control)
    if out is not None:
        out.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
        typer.echo(f"wrote {out}", err=True)
    typer.echo(f"value: {rep['value']}   cell: {' × '.join(rep['cell'])}   negotiations: {rep['n']}"
               + (f"   left out: {rep['dropped']}" if rep["dropped"] else ""))
    _write_table(rep["conditions"], ["condition", "n", "cells", "mean"], None)
    typer.echo("")
    _write_table(rep["gaps"], ["gap_name", "group", "gap", "se", "cells", "n_a", "n_b", "a", "b"], None)
    if cells:
        for g in rep["gaps"]:
            if g["per_cell"]:
                typer.echo(f"\n{g['gap_name']}{' / ' + g['group'] if g['group'] else ''}:")
                _write_table(g["per_cell"], rep["cell"] + ["a", "b", "gap", "n_a", "n_b"], None)
