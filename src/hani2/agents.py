"""Opponent negotiators: names, groups and class resolution .

An *agent spec* is either a negotiator name / dotted path or a group token
starting with ``:`` (``:llm``, ``:template``, ``:negmas``, ``:hani``,
``:genius``, ``:notext``, ``:custom``, ``:pan``). A bare token that matches a
participant group file ``<results>/groups/<key>.json`` expands to that list.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from negmas import ResponseType
from negmas.helpers import get_class
from negmas.negotiators import Negotiator
from negmas.sao import SAOResponse
from hani2.config import load_llm_settings, results_root

from negmas.sao import SAONegotiator, SAOState

try:
    from negmas_llm import HybridWithTextNegotiator as DefaultNegotiator
except ImportError:
    try:
        from negmas.sao import HybridNegotiator as DefaultNegotiator
    except ImportError:
        from negmas.sao import AspirationNegotiator as DefaultNegotiator

# Import LLM negotiators from negmas-llm
LLM_NEGOTIATORS = []
try:
    from negmas_llm import (
        LLMBoulwareTBNegotiator,
        LLMConcederTBNegotiator,
        LLMLinearTBNegotiator,
        LLMHybridNegotiator,
    )

    LLM_NEGOTIATORS = [
        "LLMHybridNegotiator",
        "LLMBoulwareTBNegotiator",
        "LLMConcederTBNegotiator",
        "LLMLinearTBNegotiator",
    ]
except ImportError:
    LLMBoulwareTBNegotiator = None
    LLMConcederTBNegotiator = None
    LLMLinearTBNegotiator = None
    LLMHybridNegotiator = None

# Import template-based negotiators from negmas-llm (*WithTextNegotiator)
TEMPLATE_BASED_NEGOTIATORS = []
try:
    from negmas_llm import (
        BoulwareWithTextNegotiator,
        ConcederWithTextNegotiator,
        LinearWithTextNegotiator,
        HybridWithTextNegotiator,
    )

    TEMPLATE_BASED_NEGOTIATORS = [
        "HybridWithTextNegotiator",
        "BoulwareWithTextNegotiator",
        "ConcederWithTextNegotiator",
        "LinearWithTextNegotiator",
    ]
except ImportError:
    BoulwareWithTextNegotiator = None
    ConcederWithTextNegotiator = None
    LinearWithTextNegotiator = None
    HybridWithTextNegotiator = None

FAST_MICRO_NEGOTIATOR = None
try:
    from negmas.sao import FastMiCRONegotiator

    _ = FastMiCRONegotiator

    FAST_MICRO_NEGOTIATOR = "FastMiCRONegotiator"
except ImportError:
    pass

from negmas.sao import all_negotiator_types

try:
    import negmas.genius.gnegotiators as gneg

    GENIUS_NEGOTITORS = [f"genius.{x}" for x in gneg.__all__]
except Exception:  # pragma: no cover
    GENIUS_NEGOTITORS = []
NEGMAS_NEGOTIATORS = [_.__name__ for _ in all_negotiator_types()]  # type: ignore
HANI_NEGOTIATORS = [
    "helpers.AverageTitForTat",
    "helpers.HardHeaded",
    "helpers.AgentK",
    "helpers.Atlas3",
    "helpers.CUHKAgent",
    "helpers.AgentGG",
]
LLM_NEGOTIATORS = [
    "LLMHybridNegotiator",
    "LLMBoulwareTBNegotiator",
    "LLMConcederTBNegotiator",
    "LLMLinearTBNegotiator",
]
TEMPLATE_BASED_NEGOTIATORS = [
    "HybridWithTextNegotiator",
    "BoulwareWithTextNegotiator",
    "ConcederWithTextNegotiator",
    "LinearWithTextNegotiator",
]

# Agent groups for command-line selection (use :group_name syntax)
AGENT_GROUPS = {
    ":llm": LLM_NEGOTIATORS,
    ":template": TEMPLATE_BASED_NEGOTIATORS,
    ":negmas": NEGMAS_NEGOTIATORS,
    ":classic": HANI_NEGOTIATORS,
    ":hani": HANI_NEGOTIATORS,  # older name of :classic
    ":genius": GENIUS_NEGOTITORS,
}

# Boulware/Linear/Conceder/Hybrid with NO text component. Bare names
# resolve via negmas.sao in get_agent_type().
NOTEXT_NEGOTIATORS = [
    "BoulwareTBNegotiator",
    "ConcederTBNegotiator",
    "LinearTBNegotiator",
    "HybridNegotiator",
]


# --- Selectable agent groups -------------------------------------------------
# Used by the launch option (--opponents / HANI2_OPPONENTS), and per browser session
# via the ?opponents= (old: ?agents=) / ?group= query args (so the HAN "playground" link and an
# admin launcher can pick the opponent pool without restarting the server).
#
# The server stays a STANDALONE tool: it resolves its own built-in group tokens
# (:llm/:template/:negmas/:hani/:genius/:pan/:notext/:custom) itself, and for
# "participant" groups it only ever READS a JSON list file that an external
# tool may drop into DB_PATH/groups/<key>.json. It never calls another service
# or reads a competition database.

def _code_base(env_name: str, server_default: str) -> Path:
    """Resolve a per-machine code-base directory from an env var, falling
    back to the SERVER default (deliberately not the local dev layout, so an
    unset var on the server just works). Set HANI2_CODE_BASE / SCMLWEB_CODE_BASE
    per machine (e.g. ~/code/projects/hani, ~/code/sites/scmlweb locally)."""
    raw = os.environ.get(env_name, "").strip()
    return Path(raw).expanduser() if raw else Path(server_default).expanduser()


def _pan_search_paths() -> list:
    """Directories where pan.py might live. pan.py is a scmlweb artifact whose
    location differs per machine, so it's derived from HANI2_CODE_BASE /
    SCMLWEB_CODE_BASE (server defaults: ~/hani and ~/scmlweb). cwd is kept as a
    last-resort convenience."""
    hani_base = _code_base("HANI2_CODE_BASE", "~/hani2") if os.environ.get("HANI2_CODE_BASE") else _code_base("HANI_CODE_BASE", "~/hani")
    scml_base = _code_base("SCMLWEB_CODE_BASE", "~/scmlweb")
    return [hani_base, scml_base / "python", Path.cwd(), Path.cwd() / "python"]


def _import_pan():
    """Import pan.py (the personality-adjusted PAN pool) from the per-machine
    code bases, or return None when it isn't present — the server stays usable
    standalone without it."""
    import sys as _sys

    for p in _pan_search_paths():
        sp = str(p)
        if (p / "pan.py").exists() and sp not in _sys.path:
            _sys.path.insert(0, sp)
            break
    try:
        import pan as _pan  # type: ignore

        return _pan
    except Exception as e:
        print(f"⚠️ pan.py not importable for the :pan group ({e}).")
        return None


def _pan_group_specs() -> list:
    """The PAN pool (HSHP/HSLP/LSHP/LSLP) as importable 'pan.<ClassName>'
    strings, or [] when pan.py is unavailable. The classes are exposed as
    pan-module globals, so 'pan.<name>' is the reliable import path (their
    __module__ can be 'abc' from the dynamic type() creation)."""
    pan = _import_pan()
    if pan is None:
        return []
    out = []
    for bucket in ("HSHP", "HSLP", "LSHP", "LSLP"):
        for cls in getattr(pan, bucket, None) or []:
            name = getattr(cls, "__name__", "") or ""
            if name:
                out.append(f"pan.{name}")
    return out


def _read_group_file(key: str) -> "list[str] | None":
    """Read DB_PATH/groups/<key>.json (written by an external tool for
    participant groups; the server only ever reads it). Two accepted shapes:

      ["spec", ...]
      {"syspath": ["/abs/dir", ...], "agents": ["spec", ...]}

    The object form lets the writer point the server at the directory holding the
    unzipped agent packages: those dirs are added to sys.path here so the
    dotted specs (``<pkg>.<module>.<Class>``) import. The server stays standalone —
    it just adds paths it was told about and imports."""
    try:
        f = results_root() / "groups" / f"{key}.json"
        if not f.exists():
            return None
        data = json.loads(f.read_text())
        agents = data
        if isinstance(data, dict):
            import sys as _sys
            for d in data.get("syspath", []) or []:
                d = str(d)
                if d and d not in _sys.path:
                    _sys.path.append(d)
            agents = data.get("agents", [])
        if isinstance(agents, list):
            return [str(x) for x in agents if str(x).strip()]
    except Exception as e:
        print(f"⚠️ Could not read agent group file for '{key}': {e}")
    return None


def _resolve_agent_token(item) -> list:
    """Resolve ONE agent-list item to a list of agent specs:
      - ':pan'/':notext'/':custom'/':llm'/':template'/... -> built-in group
      - a bare key with a DB_PATH/groups/<key>.json file  -> that list
      - anything else                                     -> a single literal
        agent spec (class name / dotted path), returned unchanged.
    """
    if not isinstance(item, str):
        return [item]
    t = item.strip()
    if not t:
        return []
    low = t.lower()
    if low == ":pan":
        return _pan_group_specs()
    if low == ":notext":
        return list(NOTEXT_NEGOTIATORS)
    if low == ":custom":
        raw = os.environ.get("HANI2_CUSTOM_AGENTS") or os.environ.get("HANI_CUSTOM_AGENTS", "")
        return _expand_agent_items([s for s in raw.split(",") if s.strip()])
    if low.startswith(":"):
        grp = AGENT_GROUPS.get(low)
        if grp:
            return list(grp)
        avail = ", ".join(list(AGENT_GROUPS) + [":pan", ":notext", ":custom"])
        print(f"⚠️ Unknown agent group '{t}'. Available: {avail}")
        return []
    # Bare token: a materialised participant group file takes priority,
    # otherwise treat it as a literal agent class / dotted path.
    fromfile = _read_group_file(t)
    if fromfile is not None:
        return _expand_agent_items(fromfile)
    return [t]


def _expand_agent_items(items) -> list:
    """Expand a list of agent-list items (group tokens + literals) into a
    flat, de-duplicated, order-preserving list of agent specs."""
    out = []
    seen = set()
    for item in items:
        for spec in _resolve_agent_token(item):
            key = spec if isinstance(spec, str) else getattr(spec, "__name__", repr(spec))
            if key in seen:
                continue
            seen.add(key)
            out.append(spec)
    return out


def resolve_agent_group(key: str) -> list:
    """Resolve a GROUP key (from ?group=...) to agent specs. Accepts a
    built-in token (':template', ':pan', …) or a participant group-file
    key ('official', 'winners', …). Returns [] for an unknown/empty group."""
    if not key:
        return []
    k = key.strip()
    fromfile = _read_group_file(k)
    if fromfile is not None:
        return _expand_agent_items(fromfile)
    token = k if k.startswith(":") else ":" + k.lower()
    return _expand_agent_items([token])


def _prime_group_syspaths() -> None:
    """Add the ``syspath`` dirs of EVERY participant group file to sys.path
    at process startup.

    ``_read_group_file`` only appends a group's code dir to sys.path as a
    SIDE EFFECT of resolving ``?group=<key>``. A dotted agent spec
    (``a<id>.<module>.<Class>``) can reach ``get_class()`` in a process that
    never materialised that group — e.g. an admin-picked / persisted
    opponent used after the Load reload, or the playground opened without
    ``?group=`` — and then the top-level package import fails with
    ``No module named 'a<id>'`` even though the package exists on disk. By
    priming every group file's syspath once at import, specs resolve no
    matter how the session reached them. Idempotent and silent on error."""
    try:
        import sys as _sys

        gdir = results_root() / "groups"
        if not gdir.is_dir():
            return
        for f in sorted(gdir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            for d in data.get("syspath", []) or []:
                d = str(d)
                if d and d not in _sys.path:
                    _sys.path.append(d)
    except Exception:
        pass


def session_agent_override(args: dict[str, Any] | None) -> "list | None":
    """Per-session opponent-pool override from the query string: ``?opponents=``
    (csv of specs/tokens; ``?agents=`` is the old name) takes precedence over
    ``?group=<key>``."""
    args = args or {}

    def _val(name):
        v = args.get(name)
        if v is None:
            return None
        v = v[0] if isinstance(v, (list, tuple)) else v
        if isinstance(v, (bytes, bytearray)):
            v = v.decode()
        return str(v).strip()

    agents = _val("opponents") or _val("agents")
    if agents:
        specs = _expand_agent_items([s for s in agents.split(",") if s.strip()])
        if specs:
            return specs
    group = _val("group")
    if group:
        specs = resolve_agent_group(group)
        if specs:
            return specs
        print(f"⚠️ Agent group '{group}' resolved to no agents; ignoring override.")
    return None


def get_agent_type(x: Negotiator | str | None) -> Negotiator:
    # Handle file: prefix for loading classes from Python files
    if isinstance(x, str) and x.startswith("file:"):
        # Format: file:path/to/filename.ClassName
        # Examples:
        #   file:mynegotiator.MyNegotiator -> load MyNegotiator from mynegotiator.py (relative)
        #   file:a/b/c.MyClass -> load MyClass from a/b/c.py (relative with /, cross-platform)
        #   file:a\b\c.MyClass -> load MyClass from a\b\c.py (relative with \, Windows)
        #   file:/absolute/path/neg.MyClass -> load MyClass from /absolute/path/neg.py (absolute Unix)
        #   file:C:/path/neg.MyClass -> load MyClass from C:/path/neg.py (absolute Windows with /)
        #   file:C:\path\neg.MyClass -> load MyClass from C:\path\neg.py (absolute Windows with \)
        # Separators: / (cross-platform, recommended) or \ (Windows)
        import importlib.util
        import sys
        from pathlib import Path

        file_spec = x[5:]  # Remove "file:" prefix

        # Split by last dot to get class name
        parts = file_spec.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(
                f"Invalid file: format. Expected 'file:path/to/filename.ClassName', got '{x}'"
            )

        path_str, classname = parts

        # Check if path is absolute or relative
        # Absolute paths: start with / (Unix/Mac) or have drive letter (Windows: C:/ or C:\)
        path_obj = Path(path_str)
        is_absolute_path = path_obj.is_absolute() or (
            len(path_str) > 1 and path_str[1] == ":"
        )

        # Construct the filepath - Path handles both / and \ automatically
        if is_absolute_path:
            # Absolute path - use as-is
            filepath = Path(path_str + ".py")
        else:
            # Relative path - resolve from current working directory
            # Path() automatically handles both / and \ separators
            filepath = Path.cwd() / f"{path_str}.py"

        if not filepath.exists():
            raise FileNotFoundError(f"Could not find {filepath}")

        # Use a unique module name based on the full path to avoid conflicts
        # Replace path separators with dots for module name
        if filepath.is_absolute():
            # For absolute paths, create a unique module name from the full path
            module_name = (
                str(filepath.resolve().with_suffix(""))
                .replace("/", ".")
                .replace("\\", ".")
                .replace(":", "_")
            )
        else:
            module_name = path_str.replace("/", ".").replace("\\", ".")

        # Load module from file
        spec = importlib.util.spec_from_file_location(module_name, filepath)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module from {filepath}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Get class from module
        if not hasattr(module, classname):
            raise AttributeError(f"Module {module_name} has no class {classname}")

        return getattr(module, classname)

    # Handle LLM negotiators from negmas-llm
    if isinstance(x, str) and x.startswith("LLM"):
        if x == "LLMHybridNegotiator" and LLMHybridNegotiator:
            return LLMHybridNegotiator
        elif x == "LLMBoulwareTBNegotiator" and LLMBoulwareTBNegotiator:
            return LLMBoulwareTBNegotiator
        elif x == "LLMConcederTBNegotiator" and LLMConcederTBNegotiator:
            return LLMConcederTBNegotiator
        elif x == "LLMLinearTBNegotiator" and LLMLinearTBNegotiator:
            return LLMLinearTBNegotiator
    # Handle template-based negotiators from negmas-llm (*WithTextNegotiator)
    if isinstance(x, str) and x.endswith("WithTextNegotiator"):
        if x == "HybridWithTextNegotiator" and HybridWithTextNegotiator:
            return HybridWithTextNegotiator
        elif x == "BoulwareWithTextNegotiator" and BoulwareWithTextNegotiator:
            return BoulwareWithTextNegotiator
        elif x == "ConcederWithTextNegotiator" and ConcederWithTextNegotiator:
            return ConcederWithTextNegotiator
        elif x == "LinearWithTextNegotiator" and LinearWithTextNegotiator:
            return LinearWithTextNegotiator
    if isinstance(x, str) and "." not in x:
        x = f"negmas.sao.{x}"
    if isinstance(x, str) and x.startswith("helpers."):
        x = x[len("helpers.") :]
        x = f"hani2.helpers.negotiators.{x}"
    if isinstance(x, str) and x.startswith("genius."):
        x = x[len("genius.") :]
        x = f"negmas.genius.gnegotiators.{x}"
    return get_class(x)  # type: ignore


def _is_llm_negotiator_class(klass) -> bool:
    """True if ``klass`` is an LLM-backed negotiator (a subclass of
    negmas-llm's ``LLMNegotiator``, which includes ``OllamaNegotiator``
    and the Prolific practice opponents defined in ``pan.py``).

    Used so make_mechanism injects the configured model into LLM
    opponents whose *type string* does not start with the ``"LLM"``
    prefix the settings UI uses -- e.g. ``pan.PAHSHP0Negotiator``. Those
    otherwise fall back to negmas-llm's hard-coded default model
    (``smollm2:135m``), which is far too small to emit valid offers and
    breaks the negotiation on its first step.
    """
    try:
        from negmas_llm import LLMNegotiator  # type: ignore
    except Exception:
        return False
    return isinstance(klass, type) and issubclass(klass, LLMNegotiator)


def _is_llm_meta_negotiator_class(klass) -> bool:
    """True if ``klass`` subclasses negmas-llm's ``LLMMetaNegotiator`` -- the
    base most HAN LLM submissions use to wrap a numeric core with an LLM
    message layer. These are NOT ``LLMNegotiator`` subclasses, so make_mechanism
    handles their model injection separately (see the elif there)."""
    try:
        from negmas_llm.meta import LLMMetaNegotiator  # type: ignore
    except Exception:
        return False
    return isinstance(klass, type) and issubclass(klass, LLMMetaNegotiator)


def _ctor_accepts(klass, param: str) -> bool:
    """True if ``klass.__init__`` declares an explicit keyword ``param`` (a
    named parameter, not merely ``**kwargs``). Used so we only inject an LLM
    setting the constructor can actually receive; injecting a name the agent
    also passes to ``super().__init__`` via ``**kwargs`` would be a
    duplicate-keyword ``TypeError``."""
    import inspect

    try:
        sig = inspect.signature(klass.__init__)
    except (TypeError, ValueError):
        return False
    p = sig.parameters.get(param)
    return p is not None and p.kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    )


# Cache of "no-accept-None" subclasses keyed by the original agent class, so we
# build one wrapper per base type rather than one per negotiator instance.
_NO_ACCEPT_NONE_CLASSES: dict[type, type] = {}


def no_accept_none_class(base: type) -> type:
    """Return a subclass of ``base`` that forbids accepting a *None* offer.

    Any agent (not just pan.py's) can decide to ACCEPT on a turn where there is
    no offer on the table (e.g. its opening move, or after the opponent sent a
    text-only / None offer). negmas' SAOMechanism treats an ACCEPT of a None
    offer as a hard break (agreement=None), which kills the negotiation. We do
    NOT want to forbid accepting real offers -- only the meaningless accept of
    a None offer. So we wrap the agent's ``__call__``: if it returns
    ACCEPT_OFFER while ``state.current_offer is None``, downgrade it to a
    REJECT_OFFER with no counter (preserving any text/data), which -- with the
    mechanism's ``end_on_no_response=False`` -- simply passes the (empty) turn
    to the human and lets the agent act normally next step.
    """
    wrapped = _NO_ACCEPT_NONE_CLASSES.get(base)
    if wrapped is not None:
        return wrapped

    def __call__(self, state: SAOState, dest: str | None = None) -> SAOResponse:
        response = base.__call__(self, state, dest)
        if (
            response.response == ResponseType.ACCEPT_OFFER
            and state.current_offer is None
        ):
            return SAOResponse(ResponseType.REJECT_OFFER, None, response.data)
        return response

    # Construct via the base's metaclass so any custom metaclass stays happy.
    meta = type(base)
    wrapped = meta(
        f"NoAcceptNone_{base.__name__}", (base,), {"__call__": __call__}
    )
    _NO_ACCEPT_NONE_CLASSES[base] = wrapped
    return wrapped


# Cache of "no-end" subclasses keyed by the original agent class (one wrapper
# per base type), parallel to _NO_ACCEPT_NONE_CLASSES.
_NO_END_CLASSES: dict[type, type] = {}


def no_end_class(base: type) -> type:
    """Return a subclass of ``base`` that never ends the negotiation itself.

    Any agent (e.g. the LLM-backed pan.py practice opponents) can return
    END_NEGOTIATION -- for an LLM that simply means it emitted
    ``"response_type": "end"`` (see negmas_llm's response map). negmas' mechanism
    then stops with ``agreement=None``. We want the agent to be able to walk away
    in a *real* negotiation, but NOT in a Prolific *practice* round, where the
    participant is still learning the interface and an agent that quits leaves
    them with a confusing no-deal outcome. So we wrap the agent's ``__call__``:
    an END_NEGOTIATION is downgraded to a plain REJECT_OFFER (no counter,
    preserving any text/data), which keeps the round going. Apply this ONLY to
    practice rounds; counted/normal negotiations keep the unwrapped class.
    """
    wrapped = _NO_END_CLASSES.get(base)
    if wrapped is not None:
        return wrapped

    def __call__(self, state: SAOState, dest: str | None = None) -> SAOResponse:
        response = base.__call__(self, state, dest)
        if response.response == ResponseType.END_NEGOTIATION:
            return SAOResponse(ResponseType.REJECT_OFFER, None, response.data)
        return response

    meta = type(base)
    wrapped = meta(f"NoEnd_{base.__name__}", (base,), {"__call__": __call__})
    _NO_END_CLASSES[base] = wrapped
    return wrapped

# --------------------------------------------------------------------------- #
# hani2 additions                                                              #
# --------------------------------------------------------------------------- #
#: Default fallback pool: non-LLM negotiators that still talk, so a casual
#: visit never incurs LLM cost.
DEFAULT_POOL = list(TEMPLATE_BASED_NEGOTIATORS) or list(NOTEXT_NEGOTIATORS)

#: The groups offered in the admin "Opponents" settings.
SELECTABLE_GROUPS = {
    "llm": LLM_NEGOTIATORS,
    "template": TEMPLATE_BASED_NEGOTIATORS,
    "notext": NOTEXT_NEGOTIATORS,
    "negmas": NEGMAS_NEGOTIATORS,
    "classic": HANI_NEGOTIATORS,
    "genius": GENIUS_NEGOTITORS,
}


def expand_agents(items) -> list:
    """Public wrapper: expand group tokens / literals into agent specs."""
    if isinstance(items, str):
        items = [s for s in items.split(",") if s.strip()]
    return _expand_agent_items(list(items or []))


def short_name(spec: Any) -> str:
    name = spec if isinstance(spec, str) else getattr(spec, "__name__", str(spec))
    return str(name).split(":")[-1].split(".")[-1]


def make_agent(spec: Any, params: dict[str, Any] | None = None, practice: bool = False,
               verbose: bool = False):
    """Instantiate an opponent from a spec, applying the safety wrappers
    and LLM model injection."""
    params = dict(params or {})
    agent_class = get_agent_type(spec)
    is_llm_string = isinstance(spec, str) and spec.startswith("LLM")
    if is_llm_string or _is_llm_negotiator_class(agent_class):
        llm = load_llm_settings()
        params["model"] = llm.get("model", "qwen3:4b-instruct")
        if is_llm_string:
            params["provider"] = llm.get("provider", "ollama")
    elif _is_llm_meta_negotiator_class(agent_class):
        llm = load_llm_settings()
        if _ctor_accepts(agent_class, "model"):
            params["model"] = llm.get("model", "qwen3:4b-instruct")
        if _ctor_accepts(agent_class, "provider"):
            params["provider"] = llm.get("provider", "ollama")
    agent_class = no_accept_none_class(agent_class)  # type: ignore
    if practice:
        agent_class = no_end_class(agent_class)
    if verbose:
        try:
            return agent_class(**params, verbose=True)
        except TypeError:
            pass
    return agent_class(**params)
