"""The model chain: which language model a session uses.

A chain is an ordered list of entries ``{connection, model, params, label}``. The first
entry that is available (its connection exists, has credentials and passes a cheap check,
see :func:`hani2.connections.probe`) is used. Entries are identified by their position, so
one model can appear several times with different ``params``.

Chains are given per *purpose* — ``assistant``, ``opponent``, ``tools``, ``text`` (offer
extraction and message writing) and ``judge`` — with a ``default`` chain every purpose falls
back to::

    {"default": [{"connection": "anthropic", "model": "claude-sonnet-5-5"},
                 {"connection": "ollama", "model": "qwen3:4b-instruct", "params": {"temperature": 0.2}}],
     "judge":   ["openai:gpt-5"]}

Where a chain comes from (most specific first; the first layer that gives a chain for the
purpose, or a ``default`` chain, wins, so a study's ``default`` beats the settings' ``assistant``):

1. the active study's ``models.json`` (or the old ``provider``/``model`` keys of its own
   ``assistant_settings.json`` / ``llm_settings.json``);
2. its project's ``models.json`` (same);
3. the start-time list: ``hani2 --models "anthropic:claude-sonnet-5-5,ollama:qwen3:4b"`` or
   ``HANI2_MODELS``;
4. the settings folder's ``models.json`` (the admin's global chain);
5. the old single-model settings (``assistant_settings.json``, ``llm_settings.json``) read as a
   one-entry chain — with a remote Ollama endpoint followed by the local Ollama server, as the
   old local fallback did.

A session resolves each purpose once, when it first needs it (the Assistant's at session
start), and keeps the result for the session (:class:`SessionModels`). A call that fails hard
(connection, sign-in or "model not found" errors, rate limits) moves the session to the next
available entry; that is recorded like the first choice. Opponents (which call the model
themselves) keep the entry they were created with for their negotiation.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from hani2 import connections as conns
from hani2 import providers as prov

FILE = "models.json"
ENV = "HANI2_MODELS"
PURPOSES = ("assistant", "opponent", "tools", "text", "judge")
PURPOSE_LABELS = {"default": "Default (every purpose)", "assistant": "The Assistant (and its autopilot)",
                  "opponent": "LLM opponents", "tools": "Tools that ask the model",
                  "text": "Offer extraction and message writing", "judge": "The evaluation judge"}
#: parameters that must not sit in a chain (they belong to a connection)
SECRET_PARAMS = re.compile(r"(?i)^(.*[_-])?(api_?key|key|token|access_token|secret|password|authorization|"
                           r"credentials?|headers|extra_headers|api_base|base_url|chatgpt_auth_file)$")
LEGACY_PARAMS = ("temperature", "max_tokens")


class ChainError(ValueError):
    """A chain or entry that cannot be read (the message says why)."""


class NoModelAvailable(RuntimeError):
    """No entry of the chain can be used."""


# --------------------------------------------------------------------------- #
# Entries                                                                      #
# --------------------------------------------------------------------------- #
@dataclass
class Entry:
    model: str
    connection: str = ""
    provider: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    label: str = ""
    #: an unnamed connection built from old settings (never stored)
    inline: conns.Connection | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.connection:
            d["connection"] = self.connection
        elif self.provider:
            d["provider"] = self.provider
        d["model"] = self.model
        if self.params:
            d["params"] = dict(self.params)
        if self.label:
            d["label"] = self.label
        return d

    @property
    def title(self) -> str:
        return self.label or f"{self.connection or self.provider or (self.inline.name if self.inline else '?')}:{self.model}"


def clean_params(params: Any, where: str = "params") -> dict[str, Any]:
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ChainError(f"{where} must be a mapping")
    bad = [k for k in params if SECRET_PARAMS.search(str(k))]
    if bad:
        raise ChainError(f"{where} may not hold {', '.join(map(repr, bad))}: keys, tokens, headers and addresses "
                         "belong to a connection (Connections page / hani2 connections add)")
    return dict(params)


def parse_entry(x: Any, strict: bool = True) -> Entry:
    """An entry from ``"provider:model"`` / ``"connection:model"`` or a mapping. Not ``strict``: an
    unknown name in ``"name:model"`` is taken as a connection (skipped until it exists)."""
    if isinstance(x, Entry):
        return x
    if isinstance(x, str):
        s = x.strip()
        head, sep, model = s.partition(":")
        if not sep or not head.strip() or not model.strip():
            raise ChainError(f"{x!r} is not provider:model (e.g. anthropic:claude-sonnet-5-5 or ollama:qwen3:4b)")
        head, model = head.strip(), model.strip()
        if any(c.name == head for c in conns.configured()):
            return Entry(model=model, connection=head)
        if prov.known(head):
            return Entry(model=model, provider=head.lower())
        if conns.get(head) is not None or not strict:
            return Entry(model=model, connection=head)
        raise ChainError(f"{head!r} in {x!r} is neither a connection nor a provider "
                         f"(providers: {', '.join(prov.PROVIDERS)})")
    if isinstance(x, dict):
        d = dict(x)
        model = str(d.pop("model", "") or "").strip()
        if not model:
            raise ChainError(f"entry {x!r} has no model")
        connection = str(d.pop("connection", "") or "").strip()
        provider = str(d.pop("provider", "") or "").strip().lower()
        label = str(d.pop("label", "") or "")
        params = clean_params(d.pop("params", None))
        extra = clean_params({k: v for k, v in d.items()}, "an entry")
        params = {**extra, **params}
        if provider and not prov.known(provider):
            raise ChainError(f"unknown provider {provider!r} in {x!r}")
        if not connection and not provider:
            raise ChainError(f"entry {x!r} names neither a connection nor a provider")
        if connection and provider:
            c = conns.get(connection)
            p = prov.get(provider)
            if c is not None and p is not None and c.provider != p.id:
                raise ChainError(f"entry {x!r}: connection {connection!r} is a {c.preset.label} connection, "
                                 f"not {p.label}; give only the connection")
        return Entry(model=model, connection=connection, provider=provider, params=params, label=label)
    raise ChainError(f"cannot read a model entry from {x!r}")


def parse_chain(x: Any, strict: bool = True) -> list[Entry]:
    """A chain from a list of entries or a comma-separated ``provider:model`` text."""
    if x is None:
        return []
    if isinstance(x, str):
        x = [s for s in x.split(",") if s.strip()]
    if not isinstance(x, (list, tuple)):
        raise ChainError("a chain is a list of entries")
    return [parse_entry(e, strict) for e in x]


def parse_chains(data: Any, strict: bool = True) -> dict[str, list[Entry]]:
    """``{purpose: chain}`` from a models.json body (a bare list is the default chain)."""
    if data is None:
        return {}
    if isinstance(data, (list, str)):
        data = {"default": data}
    if not isinstance(data, dict):
        raise ChainError("models.json must hold a mapping of purposes to chains")
    out: dict[str, list[Entry]] = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if k not in ("default", *PURPOSES):
            raise ChainError(f"unknown purpose {k!r}; use default, {', '.join(PURPOSES)}")
        out[k] = parse_chain(v, strict)
    return out


def read_layer_file(path: Path) -> dict[str, Any]:
    """A layer's own models.json as a mapping (a bare list is the default chain; ``{}`` when missing)."""
    if not path.exists():
        return {}
    data = _read(path)
    if isinstance(data, (list, str)):
        return {"default": data}
    return data if isinstance(data, dict) else {}


