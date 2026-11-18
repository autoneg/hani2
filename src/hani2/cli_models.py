"""``hani2 connections`` and ``hani2 models``: sign in to language-model providers and see
which model each purpose resolves to (see :mod:`hani2.connections`, :mod:`hani2.model_chain`)."""

from __future__ import annotations

import json
import time
from typing import Annotated, Optional

import typer

connections_app = typer.Typer(help="Connections to language-model providers: list, add, test, sign in, remove.")
models_app = typer.Typer(help="Model chains: list them per purpose and see which entry a study resolves to.")


def _fail(msg: str) -> None:
    typer.secho(f"error: {msg}", fg="red", err=True)
    raise typer.Exit(1)


@connections_app.command("list")
def connections_list(all_: Annotated[bool, typer.Option("--all", help="Also list the implicit connections.")] = False):
    """List the connections (keys are never shown)."""
    from hani2 import connections as conns

    for c in conns.all_connections(include_implicit=all_):
        d = conns.public(c)
        state = "ready" if d["credentials"] else f"not ready: {d['credentials_reason']}"
        extra = f" key={d['api_key']}" if d.get("api_key") else (f" env={d['api_key_env']}" if d.get("api_key_env") else "")
        imp = " (implicit)" if c.implicit else ""
        typer.echo(f"{c.name:<20} {c.provider:<18} {c.auth:<12} {c.base or '-':<34}{extra}{imp}  [{state}]")


@connections_app.command("providers")
def connections_providers():
    """The providers and the sign-in methods each supports."""
    from hani2 import providers as prov

    for p in prov.table():
        typer.echo(f"{p['id']:<18} {', '.join(p['auth']):<36} {p['label']}")
        if p["no_subscription"] and "subscription" not in p["auth"]:
            typer.echo(f"{'':<18} no subscription: {p['no_subscription']}")


@connections_app.command("add")
def connections_add(
    name: str,
    provider: Annotated[str, typer.Option("--provider", "-p", help="anthropic, openai, ollama_cloud, ollama, github_copilot, … (see `hani2 connections providers`).")],
    auth: Annotated[Optional[str], typer.Option("--auth", help="api_key, api_key_env, subscription or none (default: the provider's first).")] = None,
    api_key_env: Annotated[Optional[str], typer.Option("--api-key-env", help="Environment variable that holds the key (auth api_key_env).")] = None,
    key: Annotated[bool, typer.Option("--key", help="Ask for an API key and store it (auth api_key).")] = False,
    base_url: Annotated[Optional[str], typer.Option("--base-url", help="Address of the provider's API.")] = None,
    litellm_provider: Annotated[Optional[str], typer.Option("--litellm-provider", help="For provider litellm: litellm's provider name.")] = None,
    replace: Annotated[bool, typer.Option("--replace", help="Change an existing connection.")] = False,
):
    """Add a connection. Keys are stored only in the settings folder (0600)."""
    from hani2 import connections as conns

    if key and auth is None:
        auth = "api_key"
    secret = typer.prompt("API key", hide_input=True) if auth == "api_key" else None
    data = {"name": name, "provider": provider, "auth": auth, "base_url": base_url, "api_key_env": api_key_env,
            "litellm_provider": litellm_provider}
    try:
        c = conns.add({k: v for k, v in data.items() if v}, api_key=secret, replace=replace)
    except conns.ConnectionError_ as e:
        _fail(str(e))
        return
    typer.echo(f"added {c.name} ({c.provider}, {c.auth})")
    if c.auth == "subscription":
        typer.echo(f"sign in with: hani2 connections login {c.name}")


@connections_app.command("remove")
def connections_remove(name: str):
    """Remove a connection and its stored key and tokens."""
    from hani2 import connections as conns

    if not conns.remove(name):
        _fail(f"no connection named {name!r}")
    typer.echo(f"removed {name}")


