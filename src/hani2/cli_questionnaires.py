"""``hani2 questionnaire``: the predefined question sets, composing and checking form files."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer

questionnaire_app = typer.Typer(help="Predefined questionnaires: list them, build and check form files.")


@questionnaire_app.command("list")
def questionnaire_list(
    form: Annotated[Optional[str], typer.Option("--form", help="Only sets meant for pre_questionnaire, per_negotiation or post_session.")] = None,
    about: Annotated[Optional[str], typer.Option("--about", help="Only sets about the assistant or the opponent (their tags).")] = None,
    details: Annotated[bool, typer.Option("--details", help="Also print every question.")] = False,
):
    """List the predefined question sets (bundled, and your own in settings/questionnaire_library/)."""
    from hani2 import questionnaires

    for s in questionnaires.library().values():
        if form and form not in s["forms"]:
            continue
        if about and about not in s["tags"]:
            continue
        own = "  (your own)" if s["source"] == "settings" else ""
        typer.secho(f"{s['id']:24s} {s['title']}  [{len(s['questions'])} questions; {', '.join(s['forms'])}; about {' and '.join(s['tags']) or 'the participant'}]{own}", bold=True)
        typer.echo(f"    {s['description']}")
        if s["reference"]:
            typer.echo(f"    {s['reference']}")
        if details:
            for q in s["questions"]:
                typer.echo(f"      - {q.get('id')} ({q.get('type')}): {q.get('text')}")
        typer.echo("")


@questionnaire_app.command("compose")
def questionnaire_compose(
    sets: Annotated[list[str], typer.Argument(help="Set ids, in order (see `hani2 questionnaire list`).")],
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="The form file to write; an existing file gets the questions appended.")] = None,
    form: Annotated[str, typer.Option("--form", help="pre_questionnaire, per_negotiation or post_session (the title of a new file).")] = "per_negotiation",
):
    """Build a form file from predefined sets (printed, or written to --out)."""
    from hani2 import questionnaires

    if form not in questionnaires.FORMS:
        raise typer.BadParameter(f"use one of {', '.join(questionnaires.FORMS)}", param_hint="--form")
    text = out.read_text(encoding="utf-8") if out is not None and out.exists() else ""
    try:
        new, added, skipped = questionnaires.compose(text, sets, form)
    except KeyError as e:
        raise typer.BadParameter(str(e.args[0]), param_hint="SETS") from None
    if out is None:
        typer.echo(new, nl=False)
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(new, encoding="utf-8")
    typer.echo(f"{out}: added {len(added)} question(s)" + (f", skipped {len(skipped)} already there" if skipped else ""), err=True)


@questionnaire_app.command("check")
def questionnaire_check(
    files: Annotated[list[Path], typer.Argument(help="Form files (or, with --set, question set files) to check.")],
    as_set: Annotated[bool, typer.Option("--set", help="Check predefined question sets (id, title, forms, questions) instead of forms. Files inside a questionnaire_library/ folder are always checked as sets.")] = False,
):
    """Check form files or question set files (YAML, ids, types, options); exits 1 on a problem."""
    from hani2 import questionnaire_library, questionnaires

    bad = False
    for f in files:
        text = f.read_text(encoding="utf-8")
        if as_set or f.resolve().parent.name == questionnaires.LIBRARY_DIR:
            problems = questionnaire_library.check(text, in_app=False)
        else:
            problems = questionnaires.validate(text)
        if problems:
            bad = True
            typer.secho(f"{f}:", fg="red", bold=True)
            for p in problems:
                typer.echo(f"  - {p}")
        else:
            typer.echo(f"{f}: ok")
    raise typer.Exit(1 if bad else 0)