def check_chains(data: Any) -> list[str]:
    """Problems of a models.json body (``[]``: none)."""
    try:
        parse_chains(data)
    except ChainError as e:
        return [str(e)]
    return []


def connection_of(e: Entry) -> tuple[conns.Connection | None, str]:
    """The connection an entry uses, or ``(None, reason)``."""
    if e.inline is not None:
        return e.inline, ""
    if e.connection:
        c = conns.get(e.connection)
        return (c, "") if c is not None else (None, f"no connection named {e.connection!r}")
    p = prov.get(e.provider)
    if p is None:
        return None, f"unknown provider {e.provider!r}"
    if e.provider.lower() in ("chatgpt", "copilot", "github-copilot", "github_copilot"):
        return None, f"{e.provider}: subscription sign-in is {prov.NOT_OFFERED}"
    if not p.offered:
        return None, f"{p.label}: {p.not_offered}"
    c = conns.first_of(p.id)
    if c is None:
        return None, f"no {p.label} connection (add one on the Connections page)"
    return c, ""


# --------------------------------------------------------------------------- #
# Where chains come from                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class Source:
    id: str  # study:P/S | project:P | start | settings | legacy
    chains: dict[str, list[Entry]]
    implicit: bool = False

    def chain(self, purpose: str) -> list[Entry] | None:
        return self.chains.get(purpose) or self.chains.get("default") or None


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print(f"[hani2] could not read {path}; ignoring it")
        return None


