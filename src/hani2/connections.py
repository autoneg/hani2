"""Connections: named sign-ins to language-model providers.

A connection is ``{name, provider, auth, base_url?, api_key_env?, litellm_provider?, upstream?, headers?}``.
Entries of a model chain (:mod:`hani2.model_chain`) name a connection, so two connections of
one provider can live side by side (``ollama-local`` and ``ollama-cloud``, two OpenAI keys).

Storage (the settings folder only; never a project or study folder):

* ``$HANI2_HOME/settings/connections.json`` — the connections, without secrets;
* ``$HANI2_HOME/settings/secrets/connections.json`` (0600) — pasted keys and header values;
* ``$HANI2_HOME/settings/secrets/<name>/`` (0700) — a harness connection's isolated config folder
  (see :mod:`hani2.harness`; old subscription tokens were kept here too).

Subscription sign-ins (ChatGPT plans, GitHub Copilot) are not offered: their providers' terms do
not clearly allow a third-party application to use them to serve other people. A stored
connection of that kind loads *disabled*: it never resolves and says why.

Secrets never leave this module except as the arguments of a model call: every listing is
masked (:func:`public`), and :func:`redact` removes any secret from a text (errors, logs).

Without any connection, every provider has an *implicit* one named after it (``anthropic``
reads ``ANTHROPIC_API_KEY``, ``ollama`` is the local server, …), so old settings and a bare
``hani2 --models anthropic:claude-opus-5-5`` work.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hani2 import providers as prov
from hani2.config import settings_dir

FILE = "connections.json"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_LOCK = threading.RLock()


class ConnectionError_(ValueError):
    """A connection that cannot be created, changed or used (the message says why)."""


# --------------------------------------------------------------------------- #
# The connection object                                                        #
# --------------------------------------------------------------------------- #
@dataclass
class Connection:
    name: str
    provider: str
    auth: str = "api_key_env"
    base_url: str = ""
    api_key_env: str = ""
    #: for the ``litellm`` provider: litellm's provider name
    litellm_provider: str = ""
    #: header names (values are secrets)
    header_names: list[str] = field(default_factory=list)
    label: str = ""
    implicit: bool = False
    #: for a harness connection (``claude-code``, ``codex``, ``pi``): the model provider the harness calls
    upstream: str = ""
    #: why this stored connection cannot be used any more (e.g. a subscription sign-in that is not offered)
    disabled: str = ""

    @property
    def preset(self) -> prov.Provider:
        p = prov.get(self.provider)
        assert p is not None
        return p

    @property
    def litellm(self) -> str:
        """The litellm provider of this connection's models."""
        p = self.preset
        if self.provider == "litellm":
            return self.litellm_provider
        return p.litellm

    @property
    def base(self) -> str:
        return (self.base_url or self.preset.base_url).rstrip("/")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "provider": self.provider, "auth": self.auth}
        for k in ("base_url", "api_key_env", "litellm_provider", "label", "upstream"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.header_names:
            d["headers"] = list(self.header_names)
        return d


def check_name(name: Any) -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ConnectionError_(f"invalid connection name {name!r}: letters, digits, '.', '_' and '-' (up to 64)")
    return name


def _from_dict(d: dict[str, Any], implicit: bool = False, stored: bool = False) -> Connection:
    """A connection from its stored or submitted form. ``stored``: a connection read back from the
    settings folder whose sign-in is no longer offered loads *disabled* (it never resolves, and says
    why) instead of disappearing; a new one is refused."""
    p = prov.get(str(d.get("provider", "")))
    if p is None:
        raise ConnectionError_(f"unknown provider {d.get('provider')!r}; known: {', '.join(prov.PROVIDERS)}")
    auth = str(d.get("auth") or (p.auth[0] if p.auth else "none"))
    if not p.offered or auth == "subscription":
        why = p.not_offered if not p.offered else p.no_subscription or f"subscription sign-in is {prov.NOT_OFFERED}"
        if not stored:
            raise ConnectionError_(f"{p.label}: {why}")
        return Connection(name=check_name(str(d.get("name", ""))), provider=p.id, auth=auth,
                          label=str(d.get("label") or ""), disabled=f"{p.label} {auth} sign-in: {why}")
    if auth not in p.auth:
        why = f" ({p.no_subscription})" if auth == "subscription" and p.no_subscription else ""
        raise ConnectionError_(f"{p.label} does not support sign-in by {auth!r}; use one of "
                               f"{', '.join(p.auth)}{why}")
    headers = d.get("headers") or []
    if isinstance(headers, dict):
        headers = list(headers)
    c = Connection(name=check_name(str(d.get("name", ""))), provider=p.id, auth=auth,
                   base_url=str(d.get("base_url") or ""), api_key_env=str(d.get("api_key_env") or ""),
                   litellm_provider=str(d.get("litellm_provider") or ""), header_names=[str(h) for h in headers],
                   label=str(d.get("label") or ""), implicit=implicit,
                   upstream=str(d.get("upstream") or "").strip().lower())
    if p.harness:
        from hani2 import harness

        harness.check_connection(c)  # raises ConnectionError_ for a sign-in or upstream that is not allowed
    if p.needs_base_url and not c.base_url:
        raise ConnectionError_(f"{p.label} needs a base URL")
    if p.id == "litellm" and not c.litellm_provider:
        raise ConnectionError_("an 'Other litellm provider' connection needs litellm_provider (e.g. together_ai)")
    if auth == "api_key_env" and not c.api_key_env:
        c.api_key_env = p.env
    return c


# --------------------------------------------------------------------------- #
# Files                                                                        #
# --------------------------------------------------------------------------- #
def _file() -> Path:
    return settings_dir() / FILE


def secrets_dir() -> Path:
    return settings_dir() / "secrets"


def _secrets_file() -> Path:
    return secrets_dir() / "connections.json"


def token_dir(name: str) -> Path:
    """Where a connection's subscription tokens live (created 0700)."""
    d = secrets_dir() / check_name(name)
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(secrets_dir(), 0o700)
        os.chmod(d, 0o700)
    except OSError:  # pragma: no cover
        pass
    return d


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:  # pragma: no cover
        pass
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(text)
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        print(f"[hani2] could not read {path}; ignoring it")
        return {}
    return data if isinstance(data, dict) else {}


def _secrets() -> dict[str, dict[str, Any]]:
    return _read_json(_secrets_file())


def _save_secrets(data: dict) -> None:
    _write_private(_secrets_file(), json.dumps(data, indent=2))


def _stored() -> list[dict[str, Any]]:
    items = _read_json(_file()).get("connections") or []
    return [d for d in items if isinstance(d, dict)]


def _save(items: list[dict[str, Any]]) -> None:
    p = _file()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(json.dumps({"connections": items}, indent=2))
    tmp.replace(p)


# --------------------------------------------------------------------------- #
# Listing, adding, removing                                                    #
# --------------------------------------------------------------------------- #
def configured() -> list[Connection]:
    out = []
    for d in _stored():
        try:
            out.append(_from_dict(d, stored=True))
        except ConnectionError_ as e:
            print(f"[hani2] ignoring connection {d.get('name')!r} in {_file()}: {e}")
    return out


def _implicit(provider_id: str) -> Connection | None:
    p = prov.get(provider_id)
    if p is None or p.id == "litellm" or p.harness or not p.offered:
        return None  # a harness is used only when an admin adds it
    if p.id == "ollama":
        base = (os.environ.get("OLLAMA_API_BASE") or "").strip() or p.base_url
        return Connection(name="ollama", provider="ollama", auth="none", base_url=base, implicit=True)
    if p.needs_base_url and p.id != "azure":
        return None
    if "api_key_env" in p.auth:
        return Connection(name=p.id, provider=p.id, auth="api_key_env", api_key_env=p.env,
                          base_url=os.environ.get("AZURE_API_BASE", "") if p.id == "azure" else "", implicit=True)
    if p.auth == ("none",):
        return Connection(name=p.id, provider=p.id, auth="none", implicit=True)
    return None


def local_ollama() -> Connection:
    """The local Ollama server (``$HANI2_OLLAMA_LOCAL_BASE``, default localhost)."""
    base = (os.environ.get("HANI2_OLLAMA_LOCAL_BASE") or os.environ.get("HANI_OLLAMA_LOCAL_BASE")
            or "http://localhost:11434")
    return Connection(name="ollama-local", provider="ollama", auth="none", base_url=base, implicit=True)


def all_connections(include_implicit: bool = True) -> list[Connection]:
    conf = configured()
    if not include_implicit:
        return conf
    names = {c.name for c in conf}
    out = list(conf)
    for pid in prov.PROVIDERS:
        imp = _implicit(pid)
        if imp is not None and imp.name not in names:
            out.append(imp)
            names.add(imp.name)
    if "ollama-local" not in names:
        out.append(local_ollama())
    return out


def get(name: str) -> Connection | None:
    for c in all_connections():
        if c.name == name:
            return c
    return None


def first_of(provider_id: str, auth: str | None = None) -> Connection | None:
    """The first configured connection of a provider, else its implicit one."""
    p = prov.get(provider_id)
    if p is None:
        return None
    for c in configured():
        if c.provider == p.id and not c.disabled and (auth is None or c.auth == auth):
            return c
    return _implicit(p.id) if auth in (None, "api_key_env", "none") else None


def add(data: dict[str, Any], *, api_key: str | None = None, headers: dict[str, str] | None = None,
        replace: bool = False) -> Connection:
    """Add (or with ``replace``, change) a connection; ``api_key`` and header values are stored as secrets."""
    data = dict(data)
    if headers:
        data["headers"] = list(headers)
    with _LOCK:
        c = _from_dict(data)
        items = _stored()
        idx = next((i for i, d in enumerate(items) if d.get("name") == c.name), None)
        if idx is not None and not replace:
            raise ConnectionError_(f"a connection named {c.name!r} exists already")
        if c.auth == "api_key" and not api_key and not (_secrets().get(c.name) or {}).get("api_key"):
            raise ConnectionError_("an API key connection needs the key")
        if idx is None:
            items.append(c.to_dict())
        else:
            items[idx] = c.to_dict()
        _save(items)
        sec = _secrets()
        entry = dict(sec.get(c.name) or {})
        if api_key:
            entry["api_key"] = api_key
        if c.auth != "api_key":
            entry.pop("api_key", None)
        if headers is not None:
            entry["headers"] = {k: v for k, v in headers.items() if v} or {}
            if not entry["headers"]:
                entry.pop("headers")
        if entry:
            sec[c.name] = entry
        else:
            sec.pop(c.name, None)
        _save_secrets(sec)
        forget_probes(c.name)
        return c


def remove(name: str) -> bool:
    with _LOCK:
        items = _stored()
        kept = [d for d in items if d.get("name") != name]
        sec = _secrets()
        had = len(kept) != len(items) or name in sec
        _save(kept)
        if sec.pop(name, None) is not None:
            _save_secrets(sec)
        logout(name)
        forget_probes(name)
        return had


def logout(name: str) -> None:
    """Delete a connection's private folder (old subscription tokens, a harness's isolated config)."""
    import shutil

    d = secrets_dir() / name
    if d.is_dir() and _NAME.match(name):
        shutil.rmtree(d, ignore_errors=True)
    _PENDING.pop(name, None)


# --------------------------------------------------------------------------- #
# Credentials                                                                  #
# --------------------------------------------------------------------------- #
def api_key(c: Connection) -> str | None:
    if c.auth == "api_key":
        return (_secrets().get(c.name) or {}).get("api_key") or None
    if c.auth == "api_key_env":
        return (os.environ.get(c.api_key_env or c.preset.env) or "").strip() or None
    return None


def _header_values(c: Connection) -> dict[str, str]:
    return dict((_secrets().get(c.name) or {}).get("headers") or {})


def has_credentials(c: Connection) -> tuple[bool, str]:
    """Whether the connection can be tried at all (no network); ``(ok, reason)``."""
    if c.disabled:
        return False, c.disabled
    if c.preset.harness:
        from hani2 import harness

        return harness.has_credentials(c)
    if c.auth in ("api_key", "api_key_env"):
        if api_key(c):
            return True, ""
        if c.auth == "api_key_env":
            return False, f"the environment variable {c.api_key_env or c.preset.env} is not set"
        return False, "no API key stored"
    if c.provider == "bedrock" and not (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE")
                                        or os.environ.get("AWS_BEARER_TOKEN_BEDROCK")):
        return False, "no AWS credentials in the environment"
    return True, ""


def call_kwargs(c: Connection) -> dict[str, Any]:
    """The litellm arguments that sign a call in with this connection (secrets included: use them
    only for the call itself)."""
    if c.disabled:
        raise ConnectionError_(c.disabled)
    if c.preset.harness:
        from hani2 import harness

        # only the connection's name: the harness adapter reads the key itself, into the child's environment
        return {"api_base": harness.api_base_for(c)}
    kw: dict[str, Any] = {}
    key = api_key(c)
    if key:
        kw["api_key"] = key
    base = c.base_url or (c.preset.base_url if c.provider in ("ollama", "ollama_cloud") else "")
    if base:
        kw["api_base"] = base.rstrip("/")
    hv = _header_values(c)
    if hv:
        kw["extra_headers"] = {**kw.get("extra_headers", {}), **hv}
    return kw


def secret_values() -> list[str]:
    """Every stored secret (for :func:`redact`)."""
    out: list[str] = []
    try:
        from hani2 import sso

        out += sso.secrets_in_use()
    except Exception:  # noqa: BLE001
        pass
    for entry in _secrets().values():
        if not isinstance(entry, dict):
            continue
        if entry.get("api_key"):
            out.append(str(entry["api_key"]))
        out += [str(v) for v in (entry.get("headers") or {}).values() if v]
    for c in configured():
        if c.auth == "api_key_env":
            v = api_key(c)
            if v:
                out.append(v)
    for p in prov.PROVIDERS.values():
        if p.env and os.environ.get(p.env):
            out.append(os.environ[p.env])
    return [s for s in out if len(s) >= 6]


def redact(text: Any) -> str:
    """``text`` with every known secret (and anything that looks like a bearer token) masked."""
    s = str(text)
    for v in sorted(set(secret_values()), key=len, reverse=True):
        s = s.replace(v, mask(v))
    s = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}", r"\1***", s)
    s = _KEYLIKE.sub("***", s)
    return s


