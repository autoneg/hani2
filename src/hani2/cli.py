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
experiment_app = typer.Typer(help="Create and inspect experiments (old name: an experiment is a study of the default project).")
project_app = typer.Typer(help="Create and inspect projects (long-lived programmes that own studies).")
study_app = typer.Typer(help="Create and inspect studies (one data collection of a project, with its own results).")
users_app = typer.Typer(help="Manage user accounts.")
replay_app = typer.Typer(help="Explore, replay and evaluate recorded negotiations (.hrec files).")
tools_app = typer.Typer(help="List, locate and create tools.")
scenario_app = typer.Typer(help="Write scenarios by hand: start from a template, check a folder.")
app.add_typer(experiment_app, name="experiment")
app.add_typer(project_app, name="project")
app.add_typer(study_app, name="study")
app.add_typer(users_app, name="users")
app.add_typer(replay_app, name="replay")
app.add_typer(tools_app, name="tools")
app.add_typer(scenario_app, name="scenario")
groups_app = typer.Typer(help="List opponent and Assistant groups (named pools).")
app.add_typer(groups_app, name="groups")


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


def _apply_assistant_choice(value: Optional[str]) -> None:
    """Turn ``--assistant`` into environment overrides for the server
    (``HANI2_ASSISTANT`` / ``HANI2_ASSISTANT_CLASS``; the old names
    ``HANI2_SUPPORT_AGENT`` / ``HANI2_SUPPORT_AGENT_CLASS`` are set too)."""
    if not value:
        return
    from hani2.support_agent.settings import parse_assistant_choice

    try:
        mode, klass = parse_assistant_choice(value)
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="--assistant") from None
    os.environ["HANI2_ASSISTANT"] = os.environ["HANI2_SUPPORT_AGENT"] = mode
    if klass:
        if ".py:" in klass:
            path, _, attr = klass.rpartition(":")
            klass = f"{Path(path).expanduser().resolve()}:{attr}"
        _check_assistant_class(klass)
        os.environ["HANI2_ASSISTANT_CLASS"] = os.environ["HANI2_SUPPORT_AGENT_CLASS"] = klass


_apply_support_agent_choice = _apply_assistant_choice  # old name


def _assistant_option(new: Optional[str], old: Optional[str]) -> Optional[str]:
    """``--assistant``, else its old name ``--support-agent``."""
    if old and not new:
        typer.echo("note: --support-agent is now --assistant", err=True)
    return new or old


def _check_tools(value: str) -> str:
    """Load every tool class now (fail early) and return the list with file
    paths made absolute."""
    from hani2.tools.registry import import_tool

    from hani2.tools.registry import is_tool_path, load_tool_file

    out = []
    for spec in [x.strip() for x in value.split(",") if x.strip()]:
        if is_tool_path(spec):  # a tools folder or a .py file: load every tool in it
            path = Path(spec).expanduser().resolve()
            if not path.exists():
                raise typer.BadParameter(f"{spec!r} does not exist", param_hint="--tools")
            for f in [path] if path.is_file() else sorted(path.glob("*.py")):
                try:
                    load_tool_file(f)
                except Exception as e:  # noqa: BLE001
                    raise typer.BadParameter(f"cannot load tools from {f}: {e}", param_hint="--tools") from None
            out.append(str(path))
            continue
        if ".py:" in spec:
            path, _, attr = spec.rpartition(":")
            spec = f"{Path(path).expanduser().resolve()}:{attr}"
        try:
            import_tool(spec)
        except Exception as e:  # noqa: BLE001
            raise typer.BadParameter(f"cannot load tool {spec!r}: {e}", param_hint="--tools") from None
        out.append(spec)
    return ",".join(out)


def _check_opponents(value: str) -> None:
    """Fail early when the opponent list resolves to no negotiator."""
    from hani2.agents import expand_agents

    try:
        pool = expand_agents(value)
    except Exception as e:  # noqa: BLE001
        raise typer.BadParameter(f"cannot read {value!r}: {e}", param_hint="--opponents") from None
    if not pool:
        raise typer.BadParameter(f"{value!r} names no opponent agent", param_hint="--opponents")


def _check_assistant_class(klass: str) -> None:
    from hani2.support_agent.runtime import Assistant, load_class

    try:
        cls = load_class(klass)
    except Exception as e:  # noqa: BLE001
        raise typer.BadParameter(f"cannot load {klass!r}: {e}", param_hint="--assistant") from None
    if not (isinstance(cls, type) and issubclass(cls, Assistant)):
        raise typer.BadParameter(f"{klass!r} is not an Assistant (SupportAgent) subclass", param_hint="--assistant")


_check_support_agent_class = _check_assistant_class  # old name