def _is_local(url: str) -> bool:
    return any(h in (url or "") for h in ("localhost", "127.0.0.1", "0.0.0.0", "[::1]"))


def legacy_entries(settings: dict, kind: str, purpose: str) -> list[Entry]:
    """The old single model of ``settings`` as entries (``kind``: ``assistant`` or ``llm``)."""
    provider = str(settings.get("provider") or "ollama").strip().lower()
    model = str(settings.get("model") or "").strip()
    if not model:
        return []
    params = {k: settings[k] for k in LEGACY_PARAMS if settings.get(k) is not None}
    if purpose == "judge":
        params["temperature"] = settings.get("judge_temperature", 0.0)
    label = f"{kind}_settings.json"
    if provider == "ollama":
        if kind == "llm" and purpose in ("tools", "text", "judge"):
            base = str(settings.get("api_base") or settings.get("ollama_base_url") or "").strip()
            base = re.sub(r"/v1/?$", "", base)
        else:
            base = str(settings.get("api_base") or "").strip()
        base = base or (os.environ.get("OLLAMA_API_BASE") or "").strip() or "http://localhost:11434"
        cloud = "ollama.com" in base
        first = conns.Connection(name=f"{kind}-settings", provider="ollama_cloud" if cloud else "ollama",
                                 auth="api_key_env" if cloud else "none", api_key_env="OLLAMA_API_KEY" if cloud else "",
                                 base_url=base, implicit=True)
        out = [Entry(model=model, provider="ollama", params=params, label=label, inline=first)]
        if not _is_local(base):  # the old local fallback, now an entry of the chain
            out.append(Entry(model=model, provider="ollama", params=dict(params), label="local Ollama fallback",
                             inline=conns.local_ollama()))
        return out
    p = prov.get(provider)
    env_name = str(settings.get("api_key_env") or "").strip()
    pid = p.id if p is not None else "litellm"
    preset = prov.PROVIDERS[pid]
    if not (env_name and os.environ.get(env_name)):
        env_name = preset.env or env_name
    auth = "api_key_env" if "api_key_env" in preset.auth else "none"
    c = conns.Connection(name=f"{kind}-settings", provider=pid, auth=auth, api_key_env=env_name if auth != "none" else "",
                         base_url=str(settings.get("api_base") or ""),
                         litellm_provider=provider if pid == "litellm" else "", implicit=True)
    return [Entry(model=model, provider=provider, params=params, label=label, inline=c)]


def _legacy_assistant() -> dict:
    from hani2.support_agent.settings import load_assistant_settings

    return load_assistant_settings()


def _legacy_llm() -> dict:
    from hani2.config import load_llm_settings

    return load_llm_settings()


def _legacy_judge() -> dict:
    from hani2.config import get_env

    s = dict(_legacy_llm())
    s.update(get_env("evaluation.llm", {}) or {})
    return s


def _legacy_chains() -> dict[str, list[Entry]]:
    out: dict[str, list[Entry]] = {}
    try:
        out["assistant"] = legacy_entries(_legacy_assistant(), "assistant", "assistant")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    try:
        llm = _legacy_llm()
        for p in ("opponent", "tools", "text"):
            out[p] = legacy_entries(llm, "llm", p)
        out["judge"] = legacy_entries(_legacy_judge(), "llm", "judge")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
    return {k: v for k, v in out.items() if v}


def _layer_legacy(folder: Path) -> dict[str, list[Entry]]:
    """Old provider/model keys written in a study's or project's own files: a chain at that layer."""
    out: dict[str, list[Entry]] = {}
    for name in ("support_agent_settings.json", "assistant_settings.json"):
        d = _read(folder / name) if (folder / name).exists() else None
        if isinstance(d, dict) and (d.get("provider") or d.get("model")):
            out["assistant"] = legacy_entries(_legacy_assistant(), "assistant", "assistant")
    d = _read(folder / "llm_settings.json") if (folder / "llm_settings.json").exists() else None
    if isinstance(d, dict) and (d.get("provider") or d.get("model")):
        llm = _legacy_llm()
        for p in ("opponent", "tools", "text"):
            out[p] = legacy_entries(llm, "llm", p)
        out["judge"] = legacy_entries(_legacy_judge(), "llm", "judge")
    return {k: v for k, v in out.items() if v}


