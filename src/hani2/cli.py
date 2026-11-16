"""The ``hani2`` command line."""

from __future__ import annotations

import os
import shutil
import threading
import time
import webbrowser
from pathlib import Path
from typing import Annotated, Optional

import typer

from hani2 import __version__

app = typer.Typer(add_completion=False, no_args_is_help=False, help="HANI2 — Human-Agent Negotiation Interface.")
experiment_app = typer.Typer(help="Create and inspect experiments (self-contained studies).")
users_app = typer.Typer(help="Manage user accounts.")
app.add_typer(experiment_app, name="experiment")
app.add_typer(users_app, name="users")


def _open_when_ready(url: str) -> None:
    def _run():
        import urllib.request

        for _ in range(120):
            try:
                urllib.request.urlopen(url.split("?")[0].rstrip("/") + "/api/config", timeout=1)
                webbrowser.open(url)
                return
            except Exception:
                time.sleep(0.5)

    threading.Thread(target=_run, daemon=True).start()


def _serve(host: str, port: int, open_path: str | None, reload: bool = False, log_level: str = "info") -> None:
    import uvicorn

    from hani2.config import settings_dir

    if not (settings_dir() / "env.json").exists():
        from hani2 import setup as _setup

        _setup.run_setup(force=False, quiet=True)
    url_host = "localhost" if host in ("0.0.0.0", "127.0.0.1", "::") else host
    typer.secho(f"\n  HANI2 {__version__}", bold=True)
    typer.echo(f"  App         http://{url_host}:{port}/app")
    typer.echo(f"  Playground  http://{url_host}:{port}/play")
    typer.echo(f"  Admin       http://{url_host}:{port}/admin")
    typer.echo(f"  Settings    {settings_dir()}\n")
    if open_path is not None:
        _open_when_ready(f"http://{url_host}:{port}{open_path}")
    uvicorn.run("hani2.server:app", host=host, port=port, reload=reload, log_level=log_level, workers=1)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on.")] = 5006,
    host: Annotated[str, typer.Option(help="Interface to bind (0.0.0.0 to accept remote connections).")] = "127.0.0.1",
    agents: Annotated[Optional[str], typer.Option(help="Opponent pool: comma-separated negotiators and/or groups (:llm, :template, :notext, :negmas, :classic, :genius, :custom, :pan).")] = None,
    support_agent: Annotated[Optional[str], typer.Option("--support-agent", help="Who gets the support agent: on, off or auto (admins only).")] = None,
    experiment: Annotated[Optional[str], typer.Option(help="Run this experiment (see `hani2 experiment create`).")] = None,
    open_browser: Annotated[bool, typer.Option("--browser/--no-browser", help="Open the browser.")] = True,
    page: Annotated[str, typer.Option(help="Page to open: app, play or admin.")] = "app",
    verbose: Annotated[bool, typer.Option(help="Ask negotiators to print what they do.")] = False,
    dev: Annotated[bool, typer.Option(help="Auto-reload the server when Python files change.")] = False,
    version: Annotated[bool, typer.Option("--version", help="Show the version and exit.")] = False,
):
    """Start the HANI2 server (app, playground, admin and API on one port)."""
    if version:
        typer.echo(__version__)
        raise typer.Exit()
    if experiment:
        os.environ["HANI2_EXPERIMENT"] = experiment
    if ctx.invoked_subcommand is not None:
        return
    if agents:
        os.environ["HANI2_AGENTS"] = agents
    if support_agent:
        os.environ["HANI2_SUPPORT_AGENT"] = support_agent
    if verbose:
        os.environ["HANI2_VERBOSE"] = "1"
    _serve(host, port, f"/{page.strip('/')}" if open_browser else None, reload=dev)


@app.command()
def setup(
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing settings files.")] = False,
    admin_password: Annotated[Optional[str], typer.Option(help="Password for the admin account.")] = None,
):
    """Create the settings folder with defaults, users and sample scenarios."""
    from hani2 import setup as _setup

    _setup.run_setup(force=force, admin_password=admin_password)


@app.command()
def info():
    """Show where HANI2 keeps its files and how it is configured."""
    from hani2.config import experiment_dir, home, results_root, scenarios_dir, settings_dir
    from hani2.server import auth_mode, oauth_providers
    from hani2.support_agent.settings import support_agent_mode

    typer.echo(f"version         {__version__}")
    typer.echo(f"home            {home()}")
    typer.echo(f"settings        {settings_dir()}")
    typer.echo(f"scenarios       {scenarios_dir()}")
    typer.echo(f"results         {results_root()}")
    typer.echo(f"experiment      {experiment_dir() or '-'}")
    typer.echo(f"auth mode       {auth_mode()}  (oauth: {', '.join(oauth_providers()) or 'none'})")
    typer.echo(f"support agent   {support_agent_mode()}")