def _check_assistants(value: str) -> str:
    """Fail early when the Assistant pool is empty or a member does not load;
    returns the list with file paths made absolute."""
    from hani2 import groups

    items = []
    for spec in [x.strip() for x in value.split(",") if x.strip()]:
        if ".py:" in spec:
            path, _, attr = spec.rpartition(":")
            spec = f"{Path(path).expanduser().resolve()}:{attr}"
        items.append(spec)
    pool = groups.expand_assistants(items)
    if not pool:
        raise typer.BadParameter(f"{value!r} names no Assistant", param_hint="--assistants")
    from hani2.support_agent.runtime import AssistantLoadError, load_assistant_class

    for spec in pool:
        try:
            load_assistant_class(spec)
        except AssistantLoadError as e:
            raise typer.BadParameter(str(e), param_hint="--assistants") from None
    return ",".join(items)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    port: Annotated[int, typer.Option("--port", "-p", help="Port to listen on.")] = 5006,
    host: Annotated[str, typer.Option(help="Interface to bind (0.0.0.0 to accept remote connections).")] = "127.0.0.1",
    opponents: Annotated[Optional[str], typer.Option("--opponents", "--opponent", "-o", help="Opponent agent(s) the participants negotiate against: comma-separated negotiators and/or groups (:llm, :template, :notext, :negmas, :classic, :genius, :custom, :pan), e.g. BoulwareTBNegotiator or file:path/to/mine.MyNegotiator.")] = None,
    agents: Annotated[Optional[str], typer.Option("--agents", hidden=True, help="Old name of --opponents.")] = None,
    assistant: Annotated[Optional[str], typer.Option("--assistant", help="Assistant: on (everyone), off (nobody), auto (admins only), or an Assistant class to run for everyone (pkg.module:Class or path/to/file.py:Class).")] = None,
    assistants: Annotated[Optional[str], typer.Option("--assistants", help="Assistant pool: comma-separated Assistant classes and/or Assistant groups (:default, :tutorial, or a group file's key). With more than one, each human keeps one Assistant, balanced across the humans of a study.")] = None,
    no_assistant: Annotated[bool, typer.Option("--no-assistant", help="Run without the Assistant (same as --assistant off).")] = False,
    support_agent: Annotated[Optional[str], typer.Option("--support-agent", hidden=True, help="Old name of --assistant.")] = None,
    no_support_agent: Annotated[bool, typer.Option("--no-support-agent", hidden=True, help="Old name of --no-assistant.")] = False,
    tools: Annotated[Optional[str], typer.Option("--tools", help="Extra tools: comma-separated tool classes (pkg.module:Class or path/to/file.py:Class) and/or tool folders and .py files (every tool in them). Tools with timing 'agent' appear only when the Assistant adds them.")] = None,
    root_path: Annotated[str, typer.Option("--root-path", help="Sub-path the server is mounted under behind a reverse proxy, e.g. /hanplay. Works whether or not the proxy strips the prefix.")] = "",
    study: Annotated[Optional[str], typer.Option("--study", help="Default study for URLs without one, as project/study (see `hani2 study create`). Every study can still be reached at /s/<project>/<study>/.")] = None,
    experiment: Annotated[Optional[str], typer.Option(help="Old name of --study for a study of the default project (an experiment folder).")] = None,
    scenario_set: Annotated[Optional[str], typer.Option("--scenario-set", "--set", help="Scenario set to use (see `hani2 sets`), e.g. HAN2026 or ANAC2027. Admins can still change it per session.")] = None,
    scenario_types: Annotated[Optional[str], typer.Option("--scenario-types", help="Extra scenario types: comma-separated Python files or modules that register them (see the Scenarios guide).")] = None,
    scenarios: Annotated[Optional[Path], typer.Option("--scenarios", help="Folder to load saved scenarios from (instead of the settings' scenarios folder).")] = None,
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
    if root_path:
        os.environ["HANI2_ROOT_PATH"] = root_path
    if experiment:
        os.environ["HANI2_EXPERIMENT"] = experiment
    if study:
        from hani2 import projects

        try:
            projects.parse_ref(study)
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint="--study") from None
        os.environ["HANI2_STUDY"] = study
    if scenario_types:
        os.environ["HANI2_SCENARIO_TYPES"] = scenario_types
    if scenarios:
        if not scenarios.expanduser().is_dir():
            raise typer.BadParameter(f"{scenarios} is not a folder", param_hint="--scenarios")
        os.environ["HANI2_SCENARIOS_BASE"] = str(scenarios.expanduser().resolve())
    if scenario_set:
        from hani2 import scenario_sets

        found = scenario_sets.resolve(scenario_set)
        if not found:
            raise typer.BadParameter(f"unknown scenario set {scenario_set!r}; available: "
                                     f"{', '.join(scenario_sets.set_names())}", param_hint="--scenario-set")
        os.environ["HANI2_SCENARIO_SET"] = found
    if agents and not opponents:
        typer.echo("note: --agents is now --opponents", err=True)
        opponents = agents
    if opponents:
        _check_opponents(opponents)
        os.environ["HANI2_OPPONENTS"] = opponents
    _apply_assistant_choice("off" if (no_assistant or no_support_agent) else _assistant_option(assistant, support_agent))
    if assistants:
        os.environ["HANI2_ASSISTANTS"] = _check_assistants(assistants)
    if tools:
        os.environ["HANI2_TOOLS"] = _check_tools(tools)
    if ctx.invoked_subcommand is not None:
        return
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
    from hani2.support_agent.settings import assistant_mode

    typer.echo(f"version         {__version__}")
    typer.echo(f"home            {home()}")
    typer.echo(f"settings        {settings_dir()}")
    typer.echo(f"scenarios       {scenarios_dir()}")
    typer.echo(f"results         {results_root()}")
    from hani2.projects import default_study

    typer.echo(f"study           {default_study() or '-'}  ({experiment_dir() or 'no study folder'})")
    typer.echo(f"auth mode       {auth_mode()}  (oauth: {', '.join(oauth_providers()) or 'none'})")
    typer.echo(f"assistant       {assistant_mode()}")
    typer.echo(f"assistants      {os.environ.get('HANI2_ASSISTANTS') or 'study / project / assistant_settings.json'}")
    opp = os.environ.get("HANI2_OPPONENTS") or os.environ.get("HANI2_AGENTS")
    from hani2.config import get_env

    opp = opp or ", ".join(get_env("opponents", []) or get_env("agents", []) or []) or "built-in default pool"
    typer.echo(f"opponents       {opp}")


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
    seed: Annotated[int, typer.Option(help="The same seed, type and slot always give the same scenario.")] = 0,
    force: Annotated[bool, typer.Option("--force")] = False,
    scenario_set: Annotated[Optional[str], typer.Option("--set", help="Generate the types of this scenario set (default: the active set).")] = None,
):
    """Generate a pool of scenarios (filtered by opposition level)."""
    from hani2.make_scenarios import generate as _gen

    _gen(types=types, count=count, base=base, human_index=human_index, cache_inverter=cache_inverter,
         rebuild_inverses_only=rebuild_inverses, min_opposition=min_opposition, max_opposition=max_opposition,
         set_reservations=set_reservations, user_reserved_max=user_reserved_max,
         agent_reserved_max=agent_reserved_max, max_tries=max_tries, seed=seed, force=force,
         scenario_set=scenario_set)


