"""``hani2 scores``: evaluation criteria and the frozen normalisation reference of a project;
see :mod:`hani2.evaluation.criteria`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

scores_app = typer.Typer(help="Evaluation criteria and scores: the criteria catalogue and the frozen reference "
                              "that scales unbounded criteria.")


def _split(v: Optional[str]) -> list[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _target(target: str) -> tuple[str, Optional[str]]:
    from hani2 import projects

    project, _, study = target.partition("/")
    try:
        projects.check_name(project, "project")
        if study:
            projects.check_name(study, "study")
    except ValueError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1) from None
    if not projects.project_exists(project):
        typer.secho(f"no project {project!r}", fg="red", err=True)
        raise typer.Exit(1)
    if study and not projects.study_exists(projects.StudyRef(project, study)):
        typer.secho(f"no study {target!r}", fg="red", err=True)
        raise typer.Exit(1)
    return project, study or None


@scores_app.command("freeze")
def scores_freeze(
    project: Annotated[str, typer.Argument(help="The project whose reference to freeze.")],
    studies: Annotated[Optional[str], typer.Option("--studies", help="Comma-separated studies (default: the project's normalisation.reference, else every study).")] = None,
    end: Annotated[Optional[str], typer.Option("--end", help="Only games started on or before this date (YYYY-MM-DD; default: the project's normalisation.reference).")] = None,
    llm: Annotated[bool, typer.Option("--llm", help="Include the judged criteria (may call the judge for games not judged yet).")] = False,
    include_simulated: Annotated[bool, typer.Option("--include-simulated", help="Also use games of simulated participants.")] = False,
):
    """Compute the medians and quantiles of every criterion over the reference games and store them in
    projects/<project>/results/normalisation.json."""
    from hani2.evaluation import criteria

    project, _ = _target(project)
    try:
        ref = criteria.freeze(project, _split(studies) or None, end, use_llm=llm, include_simulated=include_simulated)
    except ValueError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"froze {len(ref['criteria'])} criteria over {ref['games']} games of "
               f"{', '.join(ref['studies']) or 'no study'}{' up to ' + ref['end'] if ref.get('end') else ''}")
    typer.echo(f"wrote {criteria.reference_path(project)}")


@scores_app.command("criteria")
def scores_criteria(
    target: Annotated[Optional[str], typer.Argument(help="project or project/study (default: the current study).")] = None,
    coverage: Annotated[bool, typer.Option("--coverage", help="Evaluate the games (no judge) and show each criterion's coverage.")] = False,
    out: Annotated[Optional[Path], typer.Option("-o", "--out", help="Write JSON to this file.")] = None,
):
    """List the criteria a score can use: id, source, level, direction, default normaliser and cost."""
    from hani2.evaluation import criteria

    project, study = _target(target) if target else (None, None)
    if coverage and project is None:
        typer.secho("--coverage needs a project", fg="red", err=True)
        raise typer.Exit(1)
    rows = criteria.reference_rows(project, [study] if study else None, include_simulated=True)[0] if coverage else None
    payload = criteria.api_payload(project, study, rows)
    if out:
        out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        typer.echo(f"wrote {out}")
        return
    for c in payload["criteria"]:
        cov = "" if c["coverage"] is None else f"  {100 * c['coverage']:.0f}%"
        typer.echo(f"{c['id']:<40} {c['source']:<13} {c['level']:<11} {c['direction']:<6} "
                   f"{c['normaliser_text']:<34} {c['cost']}{cov}")
    ref = payload["reference"]
    typer.echo(f"\nreference: {'frozen ' + str(ref.get('frozen_at')) if ref['frozen'] else 'none (provisional)'}")
