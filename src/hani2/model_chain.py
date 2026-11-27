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

**Named sequences.** Besides the purposes, a models.json may define any number of *named
sequences* (chains with a name) under ``sequences``; a purpose may name one instead of giving a
chain::

    {"default": [...],
     "judge": "judge-strict",
     "sequences": {"judge-strict": [{"connection": "openai", "model": "gpt-5", "params": {"effort": "high"}}],
                   "small": {"entries": ["anthropic:claude-haiku-5-5"], "description": "cheap and fast"},
                   "large": {"disabled": true}}}

Named sequences merge *per name* across the layers: the most specific layer that mentions a name
wins, so a study that defines ``small`` still sees the global ``large``; ``{"disabled": true}``
hides an inherited one. ``default`` and the purposes are sequences too (``default``, ``judge``, …)
and keep the purpose rule above. Built-in sequences (:data:`BUILTIN_SEQUENCES`: ``tiny``,
``offline``, ``small``, ``medium``, ``large``) sit below every layer. The Assistant, tools and the
judge may ask for a sequence by name for any call (:func:`completion`'s ``sequence``); with the
``own_models`` capability an Assistant may also define its own sequences for its session
(:meth:`SessionModels.define`), with its own keys and addresses.

Entry parameters are passed to the provider; ``effort`` (``reasoning_effort``) and ``thinking``
(``true``/``false`` or a token budget) are translated for each provider (:func:`litellm_kwargs`).
"""

from __future__ import annotations

import contextvars
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
#: a sequence name (also what tells a purpose's sequence reference from a ``provider:model`` text)
SEQUENCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
#: the sequences every installation has (below every layer; a layer may override or disable them).
#: ``offline`` and ``tiny`` use only the local Ollama server (connection ``ollama-local``).
BUILTIN_SEQUENCES: dict[str, dict[str, Any]] = {
    "tiny": {"description": "A tiny local Ollama model (fast, weak; good for tests and simple text tasks)",
             "entries": [{"connection": "ollama-local", "model": "qwen3:0.6b", "params": {"thinking": False}},
                         {"connection": "ollama-local", "model": "gemma3:270m"}]},
    "offline": {"description": "Only models on the local Ollama server (nothing leaves the machine)",
                "entries": [{"connection": "ollama-local", "model": "qwen3:4b-instruct"},
                            {"connection": "ollama-local", "model": "qwen3:8b", "params": {"thinking": False}},
                            {"connection": "ollama-local", "model": "qwen3:0.6b", "params": {"thinking": False}}]},
    "small": {"description": "Small, fast and cheap models",
              "entries": [{"provider": "anthropic", "model": "claude-haiku-5-5"},
                          {"provider": "openai", "model": "gpt-5-mini", "params": {"effort": "low"}},
                          {"connection": "ollama-local", "model": "qwen3:4b-instruct"}]},
    "medium": {"description": "Medium-sized models",
               "entries": [{"provider": "anthropic", "model": "claude-sonnet-5-5"},
                           {"provider": "openai", "model": "gpt-5", "params": {"effort": "medium"}},
                           {"connection": "ollama-local", "model": "qwen3:30b-a3b", "params": {"thinking": False}}]},
    "large": {"description": "The largest models (slow, expensive)",
              "entries": [{"provider": "anthropic", "model": "claude-opus-5-5", "params": {"effort": "high"}},
                          {"provider": "openai", "model": "gpt-5.5", "params": {"effort": "high"}}]},
}


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


@dataclass
class Sequence:
    """A named chain of a layer (``entries`` empty and ``disabled``: hides an inherited one)."""
    name: str
    entries: list[Entry] = field(default_factory=list)
    description: str = ""
    disabled: bool = False

    def public(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "disabled": self.disabled,
                "entries": [_entry_public(e) for e in self.entries]}


@dataclass
class Parsed:
    """A models.json body: purpose chains, purposes that name a sequence, named sequences."""
    chains: dict[str, list[Entry]] = field(default_factory=dict)
    refs: dict[str, str] = field(default_factory=dict)
    sequences: dict[str, Sequence] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.chains or self.refs or self.sequences)


def is_sequence_ref(x: Any) -> bool:
    """Whether a purpose's value names a sequence (``"small"``) rather than giving a chain."""
    return isinstance(x, str) and ":" not in x and "," not in x and bool(SEQUENCE_NAME.match(x.strip()))


def check_sequence_name(name: Any) -> str:
    if not isinstance(name, str) or not SEQUENCE_NAME.match(name):
        raise ChainError(f"invalid sequence name {name!r}: letters, digits, '.', '_' and '-' (up to 64)")
    return name


def parse_sequence(name: str, x: Any, strict: bool = True) -> Sequence:
    """A named sequence from a chain, ``{"entries", "description"}`` or ``{"disabled": true}``."""
    check_sequence_name(name)
    if x is None or x is False:
        return Sequence(name, disabled=True)
    if isinstance(x, dict):
        unknown = set(x) - {"entries", "description", "disabled"}
        if unknown:
            raise ChainError(f"sequence {name!r}: unknown keys {', '.join(sorted(unknown))} "
                             "(use entries, description, disabled)")
        if x.get("disabled"):
            return Sequence(name, description=str(x.get("description") or ""), disabled=True)
        entries = parse_chain(x.get("entries"), strict)
        if not entries:
            raise ChainError(f"sequence {name!r} has no entries (to hide an inherited one: {{\"disabled\": true}})")
        return Sequence(name, entries, str(x.get("description") or ""))
    entries = parse_chain(x, strict)
    if not entries:
        raise ChainError(f"sequence {name!r} has no entries")
    return Sequence(name, entries)


def parse_models(data: Any, strict: bool = True) -> Parsed:
    """A models.json body (a bare list is the default chain)."""
    out = Parsed()
    if data is None:
        return out
    if isinstance(data, (list, str)):
        data = {"default": data}
    if not isinstance(data, dict):
        raise ChainError("models.json must hold a mapping of purposes to chains")
    for k, v in data.items():
        if k.startswith("_"):
            continue
        if k == "sequences":
            if v is None:
                continue
            if not isinstance(v, dict):
                raise ChainError("sequences must be a mapping of names to chains")
            for name, body in v.items():
                if name in ("default", *PURPOSES):
                    if body is None or (isinstance(body, dict) and body.get("disabled")):
                        raise ChainError(f"the {name!r} sequence cannot be disabled")
                    if is_sequence_ref(body):
                        out.refs[name] = body.strip()
                    else:
                        seq = parse_sequence(name, body, strict)
                        out.chains[name] = seq.entries
                    continue
                out.sequences[name] = parse_sequence(name, body, strict)
            continue
        if k not in ("default", *PURPOSES):
            raise ChainError(f"unknown purpose {k!r}; use default, {', '.join(PURPOSES)}, or define it under "
                             "\"sequences\"")
        if is_sequence_ref(v):
            if v.strip() == k:
                raise ChainError(f"{k!r} names itself")
            out.refs[k] = v.strip()
        else:
            out.chains[k] = parse_chain(v, strict)
    return out


def parse_chains(data: Any, strict: bool = True) -> dict[str, list[Entry]]:
    """``{purpose: chain}`` from a models.json body (a bare list is the default chain; purposes that
    name a sequence and named sequences are left out: see :func:`parse_models`)."""
    return parse_models(data, strict).chains


def read_layer_file(path: Path) -> dict[str, Any]:
    """A layer's own models.json as a mapping (a bare list is the default chain; ``{}`` when missing)."""
    if not path.exists():
        return {}
    data = _read(path)
    if isinstance(data, (list, str)):
        return {"default": data}
    return data if isinstance(data, dict) else {}


def unknown_refs(data: Any) -> list[str]:
    """Problems of the sequences a models.json body's purposes name, against the sequences in
    effect at the current layer (and the body's own): missing or disabled ones."""
    try:
        parsed = parse_models(data, strict=False)
    except ChainError as e:
        return [str(e)]
    out: list[str] = []
    for purpose, name in parsed.refs.items():
        own = parsed.sequences.get(name)
        if own is not None:
            if own.disabled:
                out.append(f"{purpose!r} names the sequence {name!r}, which this file disables")
            continue
        if name in ("default", *PURPOSES):
            continue
        _ch, _src, why = sequence_chain(name)
        if why:
            out.append(f"{purpose!r} names the sequence {name!r}: {why}")
    return out


def check_chains(data: Any) -> list[str]:
    """Problems of a models.json body (``[]``: none)."""
    try:
        parse_models(data)
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
    id: str  # study:P/S | project:P | start | settings | legacy | builtin
    chains: dict[str, list[Entry]]
    implicit: bool = False
    #: purposes that name a sequence (``{"judge": "judge-strict"}``)
    refs: dict[str, str] = field(default_factory=dict)
    #: named sequences of this layer (a disabled one hides an inherited one)
    sequences: dict[str, Sequence] = field(default_factory=dict)

    def chain(self, purpose: str) -> list[Entry] | None:
        """This layer's chain of ``purpose`` (its own, the sequence it names, or its default)."""
        for p in (purpose, "default"):
            if p in self.refs:
                return _ref_chain(self.refs[p])  # [] when it is missing or disabled: stops the walk
            if self.chains.get(p):
                return self.chains[p]
        return None

    def ref_of(self, purpose: str) -> str:
        """The sequence this layer's chain of ``purpose`` names (``""``: none)."""
        if purpose in self.refs:
            return self.refs[purpose]
        return "" if self.chains.get(purpose) else self.refs.get("default", "")

    def mentions(self, purpose: str) -> bool:
        return bool(self.chains.get(purpose) or purpose in self.refs)


#: purposes being resolved through sequence references (a cycle guard)
_FOLLOWING: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar("hani2_following", default=())


def _ref_chain(name: str) -> list[Entry]:
    """The entries of the sequence a purpose names (``[]`` when it is missing, disabled or a cycle)."""
    seen = _FOLLOWING.get()
    if name in seen:
        print(f"[hani2] ERROR: the model sequences name each other in a cycle ({' -> '.join(seen + (name,))})")
        return []
    tok = _FOLLOWING.set(seen + (name,))
    try:
        ch, _src, why = sequence_chain(name)
        if why:
            print(f"[hani2] {why}")
        return ch
    finally:
        _FOLLOWING.reset(tok)


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


def _parse_layer(data: Any, where: str) -> Parsed:
    try:
        return parse_models(data, strict=False)
    except ChainError as e:
        print(f"[hani2] ERROR: {where}: {e}; ignoring it")
        return Parsed()


def _source(sid: str, p: Parsed) -> Source:
    return Source(sid, p.chains, refs=p.refs, sequences=p.sequences)


def builtin_source() -> Source:
    seqs = {}
    for name, body in BUILTIN_SEQUENCES.items():
        try:
            seqs[name] = parse_sequence(name, body, strict=False)
        except ChainError as e:  # pragma: no cover - the built-ins are checked by the tests
            print(f"[hani2] ERROR: built-in sequence {name}: {e}")
    return Source("builtin", {}, implicit=False, sequences=seqs)


def sources(include_legacy: bool = True, include_builtin: bool = True) -> list[Source]:
    """Every layer that gives chains, most specific first (bound to the current study / layer view)."""
    from hani2.config import _VIEW, settings_dir, settings_layers

    out: list[Source] = []
    for folder in settings_layers():
        f = folder / FILE
        if f.exists():
            parsed = _parse_layer(_read(f), str(f))
            if parsed.chains or parsed.refs:
                out.append(_source(_layer_id(folder), parsed))
                continue
            legacy = _layer_legacy(folder)
            if parsed.sequences or legacy:
                src = _source(_layer_id(folder), parsed)
                src.chains = legacy
                out.append(src)
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
        parsed = _parse_layer(ov, "the settings overrides (models)")
        if parsed:
            out.append(_source("overrides", parsed))
    view = _VIEW.get()
    if not (view and view[1]):
        f = settings_dir() / FILE
        if f.exists():
            parsed = _parse_layer(_read(f), str(f))
            if parsed:
                out.append(_source("settings", parsed))
    if include_legacy:
        out.append(Source("legacy", _legacy_chains(), implicit=True))
    if include_builtin:
        out.append(builtin_source())
    return out


def chain_for(purpose: str) -> tuple[list[Entry], Source | None]:
    """The chain of ``purpose`` and the layer it comes from. A layer whose chain names a sequence
    that is missing or disabled gives an empty chain (it fails visibly, see :func:`resolve`)."""
    for src in sources():
        ch = src.chain(purpose)
        if ch is not None:
            return ch, src
    return [], None


def sequence_chain(name: str, own: "dict[str, Sequence] | None" = None) -> tuple[list[Entry], Source | None, str]:
    """The entries of sequence ``name``: ``(entries, source, why_not)``.

    ``default`` and the purposes follow the purpose rule (:func:`chain_for`); any other name is
    looked up per name, most specific layer first, then the built-ins; ``own``: an Assistant's own
    sequences (checked first)."""
    if name in ("default", *PURPOSES):
        ch, src = chain_for(name)
        return ch, src, "" if ch else f"no model chain for {name}"
    if own and name in own:
        return list(own[name].entries), Source("assistant", {}), ""
    for src in sources():
        seq = src.sequences.get(name)
        if seq is None:
            continue
        if seq.disabled:
            return [], src, f"the model sequence {name!r} is disabled ({src.id})"
        return list(seq.entries), src, ""
    return [], None, f"no model sequence named {name!r} (known: {', '.join(sequence_names()) or 'none'})"


def sequence_names(include_disabled: bool = False) -> list[str]:
    """Every sequence name available at the current layer (``default`` and ``judge`` first)."""
    names: list[str] = ["default", "judge"]
    disabled: set[str] = set()
    seen: set[str] = set()
    for src in sources():
        for n, seq in src.sequences.items():
            if n in seen:
                continue
            seen.add(n)
            if seq.disabled:
                disabled.add(n)
            elif n not in names:
                names.append(n)
    if include_disabled:
        names += sorted(disabled)
    return names


def effective_sequences() -> list[dict[str, Any]]:
    """Every named sequence at the current layer: where it comes from, whether it is disabled and
    its entries (for the console and the Assistant)."""
    out: list[dict[str, Any]] = []
    for name in ("default", "judge"):
        ch, src, _ = sequence_chain(name)
        out.append({"name": name, "source": src.id if src else "", "disabled": False, "builtin": False,
                    "purpose": True, "description": PURPOSE_LABELS.get(name, ""),
                    "entries": [_entry_public(e) for e in ch]})
    seen: set[str] = set()
    for src in sources():
        for n, seq in src.sequences.items():
            if n in seen:
                continue
            seen.add(n)
            d = seq.public()
            d.update(source=src.id, builtin=src.id == "builtin", purpose=False)
            if not d["description"] and src.id != "builtin" and n in BUILTIN_SEQUENCES:
                d["description"] = BUILTIN_SEQUENCES[n].get("description", "")
            out.append(d)
    return out


def effective_chains() -> dict[str, Any]:
    """What every purpose uses at the current layer: ``{purpose: {source, entries, sequence}}`` (for the
    console)."""
    out: dict[str, Any] = {}
    for p in ("default", *PURPOSES):
        if p == "default":
            ch, src = next(((s.chain("default"), s) for s in sources() if s.mentions("default")), ([], None))
            ch = ch or []
        else:
            ch, src = chain_for(p)
        ref = ""
        if src is not None:
            ref = src.refs.get(p) or ("" if src.chains.get(p) else src.refs.get("default", ""))
        out[p] = {"source": src.id if src else "", "implicit": bool(src and src.implicit), "sequence": ref,
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
    #: the named sequence this came from (``""``: the purpose's own chain)
    sequence: str = ""

    @property
    def key(self) -> str:
        """What a session pins it under: the purpose, or ``purpose@sequence``."""
        return f"{self.purpose}@{self.sequence}" if self.sequence else self.purpose

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
            "purpose": self.purpose, "sequence": self.sequence, "status": self.status, "source": self.source,
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
            fresh: bool = False, skipped: list[dict] | None = None, sequence: str = "",
            own: "dict[str, Sequence] | None" = None) -> Resolution:
    """The first available entry of ``purpose``'s chain, or of the named ``sequence`` (from position
    ``start``)."""
    why = ""
    if chain is None:
        if sequence:
            chain, source, why = sequence_chain(sequence, own)
        else:
            chain, source = chain_for(purpose)
    res = Resolution(purpose, source=source.id if source else "", chain=list(chain),
                     implicit=bool(source and source.implicit), skipped=list(skipped or []), sequence=sequence)
    if why:
        res.error = why
        return res
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
    what = f"model sequence {sequence!r}" if sequence else f"{purpose} chain"
    ref = source.ref_of(purpose) if (source is not None and not sequence and not chain) else ""
    if ref:
        _ch, _src, why = sequence_chain(ref)
        res.error = f"the {purpose} chain of {res.source} names the model sequence {ref!r}: {why or 'it has no entries'}"
    elif not chain:
        res.error = f"no {what}"
    else:
        reasons = "; ".join(f"#{s['position']} {s['entry']}: {s['reason']}" for s in res.skipped)
        res.error = f"no model of the {what} ({res.source}) is available: {reasons}"
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
    thinking = params.pop("thinking", None)
    kw.update(thinking_kwargs(res.litellm_provider, res.model, thinking, effort))
    kw.update(params)
    apply_max_tokens(kw, res.litellm_provider or "openai", res.model, max_tokens)
    if res.connection.preset.harness:
        # litellm would refuse these for a custom provider; the harness adapter reads what it can use
        kw["allowed_openai_params"] = [k for k in ("reasoning_effort", "temperature", "top_p", "max_tokens",
                                                   "max_completion_tokens") if k in kw]
    return kw


def thinking_kwargs(litellm_provider: str, model: str, thinking: Any, effort: Any) -> dict[str, Any]:
    """The provider's arguments for an entry's ``thinking`` (``true``/``false``, a token budget or a
    provider's own ``thinking`` mapping) and ``effort`` (``none``/``minimal``/``low``/``medium``/
    ``high``/``xhigh``/``max``; ``reasoning_effort`` in litellm).

    * Ollama: ``think`` (``false`` switches a thinking model's reasoning off; gpt-oss takes the effort);
    * Anthropic: a token budget becomes ``thinking={"type": "enabled", "budget_tokens": n}``;
      ``true`` without an effort is ``reasoning_effort="medium"``;
    * everyone else: ``reasoning_effort`` (``false`` without an effort leaves it out)."""
    out: dict[str, Any] = {}
    if isinstance(thinking, dict):
        out["thinking"] = thinking
        if effort:
            out["reasoning_effort"] = effort
        return out
    if isinstance(thinking, str) and thinking.strip().lower() in ("true", "false", "on", "off", "yes", "no"):
        thinking = thinking.strip().lower() in ("true", "on", "yes")
    elif isinstance(thinking, str) and thinking.strip():
        effort, thinking = effort or thinking.strip(), True  # "thinking": "high" reads as an effort
    budget = thinking if isinstance(thinking, int) and not isinstance(thinking, bool) else None
    if litellm_provider == "ollama":
        if (model or "").startswith("gpt-oss"):
            if effort or thinking:
                out["reasoning_effort"] = effort or "medium"
        elif thinking is not None:
            out["think"] = bool(thinking)
        elif effort:
            out["reasoning_effort"] = effort
        return out
    if budget is not None and litellm_provider == "anthropic":
        if budget > 0:
            out["thinking"] = {"type": "enabled", "budget_tokens": budget}
        return out
    if thinking is False:
        if effort:
            out["reasoning_effort"] = effort
        return out
    if effort or thinking:
        out["reasoning_effort"] = effort or "medium"
    return out


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
               params: dict[str, Any] | None = None, sequence: str = "", **kwargs: Any) -> Any:
    """``litellm.completion`` with the resolved entry; a hard failure moves to the next entry.

    ``sequence``: use that named sequence instead of the purpose's chain (still recorded under
    ``purpose``)."""
    import litellm

    res = resolution or (models.get(purpose, sequence) if models is not None else resolve(purpose, sequence=sequence))
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
                              source=Source(res.source, {}, implicit=False), skipped=skipped,
                              sequence=res.sequence)
            if not nxt.ok:
                raise
            print(f"[hani2] {purpose} model {res.short()} failed ({reason}); using {nxt.short()}")
            res = nxt