@app.command()
def sets(
    name: Annotated[Optional[str], typer.Argument(help="Show only this set.")] = None,
):
    """List the scenario sets, their scenario types and which set is active."""
    from hani2 import scenario_sets
    from hani2 import scenario_store as store
    from hani2.scenarios import registry

    registry.load_plugins()
    all_sets, default = scenario_sets.load_sets()
    raw, _ = scenario_sets.raw_sets()
    set_lower = {k.lower() for k in raw}
    active = scenario_sets.active_set()
    folders = set(store.available_types())
    for set_name, types in all_sets.items():
        if name and set_name.lower() != name.lower():
            continue
        mark = " (active)" if set_name == active else ""
        mark += " (default)" if set_name == default else ""
        refs = [e for e in raw.get(set_name, []) if e.startswith("@") or e.lower() in set_lower]
        if refs:
            mark += "  = " + " + ".join(raw[set_name])
        typer.echo(f"{set_name}{mark}")
        for t in types:
            st = registry.get(t)
            if st is not None:
                title = st.story.title if st.story else "built-in generator" if st.builtin else "registered generator"
            elif t in folders:
                title = "saved scenarios"
            else:
                title = "MISSING: no generator or folder with this name"
            typer.echo(f"  {t:16s} {title}")


@scenario_app.command("new")
def scenario_new(
    type_: Annotated[str, typer.Argument(metavar="TYPE", help="Scenario type to start from (see hani2 sets).")],
    dest: Annotated[Path, typer.Argument(help="Folder to write (for a category: <scenarios>/<Name>/<scenario>).")],
    generate: Annotated[bool, typer.Option("--generate", help="Write a fresh draw of the type's generator "
                                           "instead of its template.")] = False,
    seed: Annotated[int, typer.Option(help="Seed of the draw (with --generate).")] = 0,
    force: Annotated[bool, typer.Option("--force", help="Overwrite DEST.")] = False,
):
    """Write a scenario of TYPE as YAML files to edit by hand."""
    from hani2.config import DEFAULT_SCENARIOS
    from hani2.scenario_store import save_scenario
    from hani2.scenarios import registry

    registry.load_plugins()
    dest = dest.expanduser()
    if dest.exists() and any(dest.iterdir()) and not force:
        typer.echo(f"{dest} exists and is not empty (use --force to overwrite)")
        raise typer.Exit(code=1)
    t = registry.get(type_)
    template = t.story.folder if t and t.story and t.story.folder else DEFAULT_SCENARIOS / type_
    if not generate and template.is_dir():
        shutil.copytree(template, dest, dirs_exist_ok=True)
        typer.echo(f"Copied the {type_} template to {dest}")
    elif t is not None:
        from hani2.make_scenarios import (DEFAULT_MAX_OPPOSITION, DEFAULT_MAX_TRIES, DEFAULT_MIN_OPPOSITION,
                                          make_in_band)

        try:
            s, opp, _ = make_in_band(type_, 0, DEFAULT_MIN_OPPOSITION, DEFAULT_MAX_OPPOSITION, DEFAULT_MAX_TRIES,
                                     seed=seed)
        except RuntimeError:  # no draw in the band: take any
            s, opp, _ = make_in_band(type_, 0, 0.0, 10.0, 1, seed=seed)
        save_scenario(s, dest, info_name="_info.yaml")
        typer.echo(f"Wrote a {type_} scenario (seed {seed}, opposition {opp:.2f}) to {dest}")
    else:
        typer.echo(f"Unknown scenario type {type_!r}. Available: {', '.join(registry.names())}")
        raise typer.Exit(code=2)
    typer.echo("Edit the YAML files, then run: hani2 scenario check " + str(dest))