#: provider-style API keys that are not (or no longer) stored here, e.g. echoed by an SDK error
_KEYLIKE = re.compile(r"\b(?:sk|rk|gsk|xai|hf|ghp|github_pat)[-_][A-Za-z0-9_\-]{16,}|\bAIza[0-9A-Za-z_\-]{30,}")

#: what a participant sees when a language-model call fails
LLM_ERROR_MESSAGE = "The language model could not answer right now. Please try again."


def llm_error(e: Any, *, admin: bool, generic: str = LLM_ERROR_MESSAGE) -> str:
    """The text to show in the browser for a failed language-model call ``e`` (an exception or
    its message): ``generic`` for participants, a redacted one for admins. The full text goes
    only to the server log."""
    text = f"{type(e).__name__}: {e}" if isinstance(e, BaseException) else str(e)
    print(f"[hani2] error (full text, not shown to participants): {text}", file=sys.stderr)
    return redact(text)[:500] if admin else generic


def mask(v: str | None) -> str:
    if not v:
        return ""
    return f"{v[:3]}…{v[-2:]}" if len(v) > 12 else "…"


def public(c: Connection) -> dict[str, Any]:
    """A connection as the admin console sees it (no secrets)."""
    ok, why = has_credentials(c)
    d = c.to_dict()
    p = c.preset
    d.update(implicit=c.implicit, provider_label=p.label, litellm=c.litellm, base=c.base,
             credentials=ok, credentials_reason=why, auth_methods=list(p.auth))
    if c.auth == "api_key":
        d["api_key"] = mask(api_key(c))
    if c.auth == "api_key_env":
        d["api_key_env"] = c.api_key_env or p.env
        d["api_key_env_set"] = bool(api_key(c))
    if c.header_names:
        d["headers"] = {h: "…" for h in c.header_names}
    if c.disabled:
        d["disabled"] = c.disabled
    if p.harness:
        from hani2 import harness

        d["harness"] = harness.public_info(c)
    return d