# --------------------------------------------------------------------------- #
# An Assistant's own sequences                                                 #
# --------------------------------------------------------------------------- #
#: sign-in keys an Assistant's own entry may carry (an admin's entries may not: see SECRET_PARAMS)
OWN_SIGN_IN = ("api_key", "api_base", "base_url")


def parse_own_entry(x: Any, sequence: str = "own", index: int = 0) -> Entry:
    """An entry of an Assistant's own sequence. It signs in by itself, never with the server's
    connections or keys: ``{"provider": "openai", "model": "gpt-5", "api_key": "sk-…"}`` (the
    provider's usual address) and/or ``"api_base": "https://…"`` (its own server; without a key
    nothing is sent to sign in). The key is used only for the calls and masked in every log and
    error; it is never stored. The study's models are used through the study's sequences."""
    if not isinstance(x, dict) or not any(x.get(k) for k in OWN_SIGN_IN):
        raise ChainError("an entry of an Assistant's own sequence signs in by itself: give 'api_key' and/or "
                         "'api_base' (the study's own models are used through its named sequences)")
    d = dict(x)
    if "api_key_env" in d:
        raise ChainError("an Assistant's own entry cannot read the server's environment (api_key_env); give api_key")
    sign = {k: d.pop(k) for k in OWN_SIGN_IN if k in d}
    if d.get("connection"):
        raise ChainError("an entry with its own api_key / api_base names a provider, not a connection")
    e = parse_entry(d)
    p = prov.get(e.provider)
    if p is None or p.harness or not p.offered:
        raise ChainError(f"provider {e.provider!r} cannot be used in an Assistant's own sequence")
    key = str(sign.get("api_key") or "")
    base = str(sign.get("api_base") or sign.get("base_url") or "")
    if key:
        conns.remember_secret(key)
    # auth is "inline" (its key) or "none": never the provider's environment variable
    c = conns.Connection(name=f"assistant-{sequence}-{index + 1}", provider=p.id,
                         auth="inline" if key else "none", base_url=base, implicit=True,
                         litellm_provider=e.provider if p.id == "litellm" else "")
    c.inline_key = key
    e.inline = c
    return e