@scenario_app.command("check")
def scenario_check(
    paths: Annotated[list[Path], typer.Argument(help="Scenario folders, categories or whole scenario directories.")],
    fill_hints: Annotated[bool, typer.Option("--fill-hints", help="Add the computed hints (most and least "
                                             "important issue, ideal deal) that are missing and save.")] = False,
):
    """Check that scenario folders load, can be shown and save back without loss."""
    from hani2 import scenario_store as store
    from hani2.make_scenarios import scenario_opposition
    from hani2.scenarios import registry
    from hani2.scenarios.story import fill_hints as _fill

    registry.load_plugins()
    n_err = n = 0
    for root in paths:
        folders = store.scenario_folders(root)
        if not folders:
            typer.echo(f"{root}: no scenario folders found")
            n_err += 1
        for f in folders:
            n += 1
            s, errors, warnings = store.check_scenario(f)
            if s is not None and fill_hints and not errors:
                _fill(s)
                info_name = next((x for x in store.INFO_FILES if (f / x).exists()), "_info.yaml")
                store.write_info(s.info, f / info_name)
                s, errors, warnings = store.check_scenario(f)
            extra = ""
            if s is not None and not errors:
                try:
                    extra = f" roles={','.join(store.role_names(s))} outcomes={s.outcome_space.cardinality}" \
                            f" opposition={scenario_opposition(s):.2f}"
                except Exception:  # noqa: BLE001
                    pass
            typer.echo(f"{'ERROR' if errors else 'ok   '} {f}{extra}")
            for e in errors:
                typer.echo(f"    error: {e}")
            for w in warnings:
                typer.echo(f"    warning: {w}")
            n_err += bool(errors)
    typer.echo(f"{n} scenario(s), {n_err} with errors")
    if n_err:
        raise typer.Exit(code=1)


