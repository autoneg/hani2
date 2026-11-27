"""``hani2 leaderboard``: the boards of projects and studies (:mod:`hani2.evaluation.boards`), their
evaluation cache (:mod:`hani2.evaluation.eval_cache`) and API tokens for a website."""

from __future__ import annotations

import json
from typing import Annotated, Optional

import typer

leaderboard_app = typer.Typer(help="Leaderboards of projects and studies: show a board, rebuild its evaluation "
                                   "cache, run the judge, mint an API token.")


def _target(target: str) -> tuple[str, Optional[str]]:
    from hani2.cli_scores import _target as t

    return t(target)


def _refs(project: str, study: Optional[str]):
    from hani2 import projects
    from hani2.evaluation import boards

    out = []
    for p in boards.paths_of(project, study):
        r = projects.parse_ref(p)
        if r is not None and projects.study_exists(r):
            out.append(r)
    return out


@leaderboard_app.command("show")
def leaderboard_show(
    target: Annotated[str, typer.Argument(help="<project> (the project board) or <project>/<study>.")],
    sort: Annotated[Optional[str], typer.Option("--sort", help="The score or criterion to rank by.")] = None,
    games: Annotated[Optional[str], typer.Option("--games", help="all, people or ai.")] = None,
    stratum: Annotated[Optional[str], typer.Option("--stratum", help="HI: combined, solo, paired; HAN: alone, vs_team, both.")] = None,
    window: Annotated[Optional[str], typer.Option("--window", help="all or last_<n>_days.")] = None,
    as_user: Annotated[bool, typer.Option("--as-user", help="Only the options end users may use (default: an admin's).")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Print the API's JSON (schema hani2.leaderboard/2).")] = False,
):
    """Show a board as the API serves it."""
    from hani2.evaluation import boards

    project, study = _target(target)
    q = {k: v for k, v in dict(sort=sort, games=games, stratum=stratum, window=window).items() if v}
    try:
        out = boards.board(project, study, q, admin=not as_user)
    except boards.BoardError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1) from None
    if as_json:
        typer.echo(json.dumps(out, indent=1, default=str))
        return
    qq = out["query"]
    typer.echo(f"{target}: {out['track']} board, sorted by {qq['sort']} (games {qq['games']}, stratum "
               f"{qq['stratum']}, window {qq['window']}); visibility {out.get('visibility')}")
    cols = [c for c in out["columns"] if c not in boards.COUNT_COLUMNS]
    typer.echo("  " + "  ".join(["rank", "entrant".ljust(28), *[c[:14].rjust(14) for c in cols], "games", "people"]))
    for e in out["entries"]:
        vals = [(f"{e['values'][c]['mean']:.3f}" if c in e["values"] and e["values"][c]["mean"] is not None else "—")
                .rjust(14) for c in cols]
        rank = f"={e['rank']}" if e["tied_with_leader"] else str(e["rank"])
        typer.echo("  " + "  ".join([rank.rjust(4), str(e["label"] or e["entrant"])[:28].ljust(28), *vals,
                                     str(e["games"]["all"]).rjust(5), str(e["participants"]).rjust(6)]))
    for u in out["unranked"]:
        typer.echo(f"  not ranked yet: {u['label'] or u['entrant']} ({u['games']['all']} games; {u['reason']})")
    if out["excluded"]:
        typer.echo("  excluded: " + ", ".join(f"{k} {v}" for k, v in sorted(out["excluded"].items())))
    for n in out.get("notes") or []:
        typer.echo(f"  note: {n}")
    for w in out["warnings"]:
        typer.secho(f"  warning: {w}", fg="yellow")


@leaderboard_app.command("list")
def leaderboard_list():
    """Every project that has a board, with its track, year and visibility."""
    from hani2.evaluation import boards

    for b in boards.list_boards():
        typer.echo(f"{b['project']:20s} {b['track']:4s} {str(b['year'] or ''):6s} {b['visibility']:12s} "
                   f"{len(b['studies'])} stud{'y' if len(b['studies']) == 1 else 'ies'}")


@leaderboard_app.command("refresh")
def leaderboard_refresh(
    target: Annotated[str, typer.Argument(help="<project> (every study its board reads) or <project>/<study>.")],
):
    """Rebuild the evaluation cache (<study results>/eval_cache/) from the recordings: every metric that
    needs no language model. The judge's values are kept."""
    from hani2.evaluation import eval_cache

    project, study = _target(target)
    for r in _refs(project, study):
        n = eval_cache.refresh(r)
        typer.echo(f"{r}: {n['games']} game(s) evaluated" + (f", {n['failed']} failed" if n["failed"] else "")
                   + (f", {n['removed']} stale entr{'y' if n['removed'] == 1 else 'ies'} removed" if n["removed"] else ""))


@leaderboard_app.command("judge")
def leaderboard_judge(
    target: Annotated[str, typer.Argument(help="<project> (every study its board reads) or <project>/<study>.")],
    judge: Annotated[Optional[str], typer.Option("--judge", help="Judge with exactly this model (provider:model) instead of the configured judge chain.")] = None,
    limit: Annotated[Optional[int], typer.Option("--limit", help="Judge at most this many games per study.")] = None,
    again: Annotated[bool, typer.Option("--again", help="Judge games that were judged before too.")] = False,
):
    """Run the language-model judge on the games not judged yet, and add its criteria to the cache. A score
    that needs judged criteria is provisional while fewer than 80 % of its games were judged."""
    from hani2.evaluation import eval_cache

    project, study = _target(target)
    for r in _refs(project, study):
        n = eval_cache.judge(r, judge=judge, limit=limit, again=again)
        typer.echo(f"{r}: {n['judged']} judged, {n['skipped']} already judged or unfinished"
                   + (f", {n['failed']} failed" if n["failed"] else ""))


@leaderboard_app.command("token")
def leaderboard_token(
    provider: Annotated[str, typer.Argument(help="The sign-in provider whose secret signs the token (auth.sso in env.json).")],
    root_path: Annotated[Optional[str], typer.Option("--root-path", help="The server's root path (default: HANI2_ROOT_PATH).")] = None,
    lifetime: Annotated[int, typer.Option("--lifetime", help="Seconds the token is valid (at most 120).")] = 120,
):
    """Mint an API token for the leaderboard API (to try the API by hand; a website mints its own)."""
    import os

    from hani2 import sso

    try:
        tok = sso.mint_api_token(provider, root_path=root_path if root_path is not None else
                                 os.environ.get("HANI2_ROOT_PATH", ""), lifetime=lifetime)
    except sso.SSOError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1) from None
    typer.echo(tok)
