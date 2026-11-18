"""Per-negotiation LLM call logging for the negotiation server.

When enabled (env ``HANI_LLM_LOG`` truthy), every ``litellm.completion`` call
made by the opponent agent during a negotiation is appended — prompt, full
response, hidden reasoning if any, model, latency and token budget — to ONE
log file per negotiation, stored beside that negotiation's other data under the
participant's session directory (``<user_path>/llm_logs/<mechanism_id>.jsonl``).

This complements the negotiation trace: the trace shows *what* was offered; this
shows *why* — the exact prompts and raw model output, so an empty/None turn can
be diagnosed later.

Design
------
* A single global wrapper around ``litellm.completion`` (installed once) writes
  an entry whenever a log target is active.
* The active target is held in a :class:`contextvars.ContextVar`, set only for
  the duration of a mechanism ``step()`` (see :func:`attach_mechanism`). Because
  each browser session steps its own mechanism, concurrent Prolific participants
  never cross-write: each ``step`` sets its own file in its own context and
  resets it immediately after.
* Fully env-gated and best-effort: any logging error is swallowed so it can
  never disturb a live negotiation.
"""

from __future__ import annotations

import contextvars
import json
import os
import threading
import time
from pathlib import Path

# The log file the CURRENT step should write to (None = logging inactive).
_current_log: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "hani2_llm_log", default=None
)
_installed = False
_install_lock = threading.Lock()
_write_lock = threading.Lock()


def enabled() -> bool:
    """Whether per-negotiation LLM logging is switched on via the environment."""
    return (os.environ.get("HANI2_LLM_LOG") or os.environ.get("HANI_LLM_LOG", "")).strip().lower() in ("1", "true", "yes", "on")


def install(force: bool = False) -> None:
    """Wrap ``litellm.completion`` once so active calls are logged (to the
    per-negotiation file when logging is on, and to the session's recording
    — see :mod:`hani2.recording`).

    Safe to call repeatedly; a no-op if already installed, or if logging is
    disabled and ``force`` is not set.
    """
    global _installed
    if _installed or not (enabled() or force):
        return
    with _install_lock:
        if _installed:
            return
        try:
            import litellm
        except Exception:  # noqa: BLE001 - litellm always present in practice
            return
        original = litellm.completion

        def _logged_completion(*args, **kwargs):
            target = _current_log.get()
            t0 = time.perf_counter()
            try:
                resp = original(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                if target:
                    _write(target, kwargs, None, time.perf_counter() - t0, error=_redact(repr(exc)))
                _record(kwargs, None, time.perf_counter() - t0, _redact(repr(exc)))
                raise
            if target:
                _write(target, kwargs, resp, time.perf_counter() - t0)
            _record(kwargs, resp, time.perf_counter() - t0)
            return resp

        litellm.completion = _logged_completion
        _installed = True


def _redact(text: str) -> str:
    """``text`` without any stored key or token (see :func:`hani2.connections.redact`)."""
    try:
        from hani2.connections import redact

        return redact(text)
    except Exception:  # noqa: BLE001
        return text


def _record(kwargs: dict, resp, dt: float, error: str | None = None) -> None:
    try:
        from hani2.recording.recorder import record_llm_call

        record_llm_call(kwargs, resp, dt, error)
    except Exception:  # noqa: BLE001
        pass


def _write(target: str, kwargs: dict, resp, dt: float, error: str | None = None) -> None:
    """Append one JSON-lines entry for a single LLM call. Never raises."""
    try:
        content = ""
        reasoning = None
        if resp is not None:
            try:
                msg = resp.choices[0].message
                content = msg.content or ""
                reasoning = getattr(msg, "reasoning_content", None)
            except Exception:  # noqa: BLE001
                pass
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "model": kwargs.get("model"),
            "latency_s": round(dt, 3),
            "num_predict": kwargs.get("num_predict") or kwargs.get("max_tokens"),
            "temperature": kwargs.get("temperature"),
            "messages": kwargs.get("messages"),
            "response": content,
            "empty_response": not content.strip(),
        }
        if reasoning:
            entry["reasoning"] = reasoning
        if error:
            entry["error"] = error
        path = Path(target)
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, default=str, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 - logging must never break a negotiation
        pass


def attach_mechanism(mechanism, log_path: str | os.PathLike) -> None:
    """Route LLM calls made during ``mechanism.step()`` to ``log_path``.

    Wraps the mechanism's ``step`` so the log target is active only while the
    negotiation is being stepped (which is when the opponent agent calls its
    LLM). Announces the log file path on the terminal once. No-op if disabled.
    """
    if not enabled():
        return
    install()
    log_path = str(log_path)
    original_step = mechanism.step

    def _step(*args, **kwargs):
        token = _current_log.set(log_path)
        try:
            return original_step(*args, **kwargs)
        finally:
            _current_log.reset(token)

    try:
        mechanism.step = _step  # type: ignore[assignment]
    except Exception:  # noqa: BLE001
        return
    print(
        f"[hani2] LLM call log for negotiation {getattr(mechanism, 'id', '?')}: "
        f"{log_path}",
        flush=True,
    )