@experiment_app.command("create")
def experiment_create(
    name: str,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing files.")] = False,
    assistants: Annotated[Optional[str], typer.Option("--assistants", help="Assistant pool: comma-separated Assistant classes and/or Assistant groups (:default, :tutorial, or a group file's key). With more than one, each human keeps one Assistant, balanced across the humans of a study.")] = None,
    no_assistant: Annotated[bool, typer.Option("--no-assistant", help="Run this experiment without the Assistant (e.g. a competition).")] = False,
    assistant: Annotated[Optional[str], typer.Option("--assistant", help="Assistant for this experiment: on, off, auto, or an Assistant class (pkg.module:Class or path/to/file.py:Class).")] = None,
    no_support_agent: Annotated[bool, typer.Option("--no-support-agent", hidden=True, help="Old name of --no-assistant.")] = False,
    support_agent: Annotated[Optional[str], typer.Option("--support-agent", hidden=True, help="Old name of --assistant.")] = None,
    no_webmcp: Annotated[bool, typer.Option("--no-webmcp", help="Do not expose WebMCP tools to browser agents in this experiment.")] = False,
    opponents: Annotated[Optional[str], typer.Option("--opponents", "--opponent", "-o", help="Opponent agent(s) for this experiment: comma-separated negotiators and/or groups.")] = None,
    tools: Annotated[Optional[str], typer.Option("--tools", help="Extra tools for this experiment: comma-separated tool classes (pkg.module:Class or path/to/file.py:Class) and/or tool folders and .py files.")] = None,
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

    assistant = _assistant_option(assistant, support_agent)
    if no_assistant or no_support_agent:
        assistant = "off"
    if assistant:
        from hani2.support_agent.settings import parse_assistant_choice

        try:
            mode, klass = parse_assistant_choice(assistant)
        except ValueError as e:
            raise typer.BadParameter(str(e), param_hint="--assistant") from None
        sa = {"mode": mode}
        if klass:
            if ".py:" in klass:
                path, _, attr = klass.rpartition(":")
                klass = f"{Path(path).expanduser().resolve()}:{attr}"
            _check_assistant_class(klass)
            sa["agent_class"] = klass
        (exp / "assistant_settings.json").write_text(_json.dumps(sa, indent=2))
        if mode == "off":
            (exp / "autopilot_settings.json").write_text(_json.dumps({"allowed": False}, indent=2))
            typer.echo("  assistant: off (assistant_settings.json), autopilot: off")
        else:
            typer.echo(f"  assistant: {mode}{' using ' + klass if klass else ''} (assistant_settings.json)")
    if no_webmcp or opponents or tools:
        envf = exp / "env.json"
        env = _json.loads(envf.read_text()) if envf.exists() else {}
        if no_webmcp:
            env["webmcp"] = {"enabled": False}
            typer.echo("  WebMCP: off (env.json)")
        if tools:
            env.setdefault("tools", {})
            extra = list(env["tools"].get("extra") or [])
            extra += [t for t in _check_tools(tools).split(",") if t not in extra]
            env["tools"]["extra"] = extra
            typer.echo(f"  tools: {', '.join(extra)} (env.json)")
        if opponents:
            _check_opponents(opponents)
            env["opponents"] = [o.strip() for o in opponents.split(",") if o.strip()]
            typer.echo(f"  opponents: {', '.join(env['opponents'])} (env.json)")
        envf.write_text(_json.dumps(env, indent=2))
    typer.echo(f"Created experiment at {exp}")
    typer.echo(f"Run it with:  hani2 --experiment {name}   (it is the study default/{name}: /s/default/{name}/play)")


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


# --------------------------------------------------------------------------- #
# hani2 replay                                                                 #
# --------------------------------------------------------------------------- #
PathsArg = Annotated[Optional[list[Path]], typer.Argument(help="Recording files or folders (default: every recording in the results folder).")]


def _paths(paths: Optional[list[Path]]) -> list[Path]:
    if paths:
        return [p.expanduser() for p in paths]
    from hani2.config import results_root

    return [results_root()]


def _parse_options(option: Optional[list[str]]) -> dict:
    import json

    out: dict = {}
    for o in option or []:
        k, _, v = o.partition("=")
        try:
            out[k.strip()] = json.loads(v)
        except Exception:
            out[k.strip()] = v
    return out


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _write_table(rows: list[dict], columns: list[str], out: Optional[Path]) -> None:
    import csv
    import json
    import sys

    if out is None:
        widths = {c: max([len(c)] + [min(40, len(_fmt(r.get(c)))) for r in rows]) for c in columns}
        typer.echo("  ".join(c.ljust(widths.get(c, len(c))) for c in columns))
        for r in rows:
            typer.echo("  ".join(_fmt(r.get(c))[:40].ljust(widths.get(c, 0)) for c in columns))
        return
    if out.suffix == ".json":
        out.write_text(json.dumps(rows, indent=1, default=str))
    else:
        with (out.open("w", newline="") if str(out) != "-" else sys.stdout) as fh:
            w = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    typer.echo(f"wrote {out}", err=True)


@replay_app.command("list")
def replay_list(paths: PathsArg = None,
                all: Annotated[bool, typer.Option("--all", help="Include recordings where no negotiation started.")] = False):
    """List recordings."""
    from hani2.recording import Recording, iter_recordings

    rows = []
    for root in _paths(paths):
        for f in iter_recordings(root):
            try:
                r = Recording.load(f)
            except Exception as e:  # noqa: BLE001
                typer.secho(f"{f}: {e}", fg="red", err=True)
                continue
            if r.start is None and not all:
                continue
            st, sm = r.start or {}, r.summary or {}
            rows.append(dict(id=r.id, user=(r.header.get("session") or {}).get("user"), scenario=(r.scenario or {}).get("name"),
                             opponent=st.get("opponent"), status=sm.get("status") or ("incomplete" if not r.complete else "-"),
                             utility=sm.get("human_utility"), seconds=round(r.duration, 1), events=len(r.events)))
    _write_table(rows, ["id", "user", "scenario", "opponent", "status", "utility", "seconds", "events"], None)
    typer.echo(f"{len(rows)} recording(s)", err=True)


@replay_app.command("show")
def replay_show(path: Path, events: Annotated[bool, typer.Option("--events", help="Print every event.")] = False):
    """Summarise one recording (what was recorded, the result)."""
    import collections
    import json

    from hani2.recording import Recording

    r = Recording.load(path)
    sess = r.header.get("session") or {}
    typer.secho(f"{r.id}", bold=True)
    typer.echo(f"  user {sess.get('user')}  mode {sess.get('mode')}  created {r.header.get('created')}  "
               f"duration {r.duration:.1f}s  complete {r.complete}")
    sc = r.scenario or {}
    typer.echo(f"  scenario {sc.get('name')}  outcomes {sc.get('n_outcomes')}  human seat {sc.get('human_id')}")
    st = r.start or {}
    typer.echo(f"  opponent {st.get('opponent')}  assistant {(st.get('support_agent') or {}).get('name')}")
    typer.echo(f"  result {json.dumps(r.summary, default=str)}")
    c = collections.Counter(e.get("k") for e in r.events)
    typer.echo("  records " + ", ".join(f"{k}={v}" for k, v in c.most_common()))
    tel = collections.Counter(t for _, t, _ in r.telemetry())
    if tel:
        typer.echo("  telemetry " + ", ".join(f"{k}={v}" for k, v in tel.most_common()))
    if events:
        for e in r.events:
            e2 = {k: v for k, v in e.items() if k not in ("full", "delta")}
            typer.echo(f"  {e.get('t', 0):8.3f} {e.get('k'):<10} {json.dumps(e2, default=str)[:200]}")


@replay_app.command("metrics")
def replay_metrics():
    """List the evaluation metrics."""
    from hani2.evaluation import available_metrics

    for m in available_metrics():
        flag = " (LLM)" if m["needs_llm"] else ""
        dflt = "" if m["default"] else " [not default]"
        typer.secho(f"{m['name']}  — {m['kind']}{flag}{dflt}", bold=True)
        typer.echo(f"    {m['description'].splitlines()[0] if m['description'] else ''}")
        for c in m["columns"]:
            typer.echo(f"      {c['name']:<34} {c['description']}")


MetricsOpt = Annotated[Optional[str], typer.Option("--metrics", "-m", help="Comma-separated metric names (default: every default metric; see `hani2 replay metrics`).")]
LlmOpt = Annotated[bool, typer.Option("--llm", help="Also run the LLM-judged (soft) metrics.")]
OptionOpt = Annotated[Optional[list[str]], typer.Option("--option", help="Metric option key=value (value as JSON), e.g. click_through_seconds=2.")]


@replay_app.command("evaluate")
def replay_evaluate(
    paths: PathsArg = None,
    metrics: MetricsOpt = None,
    llm: LlmOpt = False,
    refresh: Annotated[bool, typer.Option(help="Ask the LLM judge again instead of using cached judgements.")] = False,
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="Write the table to a .csv or .json file.")] = None,
    columns: Annotated[Optional[str], typer.Option(help="Comma-separated columns to show.")] = None,
    option: OptionOpt = None,
):
    """Compute evaluation metrics for recordings."""
    from hani2.evaluation import evaluate_paths

    res = evaluate_paths(_paths(paths), metrics.split(",") if metrics else None, use_llm=llm, refresh=refresh,
                         options=_parse_options(option))
    for k, errs in res["errors"].items():
        typer.secho(f"{k}: {errs}", fg="yellow", err=True)
    cols = ["id", "user", "scenario", "opponent"] + [c["name"] for c in res["columns"]]
    if columns:
        cols = ["id"] + [c for c in columns.split(",") if c]
    elif out is None:
        cols = cols[:12]
        typer.echo("(showing the first columns; use --out or --columns for more)", err=True)
    _write_table(res["rows"], cols, out)


