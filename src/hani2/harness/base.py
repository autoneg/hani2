"""The parts every harness adapter shares: limits, the child's environment, isolated folders,
transcripts and the result of a call.

Safety model (every adapter keeps to it; :mod:`tests.test_harness` checks the command lines):

* **Sign-in by API key only.** The child gets the connection's key in one environment variable
  and nothing else that can sign in: its environment is built from an *allowlist*
  (:data:`PASSTHROUGH`), never copied from the server's, so OAuth tokens, subscription
  variables and other keys of the server never reach it.
* **Isolated configuration.** ``HOME`` and the harness's own config folder point to an empty
  per-connection folder under ``settings/secrets/<name>/`` (0700), so a sign-in, settings,
  memory files, plugins, hooks or MCP servers of the server's user are never read.
* **No built-in tools.** File, shell, web, edit and MCP tools of the harness are off; only
  HANI2's own functions are offered (for the Assistant), and each one runs through HANI2's
  :class:`~hani2.support_agent.tools.ToolDispatcher`.
* **An empty working folder** per call (a fresh temporary folder, removed afterwards).
* **Caps** on turns and time per call (:class:`Limits`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: variables copied from the server's environment into a harness's (nothing that signs in)
PASSTHROUGH = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "USER", "LOGNAME", "SHELL",
               "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS", "REQUESTS_CA_BUNDLE",
               "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy",
               "SYSTEMROOT", "COMSPEC", "PATHEXT")

#: an executor of one HANI2 function: ``(name, arguments) -> result`` (through the dispatcher)
Execute = Callable[[str, dict], Any]


class HarnessError(RuntimeError):
    """A harness call that failed (the message never holds a secret)."""


class HarnessUnavailable(HarnessError):
    """The harness cannot be used at all (not installed, an extra missing, no key)."""


class HarnessTimeout(HarnessError):
    """The call took longer than its time cap (named so the model chain treats it as hard)."""


@dataclass
class Limits:
    """Caps on one call. Entry ``params`` may set ``timeout`` (seconds) and ``max_turns``."""

    timeout: float = 120.0
    #: model turns per call (a turn may call HANI2 functions; plain completions use 1)
    max_turns: int = 8
    #: Claude Code only: the most a call may spend (``--max-budget-usd``)
    max_budget_usd: float | None = None

    @classmethod
    def from_params(cls, params: dict[str, Any], *, tools: bool) -> Limits:
        def num(k: str, default: float, lo: float, hi: float) -> float:
            try:
                v = float(params.get(k, default))
            except (TypeError, ValueError):
                v = default
            return min(max(v, lo), hi)

        budget = params.get("max_budget_usd")
        return cls(timeout=num("timeout", 120.0, 5.0, 900.0),
                   max_turns=int(num("max_turns", 8 if tools else 1, 1, 40)),
                   max_budget_usd=float(budget) if isinstance(budget, (int, float)) and budget > 0 else None)


@dataclass
class ToolCall:
    """One HANI2 function the harness called, with the dispatcher's result."""

    id: str
    name: str
    arguments: dict
    result: Any


@dataclass
class HarnessReply:
    text: str
    calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float | None = None
    #: what the harness reported about itself (session id, version) — never a secret
    meta: dict[str, Any] = field(default_factory=dict)


def child_env(home: Path, extra: dict[str, str]) -> dict[str, str]:
    """The whole environment of a harness process: :data:`PASSTHROUGH`, an isolated ``HOME`` and
    ``TMPDIR``, and ``extra`` (the adapter's config-folder variable and the one key)."""
    env = {k: os.environ[k] for k in PASSTHROUGH if os.environ.get(k)}
    tmp = home / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    env.update(HOME=str(home), TMPDIR=str(tmp), TERM="dumb", NO_COLOR="1")
    env.update({k: v for k, v in extra.items() if v is not None})
    return env


def private_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:  # pragma: no cover
        pass
    return path


@contextmanager
def empty_workdir() -> Iterator[Path]:
    """A fresh, empty working folder for one call (removed afterwards)."""
    d = Path(tempfile.mkdtemp(prefix="hani2-harness-"))
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Transcripts                                                                  #
# --------------------------------------------------------------------------- #
def split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    """``(system prompt, the other messages)``; several system messages are joined."""
    sys_parts, rest = [], []
    for m in messages:
        if m.get("role") == "system":
            sys_parts.append(_text(m.get("content")))
        else:
            rest.append(m)
    return "\n\n".join(p for p in sys_parts if p), rest


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # OpenAI content parts
        return "\n".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
    return "" if content is None else str(content)


def render_prompt(messages: list[dict]) -> str:
    """The conversation (without the system prompt) as one prompt: a single user message is sent
    as it is; a longer history is written out with its HANI2 function calls and results."""
    from hani2.support_agent.runtime import flatten_tool_messages

    flat = flatten_tool_messages(messages)
    if len(flat) == 1 and flat[0].get("role") == "user":
        return _text(flat[0].get("content"))
    lines = ["The conversation so far (oldest first). Continue it: write the assistant's next reply to "
             "the last message, as the assistant."]
    for m in flat:
        role = str(m.get("role") or "user")
        lines.append(f"\n<{role}>\n{_text(m.get('content')).strip()}\n</{role}>")
    return "\n".join(lines)