@connections_app.command("test")
def connections_test(name: str, model: Annotated[Optional[str], typer.Option("--model", "-m", help="Check this model.")] = None):
    """Check a connection now (and a model, if given)."""
    from hani2 import connections as conns

    c = conns.get(name)
    if c is None:
        _fail(f"no connection named {name!r}")
        return
    conns.forget_probes(name)
    if model:
        p = conns.probe(c, model, fresh=True)
        typer.echo(f"{name}:{model}: {'available' if p.ok else 'not available: ' + p.reason}"
                   + ("" if p.verified or not p.ok else " (credentials only)"))
        raise typer.Exit(0 if p.ok else 1)
    ok, why = conns.has_credentials(c)
    if not ok:
        _fail(why)
    models = conns.list_models(c)
    typer.echo(f"{name}: credentials present" + (f"; {len(models)} models: {', '.join(models[:20])}" if models else ""))


@connections_app.command("login")
def connections_login(name: str, timeout: Annotated[int, typer.Option(help="Seconds to wait.")] = 900):
    """Sign in to a subscription connection with a device code."""
    from hani2 import connections as conns

    try:
        st = conns.start_login(name)
    except Exception as e:  # noqa: BLE001
        _fail(conns.redact(str(e)))
        return
    typer.echo(f"Open {st['verification_uri']} and enter the code {st['user_code']}")
    typer.echo("Device codes are a common phishing target: never share this code.")
    end = time.time() + timeout
    while time.time() < end:
        time.sleep(st.get("interval", 5))
        r = conns.poll_login(name)
        if r["status"] == "connected":
            typer.echo(f"signed in: {name}")
            return
        if r["status"] in ("expired", "denied", "none"):
            _fail(f"sign-in {r['status']}")
    _fail("timed out")


@connections_app.command("logout")
def connections_logout(name: str):
    """Forget a subscription connection's tokens."""
    from hani2 import connections as conns

    conns.logout(name)
    typer.echo(f"signed out: {name}")


def _bound(study: Optional[str]):
    import contextlib

    from hani2 import projects

    if not study:
        return contextlib.nullcontext()
    try:
        ref = projects.parse_ref(study)
    except ValueError as e:
        _fail(str(e))
    if ref is None or not projects.study_exists(ref):
        _fail(f"unknown study {study!r}")
    return projects.use_study(ref)


StudyOpt = Annotated[Optional[str], typer.Option("--study", help="Resolve as a session of this study (project/study).")]


@models_app.command("list")
def models_list(study: StudyOpt = None, as_json: Annotated[bool, typer.Option("--json")] = False):
    """The chain every purpose uses, and where it comes from."""
    from hani2 import model_chain

    with _bound(study):
        eff = model_chain.effective_chains()
    if as_json:
        typer.echo(json.dumps(eff, indent=2))
        return
    for purpose, d in eff.items():
        typer.echo(f"{purpose} (from {d['source'] or '-'}{', old settings' if d['implicit'] else ''}):")
        for i, e in enumerate(d["entries"], 1):
            params = f" {json.dumps(e['params'])}" if e.get("params") else ""
            typer.echo(f"  {i}. {e.get('connection') or e.get('provider')}:{e['model']}{params}"
                       + (f"  ({e['label']})" if e.get("label") else ""))


@models_app.command("resolve")
def models_resolve(study: StudyOpt = None,
                   purpose: Annotated[Optional[str], typer.Option("--purpose", help="Only this purpose.")] = None,
                   as_json: Annotated[bool, typer.Option("--json")] = False):
    """Which entry each purpose would use now (checks the providers)."""
    from hani2 import connections as conns
    from hani2 import model_chain

    purposes = [purpose] if purpose else list(model_chain.PURPOSES)
    out = {}
    with _bound(study):
        conns.forget_probes()
        for p in purposes:
            if p not in model_chain.PURPOSES:
                _fail(f"unknown purpose {p!r}; use {', '.join(model_chain.PURPOSES)}")
            out[p] = model_chain.resolve(p, fresh=True).record()
    if as_json:
        typer.echo(json.dumps(out, indent=2))
        return
    bad = False
    for p, r in out.items():
        if r["status"] == "none":
            bad = True
            typer.echo(f"{p:<10} NONE  {r['error']}")
        else:
            typer.echo(f"{p:<10} {r['connection']}:{r['model']}  (#{r['position']} of {r['source']}, {r['status']})")
        for s in r["skipped"]:
            typer.echo(f"{'':<12}skipped #{s['position']} {s['entry']}: {s['reason']}")
    if bad:
        raise typer.Exit(1)