# --------------------------------------------------------------------------- #
# Probes: is a model usable now?                                               #
# --------------------------------------------------------------------------- #
@dataclass
class Probe:
    ok: bool
    reason: str = ""
    verified: bool = True
    at: float = field(default_factory=time.time)
    models: list[str] | None = None


_PROBES: dict[tuple, Probe] = {}
OK_TTL = 300.0
FAIL_TTL = 30.0


def probing_enabled() -> bool:
    return (os.environ.get("HANI2_MODEL_PROBE") or "on").strip().lower() not in ("0", "off", "false", "no")


def probe_timeout() -> float:
    try:
        return float(os.environ.get("HANI2_MODEL_PROBE_TIMEOUT") or 3.0)
    except ValueError:
        return 3.0


def forget_probes(name: str | None = None) -> None:
    for k in list(_PROBES):
        if name is None or k[0] == name:
            _PROBES.pop(k, None)


def _http_get(url: str, headers: dict[str, str] | None = None, params: dict | None = None) -> Any:
    """GET ``url`` and return the JSON body (raises on any failure). Replaced in tests."""
    import httpx

    r = httpx.get(url, headers=headers or {}, params=params, timeout=probe_timeout())
    r.raise_for_status()
    return r.json()


def _ids(data: Any, key: str = "data", field_: str = "id") -> list[str]:
    items = data.get(key) if isinstance(data, dict) else data
    out = []
    for it in items or []:
        if isinstance(it, dict) and isinstance(it.get(field_), str):
            out.append(it[field_])
    return out


