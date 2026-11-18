"""Connections: named sign-ins to language-model providers.

A connection is ``{name, provider, auth, base_url?, api_key_env?, litellm_provider?, headers?}``.
Entries of a model chain (:mod:`hani2.model_chain`) name a connection, so two connections of
one provider can live side by side (``ollama-local`` and ``ollama-cloud``, two OpenAI keys).

Storage (the settings folder only; never a project or study folder):

* ``$HANI2_HOME/settings/connections.json`` — the connections, without secrets;
* ``$HANI2_HOME/settings/secrets/connections.json`` (0600) — pasted keys and header values;
* ``$HANI2_HOME/settings/secrets/<name>/`` (0700) — subscription tokens.

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
import stat
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
        if self.auth == "subscription" and p.subscription_litellm:
            return p.subscription_litellm
        return p.litellm

    @property
    def base(self) -> str:
        return (self.base_url or self.preset.base_url).rstrip("/")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name, "provider": self.provider, "auth": self.auth}
        for k in ("base_url", "api_key_env", "litellm_provider", "label"):
            if getattr(self, k):
                d[k] = getattr(self, k)
        if self.header_names:
            d["headers"] = list(self.header_names)
        return d


def check_name(name: Any) -> str:
    if not isinstance(name, str) or not _NAME.match(name):
        raise ConnectionError_(f"invalid connection name {name!r}: letters, digits, '.', '_' and '-' (up to 64)")
    return name


def _from_dict(d: dict[str, Any], implicit: bool = False) -> Connection:
    p = prov.get(str(d.get("provider", "")))
    if p is None:
        raise ConnectionError_(f"unknown provider {d.get('provider')!r}; known: {', '.join(prov.PROVIDERS)}")
    auth = str(d.get("auth") or (p.auth[0] if p.auth else "none"))
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
                   label=str(d.get("label") or ""), implicit=implicit)
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
            out.append(_from_dict(d))
        except ConnectionError_ as e:
            print(f"[hani2] ignoring connection {d.get('name')!r} in {_file()}: {e}")
    return out


def _implicit(provider_id: str) -> Connection | None:
    p = prov.get(provider_id)
    if p is None or p.id == "litellm":
        return None
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
        if c.provider == p.id and (auth is None or c.auth == auth):
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
    """Forget a connection's subscription tokens."""
    d = secrets_dir() / name
    if d.is_dir() and _NAME.match(name):
        for f in d.iterdir():
            try:
                f.unlink()
            except OSError:  # pragma: no cover
                pass
        try:
            d.rmdir()
        except OSError:  # pragma: no cover
            pass
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


def _copilot_file(c: Connection) -> Path:
    return secrets_dir() / c.name / "github-access-token"


def _chatgpt_file(c: Connection) -> Path:
    return secrets_dir() / c.name / "chatgpt-auth.json"


def has_credentials(c: Connection) -> tuple[bool, str]:
    """Whether the connection can be tried at all (no network); ``(ok, reason)``."""
    if c.auth in ("api_key", "api_key_env"):
        if api_key(c):
            return True, ""
        if c.auth == "api_key_env":
            return False, f"the environment variable {c.api_key_env or c.preset.env} is not set"
        return False, "no API key stored"
    if c.auth == "subscription":
        if c.provider == "github_copilot":
            return (_copilot_file(c).exists(), "" if _copilot_file(c).exists() else "not signed in")
        if c.provider == "openai":
            try:
                data = json.loads(_chatgpt_file(c).read_text())
            except (OSError, json.JSONDecodeError):
                return False, "not signed in"
            return (bool(data.get("refresh_token") or data.get("access_token")),
                    "" if data.get("refresh_token") or data.get("access_token") else "not signed in")
        return False, "this provider has no subscription sign-in"
    if c.provider == "bedrock" and not (os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE")
                                        or os.environ.get("AWS_BEARER_TOKEN_BEDROCK")):
        return False, "no AWS credentials in the environment"
    return True, ""


def _copilot_session(c: Connection) -> tuple[str, str]:
    """``(token, api_base)`` of a Copilot connection (litellm's token exchange; cached until it expires)."""
    from litellm.llms.github_copilot.github_host import github_host_endpoints
    from litellm.llms.github_copilot.per_user_auth import exchange_github_token

    gh = _copilot_file(c).read_text().strip()
    sess = exchange_github_token(c.name, gh, c.name, github_host_endpoints("github.com"))
    return sess.token, sess.api_base


def _copilot_headers() -> dict[str, str]:
    from litellm.llms.github_copilot.common_utils import get_copilot_default_headers

    h = get_copilot_default_headers("x")
    for k in ("Authorization", "content-type", "x-request-id"):
        h.pop(k, None)
    return h


def call_kwargs(c: Connection) -> dict[str, Any]:
    """The litellm arguments that sign a call in with this connection (secrets included: use them
    only for the call itself)."""
    kw: dict[str, Any] = {}
    key = api_key(c)
    if c.provider == "github_copilot":
        token, base = _copilot_session(c)
        kw.update(api_key=token, api_base=base, extra_headers=_copilot_headers())
    elif c.provider == "openai" and c.auth == "subscription":
        kw["chatgpt_auth_file"] = str(_chatgpt_file(c))
    else:
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
    return s


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
    if c.auth == "subscription":
        d["signed_in"] = ok
        d["login_pending"] = c.name in _PENDING
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
    if c.auth == "subscription" and c.provider == "openai":
        kind = "chatgpt"
    try:
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
        if kind == "copilot":
            token, base = _copilot_session(c)
            data = _http_get(f"{base}/models", {"Authorization": f"Bearer {token}", **_copilot_headers()})
            ids = _ids(data)
            if not _model_listed(model, ids):
                return Probe(False, f"model {model!r} is not in this Copilot plan", models=ids)
            return Probe(True, models=ids)
        if kind == "chatgpt":
            _chatgpt_fresh_token(c)
            return Probe(True, verified=False)
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