def start_chain() -> list[Entry]:
    """The start-time list (``--models`` / ``HANI2_MODELS``)."""
    raw = (os.environ.get(ENV) or "").strip()
    return parse_chain(raw) if raw else []


def _layer_id(folder: Path) -> str:
    from hani2.layers import layer_of_path

    return layer_of_path(folder / FILE)


def sources(include_legacy: bool = True) -> list[Source]:
    """Every layer that gives chains, most specific first (bound to the current study / layer view)."""
    from hani2.config import _VIEW, settings_dir, settings_layers

    out: list[Source] = []
    for folder in settings_layers():
        f = folder / FILE
        if f.exists():
            data = _read(f)
            try:
                chains = parse_chains(data, strict=False)
            except ChainError as e:
                print(f"[hani2] ERROR: {f}: {e}; ignoring it")
                chains = {}
            if chains:
                out.append(Source(_layer_id(folder), chains))
                continue
        legacy = _layer_legacy(folder)
        if legacy:
            out.append(Source(_layer_id(folder), legacy))
    try:
        start = start_chain()
    except ChainError as e:
        print(f"[hani2] ERROR: {ENV}: {e}; ignoring it")
        start = []
    if start:
        out.append(Source("start", {"default": start}))
    from hani2.config import override_for

    ov = override_for(FILE)
    if ov:
        try:
            chains = parse_chains(ov, strict=False)
        except ChainError as e:
            print(f"[hani2] ERROR: the settings overrides (models): {e}; ignoring them")
            chains = {}
        if chains:
            out.append(Source("overrides", chains))
    view = _VIEW.get()
    if not (view and view[1]):
        f = settings_dir() / FILE
        if f.exists():
            try:
                chains = parse_chains(_read(f), strict=False)
            except ChainError as e:
                print(f"[hani2] ERROR: {f}: {e}; ignoring it")
                chains = {}
            if chains:
                out.append(Source("settings", chains))
    if include_legacy:
        out.append(Source("legacy", _legacy_chains(), implicit=True))
    return out


def chain_for(purpose: str) -> tuple[list[Entry], Source | None]:
    for src in sources():
        ch = src.chain(purpose)
        if ch:
            return ch, src
    return [], None


def effective_chains() -> dict[str, Any]:
    """What every purpose uses at the current layer: ``{purpose: {source, entries}}`` (for the console)."""
    out: dict[str, Any] = {}
    for p in ("default", *PURPOSES):
        if p == "default":
            ch, src = next(((s.chains["default"], s) for s in sources() if s.chains.get("default")), ([], None))
        else:
            ch, src = chain_for(p)
        out[p] = {"source": src.id if src else "", "implicit": bool(src and src.implicit),
                  "entries": [_entry_public(e) for e in ch]}
    return out


def _entry_public(e: Entry) -> dict[str, Any]:
    d = e.to_dict()
    if e.inline is not None:
        d["connection"] = e.inline.name
        d["provider"] = e.inline.provider
        d["base"] = e.inline.base
    return d


# --------------------------------------------------------------------------- #
# Resolution                                                                   #
# --------------------------------------------------------------------------- #
def litellm_model(c: conns.Connection, model: str) -> str:
    lp = c.litellm
    if lp == "ollama":
        return f"ollama_chat/{model}"
    return f"{lp}/{model}" if lp else model


@dataclass
class Resolution:
    purpose: str
    source: str = ""
    entry: Entry | None = None
    index: int = -1
    connection: conns.Connection | None = field(default=None, repr=False)
    status: str = "none"  # ok | unverified | none
    skipped: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    chain: list[Entry] = field(default_factory=list, repr=False)
    implicit: bool = False
    at: float = field(default_factory=time.time)

    @property
    def ok(self) -> bool:
        return self.status != "none" and self.entry is not None and self.connection is not None

    @property
    def provider(self) -> str:
        return self.connection.provider if self.connection else ""

    @property
    def model(self) -> str:
        return self.entry.model if self.entry else ""

    @property
    def litellm_provider(self) -> str:
        return self.connection.litellm if self.connection else ""

    @property
    def litellm_model(self) -> str:
        return litellm_model(self.connection, self.model) if self.connection and self.entry else ""

    @property
    def is_ollama(self) -> bool:
        return self.litellm_provider == "ollama"

    @property
    def is_harness(self) -> bool:
        """The entry runs through an agent harness (see :mod:`hani2.harness`)."""
        return bool(self.connection is not None and self.connection.preset.harness)

    def short(self) -> str:
        return f"{self.connection.name}:{self.model}" if self.ok else ""

    def record(self) -> dict[str, Any]:
        """What results, events and recordings keep (no secrets)."""
        e, c = self.entry, self.connection
        return {
            "purpose": self.purpose, "status": self.status, "source": self.source,
            "position": self.index + 1 if self.index >= 0 else None, "chain_length": len(self.chain),
            "label": e.label if e else "", "connection": c.name if c else "", "provider": c.provider if c else "",
            "auth": c.auth if c else "", "model": e.model if e else "", "litellm_model": self.litellm_model,
            "params": dict(e.params) if e else {}, "skipped": list(self.skipped), "error": self.error,
        }


