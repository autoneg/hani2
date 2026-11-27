"""The hosted-agent protocol (``hani2-hosted/1``): specs, endpoints and the JSON encodings.

A hosted (self-hosted, remote) agent is reached at an address instead of being imported:

* ``remote:<name>`` — an endpoint registered for the project (:mod:`hani2.hosting.registry`);
* ``remote+https://host:port[/path][#token_env=VAR]`` — a direct address (admins and files only);
* ``{"url": ..., "token_env": ...}`` — the same as a mapping in ``study.yaml`` / ``project.yaml``.

HANI2 never deserialises Python objects from a host: what a host sends back is plain JSON (an
outcome, a text, action names with arguments) that HANI2 checks. The host does deserialise the
utility function HANI2 sends (negmas serialisation); it trusts HANI2 because it holds the token.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

PROTOCOL = "hani2-hosted/1"
REMOTE_PREFIX = "remote:"
DIRECT_PREFIXES = ("remote+http://", "remote+https://")
KINDS = ("assistant", "opponent")
DEFAULT_TIMEOUT = 30.0
#: the most outcomes a utility function is sent as a table (when negmas cannot serialise it)
MAX_TABLE = 100_000
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class HostedError(RuntimeError):
    """A hosted agent could not be reached, refused, timed out or answered nonsense. The message never
    holds the token."""


def valid_name(name: Any) -> bool:
    return isinstance(name, str) and bool(_NAME.match(name)) and ".." not in name


def is_remote_spec(spec: Any) -> bool:
    """Whether ``spec`` names a hosted agent (a ``remote:`` name, a ``remote+http(s)://`` address or a
    mapping with ``url``)."""
    if isinstance(spec, dict):
        return isinstance(spec.get("url"), str)
    if not isinstance(spec, str):
        return False
    s = spec.strip().lower()
    return s.startswith(REMOTE_PREFIX) or s.startswith(DIRECT_PREFIXES)


def is_direct_address(spec: Any) -> bool:
    """A spec that names an address (not a registered name): never accepted from a non-admin's URL."""
    if isinstance(spec, dict):
        return True
    return isinstance(spec, str) and spec.strip().lower().startswith(DIRECT_PREFIXES)


def spec_from_mapping(m: dict) -> str:
    """``{"url": "https://h:1", "token_env": "T"}`` → ``remote+https://h:1#token_env=T``; a mapping with
    ``name`` (a registered endpoint) → ``remote:<name>``."""
    if m.get("name") and not m.get("url"):
        return REMOTE_PREFIX + str(m["name"])
    url = str(m["url"]).strip()
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"a hosted agent's url must start with http:// or https:// (got {url!r})")
    frag = f"#token_env={m['token_env']}" if m.get("token_env") else ""
    return "remote+" + url + frag


def normalise_spec(spec: Any) -> Any:
    """A mapping becomes its string spec; anything else is returned unchanged."""
    if isinstance(spec, dict) and is_remote_spec(spec) or isinstance(spec, dict) and spec.get("name"):
        return spec_from_mapping(spec)
    return spec


@dataclass
class Endpoint:
    """Where and how to reach one hosted agent. ``name`` is what results and boards record."""

    name: str
    url: str
    token: str | None = None
    kind: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    team: str = ""

    @property
    def label(self) -> str:
        return self.name

    def public(self) -> dict[str, Any]:
        """What may be shown to an admin (never the token)."""
        return {"name": self.name, "url": self.url, "kind": self.kind, "team": self.team, "timeout": self.timeout,
                "has_token": bool(self.token)}


def _check_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise HostedError(f"not a valid address: {url!r}")
    return url.rstrip("/")


def direct_name(url: str) -> str:
    """The name a direct address is recorded under: ``host:port`` (no path, no credentials)."""
    p = urlsplit(url)
    return f"{p.hostname}{':' + str(p.port) if p.port else ''}"


def parse_direct(spec: str, timeout: float | None = None) -> Endpoint:
    """``remote+https://host:port/path#token_env=VAR`` → an :class:`Endpoint` (the token from ``VAR``)."""
    s = spec.strip()[len("remote+"):]
    url, _, frag = s.partition("#")
    token = None
    params = dict(p.split("=", 1) for p in frag.split("&") if "=" in p) if frag else {}
    if params.get("token_env"):
        token = os.environ.get(params["token_env"]) or None
    t = float(params["timeout"]) if params.get("timeout") else (timeout or DEFAULT_TIMEOUT)
    url = _check_url(url)
    return Endpoint(name="remote+" + direct_name(url), url=url, token=token, timeout=t)


