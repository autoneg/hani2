"""``hani2 host-assistant`` / ``hani2 host-opponent`` (a team serves its agent) and ``hani2 hosted``
(organisers register the teams' endpoints). See :mod:`hani2.hosting`."""

from __future__ import annotations

import json
import os
from typing import Annotated, Optional

import typer

hosted_app = typer.Typer(help="Self-hosted Assistants and opponents of a project: register, list, check, remove.")


def _token(token_env: Optional[str], token: Optional[str], insecure: bool) -> Optional[str]:
    if token:
        return token
    var = token_env or "HANI2_HOSTED_TOKEN"
    tok = os.environ.get(var)
    if not tok and not insecure:
        typer.secho(f"Set the token HANI2 gave your team in ${var} (or pass --token-env NAME). "
                    "Use --insecure-no-token only on your own machine.", fg="red", err=True)
        raise typer.Exit(2)
    return tok or None


def _serve(kind: str, agent: str, host: str, port: int, token_env, token, insecure, name, version, model,
           events, idle_timeout, max_sessions) -> None:
    import sys

    from hani2.hosting import serve

    sys.path.insert(0, os.getcwd())  # `my_module:MyAgent` from the current folder
    tok = _token(token_env, token, insecure)
    m = None
    if model:
        p, _, n = model.partition(":") if ":" in model else ("", "", model)
        m = {"provider": p, "model": n} if p else {"model": n}
    typer.echo(f"Serving the {kind} {agent} on http://{host}:{port} (protocol hani2-hosted/1). "
               f"Give HANI2's organisers this address; stop with Ctrl-C.")
    serve(kind, agent, host=host, port=port, token=tok, allow_no_token=insecure, name=name, version=version or "",
          model=m, events=[e for e in (events or "").split(",") if e.strip()], idle_timeout=idle_timeout,
          max_sessions=max_sessions)


_HOST = Annotated[str, typer.Option("--host", help="The interface to listen on.")]
_PORT = Annotated[int, typer.Option("--port", help="The port to listen on.")]
_TOKEN_ENV = Annotated[Optional[str], typer.Option("--token-env", help="The variable holding your team's token (default HANI2_HOSTED_TOKEN).")]
_TOKEN = Annotated[Optional[str], typer.Option("--token", help="The token itself (prefer --token-env: a command line is visible to other users).")]
_INSECURE = Annotated[bool, typer.Option("--insecure-no-token", help="Accept requests without a token (local tests only).")]
_NAME = Annotated[Optional[str], typer.Option("--name", help="The name the host reports (default: the class name).")]
_VERSION = Annotated[Optional[str], typer.Option("--version", help="A version string you declare (shown by HANI2; a hint only).")]
_MODEL = Annotated[Optional[str], typer.Option("--model", help="The model you report, provider:model (default: what your agent uses, if HANI2 can tell).")]
_IDLE = Annotated[float, typer.Option("--idle-timeout", help="Seconds after which an idle negotiation is dropped.")]
_MAX = Annotated[int, typer.Option("--max-sessions", help="The most negotiations at once.")]


def host_assistant(
    agent: Annotated[str, typer.Argument(help="Your Assistant class: module:Class or path/to/file.py:Class.")],
    host: _HOST = "0.0.0.0", port: _PORT = 8700, token_env: _TOKEN_ENV = None, token: _TOKEN = None,
    insecure: _INSECURE = False, name: _NAME = None, version: _VERSION = None, model: _MODEL = None,
    events: Annotated[Optional[str], typer.Option("--events", help="Optional events to receive: draft_changed,action_requested.")] = None,
    idle_timeout: _IDLE = 3600.0, max_sessions: _MAX = 200,
):
    """Serve your Assistant class so HANI2 can call it (it uses your own language model)."""
    _serve("assistant", agent, host, port, token_env, token, insecure, name, version, model, events, idle_timeout,
           max_sessions)