_CLAUDE5 = re.compile(r"claude-[a-z]+-(?:[5-9]|\d\d)(?:\b|-|$)")
#: Claude models that refuse a forced tool choice (tool_choice any / a named tool)
_NO_FORCED_TOOLS = re.compile(r"claude-(?:(?:opus|sonnet)-5-[5-9]|(?:fable|mythos)-5-[1-9]|[a-z]+-(?:[6-9]|\d\d)(?:\b|-|$))")


def _drop_for(c: conns.Connection | None, model: str) -> tuple[str, ...]:
    """Sampling parameters the model refuses (Claude 5 models, through any provider)."""
    if _CLAUDE5.search(model or ""):
        return prov.PROVIDERS["anthropic"].drop_params
    return ()


def forced_tools_ok(model: str) -> bool:
    """Whether the model accepts a forced tool choice (``tool_choice="required"``)."""
    return not _NO_FORCED_TOOLS.search(model or "")


def resolve(purpose: str, *, start: int = 0, chain: list[Entry] | None = None, source: Source | None = None,
            fresh: bool = False, skipped: list[dict] | None = None) -> Resolution:
    """The first available entry of ``purpose``'s chain (from position ``start``)."""
    if chain is None:
        chain, source = chain_for(purpose)
    res = Resolution(purpose, source=source.id if source else "", chain=list(chain),
                     implicit=bool(source and source.implicit), skipped=list(skipped or []))
    first_usable: tuple[int, Entry, conns.Connection] | None = None
    for i in range(start, len(chain)):
        e = chain[i]
        c, why = connection_of(e)
        if c is None:
            res.skipped.append({"position": i + 1, "entry": e.title, "reason": why})
            continue
        if c.preset.harness:
            from hani2 import harness

            why = harness.refused_for(c, purpose)
            if why:
                res.skipped.append({"position": i + 1, "entry": e.title, "reason": why})
                continue
        bad = conns.refusal(c, e.model)
        if bad:
            res.skipped.append({"position": i + 1, "entry": e.title, "reason": bad})
            continue
        if first_usable is None:
            first_usable = (i, e, c)
        pr = conns.probe(c, e.model, fresh=fresh)
        if pr.ok:
            res.entry, res.index, res.connection = e, i, c
            res.status = "ok" if pr.verified else "unverified"
            return res
        res.skipped.append({"position": i + 1, "entry": e.title, "reason": conns.redact(pr.reason)})
    if res.implicit and first_usable is not None:
        # the old single-model settings: use them as before, even when the check failed
        i, e, c = first_usable
        res.entry, res.index, res.connection, res.status = e, i, c, "unverified"
        return res
    if not chain:
        res.error = f"no model chain for {purpose}"
    else:
        reasons = "; ".join(f"#{s['position']} {s['entry']}: {s['reason']}" for s in res.skipped)
        res.error = f"no model of the {purpose} chain ({res.source}) is available: {reasons}"
    return res


def resolve_entry(e: Entry, purpose: str = "test") -> Resolution:
    """Resolve a single entry (``Test`` buttons)."""
    return resolve(purpose, chain=[e], source=Source("test", {}), fresh=True)


