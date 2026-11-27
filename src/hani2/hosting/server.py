"""The host side: serve a HANI2 Assistant class or a negmas negotiator over ``hani2-hosted/1``.

``hani2 host-opponent my_module:MyNegotiator --token-env TEAM_TOKEN`` or
``hani2 host-assistant my_module:MyAssistant --token-env TEAM_TOKEN`` (see :func:`serve`), or in Python::

    from hani2.hosting import make_app
    app = make_app("opponent", "negmas.sao.BoulwareTBNegotiator", token="...")   # any ASGI server

**Isolation:** every negotiation is a session id that HANI2 makes; the host keeps one agent instance
per id (:class:`SessionStore`), steps of one session run one at a time, and sessions never share
state. A session idle for ``idle_timeout`` seconds is dropped; at most ``max_sessions`` live at once.
A repeated step (the same ``seq``) returns the stored reply, so a retry never acts twice.
"""

from __future__ import annotations

import secrets
import threading
import time
import traceback
from typing import Any, Callable

from hani2.hosting.protocol import (KINDS, PROTOCOL, HostedError, decode_outcome_space, decode_state, decode_ufun,
                                    json_safe, valid_name)

DEFAULT_IDLE_TIMEOUT = 3600.0
DEFAULT_MAX_SESSIONS = 200


class SessionStore:
    """One runner per session id, with idle cleanup."""

    def __init__(self, idle_timeout: float = DEFAULT_IDLE_TIMEOUT, max_sessions: int = DEFAULT_MAX_SESSIONS):
        self.idle_timeout = float(idle_timeout)
        self.max_sessions = int(max_sessions)
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._items)

    def ids(self) -> list[str]:
        with self._lock:
            return list(self._items)

    def reap(self, now: float | None = None) -> list[str]:
        """Drop the sessions idle longer than ``idle_timeout``; returns their ids."""
        now = time.time() if now is None else now
        with self._lock:
            gone = [k for k, v in self._items.items() if now - v["used"] > self.idle_timeout]
            items = [self._items.pop(k) for k in gone]
        for it in items:
            _safe_close(it["runner"])
        return gone

    def add(self, sid: str, runner: Any) -> None:
        self.reap()
        with self._lock:
            if sid in self._items:
                raise KeyError(sid)
            if len(self._items) >= self.max_sessions:
                raise OverflowError(f"this host already runs {self.max_sessions} negotiations")
            self._items[sid] = {"runner": runner, "used": time.time(), "lock": threading.Lock(), "seq": None,
                                "reply": None}

    def get(self, sid: str) -> dict[str, Any] | None:
        with self._lock:
            it = self._items.get(sid)
            if it is not None:
                it["used"] = time.time()
            return it

    def drop(self, sid: str) -> bool:
        with self._lock:
            it = self._items.pop(sid, None)
        if it is None:
            return False
        _safe_close(it["runner"])
        return True


def _safe_close(runner: Any) -> None:
    try:
        runner.close()
    except Exception:  # noqa: BLE001
        traceback.print_exc()


# --------------------------------------------------------------------------- #
# Opponents                                                                    #
# --------------------------------------------------------------------------- #
def _encode_response(resp: Any) -> dict:
    from negmas import ResponseType

    r = getattr(resp, "response", None)
    data = getattr(resp, "data", None)
    data = data if isinstance(data, dict) else {}
    out: dict[str, Any] = {"text": data.get("text"), "data": json_safe({k: v for k, v in data.items() if k != "text"})}
    if r == ResponseType.ACCEPT_OFFER:
        out["response"] = "accept"
    elif r == ResponseType.END_NEGOTIATION:
        out["response"] = "end"
    else:
        out["response"] = "reject"
        o = getattr(resp, "outcome", None)
        out["outcome"] = json_safe(list(o)) if o is not None else None
    return out


class OpponentRunner:
    """One hosted negotiator for one negotiation. It joins a local stand-in mechanism with the same
    outcome space and limits (never run) whose state follows the one HANI2 sends, so the negotiator
    sees an ordinary interface (``self.nmi``, ``self.ufun``, ``state.relative_time``)."""

    def __init__(self, factory: Callable[..., Any], setup: dict, model: Any = None):
        from negmas.sao import SAOMechanism, SAONegotiator, SAOResponse
        from negmas import ResponseType

        class _Partner(SAONegotiator):  # the human side of the stand-in mechanism; never asked
            def __call__(self, state, dest=None):
                return SAOResponse(ResponseType.REJECT_OFFER, None)

        os_ = decode_outcome_space(setup["outcome_space"])
        ufun = decode_ufun(setup["ufun"])
        self.mechanism = SAOMechanism(outcome_space=os_, n_steps=setup.get("n_steps") or None,
                                      time_limit=setup.get("time_limit") or None, ignore_negotiator_exceptions=False)
        name = str(setup.get("name") or "opponent")
        self.negotiator = factory(name=name)
        self.partner = _Partner(name="partner")
        self.mechanism.add(self.negotiator, ufun=ufun)
        self.mechanism.add(self.partner)
        self.model = model
        self._started = False

    def step(self, body: dict) -> dict:
        state = decode_state(body.get("state") or {}, me=self.negotiator.id, partner=self.partner.id)
        self.mechanism._current_state = state  # what self.nmi.state reads
        if not self._started:
            self._started = True
            start = getattr(self.negotiator, "_on_negotiation_start", None) or self.negotiator.on_negotiation_start
            start(state)
        out = _encode_response(self.negotiator(state, None))
        if self.model:
            out["model"] = self.model
        return out

    def close(self) -> None:
        if self._started:
            try:
                end = getattr(self.negotiator, "_on_negotiation_end", None) or self.negotiator.on_negotiation_end
                end(self.mechanism.state)
            except Exception:  # noqa: BLE001
                pass


