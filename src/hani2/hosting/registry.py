"""Registered hosted agents of a project: ``<project>/hosted_agents.json``.

Each entry: ``{name, kind: assistant|opponent, url, token, team, enabled, timeout, added}``. A spec
``remote:<name>`` names an entry of the current study's project. The tokens never leave the server:
:func:`public` drops them for the console and the CLI.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hani2.hosting.protocol import (DEFAULT_TIMEOUT, KINDS, REMOTE_PREFIX, Endpoint, HostedError, _check_url,
                                    is_direct_address, normalise_spec, parse_direct, valid_name)

FILE = "hosted_agents.json"
_lock = threading.Lock()


def path(project: str) -> Path:
    from hani2 import projects

    return projects.project_dir(projects.check_name(project, "project")) / FILE


def _read(project: str) -> list[dict]:
    p = path(project)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError):
        return []
    items = data.get("agents") if isinstance(data, dict) else data
    return [e for e in items or [] if isinstance(e, dict) and valid_name(e.get("name"))]


def _write(project: str, entries: list[dict]) -> None:
    p = path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"agents": entries}, indent=1))
    try:
        os.chmod(tmp, 0o600)  # it holds the teams' tokens
    except OSError:
        pass
    tmp.replace(p)


def entries(project: str, kind: str | None = None, *, enabled_only: bool = False) -> list[dict]:
    out = _read(project)
    if kind:
        out = [e for e in out if e.get("kind") == kind]
    if enabled_only:
        out = [e for e in out if e.get("enabled", True)]
    return out


def public(e: dict) -> dict:
    """An entry without its token (``has_token`` says whether it has one)."""
    d = {k: v for k, v in e.items() if k != "token"}
    d["has_token"] = bool(e.get("token"))
    d["spec"] = REMOTE_PREFIX + str(e.get("name"))
    return d


def get(project: str, name: str) -> dict | None:
    return next((e for e in _read(project) if e.get("name") == name), None)


def new_token() -> str:
    return "h2t_" + secrets.token_urlsafe(24)


def add(project: str, name: str, kind: str, url: str, *, token: str | None = None, team: str = "",
        timeout: float | None = None, replace: bool = False, enabled: bool = True) -> tuple[dict, str]:
    """Register (or with ``replace`` update) an endpoint; returns ``(entry, token)``. Without ``token`` a
    new one is made: give it to the team, who start their host with it."""
    if not valid_name(name):
        raise ValueError(f"invalid name {name!r}: use letters, digits, '.', '_' and '-'")
    if kind not in KINDS:
        raise ValueError(f"kind must be assistant or opponent (got {kind!r})")
    try:
        url = _check_url(str(url).strip())
    except HostedError as e:
        raise ValueError(str(e)) from None
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0 or timeout > 600):
        raise ValueError("timeout must be a number of seconds in (0, 600]")
    with _lock:
        items = _read(project)
        old = next((e for e in items if e.get("name") == name), None)
        if old is not None and not replace:
            raise ValueError(f"{name!r} is already registered (use replace to change it)")
        tok = token or (old or {}).get("token") or new_token()
        e = {"name": name, "kind": kind, "url": url, "token": tok, "team": str(team or ""), "enabled": bool(enabled),
             "timeout": float(timeout) if timeout else (old or {}).get("timeout"),
             "added": (old or {}).get("added") or datetime.now(timezone.utc).replace(microsecond=0).isoformat()}
        items = [x for x in items if x.get("name") != name] + [e]
        _write(project, items)
    return e, tok


def remove(project: str, name: str) -> bool:
    with _lock:
        items = _read(project)
        keep = [e for e in items if e.get("name") != name]
        if len(keep) == len(items):
            return False
        _write(project, keep)
    return True


def set_enabled(project: str, name: str, on: bool) -> bool:
    with _lock:
        items = _read(project)
        hit = False
        for e in items:
            if e.get("name") == name:
                e["enabled"] = bool(on)
                hit = True
        if hit:
            _write(project, items)
    return hit


def endpoint_of(e: dict, timeout: float | None = None) -> Endpoint:
    return Endpoint(name=REMOTE_PREFIX + str(e["name"]), url=str(e["url"]), token=e.get("token") or None,
                    kind=e.get("kind"), timeout=float(e.get("timeout") or timeout or DEFAULT_TIMEOUT),
                    team=str(e.get("team") or ""))


def _project() -> str | None:
    try:
        from hani2 import projects

        return projects.current_project_name()
    except Exception:  # noqa: BLE001
        return None


def resolve(spec: Any, *, project: str | None = None, kind: str | None = None,
            timeout: float | None = None) -> Endpoint:
    """The :class:`Endpoint` of a hosted spec. ``remote:<name>`` is looked up in ``project`` (default:
    the current study's project); a direct address is parsed. Raises :class:`HostedError`."""
    spec = normalise_spec(spec)
    s = str(spec).strip()
    if timeout is None:
        timeout = hosted_settings().get("timeout")
    if is_direct_address(s):
        ep = parse_direct(s, timeout)
        ep.kind = kind
        return ep
    if not s.lower().startswith(REMOTE_PREFIX):
        raise HostedError(f"{s!r} is not a hosted agent")
    name = s[len(REMOTE_PREFIX):]
    project = project or _project()
    e = get(project, name) if project else None
    if e is None:
        raise HostedError(f"no hosted agent {name!r} is registered for project {project!r} "
                          "(`hani2 hosted add` or the admin console)")
    if not e.get("enabled", True):
        raise HostedError(f"the hosted agent {name!r} is switched off")
    if kind and e.get("kind") and e["kind"] != kind:
        raise HostedError(f"{name!r} is registered as an {e['kind']}, not an {kind}")
    return endpoint_of(e, timeout)


# --------------------------------------------------------------------------- #
# The self-hosted mode of a project / study                                    #
# --------------------------------------------------------------------------- #
HOSTED_KEYS = ("assistants", "opponents", "timeout", "max_failures")
HOSTED_DEFAULTS: dict[str, Any] = {"assistants": False, "opponents": False, "timeout": DEFAULT_TIMEOUT,
                                   "max_failures": 3}


def check_hosted_block(v: Any, where: str = "hosted") -> list[str]:
    """What is wrong with a ``hosted:`` block (``[]``: nothing)."""
    if v is None:
        return []
    if not isinstance(v, dict):
        return [f"'{where}' must be a mapping like {{assistants: true, opponents: false, timeout: 30}}"]
    out = []
    unknown = sorted(set(v) - set(HOSTED_KEYS))
    if unknown:
        out.append(f"'{where}': unknown key(s) {', '.join(unknown)}; use {', '.join(HOSTED_KEYS)}")
    for k in ("assistants", "opponents"):
        if k in v and not isinstance(v[k], bool):
            out.append(f"'{where}.{k}' must be true or false")
    t = v.get("timeout")
    if t is not None and (isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 < t <= 600):
        out.append(f"'{where}.timeout' must be a number of seconds in (0, 600]")
    m = v.get("max_failures")
    if m is not None and (isinstance(m, bool) or not isinstance(m, int) or m < 1):
        out.append(f"'{where}.max_failures' must be a whole number ≥ 1")
    return out


def hosted_settings(ref: Any = None) -> dict[str, Any]:
    """The ``hosted:`` block in effect (the study's over the project's), with defaults."""
    try:
        from hani2 import projects

        v = projects.setting("hosted", None, ref=ref) if ref is not None else projects.setting("hosted", None)
    except Exception:  # noqa: BLE001
        v = None
    out = dict(HOSTED_DEFAULTS)
    if isinstance(v, dict) and not check_hosted_block(v):
        out.update({k: v[k] for k in HOSTED_KEYS if v.get(k) is not None})
    return out


def hosted_pool(kind: str, ref: Any = None) -> list[str]:
    """``remote:<name>`` of every enabled registered agent of ``kind`` when the study's ``hosted`` block
    makes that side self-hosted, else ``[]``."""
    s = hosted_settings(ref)
    if not s.get("assistants" if kind == "assistant" else "opponents"):
        return []
    project = getattr(ref, "project", None) or _project()
    if not project:
        return []
    return [REMOTE_PREFIX + e["name"] for e in entries(project, kind, enabled_only=True)]
