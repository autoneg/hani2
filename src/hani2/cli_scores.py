"""``hani2 scores``: evaluation criteria, the frozen normalisation reference of a project
(:mod:`hani2.evaluation.criteria`) and the scores of a project or study
(:mod:`hani2.evaluation.scores`)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer

scores_app = typer.Typer(help="Evaluation criteria and scores: the criteria catalogue, the frozen reference "
                              "that scales unbounded criteria, and the scores of a project or study.")


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


# --------------------------------------------------------------------------- #
# Defined scores: list, show, check, set, remove, enable, duplicate            #
# --------------------------------------------------------------------------- #
def _fail(msg: str) -> None:
    typer.secho(msg, fg="red", err=True)
    raise typer.Exit(1)


def _coverage_rows(project: str, study: Optional[str]) -> list[dict]:
    from hani2.evaluation import criteria

    return criteria.reference_rows(project, [study] if study else None, include_simulated=True)[0]


@scores_app.command("list")
def scores_list(
    target: Annotated[str, typer.Argument(help="project or project/study.")],
    out: Annotated[Optional[Path], typer.Option("-o", "--out", help="Write JSON to this file.")] = None,
):
    """List the scores of a project or study: the built-ins, the project's and the study's, whether each
    is enabled, and what is wrong."""
    from hani2.evaluation import scores as S

    project, study = _target(target)
    ss = S.resolve(project, study)
    if out:
        out.write_text(json.dumps(ss.to_dict(), indent=1), encoding="utf-8")
        typer.echo(f"wrote {out}")
        return
    for k, s in ss.scores.items():
        typer.echo(f"{'*' if k in ss.enabled else ' '} {k:<24} {s.origin:<8} {s.track:<4} "
                   f"{len(s.components):>2} part(s)  {s.title}")
    typer.echo(f"\n* enabled ({'scores_enabled of the ' + ss.enabled_set_by if ss.enabled_set_by != 'default' else 'default: every score'})")
    for w in ss.warnings:
        typer.secho(f"warning: {w}", fg="yellow")
    for p in ss.problems:
        typer.secho(f"problem: {p}", fg="red")


@scores_app.command("show")
def scores_show(
    target: Annotated[str, typer.Argument(help="project or project/study.")],
    key: Annotated[str, typer.Argument(help="The score.")],
    coverage: Annotated[bool, typer.Option("--coverage", help="Evaluate the games (no judge) and show each component's coverage.")] = False,
):
    """Show one score: its definition, the weights in effect (summing to 1), each component's direction
    and normaliser, the weights flattened down to criteria and (with --coverage) the coverage in the data."""
    import yaml

    from hani2.evaluation import criteria
    from hani2.evaluation import scores as S

    project, study = _target(target)
    ss = S.resolve(project, study)
    if key not in ss.scores:
        bad = [p for p in ss.problems if f"'{key}'" in p]
        _fail(f"no usable score {key!r} in {target}" + (": " + "; ".join(bad) if bad else ""))
    s = ss.scores[key]
    rows = _coverage_rows(project, study) if coverage else None
    typer.echo(f"{key}: {s.title} ({s.origin}, track {s.track}, {'enabled' if key in ss.enabled else 'not enabled'})")
    if s.description:
        typer.echo(s.description)
    typer.echo(f"missing: {s.missing}, min_coverage: {s.min_coverage:g}\n")
    w = S.weights_in_effect(s)
    for c in s.components:
        cov = ""
        if rows is not None:
            v = criteria.coverage(rows, c.column)
            cov = "  coverage " + ("-" if v is None else f"{100 * v:.0f}%")
        typer.echo(f"  {100 * w.get(c.column, 0):6.2f} %  {c.column:<32} {c.direction:<6} "
                   f"{criteria.describe_normaliser(c.normaliser, c.direction)}{cov}")
    flat = S.flattened(key, ss.scores)
    if set(flat) != {c.column for c in s.components}:
        typer.echo("\nflattened to criteria:")
        for k, v in sorted(flat.items(), key=lambda kv: -kv[1]):
            typer.echo(f"  {100 * v:6.2f} %  {k}")
    typer.echo("\n" + yaml.safe_dump({key: S.definition(s)}, sort_keys=False, allow_unicode=True).rstrip())


@scores_app.command("check")
def scores_check(
    target: Annotated[str, typer.Argument(help="project or project/study.")],
    coverage: Annotated[bool, typer.Option("--coverage", help="Evaluate the games (no judge): the participant-level rule and each enabled score's coverage.")] = False,
):
    """Check the scores of a project or study as saving would: weights summing to 1, known criteria,
    directions, normalisers, cycles, key clashes, ``scores_enabled`` and (with --coverage) the
    participant-level rule. Exits with 1 when something is wrong."""
    from hani2.evaluation import scores as S

    project, study = _target(target)
    rows = _coverage_rows(project, study) if coverage else None
    ss = S.resolve(project, study, strict=True, rows=rows)
    for p in ss.problems:
        typer.secho(f"problem: {p}", fg="red")
    if rows is not None:
        scored = S.score_rows(rows, ss)
        for k in ss.enabled:
            vals = [r.get(k) for r in scored]
            n = sum(v is not None for v in vals)
            typer.echo(f"{k:<24} {n}/{len(rows)} games with a value")
    if ss.problems:
        raise typer.Exit(1)
    typer.echo(f"ok: {len(ss.scores)} score(s), {len(ss.enabled)} enabled")


def _definition_from(file: Optional[Path], text: Optional[str]) -> dict:
    import yaml

    if (file is None) == (text is None):
        _fail("give the definition with --file or --json")
    try:
        data = yaml.safe_load(file.read_text(encoding="utf-8") if file else text)
    except (OSError, yaml.YAMLError) as e:
        _fail(f"cannot read the definition: {e}")
    if not isinstance(data, dict):
        _fail("the definition must be a mapping (title, track, components, …)")
    return data


@scores_app.command("set")
def scores_set(
    target: Annotated[str, typer.Argument(help="project or project/study (the file the score goes in).")],
    key: Annotated[str, typer.Argument(help="The score's key.")],
    file: Annotated[Optional[Path], typer.Option("-f", "--file", help="A YAML or JSON file with the definition.")] = None,
    text: Annotated[Optional[str], typer.Option("--json", help="The definition as JSON (or YAML) text.")] = None,
):
    """Add or replace a score in project.yaml or study.yaml. Refused unless the weights sum to 1 (100 %)
    and every check passes."""
    from hani2.evaluation import scores as S

    project, study = _target(target)
    data = _definition_from(file, text)
    try:
        S.save_score(project, study, key, data)
    except ValueError as e:
        _fail(str(e))
    typer.echo(f"saved score {key!r} in {target}")


@scores_app.command("remove")
def scores_remove(
    target: Annotated[str, typer.Argument(help="project or project/study.")],
    key: Annotated[str, typer.Argument(help="The score's key.")],
):
    """Remove a score from project.yaml or study.yaml (refused while another score contains it or
    scores_enabled names it)."""
    from hani2.evaluation import scores as S

    project, study = _target(target)
    try:
        S.delete_score(project, study, key)
    except KeyError:
        _fail(f"{target} defines no score {key!r}")
    except ValueError as e:
        _fail(str(e))
    typer.echo(f"removed score {key!r} from {target}")


@scores_app.command("enable")
def scores_enable(
    target: Annotated[str, typer.Argument(help="project or project/study.")],
    keys: Annotated[Optional[str], typer.Argument(help="Comma-separated scores to enable (in order).")] = None,
    default: Annotated[bool, typer.Option("--default", help="Remove scores_enabled: inherit (study) or enable every score (project).")] = False,
):
    """Set scores_enabled: the scores computed and shown in the boards, results views and exports."""
    from hani2.evaluation import scores as S

    project, study = _target(target)
    if default == bool(keys):
        _fail("give the scores to enable, or --default")
    try:
        enabled = S.save_enabled(project, study, None if default else _split(keys))
    except ValueError as e:
        _fail(str(e))
    typer.echo(f"enabled in {target}: {', '.join(enabled)}")


@scores_app.command("duplicate")
def scores_duplicate(
    target: Annotated[str, typer.Argument(help="project or project/study (where the copy goes).")],
    source: Annotated[str, typer.Argument(help="The score to copy (for example a built-in).")],
    key: Annotated[str, typer.Argument(help="The copy's key.")],
):
    """Copy a score (for example a read-only built-in) under a new key, where it can be edited."""
    from hani2.evaluation import scores as S

    project, study = _target(target)
    try:
        S.duplicate(project, study, source, key)
    except KeyError:
        _fail(f"no score {source!r} in {target}")
    except ValueError as e:
        _fail(str(e))
    typer.echo(f"copied {source!r} to {key!r} in {target}")