def opponent_factory(spec: Any) -> Callable[..., Any]:
    """A callable that makes the negotiator: a class, a ``module:Class`` / ``module.Class`` / negmas name /
    ``file:`` spec (as HANI2's opponent specs), or any callable taking ``name=``."""
    if callable(spec) and not isinstance(spec, str):
        return spec
    from hani2.agents import get_agent_type

    s = str(spec).strip()
    if ":" in s and not s.startswith("file:"):
        mod, _, attr = s.rpartition(":")
        s = f"{mod}.{attr}"
    return get_agent_type(s)


# --------------------------------------------------------------------------- #
# The app                                                                      #
# --------------------------------------------------------------------------- #
def make_app(kind: str, agent: Any, *, token: str | None = None, name: str | None = None, version: str = "",
             model: Any = None, events: list[str] | None = None, idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
             max_sessions: int = DEFAULT_MAX_SESSIONS, allow_no_token: bool = False):
    """A FastAPI app serving ``agent`` (an opponent spec / class, or an Assistant class / spec) as ``kind``.

    ``token``: the team's secret; every request must carry ``Authorization: Bearer <token>`` (only
    ``GET /health`` needs none). Without a token the host refuses to start unless ``allow_no_token``
    (local tests). ``version``: whatever the team declares (shown by HANI2; a hint, never checked).
    ``model``: ``{"provider", "model"}`` reported with every reply when the agent does not report its
    own. ``events``: optional Assistant events the host wants (``draft_changed``)."""
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse

    if kind not in KINDS:
        raise ValueError(f"kind must be assistant or opponent (got {kind!r})")
    if not token and not allow_no_token:
        raise ValueError("a hosted agent needs a token (--token-env VAR); HANI2 sends it with every request")
    if kind == "opponent":
        factory = opponent_factory(agent)

        def make_runner(setup: dict) -> Any:
            return OpponentRunner(factory, setup, model=model)
        label = name or getattr(factory, "__name__", "opponent")
    else:
        from hani2.hosting.host_assistant import AssistantRunner, assistant_factory

        klass = assistant_factory(agent)

        def make_runner(setup: dict) -> Any:
            return AssistantRunner(klass, setup, model=model)
        label = name or getattr(klass, "name", None) or getattr(klass, "__name__", "assistant")
    store = SessionStore(idle_timeout, max_sessions)
    app = FastAPI(title=f"HANI2 hosted {kind}: {label}", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.store = store
    expected = f"Bearer {token}" if token else None

    @app.middleware("http")
    async def _auth(request: Request, call_next):
        if request.url.path != "/health" and expected is not None:
            got = request.headers.get("authorization") or ""
            if not secrets.compare_digest(got.encode(), expected.encode()):
                return JSONResponse({"error": "missing or wrong token"}, status_code=401)
        return await call_next(request)

    @app.get("/health")
    def _health():
        return {"ok": True}

    @app.get("/info")
    def _info():
        return json_safe({"protocol": PROTOCOL, "kind": kind, "name": label, "version": version,
                          "events": list(events or []), "model": model, "sessions": len(store)})

    @app.post("/sessions")
    def _create(body: dict):
        sid = str(body.get("session_id") or "")
        if not valid_name(sid):
            return JSONResponse({"error": "session_id must be letters, digits, '.', '_' or '-' (≤ 64)"}, 400)
        if body.get("kind") not in (None, kind):
            return JSONResponse({"error": f"this host serves an {kind}"}, 400)
        if store.get(sid) is not None:
            return {"ok": True, "existing": True}  # a retried create
        try:
            runner = make_runner(body.get("setup") or {})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return JSONResponse({"ok": False, "error": f"could not start the agent: {type(e).__name__}: {e}"}, 500)
        try:
            store.add(sid, runner)
        except KeyError:
            _safe_close(runner)
            return {"ok": True, "existing": True}
        except OverflowError as e:
            _safe_close(runner)
            return JSONResponse({"ok": False, "error": str(e)}, 503)
        out: dict[str, Any] = {"ok": True, "version": version}
        m = getattr(runner, "model_info", None)
        m = m() if callable(m) else (m or model)
        if m:
            out["model"] = m
        return json_safe(out)

    @app.post("/sessions/{sid}/step")
    def _step(sid: str, body: dict):
        it = store.get(sid)
        if it is None:
            return JSONResponse({"error": f"no session {sid!r} (expired or never created)"}, 404)
        seq = body.get("seq")
        with it["lock"]:
            if seq is not None and seq == it["seq"] and body.get("event") != "results":
                return it["reply"]
            try:
                reply = json_safe(it["runner"].step(body))
            except HostedError as e:
                return JSONResponse({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                traceback.print_exc()
                return JSONResponse({"error": f"{type(e).__name__}: {e}"}, 500)
            it["seq"], it["reply"] = seq, reply
            if version and "version" not in reply:
                reply["version"] = version
            return reply

    @app.delete("/sessions/{sid}")
    def _end(sid: str):
        return {"ok": store.drop(sid)}

    return app


def serve(kind: str, agent: Any, *, host: str = "0.0.0.0", port: int = 8700, **kw: Any) -> None:
    """Run the host (uvicorn) until interrupted."""
    import uvicorn

    app = make_app(kind, agent, **kw)
    store: SessionStore = app.state.store

    def _reaper() -> None:
        while True:
            time.sleep(max(5.0, min(60.0, store.idle_timeout / 4)))
            store.reap()

    threading.Thread(target=_reaper, daemon=True, name="hosted-reaper").start()
    uvicorn.run(app, host=host, port=port, log_level="warning")