def _model_listed(model: str, ids: list[str]) -> bool:
    if not ids:
        return True  # an empty list says nothing
    m = model.split("/", 1)[-1] if model.startswith(("ollama/", "ollama_chat/")) else model
    cand = {m, f"{m}:latest", m.removesuffix(":latest")}
    return any(i in cand or i.removeprefix("models/") in cand for i in ids)


def _probe_now(c: Connection, model: str) -> Probe:
    ok, why = has_credentials(c)
    if not ok:
        return Probe(False, why)
    kind = c.preset.probe
    try:
        if kind == "harness":
            from hani2 import harness

            return harness.probe(c, model)
        if kind == "ollama_tags":
            key = api_key(c)
            data = _http_get(f"{c.base}/api/tags", {"Authorization": f"Bearer {key}"} if key else None)
            ids = _ids(data, "models", "name") or _ids(data, "models", "model")
            if not _model_listed(model, ids):
                hint = " (run `ollama pull` on the server, or `ollama signin` for -cloud models)" \
                    if c.provider == "ollama" else ""
                return Probe(False, f"model {model!r} not found on {c.base}{hint}", models=ids)
            return Probe(True, models=ids)
        if kind == "anthropic":
            data = _http_get(f"{c.base}/v1/models", {"x-api-key": api_key(c) or "", "anthropic-version": "2023-06-01"},
                             {"limit": 1000})
            ids = _ids(data)
            if ids and not any(i == model or i.startswith(model) for i in ids):
                return Probe(False, f"model {model!r} is not offered to this key", models=ids)
            return Probe(True, models=ids)
        if kind == "openai_models":
            key = api_key(c)
            data = _http_get(f"{c.base}/models", {"Authorization": f"Bearer {key}"} if key else None)
            ids = _ids(data)
            if not _model_listed(model, ids):
                return Probe(False, f"model {model!r} is not offered by {c.base}", models=ids)
            return Probe(True, models=ids)
        if kind == "gemini":
            data = _http_get(f"{c.base}/v1beta/models", params={"key": api_key(c) or "", "pageSize": 1000})
            ids = [i.removeprefix("models/") for i in _ids(data, "models", "name")]
            if not _model_listed(model, ids):
                return Probe(False, f"model {model!r} is not offered to this key", models=ids)
            return Probe(True, models=ids)
    except Exception as e:  # noqa: BLE001 - any failure means "not available"
        return Probe(False, _short_error(e))
    return Probe(True, verified=False)