@replay_app.command("compare")
def replay_compare(
    paths: PathsArg = None,
    by: Annotated[str, typer.Option(help="Group by: opponent, support_agent (the Assistant), user, scenario, experiment, …")] = "opponent",
    metrics: MetricsOpt = None,
    llm: LlmOpt = False,
    out: Annotated[Optional[Path], typer.Option("--out", "-o", help="Write the group table to a .csv or .json file.")] = None,
    columns: Annotated[Optional[str], typer.Option(help="Comma-separated columns to show.")] = None,
    option: OptionOpt = None,
):
    """Compare groups of recordings (mean per group, scenario-balanced means and pass^k)."""
    from hani2.evaluation import compare_rows, evaluate_paths

    opts = _parse_options(option)
    res = evaluate_paths(_paths(paths), metrics.split(",") if metrics else None, use_llm=llm, options=opts)
    numeric = [c for c in res["columns"] if any(isinstance(r.get(c["name"]), (int, float)) and not isinstance(r.get(c["name"]), bool) for r in res["rows"])]
    cmp = compare_rows(res["rows"], by=by, columns=numeric, success=str(opts.get("success", "agreement")),
                       success_threshold=opts.get("success_threshold"))
    names = [c for c in (columns.split(",") if columns else [c["name"] for c in numeric])]
    rows = [dict(group=g["group"], n=g["n"], **{c: g["mean"].get(c) for c in names}) for g in cmp["groups"]]
    shown = ["group", "n"] + (names if out is not None or columns else names[:10])
    _write_table(rows, shown, out)
    if cmp["reliability"]:
        typer.echo("\npass^k (success = %s):" % cmp["success"])
        _write_table(cmp["reliability"], ["group", "k", "pass_hat_k", "scenarios"], None)


@replay_app.command("export")
def replay_export(path: Path, out: Annotated[Path, typer.Option("--out", "-o", help="JSON file to write.")]):
    """Write a recording as plain JSON (header + events)."""
    import json

    from hani2.recording import Recording

    out.write_text(json.dumps(Recording.load(path).to_json(), default=str))
    typer.echo(f"wrote {out}")


@replay_app.command("open")
def replay_open(
    paths: PathsArg = None,
    port: Annotated[int, typer.Option("--port", "-p")] = 5006,
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    open_browser: Annotated[bool, typer.Option("--browser/--no-browser")] = True,
):
    """Start the server and open the replay tool (also showing recordings in PATHS)."""
    if paths:
        os.environ["HANI2_REPLAY_DIRS"] = os.pathsep.join(str(p.expanduser().resolve()) for p in paths)
    _serve(host, port, "/replay" if open_browser else None)




# --------------------------------------------------------------------------- #
# Tools                                                                        #
# --------------------------------------------------------------------------- #
_TOOL_TEMPLATE = '''"""{title}: {doc}"""

from hani2.tools import Tool, ui


class {cls}(Tool):
    name = "{title}"
    description = "One line saying what {title} does."
    help = """
    **What it shows.** Describe what the participant sees.

    **How to use it.** Describe the controls and how the numbers are worked out.
    """
    icon = "wrench"
    pane = "side"  # upper, lower or side
    timing = "start"  # always, load, start or end

    def view(self):
        offers = len(self.trace())
        return [ui.stat("Offers so far", offers)]
'''

_LLM_TOOL_TEMPLATE = '''"""{title}: {doc}"""

from hani2.tools import LLMTool


class {cls}(LLMTool):
    name = "{title}"
    description = "One line saying what {title} does."
    help = """
    **What it does.** Describe what the participant gets.

    **How it works.** Pressing the button sends the issues and the offers so far to the
    language model with the instructions below; the reply is shown here.
    """
    icon = "sparkles"
    button_label = "Ask"
    prompt = """You help a person who is negotiating. Answer in at most five short bullet points."""
'''