@app.command()
def generate(
    types: Annotated[Optional[list[str]], typer.Option("--type", "-t", help="Scenario type(s). Default: all.")] = None,
    count: Annotated[int, typer.Option("-n", "--count", help="Scenarios per type.")] = 50,
    base: Annotated[Optional[Path], typer.Option(help="Pool directory (default: the scenarios directory).")] = None,
    human_index: Annotated[int, typer.Option(help="The human's negotiator index.")] = 1,
    cache_inverter: Annotated[bool, typer.Option("--cache-inverter/--no-cache-inverter")] = True,
    rebuild_inverses: Annotated[bool, typer.Option("--rebuild-inverses", help="Only rebuild cached inverses.")] = False,
    min_opposition: Annotated[float, typer.Option()] = 0.35,
    max_opposition: Annotated[float, typer.Option()] = 0.90,
    set_reservations: Annotated[bool, typer.Option("--set-reservations/--no-set-reservations")] = True,
    user_reserved_max: Annotated[float, typer.Option()] = 0.10,
    agent_reserved_max: Annotated[float, typer.Option()] = 0.20,
    max_tries: Annotated[int, typer.Option()] = 60,
    seed: Annotated[int, typer.Option()] = 0,
    force: Annotated[bool, typer.Option("--force")] = False,
):
    """Generate a pool of scenarios (filtered by opposition level)."""
    from hani2.make_scenarios import generate as _gen

    _gen(types=types, count=count, base=base, human_index=human_index, cache_inverter=cache_inverter,
         rebuild_inverses_only=rebuild_inverses, min_opposition=min_opposition, max_opposition=max_opposition,
         set_reservations=set_reservations, user_reserved_max=user_reserved_max,
         agent_reserved_max=agent_reserved_max, max_tries=max_tries, seed=seed, force=force)


@experiment_app.command("create")
def experiment_create(
    name: str,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing files.")] = False,
    no_support_agent: Annotated[bool, typer.Option("--no-support-agent", help="Run this experiment without a support agent (e.g. a competition).")] = False,
    no_webmcp: Annotated[bool, typer.Option("--no-webmcp", help="Do not expose WebMCP tools to browser agents in this experiment.")] = False,
):
    """Scaffold a self-contained experiment folder."""
    from hani2.config import DEFAULT_SCENARIOS, DEFAULT_SETTINGS_DIR, experiments_root, get_settings_file, scenarios_dir

    exp = experiments_root() / name
    (exp / "results").mkdir(parents=True, exist_ok=True)
    (exp / "questionnaires").mkdir(parents=True, exist_ok=True)
    for fname in ("consent.md", "scenario_order.txt", "announcements.md"):
        dst = exp / fname
        src = get_settings_file(fname)
        if src.exists() and (force or not dst.exists()):
            shutil.copyfile(src, dst)
    q = exp / "questionnaires" / "per_negotiation.yaml"
    if force or not q.exists():
        shutil.copyfile(DEFAULT_SETTINGS_DIR / "questionnaires" / "per_negotiation.yaml", q)
    sdst = exp / "scenarios"
    src_scen = scenarios_dir() if scenarios_dir().is_dir() else DEFAULT_SCENARIOS
    if force or not sdst.exists():
        shutil.copytree(src_scen, sdst, dirs_exist_ok=True)
    import json as _json

    if no_support_agent:
        (exp / "support_agent_settings.json").write_text(_json.dumps({"mode": "off"}, indent=2))
        auto = exp / "autopilot_settings.json"
        auto.write_text(_json.dumps({"allowed": False}, indent=2))
        typer.echo("  support agent: off (support_agent_settings.json), autopilot: off")
    if no_webmcp:
        envf = exp / "env.json"
        env = _json.loads(envf.read_text()) if envf.exists() else {}
        env["webmcp"] = {"enabled": False}
        envf.write_text(_json.dumps(env, indent=2))
        typer.echo("  WebMCP: off (env.json)")
    typer.echo(f"Created experiment at {exp}")
    typer.echo(f"Run it with:  hani2 --experiment {name}")


@experiment_app.command("list")
def experiment_list():
    """List experiments."""
    from hani2.config import experiments_root

    root = experiments_root()
    if not root.is_dir():
        typer.echo("No experiments yet.")
        return
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        n = len(list((d / "results").glob("*/results.csv"))) if (d / "results").is_dir() else 0
        typer.echo(f"{d.name:30s} {n} participant(s)")


@users_app.command("list")
def users_list():
    """List user accounts."""
    from hani2 import auth

    for u in sorted(auth.load_users()):
        m = auth.get_meta(u)
        typer.echo(f"{u:24s} {'admin' if auth.is_admin_user(u) else 'user ':5s} {m.get('email', '')}")


@users_app.command("add")
def users_add(
    username: str,
    password: Annotated[str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True)],
    admin: Annotated[bool, typer.Option("--admin")] = False,
    email: Annotated[str, typer.Option()] = "",
):
    """Create a user account."""
    from hani2 import auth

    err = auth.validate_new_user(username, password)
    if err:
        typer.secho(err, fg="red")
        raise typer.Exit(1)
    auth.create_user(username, password, consented=True, email=email, **({"role": "admin"} if admin else {}))
    typer.echo(f"Created {username}")


@users_app.command("passwd")
def users_passwd(username: str, password: Annotated[str, typer.Option(prompt=True, hide_input=True, confirmation_prompt=True)]):
    """Set a user's password."""
    from hani2 import auth

    if not auth.set_password(username, password):
        typer.secho("No such user", fg="red")
        raise typer.Exit(1)
    typer.echo("Password updated")


@users_app.command("remove")
def users_remove(username: str):
    """Delete a user account."""
    from hani2 import auth

    typer.echo("Removed" if auth.delete_user(username) else "No such user")


if __name__ == "__main__":  # pragma: no cover
    app()