def short_label(spec: Any) -> str:
    """A display name for a hosted spec: the registered name, or ``host:port`` (never a token or path)."""
    spec = normalise_spec(spec)
    s = str(spec).strip()
    if s.lower().startswith(REMOTE_PREFIX):
        return s[len(REMOTE_PREFIX):]
    if s.lower().startswith(DIRECT_PREFIXES):
        try:
            return direct_name(s[len("remote+"):].partition("#")[0])
        except Exception:  # noqa: BLE001
            return "remote"
    return s


def recorded_spec(spec: Any) -> str:
    """What results rows and events record for a hosted spec: ``remote:<name>`` as given, a direct
    address without its fragment (no token variable names, no query)."""
    spec = normalise_spec(spec)
    s = str(spec).strip()
    if s.lower().startswith(DIRECT_PREFIXES):
        return "remote+" + direct_name(s[len("remote+"):].partition("#")[0])
    return s


# --------------------------------------------------------------------------- #
# JSON encodings                                                               #
# --------------------------------------------------------------------------- #
def json_safe(v: Any, depth: int = 0) -> Any:
    """``v`` as plain JSON (tuples become lists, non-finite floats ``None``, unknown objects strings)."""
    if depth > 12:
        return None
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else None
    if isinstance(v, dict):
        return {str(k): json_safe(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [json_safe(x, depth + 1) for x in v]
    try:
        import numpy as np  # noqa: PLC0415

        if isinstance(v, np.generic):
            return json_safe(v.item(), depth + 1)
    except Exception:  # noqa: BLE001
        pass
    return str(v)


def encode_outcome_space(os_: Any) -> dict:
    """The outcome space as its issues (negmas serialisation of each issue) and name."""
    from negmas.serialization import serialize

    return {"name": getattr(os_, "name", None), "issues": [serialize(i) for i in os_.issues]}


def decode_outcome_space(d: dict) -> Any:
    from negmas.outcomes import make_os
    from negmas.serialization import deserialize

    d = copy.deepcopy(d)  # negmas' deserialize consumes its input
    if isinstance(d, dict) and "issues" in d and "__python_class__" not in d:
        return make_os([deserialize(i) for i in d["issues"]], name=d.get("name"))
    return deserialize(d)


def _sample(os_: Any, n: int = 200) -> list:
    try:
        return list(os_.enumerate_or_sample(max_cardinality=n))[:n]
    except Exception:  # noqa: BLE001
        return []


def encode_ufun(u: Any) -> dict:
    """A utility function for the host: the negmas serialisation as YAML (JSON would turn the integer
    keys of a value table into strings), checked by a round trip on a sample of outcomes; else a table
    of every outcome's utility (up to :data:`MAX_TABLE` outcomes)."""
    import yaml
    from negmas.serialization import deserialize, serialize

    try:
        text = yaml.safe_dump(serialize(u), sort_keys=False)
        back = deserialize(yaml.safe_load(text))
        for o in _sample(u.outcome_space):
            a, b = float(u(o)), float(back(o))
            if not (math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9) or (math.isnan(a) and math.isnan(b))):
                raise ValueError("round trip changed a utility")
        return {"format": "negmas-yaml", "ufun": text}
    except Exception:  # noqa: BLE001
        pass
    os_ = u.outcome_space
    n = getattr(os_, "cardinality", math.inf)
    if not n or n > MAX_TABLE:
        raise HostedError("the utility function cannot be sent to the hosted agent (not serialisable and too "
                          "many outcomes for a table)")
    outs = list(os_.enumerate_or_sample())
    return {"format": "table", "outcome_space": encode_outcome_space(os_),
            "outcomes": [json_safe(list(o)) for o in outs], "values": [json_safe(float(u(o))) for o in outs],
            "reserved_value": json_safe(float(u.reserved_value)) if u.reserved_value is not None else None}


def decode_ufun(d: dict) -> Any:
    from negmas.serialization import deserialize

    d = copy.deepcopy(d)  # negmas' deserialize consumes its input
    if d.get("format") == "table":
        from negmas.preferences import MappingUtilityFunction

        os_ = decode_outcome_space(d["outcome_space"])
        table: Any = {tuple(o): float(v) if v is not None else 0.0 for o, v in zip(d["outcomes"], d["values"])}
        return MappingUtilityFunction(table, outcome_space=os_, reserved_value=d.get("reserved_value") or 0.0)
    if d.get("format") == "negmas-yaml":
        import yaml

        return deserialize(yaml.safe_load(d["ufun"]))
    return deserialize(d["ufun"])


def issue_names(os_: Any) -> list[str]:
    return [str(i.name) for i in getattr(os_, "issues", ())]


def check_outcome(value: Any, os_: Any) -> tuple | None:
    """A host's outcome (a list in issue order, or ``{issue: value}``) as a tuple of the outcome space, or
    ``None`` when it is missing; raises :class:`HostedError` when it is not a valid outcome."""
    if value is None:
        return None
    issues = list(getattr(os_, "issues", ()))
    if isinstance(value, dict):
        try:
            value = [value[i.name] for i in issues]
        except KeyError as e:
            raise HostedError(f"the outcome has no value for issue {e.args[0]!r}") from None
    if not isinstance(value, (list, tuple)) or len(value) != len(issues):
        raise HostedError(f"an outcome must give one value per issue ({len(issues)})")
    out = []
    for i, v in zip(issues, value):
        # numbers arrive from JSON as floats or ints: try the value as given, then its other form
        cands = [v]
        if isinstance(v, float) and v.is_integer():
            cands.append(int(v))
        elif isinstance(v, int) and not isinstance(v, bool):
            cands.append(float(v))
        for c in cands:
            try:
                if i.is_valid(c):
                    out.append(c)
                    break
            except Exception:  # noqa: BLE001
                pass
        else:
            raise HostedError(f"{v!r} is not a valid value of issue {i.name!r}")
    return tuple(out)


def encode_state(state: Any, me: str | None = None) -> dict:
    """The parts of an SAO state a hosted opponent needs (plain JSON); ``current_proposer`` is ``self``,
    ``partner`` or ``None``."""
    prop = getattr(state, "current_proposer", None)
    data = getattr(state, "current_data", None)
    return json_safe({
        "step": getattr(state, "step", 0), "time": getattr(state, "time", 0.0),
        "relative_time": getattr(state, "relative_time", 0.0), "running": getattr(state, "running", True),
        "current_offer": list(state.current_offer) if getattr(state, "current_offer", None) is not None else None,
        "current_proposer": None if prop is None else ("self" if me is not None and prop == me else "partner"),
        "current_text": (data or {}).get("text") if isinstance(data, dict) else None,
        "current_data": data if isinstance(data, dict) else None,
        "n_acceptances": getattr(state, "n_acceptances", 0),
    })


def decode_state(d: dict, me: str | None = None, partner: str | None = None) -> Any:
    """An :class:`negmas.sao.SAOState` from :func:`encode_state` (on the host)."""
    from negmas.sao import SAOState

    prop = d.get("current_proposer")
    offer = d.get("current_offer")
    return SAOState(running=bool(d.get("running", True)), started=True, step=int(d.get("step") or 0),
                    time=float(d.get("time") or 0.0), relative_time=float(d.get("relative_time") or 0.0),
                    current_offer=tuple(offer) if offer is not None else None,
                    current_proposer=me if prop == "self" else (partner if prop == "partner" else None),
                    current_data=d.get("current_data") or ({"text": d["current_text"]} if d.get("current_text") else None),
                    n_acceptances=int(d.get("n_acceptances") or 0), n_negotiators=2)


def model_label(m: Any) -> str:
    """``provider/model`` from a host's ``model`` field (a mapping or a string), cut to 120 characters."""
    if not m:
        return ""
    if isinstance(m, dict):
        p, n = str(m.get("provider") or "").strip(), str(m.get("model") or "").strip()
        s = f"{p}/{n}" if p and n else (n or p)
    else:
        s = str(m)
    return re.sub(r"[\r\n\t]", " ", s)[:120]