@tools_app.command("list")
def tools_list():
    """List every tool the server would offer, with where it comes from."""
    from hani2.tools.registry import SOURCES, discover_tool_classes, tool_specs

    specs = {s.cls: s for s in tool_specs()}
    for cls in discover_tool_classes():
        spec = specs.get(cls)
        state = "disabled in env.json" if spec is None else (
            f"{spec.pane}/{spec.timing}" + (" admin-only" if spec.admin_only else "") + ("" if spec.enabled else " off"))
        typer.echo(f"{(cls.name or cls.__name__):28} {state:24} {SOURCES.get(cls, '?')}")
        if not (cls.help or "").strip():
            typer.secho(f"{'':28} (no help text: add a `help` attribute)", fg="yellow")


@tools_app.command("path")
def tools_path():
    """Show the folders searched for tool files."""
    from hani2.tools.registry import tool_paths

    for p in tool_paths():
        typer.echo(f"{p}{'' if p.exists() else '  (missing)'}")


@tools_app.command("new")
def tools_new(
    name: Annotated[str, typer.Argument(help="The tool's title, e.g. \"Deal Summary\".")],
    llm: Annotated[bool, typer.Option("--llm", help="Start from LLMTool (a tool that asks the language model).")] = False,
    folder: Annotated[Optional[Path], typer.Option(help="Where to write the file (default: the tools folder).")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
):
    """Create a new tool file, ready to edit, in the tools folder."""
    import re

    from hani2.tools.registry import tools_dir

    words = re.findall(r"[A-Za-z0-9]+", name)
    if not words:
        raise typer.BadParameter("the name needs at least one letter or digit")
    cls = "".join(w[:1].upper() + w[1:] for w in words)
    if cls[0].isdigit():
        cls = "Tool" + cls
    target_dir = (folder or tools_dir()).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / ("_".join(w.lower() for w in words) + ".py")
    if path.exists() and not force:
        typer.secho(f"{path} exists (use --force to overwrite)", fg="red")
        raise typer.Exit(1)
    template = _LLM_TOOL_TEMPLATE if llm else _TOOL_TEMPLATE
    doc = "a tool that asks the language model." if llm else "a HANI2 tool."
    path.write_text(template.format(title=name.strip(), cls=cls, doc=doc))
    typer.echo(f"Created {path}")
    if folder is not None and folder.expanduser().resolve() != tools_dir().resolve():
        typer.echo(f"Start the server with `hani2 --tools {target_dir}` to load it.")
    else:
        typer.echo("New sessions pick it up; edit it and open a new session to see your changes.")


# --------------------------------------------------------------------------- #
# Projects and studies                                                         #
# --------------------------------------------------------------------------- #
def _ref(value: str):
    from hani2 import projects

    try:
        ref = projects.parse_ref(value)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    if ref is None:
        raise typer.BadParameter("give a study as project/study")
    return ref


def _echo_mapping(data: dict, indent: str = "  ") -> None:
    for k, v in data.items():
        if v in (None, "", {}, []):
            continue
        typer.echo(f"{indent}{k:20s} {v}")


@project_app.command("create")
def project_create(
    name: str,
    full_name: Annotated[Optional[str], typer.Option("--full-name", help="Full name shown to participants.")] = None,
    kind: Annotated[Optional[str], typer.Option(help="What is evaluated: opponent, assistant or none (default none).")] = None,
    description: Annotated[Optional[str], typer.Option("--description", help="Short description.")] = None,
    link: Annotated[Optional[str], typer.Option(help="Web page of the project.")] = None,
    year: Annotated[Optional[int], typer.Option(help="Year of the project.")] = None,
    organizer: Annotated[Optional[str], typer.Option(help="Who runs it.")] = None,
    contact: Annotated[Optional[str], typer.Option(help="Contact for participants (e-mail).")] = None,
):
    """Create a project (or update its project.yaml)."""
    from hani2 import projects

    try:
        pr = projects.create_project(name, full_name=full_name, kind=kind, short_description=description, link=link,
                                     year=year, organizer=organizer, contact=contact)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    typer.echo(f"Project {pr.name} at {projects.project_dir(pr.name)}")
    typer.echo(f"Add a study with:  hani2 study create {pr.name}/<study> --type prolific|online|lab")


@project_app.command("list")
def project_list():
    """List projects and their studies."""
    from hani2 import projects

    for name in projects.list_projects():
        pr = projects.load_project(name)
        studies = projects.list_studies(name)
        typer.echo(f"{name:24s} {pr.kind:9s} {len(studies)} stud{'y' if len(studies) == 1 else 'ies'}"
                   + (f"  {pr.full_name}" if pr.full_name else ""))


@project_app.command("show")
def project_show(name: str):
    """Show a project's settings and studies."""
    from hani2 import projects

    if not projects.project_exists(name):
        raise typer.BadParameter(f"no project {name!r}")
    pr = projects.load_project(name)
    typer.echo(f"{name}  ({pr.path or 'no folder: uses the settings folder'})")
    _echo_mapping({k: v for k, v in pr.to_dict().items() if k != "name"})
    for st in projects.list_studies(name):
        typer.echo(f"  study {st}")


@study_app.command("create")
def study_create(
    ref: Annotated[str, typer.Argument(help="project/study (a bare name is a study of the default project).")],
    type: Annotated[Optional[str], typer.Option("--type", help="prolific, online or lab (default prolific; kept when updating).")] = None,
    title: Annotated[Optional[str], typer.Option(help="Title shown to participants.")] = None,
    completion_code: Annotated[Optional[str], typer.Option("--completion-code", help="Completion code (Prolific).")] = None,
    completion_url: Annotated[Optional[str], typer.Option("--completion-url", help="Where participants go at the end ({pid} is the participant id).")] = None,
    prolific_study_id: Annotated[Optional[str], typer.Option("--prolific-study-id", help="The Prolific study id.")] = None,
    link: Annotated[Optional[str], typer.Option(help="Web page of the study.")] = None,
    start: Annotated[Optional[str], typer.Option(help="Start date (YYYY-MM-DD).")] = None,
    end: Annotated[Optional[str], typer.Option(help="End date (YYYY-MM-DD).")] = None,
    n_required: Annotated[Optional[int], typer.Option("--n-required", help="Counted negotiations per participant.")] = None,
    end_text: Annotated[Optional[str], typer.Option("--end-text", help="Text of the end page (may use {{variables}}).")] = None,
    base_url: Annotated[Optional[str], typer.Option("--base-url", help="Public address of this server for the printed links (default: HANI2_PUBLIC_URL).")] = None,
):
    """Create a study (or update its study.yaml) and print the links to give participants."""
    from hani2 import projects

    r = _ref(ref)
    try:
        st = projects.create_study(r, type=type, title=title, completion_code=completion_code,
                                   completion_url=completion_url, prolific_study_id=prolific_study_id, link=link,
                                   start=start, end=end, n_required=n_required, end_text=end_text)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    typer.echo(f"Study {r} ({st.type}) at {st.path}")
    _print_links(r, base_url)


def _print_links(r, base_url: Optional[str]) -> None:
    from hani2 import projects

    links = projects.participant_links(r, (base_url or projects.public_base_url()))
    labels = {"prolific": "Prolific study URL", "participant": "Participant link", "session_code": "Session-code link",
              "play": "Play page", "app": "App (log in)"}
    for k in ("prolific", "participant", "session_code", "play", "app"):
        if k in links:
            typer.echo(f"  {labels[k]:20s} {links[k]}")


@study_app.command("list")
def study_list(project: Annotated[Optional[str], typer.Argument(help="Only this project.")] = None):
    """List studies (project/study, type, participants)."""
    from hani2 import projects

    names = [project] if project else projects.list_projects()
    for p in names:
        for s in projects.list_studies(p):
            r = projects.StudyRef(p, s)
            st = projects.load_study(r)
            res = projects.study_dir(r) / "results"
            n = len(list(res.glob("*/results.csv"))) if res.is_dir() else 0
            typer.echo(f"{str(r):36s} {st.type:9s} {n} participant(s)" + ("  (experiment folder)" if st.legacy else ""))


@study_app.command("show")
def study_show(
    ref: str,
    base_url: Annotated[Optional[str], typer.Option("--base-url", help="Public address of this server.")] = None,
):
    """Show a study's settings and the links to give participants."""
    from hani2 import projects

    r = _ref(ref)
    if not projects.study_exists(r):
        raise typer.BadParameter(f"no study {r}")
    st = projects.load_study(r)
    typer.echo(f"{r}  ({st.path})")
    _echo_mapping({k: v for k, v in st.to_dict().items() if k not in ("name", "project")})
    _print_links(r, base_url)


@groups_app.command("list")
def groups_list(
    project: Annotated[Optional[str], typer.Option("--project", help="List the groups of this project (its folder, its studies and the settings folder).")] = None,
    study: Annotated[Optional[str], typer.Option("--study", help="List the groups as this study (project/study) resolves them (default: the default study).")] = None,
    kind: Annotated[Optional[str], typer.Option("--kind", help="opponent or assistant (default: both).")] = None,
    builtin: Annotated[bool, typer.Option("--builtin/--no-builtin", help="Include the built-in groups.")] = True,
):
    """List opponent and Assistant groups with their members and where they come from."""
    from hani2 import groups, projects

    try:
        kinds = [groups.check_kind(kind)] if kind else list(groups.KINDS)
        kw: dict = {"project": project} if project else {"ref": projects.parse_ref(study) if study else None}
    except ValueError as e:
        raise typer.BadParameter(str(e)) from None
    for k in kinds:
        typer.secho(f"{k.capitalize()} groups", bold=True)
        items = groups.list_groups(k, include_builtin=builtin, **kw)
        if not items:
            typer.echo("  (none)")
        for g in items:
            where = g["path"] or "built-in"
            mark = " (shadowed)" if g.get("active") is False else ""
            typer.echo(f"  :{g['key']:<22s} {g['source']:<10s} {where}{mark}")
            if g.get("description"):
                typer.echo(f"      {g['description']}")
            members = g["members"]
            shown = ", ".join(members[:8]) + (f", … (+{len(members) - 8})" if len(members) > 8 else "")
            typer.echo(f"      members: {shown or '-'}")
            if g.get("assistant"):
                typer.echo(f"      assistant: {g['assistant']}")


if __name__ == "__main__":  # pragma: no cover
    app()