# --------------------------------------------------------------------------- #
# A session's models                                                           #
# --------------------------------------------------------------------------- #
class SessionModels:
    """The entries a session uses, one per purpose (and per named sequence a call asked for),
    resolved once and kept (pinned)."""

    def __init__(self, session: Any = None):
        self.session = session
        self.pinned: dict[str, Resolution] = {}
        self.changes: list[dict[str, Any]] = []
        #: sequences the Assistant defined for this session (``own_models`` capability; never stored)
        self.own: dict[str, Sequence] = {}
        self._lock = threading.RLock()

    def _bound(self):
        import contextlib

        from hani2 import projects

        s = self.session
        if s is None:
            return contextlib.nullcontext()
        return projects.use_study(getattr(s, "study_ref", None))

    def get(self, purpose: str, sequence: str = "") -> Resolution:
        """The pinned entry of ``purpose`` (or of the named ``sequence``, used for ``purpose``)."""
        key = f"{purpose}@{sequence}" if sequence else purpose
        with self._lock:
            res = self.pinned.get(key)
            if res is None:
                with self._bound():
                    res = resolve(purpose, sequence=sequence, own=self.own)
                self.pinned[key] = res
                self._announce(res, "model_resolved")
            return res

    def peek(self, purpose: str, sequence: str = "") -> Resolution | None:
        return self.pinned.get(f"{purpose}@{sequence}" if sequence else purpose)

    def sequences(self) -> list[dict[str, Any]]:
        """The named sequences this session can use (the admin's and the Assistant's own)."""
        with self._bound():
            out = [d for d in effective_sequences() if not d["disabled"]]
        out += [{**seq.public(), "source": "assistant", "builtin": False, "purpose": False}
                for seq in self.own.values()]
        return out

    def define(self, name: str, entries: Any, description: str = "") -> Sequence:
        """Add (or replace) one of the Assistant's own sequences for this session. Entries may carry
        their own sign-in (``api_key``, ``api_key_env``, ``api_base``): see :func:`parse_own_entry`.
        A name the admin's sequences (or a purpose) already use is refused."""
        check_sequence_name(name)
        with self._bound():
            taken = name in ("default", *PURPOSES) or name in sequence_names(include_disabled=True)
        if taken:
            raise ChainError(f"{name!r} is already a model sequence of the study; choose another name")
        if isinstance(entries, (str, dict)):
            entries = [entries]
        if not isinstance(entries, (list, tuple)) or not entries:
            raise ChainError("a sequence needs at least one entry")
        seq = Sequence(name, [parse_own_entry(e, name, i) for i, e in enumerate(entries)], str(description or ""))
        with self._lock:
            self.own[name] = seq
            for k in [k for k in self.pinned if k.endswith(f"@{name}")]:
                self.pinned.pop(k, None)
        return seq

    def advance(self, purpose: str, reason: str, failed: Resolution | None = None) -> Resolution:
        """The next available entry after ``failed`` (default: the pinned entry) had a hard failure.

        The next entry is found from the entry that failed, not from the pinned one, so a call whose
        entry another call has already moved past still tries every later entry in order. The pinned
        entry only moves forward."""
        with self._lock:
            key = failed.key if failed is not None else purpose
            seq = failed.sequence if failed is not None else ""
            cur = self.pinned.get(key) or self.get(purpose, seq)
            base = failed if failed is not None else cur
            skipped = base.skipped + [{"position": base.index + 1, "entry": base.entry.title if base.entry else "",
                                       "reason": reason}]
            with self._bound():
                nxt = resolve(purpose, start=base.index + 1, chain=base.chain,
                              source=Source(base.source, {}, implicit=False), skipped=skipped, sequence=seq)
            if nxt.ok and nxt.index > cur.index:
                self.pinned[key] = nxt
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

    def assistant_sequence(self) -> str:
        """The named sequence the session's Assistant uses for its replies (``""``: its chain)."""
        sa = getattr(self.session, "support_agent", None)
        try:
            return str(sa._sequence() or "") if sa is not None and hasattr(sa, "_sequence") else ""
        except Exception:  # noqa: BLE001
            return ""

    def attribution(self) -> dict[str, str]:
        """Results columns (added after the existing ones). ``assistant_llm`` is the entry of the
        sequence the Assistant uses for its replies when it chose one."""
        out = {}
        aseq = self.assistant_sequence()
        for p in ("assistant", "opponent"):
            r = self.pinned.get(f"{p}@{aseq}") if p == "assistant" and aseq else None
            r = r or self.pinned.get(p)
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