def tool_specs(tools: list[dict]) -> list[dict]:
    """``[{name, description, parameters}]`` from OpenAI-style function schemas."""
    out = []
    for t in tools or []:
        f = t.get("function", t) if isinstance(t, dict) else {}
        name = str(f.get("name") or "")
        if name:
            params = f.get("parameters") or {"type": "object", "properties": {}}
            out.append({"name": name, "description": str(f.get("description") or ""), "parameters": params})
    return out


def safe_execute(execute: Execute, name: str, args: Any) -> Any:
    """Run one function through the dispatcher; an error becomes a result (the harness sees it)."""
    if not isinstance(args, dict):
        try:
            args = json.loads(args) if isinstance(args, str) and args.strip() else {}
        except json.JSONDecodeError:
            args = {}
    try:
        return execute(name, args if isinstance(args, dict) else {})
    except Exception as e:  # noqa: BLE001
        from hani2.connections import redact

        return {"ok": False, "error": redact(f"{type(e).__name__}: {e}")[:500]}


# --------------------------------------------------------------------------- #
# Finding the harness                                                          #
# --------------------------------------------------------------------------- #
_VERSIONS: dict[str, tuple[float, dict[str, Any]]] = {}
_VLOCK = threading.Lock()


def find_cli(names: tuple[str, ...], env_var: str) -> str | None:
    """The harness's executable: ``$<env_var>`` if set, else the first of ``names`` on ``PATH``."""
    explicit = (os.environ.get(env_var) or "").strip()
    if explicit:
        return explicit if Path(explicit).is_file() else None
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def cli_version(path: str | None, args: tuple[str, ...] = ("--version",), ttl: float = 600.0) -> dict[str, Any]:
    """``{found, path, version, error}`` of an executable (cached; runs ``--version`` with an empty
    environment, so it reads no configuration)."""
    if not path:
        return {"found": False, "path": "", "version": "", "error": "not installed (not on PATH)"}
    with _VLOCK:
        hit = _VERSIONS.get(path)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    try:
        with tempfile.TemporaryDirectory(prefix="hani2-harness-v-") as home:
            env = {"PATH": os.environ.get("PATH", ""), "HOME": home, "NO_COLOR": "1"}
            r = subprocess.run([path, *args], capture_output=True, text=True, timeout=10, env=env, cwd=home)
        out = (r.stdout or r.stderr or "").strip().splitlines()
        info = {"found": True, "path": path, "version": out[0].strip() if out else "", "error": ""}
    except Exception as e:  # noqa: BLE001
        info = {"found": False, "path": path, "version": "", "error": f"cannot run it: {type(e).__name__}"}
    with _VLOCK:
        _VERSIONS[path] = (time.time(), info)
    return info


class HarnessAdapter:
    """One harness. Subclasses set the class attributes and implement :meth:`complete` (and
    :meth:`run_tools` when ``tools`` is true)."""

    id: str = ""
    label: str = ""
    #: whether HANI2's functions can be offered safely (the Assistant's purpose)
    tools: bool = False
    #: the purposes this harness may serve (``None``: every purpose); a usage rule, see the adapter
    purposes: tuple[str, ...] | None = None
    #: the model providers this harness may call, ``{upstream: (key env var, label)}``
    upstreams: dict[str, tuple[str, str]] = {}
    default_upstream: str = ""
    #: the model the console's Test uses, per upstream
    default_models: dict[str, str] = {}
    #: the Python extra that holds the harness's SDK (if any)
    extra: str = ""
    #: the terms checked for this harness (shown in the console and the docs)
    sources: tuple[str, ...] = ()
    #: why only API keys are allowed
    auth_reason: str = ""

    def status(self) -> dict[str, Any]:
        """``{found, path, version, error}`` (no network, no configuration read)."""
        raise NotImplementedError

    def build(self, c: Any, model: str, *, system: str, prompt: str, workdir: Path, limits: Limits,
              tools: list[dict] | None = None, params: dict | None = None) -> dict[str, Any]:
        """What the adapter will start: ``{argv | options, env, cwd}`` (tests inspect it)."""
        raise NotImplementedError

    def complete(self, c: Any, model: str, messages: list[dict], params: dict[str, Any]) -> HarnessReply:
        raise NotImplementedError

    def run_tools(self, c: Any, model: str, messages: list[dict], tools: list[dict], execute: Execute,
                  params: dict[str, Any]) -> HarnessReply:
        raise HarnessUnavailable(f"{self.label} does not call HANI2's functions (completion only)")

    def check_model(self, c: Any, model: str) -> str:
        """Why ``model`` cannot be used through ``c`` (``""``: it can)."""
        return ""