# --------------------------------------------------------------------------- #
# Calls                                                                        #
# --------------------------------------------------------------------------- #
def litellm_kwargs(res: Resolution, **overrides: Any) -> dict[str, Any]:
    """The arguments of ``litellm.completion`` for a resolved entry (secrets included)."""
    from negmas_llm.common import apply_max_tokens

    if not res.ok:
        raise NoModelAvailable(res.error or f"no model for {res.purpose}")
    assert res.connection is not None and res.entry is not None
    bad = conns.refusal(res.connection, res.model)
    if bad:
        raise NoModelAvailable(f"{res.short()}: {bad}")
    if res.connection.preset.harness:
        from hani2 import harness

        harness.install_litellm_provider()
    params = {**res.entry.params, **{k: v for k, v in overrides.items() if v is not None}}
    for k in _drop_for(res.connection, res.model):
        params.pop(k, None)
    kw: dict[str, Any] = {"model": res.litellm_model}
    kw.update(conns.call_kwargs(res.connection))
    max_tokens = params.pop("max_tokens", None)
    effort = params.pop("reasoning_effort", None) or params.pop("reasoning", None) or params.pop("effort", None)
    if effort:
        kw["reasoning_effort"] = effort
    kw.update(params)
    apply_max_tokens(kw, res.litellm_provider or "openai", res.model, max_tokens)
    if res.connection.preset.harness:
        # litellm would refuse these for a custom provider; the harness adapter reads what it can use
        kw["allowed_openai_params"] = [k for k in ("reasoning_effort", "temperature", "top_p", "max_tokens",
                                                   "max_completion_tokens") if k in kw]
    return kw


_HARD = ("HarnessError", "HarnessUnavailable", "HarnessTimeout", "AuthenticationError", "NotFoundError", "APIConnectionError", "ServiceUnavailableError",
         "PermissionDeniedError", "RateLimitError", "Timeout", "TimeoutError", "TimeoutException", "InternalServerError",
         "BadGatewayError")


_HARD_STATUS = {401, 402, 403, 404, 408, 429}
# "model 'x' not found", "The model `x` does not exist", "model not found" -- not any "not found"
_MODEL_MISSING = re.compile(r"\bmodel(?:\s+[\"'`]?[\w./:@-]+[\"'`]?)?\s+(?:is\s+)?(?:not found|does not exist)")


def hard_failure(e: BaseException) -> bool:
    """Errors after which the next entry of the chain is tried."""
    if any(c.__name__ in _HARD for c in type(e).__mro__):  # exact names: FileNotFoundError is not NotFoundError
        return True
    status = getattr(e, "status_code", None)
    if isinstance(status, int) and (status in _HARD_STATUS or status >= 500):
        return True
    msg = str(e).lower()
    return bool(_MODEL_MISSING.search(msg)) or "connection refused" in msg


def completion(purpose: str, messages: list[dict] | Callable[[Resolution], list[dict]], *,
               models: "SessionModels | None" = None, resolution: Resolution | None = None,
               params: dict[str, Any] | None = None, **kwargs: Any) -> Any:
    """``litellm.completion`` with the resolved entry; a hard failure moves to the next entry."""
    import litellm

    res = resolution or (models.get(purpose) if models is not None else resolve(purpose))
    tried = 0
    while True:
        if not res.ok:
            raise NoModelAvailable(res.error or f"no model for {purpose}")
        kw = litellm_kwargs(res, **(params or {}))
        kw["messages"] = messages(res) if callable(messages) else messages
        kw.update(kwargs)
        if kw.get("tool_choice") == "required" and not forced_tools_ok(res.model):
            kw["tool_choice"] = "auto"  # the model refuses forced tool use; the prompt asks for an action
        try:
            return litellm.completion(**kw)
        except Exception as e:  # noqa: BLE001
            tried += 1
            if not hard_failure(e) or tried > len(res.chain):
                raise
            reason = conns.redact(f"{type(e).__name__}: {e}")[:300]
            if models is not None and resolution is None:
                nxt = models.advance(purpose, reason, failed=res)
            else:
                skipped = res.skipped + [{"position": res.index + 1, "entry": res.entry.title if res.entry else "",
                                          "reason": reason}]
                nxt = resolve(purpose, start=res.index + 1, chain=res.chain,
                              source=Source(res.source, {}, implicit=False), skipped=skipped)
            if not nxt.ok:
                raise
            print(f"[hani2] {purpose} model {res.short()} failed ({reason}); using {nxt.short()}")
            res = nxt