def host_opponent(
    agent: Annotated[str, typer.Argument(help="Your negotiator: module:Class, a negmas name or file:path/neg.Class.")],
    host: _HOST = "0.0.0.0", port: _PORT = 8701, token_env: _TOKEN_ENV = None, token: _TOKEN = None,
    insecure: _INSECURE = False, name: _NAME = None, version: _VERSION = None, model: _MODEL = None,
    idle_timeout: _IDLE = 3600.0, max_sessions: _MAX = 200,
):
    """Serve your negotiator (a negmas SAONegotiator) so HANI2 can use it as an opponent."""
    _serve("opponent", agent, host, port, token_env, token, insecure, name, version, model, None, idle_timeout,
           max_sessions)


@hosted_app.command("add")
def hosted_add(
    project: Annotated[str, typer.Argument(help="The project.")],
    name: Annotated[str, typer.Argument(help="The name HANI2 records (results, boards): usually the team's.")],
    url: Annotated[str, typer.Argument(help="The team's address, e.g. https://team.example.org:8700")],
    kind: Annotated[str, typer.Option("--kind", help="assistant or opponent.")] = "assistant",
    team: Annotated[str, typer.Option("--team", help="The team (for the console).")] = "",
    token: Annotated[Optional[str], typer.Option("--token", help="The team's token (default: a new one is made and printed).")] = None,
    timeout: Annotated[Optional[float], typer.Option("--timeout", help="Seconds per call (default: the project's hosted.timeout, 30).")] = None,
    replace: Annotated[bool, typer.Option("--replace", help="Change an existing entry (keeps its token unless --token).")] = False,
):
    """Register a team's hosted agent; use it as remote:<name>, or let `hosted: {assistants: true}` take
    every registered one."""
    from hani2.hosting import registry

    try:
        e, tok = registry.add(project, name, kind, url, token=token, team=team, timeout=timeout, replace=replace)
    except ValueError as ex:
        typer.secho(str(ex), fg="red", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"registered remote:{e['name']} ({e['kind']}) at {e['url']}")
    if not token:
        typer.echo(f"token for the team (shown once here; they start their host with it): {tok}")


@hosted_app.command("list")
def hosted_list(project: Annotated[str, typer.Argument(help="The project.")],
                as_json: Annotated[bool, typer.Option("--json")] = False):
    """The project's hosted agents (never their tokens)."""
    from hani2.hosting import registry

    items = [registry.public(e) for e in registry.entries(project)]
    if as_json:
        typer.echo(json.dumps(items, indent=1))
        return
    if not items:
        typer.echo("no hosted agents")
    for e in items:
        typer.echo(f"{e['spec']:28s} {e['kind']:9s} {'on ' if e.get('enabled', True) else 'off'} {e['url']}"
                   + (f"  ({e['team']})" if e.get("team") else ""))


@hosted_app.command("remove")
def hosted_remove(project: Annotated[str, typer.Argument()], name: Annotated[str, typer.Argument()]):
    """Remove a hosted agent."""
    from hani2.hosting import registry

    if not registry.remove(project, name):
        typer.secho(f"no hosted agent {name!r}", fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(f"removed remote:{name}")


@hosted_app.command("enable")
def hosted_enable(project: Annotated[str, typer.Argument()], name: Annotated[str, typer.Argument()],
                  off: Annotated[bool, typer.Option("--off", help="Switch it off instead.")] = False):
    """Switch a hosted agent on (or --off): a switched-off one is not used."""
    from hani2.hosting import registry

    if not registry.set_enabled(project, name, not off):
        typer.secho(f"no hosted agent {name!r}", fg="red", err=True)
        raise typer.Exit(1)
    typer.echo(f"remote:{name} {'off' if off else 'on'}")


@hosted_app.command("check")
def hosted_check(project: Annotated[str, typer.Argument()],
                 name: Annotated[Optional[str], typer.Argument(help="One agent (default: all).")] = None):
    """Call each host's /info with its token: reachable, the right kind, its declared name and version."""
    from hani2.hosting import client, registry

    bad = 0
    for e in registry.entries(project):
        if name and e["name"] != name:
            continue
        r = client.check(registry.endpoint_of(e))
        info = r.get("info") or {}
        if r["ok"]:
            typer.echo(f"ok   remote:{e['name']}: {info.get('name')} {info.get('version') or ''} "
                       f"({r['latency'] * 1000:.0f} ms)")
        else:
            bad += 1
            typer.secho(f"FAIL remote:{e['name']}: {r.get('error')}", fg="red")
    raise typer.Exit(1 if bad else 0)