def _short_error(e: Exception) -> str:
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status in (401, 403):
        return f"the provider refused the credentials (HTTP {status})"
    if status:
        return f"the provider answered HTTP {status}"
    name = type(e).__name__
    if "Timeout" in name:
        return f"no answer within {probe_timeout():g}s"
    if "Connect" in name:
        return "cannot connect"
    return redact(f"{name}: {e}")[:200]


#: why an Ollama cloud model through a local server is refused
OLLAMA_CLOUD_REFUSED = ("cloud models (names ending in -cloud) through a local Ollama server use the server's "
                        "Ollama account sign-in, and Ollama's terms (one account per person; shared use through "
                        "the Team plan) do not clearly allow an application to serve others with it. Use an "
                        "Ollama Cloud connection with an API key (provider ollama_cloud) instead.")


def refusal(c: Connection, model: str) -> str:
    """Why ``model`` may never be used through ``c`` (``""``: no rule against it). Unlike a failed
    check, a refusal is final: not even the old single-model settings use the entry unchecked."""
    if c.disabled:
        return c.disabled
    if c.provider == "ollama" and (model or "").strip().endswith("-cloud"):
        return OLLAMA_CLOUD_REFUSED
    return ""


def probe(c: Connection, model: str, *, fresh: bool = False) -> Probe:
    """Whether ``model`` can be used through ``c`` now (cached: 5 min when it works, 30 s when not).

    With ``HANI2_MODEL_PROBE=off`` only the credentials are checked (no network)."""
    bad = refusal(c, model)
    if bad:
        return Probe(False, bad)
    if not probing_enabled():
        ok, why = has_credentials(c)
        return Probe(ok, why, verified=False)
    key = (c.name, c.provider, c.auth, c.base, model)
    hit = _PROBES.get(key)
    if hit is not None and not fresh and time.time() - hit.at < (OK_TTL if hit.ok else FAIL_TTL):
        return hit
    res = _probe_now(c, model)
    _PROBES[key] = res
    return res


def list_models(c: Connection) -> list[str]:
    """The models a connection offers (``[]`` when it cannot say)."""
    p = _probe_now(c, "")
    return list(p.models or [])


# --------------------------------------------------------------------------- #
# Subscription sign-in: not offered                                            #
# --------------------------------------------------------------------------- #
#: name -> a sign-in in progress (none can be started any more; kept for :func:`logout`)
_PENDING: dict[str, dict[str, Any]] = {}


def start_login(name: str) -> dict[str, Any]:
    """Subscription sign-ins are not offered (see :data:`hani2.providers.NOT_OFFERED`)."""
    raise ConnectionError_(f"{name}: subscription sign-in is {prov.NOT_OFFERED}. Use an API key connection.")


def poll_login(name: str) -> dict[str, Any]:
    """No sign-in can be in progress: ``{status: connected|none}``."""
    c = get(name)
    return {"status": "connected" if c is not None and has_credentials(c)[0] else "none"}