# --------------------------------------------------------------------------- #
# A session's models                                                           #
# --------------------------------------------------------------------------- #
class SessionModels:
    """The entries a session uses, one per purpose, resolved once and kept (pinned)."""

    def __init__(self, session: Any = None):
        self.session = session
        self.pinned: dict[str, Resolution] = {}
        self.changes: list[dict[str, Any]] = []
        self._lock = threading.RLock()

    def _bound(self):
        import contextlib

        from hani2 import projects

        s = self.session
        if s is None:
            return contextlib.nullcontext()
        return projects.use_study(getattr(s, "study_ref", None))

    def get(self, purpose: str) -> Resolution:
        with self._lock:
            res = self.pinned.get(purpose)
            if res is None:
                with self._bound():
                    res = resolve(purpose)
                self.pinned[purpose] = res
                self._announce(res, "model_resolved")
            return res

    def peek(self, purpose: str) -> Resolution | None:
        return self.pinned.get(purpose)

    def advance(self, purpose: str, reason: str, failed: Resolution | None = None) -> Resolution:
        """The next available entry after ``failed`` (default: the pinned entry) had a hard failure.

        The next entry is found from the entry that failed, not from the pinned one, so a call whose
        entry another call has already moved past still tries every later entry in order. The pinned
        entry only moves forward."""
        with self._lock:
            cur = self.pinned.get(purpose) or self.get(purpose)
            base = failed if failed is not None else cur
            skipped = base.skipped + [{"position": base.index + 1, "entry": base.entry.title if base.entry else "",
                                       "reason": reason}]
            with self._bound():
                nxt = resolve(purpose, start=base.index + 1, chain=base.chain,
                              source=Source(base.source, {}, implicit=False), skipped=skipped)
            if nxt.ok and nxt.index > cur.index:
                self.pinned[purpose] = nxt
                self._announce(nxt, "model_fallback", previous=cur)
            elif not nxt.ok and base is cur:
                self._announce(nxt, "model_fallback", previous=cur)
            return nxt

    def _announce(self, res: Resolution, action: str, previous: Resolution | None = None) -> None:
        rec = res.record()
        if previous is not None:
            rec["previous"] = {"connection": previous.connection.name if previous.connection else "",
                               "model": previous.model, "position": previous.index + 1}
        self.changes.append({"at": time.time(), "action": action, **rec})
        s = self.session
        if s is None:
            return
        try:
            from hani2 import events as ev

            sid = getattr(s, "sid", None)
            if res.ok or previous is not None:
                ev.log_event(sid, action, user=getattr(s, "user", None), component="models", action=res.purpose,
                             value=rec)
            else:
                ev.log_event(sid, ev.EventType.ERROR, user=getattr(s, "user", None), component="models",
                             action="model_unavailable", value=rec)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        if not res.ok and previous is not None:
            # a call failed and no later entry is available: the call's own error is shown by its
            # caller; the session keeps its entry (the next call may work again)
            print(f"[hani2] {res.purpose}: no further model to fall back to ({res.error})")
            return
        if not res.ok:
            msg = f"No language model is available for {PURPOSE_LABELS.get(res.purpose, res.purpose).lower()}: {res.error}"
            print(f"[hani2] ERROR: {msg}")
            try:
                s.model_error = msg
                s.toast(msg, "error", duration=0)
            except Exception:  # noqa: BLE001
                pass

    def records(self) -> dict[str, dict[str, Any]]:
        return {p: r.record() for p, r in self.pinned.items()}

    def attribution(self) -> dict[str, str]:
        """Results columns (added after the existing ones)."""
        out = {}
        for p in ("assistant", "opponent"):
            r = self.pinned.get(p)
            out[f"{p}_llm"] = r.short() if r is not None else ""
            out[f"{p}_llm_entry"] = f"{r.source}#{r.index + 1}" if r is not None and r.ok else ""
        out["llm_models"] = json.dumps(self.records(), default=str) if self.pinned else ""
        return out


#: results columns of :meth:`SessionModels.attribution`
MODEL_COLUMNS = ["assistant_llm", "assistant_llm_entry", "opponent_llm", "opponent_llm_entry", "llm_models"]


def models_of(obj: Any) -> SessionModels | None:
    """The :class:`SessionModels` of a session, a session state dict or a tool (``None`` if none)."""
    if obj is None:
        return None
    if isinstance(obj, SessionModels):
        return obj
    if isinstance(obj, dict):
        obj = obj.get("_session")
    m = getattr(obj, "models", None)
    if isinstance(m, SessionModels):
        return m
    s = getattr(obj, "session", None)
    m = getattr(s, "models", None)
    return m if isinstance(m, SessionModels) else None