def probe(c: Connection, model: str, *, fresh: bool = False) -> Probe:
    """Whether ``model`` can be used through ``c`` now (cached: 5 min when it works, 30 s when not).

    With ``HANI2_MODEL_PROBE=off`` only the credentials are checked (no network)."""
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
# Subscription sign-in (device codes)                                          #
# --------------------------------------------------------------------------- #
#: name -> the flow in progress (the device code stays on the server)
_PENDING: dict[str, dict[str, Any]] = {}


def _run(coro):
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # called from a running loop (should not happen: the API runs this in a worker thread)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()


def _chatgpt_authenticator(c: Connection):
    from litellm.llms.chatgpt.authenticator import Authenticator

    token_dir(c.name)
    return Authenticator(auth_file=str(_chatgpt_file(c)))


def _chatgpt_fresh_token(c: Connection) -> str:
    """A valid ChatGPT access token, refreshed when it has expired (never starts a sign-in)."""
    auth = _chatgpt_authenticator(c)
    data = auth._read_auth_file() or {}
    tok = data.get("access_token")
    if tok and not auth._is_token_expired(data, tok):
        return tok
    if not data.get("refresh_token"):
        raise ConnectionError_("not signed in")
    return auth._refresh_tokens(data["refresh_token"])["access_token"]


def start_login(name: str) -> dict[str, Any]:
    """Start a device-code sign-in; returns ``{user_code, verification_uri, interval, expires_in}``."""
    c = get(name)
    if c is None or c.implicit:
        raise ConnectionError_(f"unknown connection {name!r}")
    if c.auth != "subscription":
        raise ConnectionError_(f"{name} signs in with {c.auth}, not a subscription")
    if c.provider == "github_copilot":
        from litellm.llms.github_copilot.github_host import github_host_endpoints
        from litellm.llms.github_copilot.per_user_auth import astart_device_flow

        st = _run(astart_device_flow(github_host_endpoints("github.com")))
        flow = {"kind": "copilot", "device_code": st.device_code, "interval": max(int(st.interval or 5), 1),
                "expires": time.time() + float(st.expires_in or 900), "user_code": st.user_code,
                "verification_uri": st.verification_uri}
    elif c.provider == "openai":
        from litellm.llms.chatgpt.common_utils import CHATGPT_DEVICE_VERIFY_URL

        auth = _chatgpt_authenticator(c)
        dc = auth._request_device_code()
        flow = {"kind": "chatgpt", "device_code": dc, "interval": max(int(dc.get("interval") or 5), 1),
                "expires": time.time() + 900, "user_code": dc["user_code"],
                "verification_uri": CHATGPT_DEVICE_VERIFY_URL}
    else:  # pragma: no cover - guarded by the provider table
        raise ConnectionError_(f"{c.provider} has no device sign-in")
    flow["next"] = time.time()
    _PENDING[name] = flow
    return {"status": "pending", "user_code": flow["user_code"], "verification_uri": flow["verification_uri"],
            "interval": flow["interval"], "expires_in": int(flow["expires"] - time.time())}


def poll_login(name: str) -> dict[str, Any]:
    """One poll of a sign-in in progress: ``{status: pending|connected|expired|denied|none, …}``."""
    flow = _PENDING.get(name)
    c = get(name)
    if flow is None or c is None:
        return {"status": "connected" if c is not None and has_credentials(c)[0] else "none"}
    if time.time() > flow["expires"]:
        _PENDING.pop(name, None)
        return {"status": "expired"}
    base = {"user_code": flow["user_code"], "verification_uri": flow["verification_uri"], "interval": flow["interval"]}
    if time.time() < flow["next"]:
        return {"status": "pending", **base}
    flow["next"] = time.time() + flow["interval"]
    if flow["kind"] == "copilot":
        from litellm.llms.github_copilot.github_host import github_host_endpoints
        from litellm.llms.github_copilot.per_user_auth import apoll_device_flow

        res = _run(apoll_device_flow(flow["device_code"], github_host_endpoints("github.com")))
        if res.status == "connected" and res.access_token:
            _write_private(token_dir(name) / "github-access-token", res.access_token)
            _PENDING.pop(name, None)
            forget_probes(name)
            return {"status": "connected"}
        if res.status == "slow_down":
            flow["interval"] = int(res.interval or flow["interval"] + 5)
        if res.status in ("expired", "denied"):
            _PENDING.pop(name, None)
            return {"status": res.status}
        return {"status": "pending", **base}
    # chatgpt: one request of litellm's poll loop, then its token exchange
    import httpx
    from litellm.llms.chatgpt.common_utils import CHATGPT_DEVICE_TOKEN_URL

    dc = flow["device_code"]
    r = httpx.post(CHATGPT_DEVICE_TOKEN_URL, json={"device_auth_id": dc["device_auth_id"], "user_code": dc["user_code"]},
                   timeout=15)
    if r.status_code in (403, 404):
        return {"status": "pending", **base}
    r.raise_for_status()
    data = r.json()
    if not (data.get("authorization_code") and data.get("code_verifier")):
        return {"status": "pending", **base}
    auth = _chatgpt_authenticator(c)
    tokens = auth._exchange_code_for_tokens({"authorization_code": data["authorization_code"],
                                             "code_challenge": data.get("code_challenge", ""),
                                             "code_verifier": data["code_verifier"]})
    auth._write_auth_file(auth._build_auth_record(tokens))
    try:
        os.chmod(_chatgpt_file(c), stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # pragma: no cover
        pass
    _PENDING.pop(name, None)
    forget_probes(name)
    return {"status": "connected"}
