"""Records everything that happens in a session into ``.hrec`` files.

One :class:`SessionRecorder` belongs to each :class:`~hani2.session.NegotiationSession`.
Every negotiation gets its own recording, which starts when a scenario is
loaded and ends when the next one is loaded or the session closes (so the
questionnaire after a negotiation is part of it). Files are written to
``<results root>/<user>/recordings/``.

Recording is best-effort: an error here never disturbs a negotiation. Turn it
off with ``HANI2_RECORD=0`` or ``"recording": {"enabled": false}`` in env.json.
"""

from __future__ import annotations

import contextlib
import contextvars
import gzip
import json
import math
import os
import shutil
import threading
import time
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from hani2.recording.format import FORMAT, KEYFRAME_EVERY, PARTIAL_SUFFIX, SUFFIX, VERSION, diff, dumps_line

#: the session whose work the current thread is doing (set by the session's executors)
CURRENT_SID: contextvars.ContextVar[str | None] = contextvars.ContextVar("hani2_rec_sid", default=None)
#: who the current language-model call is for: support | opponent | autopilot | service | judge
LLM_ROLE: contextvars.ContextVar[str] = contextvars.ContextVar("hani2_rec_role", default="service")
#: who is acting on the participant's seat in this thread (``human`` while a browser message is handled)
_ACTOR = threading.local()

_REGISTRY: dict[str, "SessionRecorder"] = {}
_REG_LOCK = threading.Lock()
_PRE_BUFFER = 4000
_MAX_TEXT = 20000


def enabled() -> bool:
    if os.environ.get("HANI2_RECORD", "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    try:
        from hani2.config import get_env

        return bool(get_env("recording.enabled", True))
    except Exception:  # pragma: no cover
        return True


def get(sid: str | None) -> "SessionRecorder | None":
    return _REGISTRY.get(sid) if sid else None


def current() -> "SessionRecorder | None":
    return get(CURRENT_SID.get())


@contextlib.contextmanager
def bind(sid: str | None, role: str | None = None):
    """Run a block on behalf of session ``sid`` (and LLM ``role``)."""
    t1 = CURRENT_SID.set(sid)
    t2 = LLM_ROLE.set(role) if role else None
    try:
        yield
    finally:
        CURRENT_SID.reset(t1)
        if t2 is not None:
            LLM_ROLE.reset(t2)


@contextlib.contextmanager
def llm_role(role: str):
    tok = LLM_ROLE.set(role)
    try:
        yield
    finally:
        LLM_ROLE.reset(tok)


@contextlib.contextmanager
def acting(actor: str):
    prev = getattr(_ACTOR, "name", None)
    _ACTOR.name = actor
    try:
        yield
    finally:
        _ACTOR.name = prev


def current_actor() -> str | None:
    return getattr(_ACTOR, "name", None)


def _clean(v: Any) -> Any:
    """JSON-safe copy (NaN/inf → None, tuples → lists, objects → str)."""
    from hani2.tools.ui import jsonable

    return jsonable(v)


def _trunc(s: Any, n: int = _MAX_TEXT) -> Any:
    if isinstance(s, str) and len(s) > n:
        return s[:n] + f"… [{len(s) - n} more characters]"
    return s


class SessionRecorder:
    def __init__(self, session: Any):
        self.session = session
        self.sid = session.sid
        self.lock = threading.RLock()
        self.seq = 0
        self.fh = None
        self.path: Path | None = None
        self.t0 = time.time()
        self.rec_id: str | None = None
        self.n_events = 0
        self.n_states = 0
        self.last_state: dict | None = None
        self.last_tools: dict[str, Any] = {}
        self.pre: list[dict] = []  # events before the first scenario is loaded (wall-clock t)
        self.last_viewport: list | None = None
        self.llm_prefix: dict[str, list] = {}
        self.meta: dict[str, Any] = {}
        with _REG_LOCK:
            _REGISTRY[self.sid] = self
        try:
            from hani2 import llm_logging

            llm_logging.install(force=True)
        except Exception:  # pragma: no cover
            pass

    # ------------------------------------------------------------------ #
    # File lifecycle                                                      #
    # ------------------------------------------------------------------ #
    def _dir(self) -> Path:
        return Path(self.session.ss["user_path"]) / "recordings"

    def begin(self) -> None:
        """Start a new recording (a scenario was loaded)."""
        try:
            self.finalize()
            with self.lock:
                now = time.time()
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(self.session._scenario_name()))[:40]
                self.rec_id = f"{stamp}-{safe}-{uuid.uuid4().hex[:6]}"
                d = self._dir()
                d.mkdir(parents=True, exist_ok=True)
                self.path = d / f"{self.rec_id}{PARTIAL_SUFFIX}"
                self.fh = self.path.open("w", encoding="utf-8")
                self.t0 = now
                self.n_events = 0
                self.n_states = 0
                self.llm_prefix = {}
                self.meta = {"started": datetime.now().isoformat()}
                s = self.session
                from hani2 import __version__

                header = dict(
                    k="header", format=FORMAT, version=VERSION, id=self.rec_id, t0=now,
                    created=datetime.now().astimezone().isoformat(),
                    session=dict(sid=s.sid, user=s.user, display_name=s.display_name, mode=s.mode,
                                 is_admin=s.is_admin, user_agent=s.ss.get("user_agent", ""),
                                 query={k: str(v) for k, v in (s.query or {}).items()}),
                    app=dict(name="hani2", version=__version__),
                )
                try:
                    from hani2 import projects
                    from hani2.config import experiment_name

                    with projects.use_study(getattr(s, "study_ref", None)):
                        header["experiment"] = experiment_name()
                    header.update(projects.stamp(getattr(s, "study_ref", None)))
                except Exception:
                    pass
                self._line(header)
                # what was already on screen when this recording started
                for e in self.pre:
                    e = dict(e)
                    e["t"] = 0.0
                    self._line(e)
                self.pre = []
                if self.last_viewport is not None:
                    self._line({"t": 0.0, "k": "tel", "sent": None, "ev": [[None, *self.last_viewport]], "carry": True})
                if self.last_state is not None:
                    self._line({"t": 0.0, "k": "out", "m": "state", "seq": self.seq, "full": self.last_state, "carry": True})
                for tid, view in self.last_tools.items():
                    self._line({"t": 0.0, "k": "out", "m": "tool", "seq": self.seq, "id": tid, "full": view, "carry": True})
        except Exception:
            traceback.print_exc()

    def _line(self, rec: dict) -> None:
        if self.fh is None:
            return
        try:
            self.fh.write(dumps_line(rec) + "\n")
        except ValueError:
            self.fh.write(dumps_line(_clean(rec)) + "\n")
        self.fh.flush()
        self.n_events += 1

    def _write(self, _kind: str, /, **fields: Any) -> None:
        fields.pop("t", None)
        fields.pop("k", None)
        try:
            with self.lock:
                if self.fh is None:
                    if len(self.pre) < _PRE_BUFFER:
                        self.pre.append({"k": _kind, **fields})
                    return
                self._line({"t": round(time.time() - self.t0, 4), "k": _kind, **fields})
        except Exception:
            traceback.print_exc()

    def finalize(self) -> Path | None:
        """Close the current recording: compress it and write its summary."""
        with self.lock:
            fh, path = self.fh, self.path
            if fh is None or path is None:
                return None
            try:
                self._line({"t": round(time.time() - self.t0, 4), "k": "end", "n_events": self.n_events})
            except Exception:
                pass
            self.fh = None
            meta = dict(self.meta)
            rec_id = self.rec_id
            t0 = self.t0
        try:
            fh.close()
            final = path.with_name(f"{rec_id}{SUFFIX}")
            with path.open("rb") as src, gzip.open(final, "wb", compresslevel=6) as dst:
                shutil.copyfileobj(src, dst)
            path.unlink(missing_ok=True)
            self._write_index(final, rec_id, t0, meta)
            return final
        except Exception:
            traceback.print_exc()
            return path

    def _write_index(self, final: Path, rec_id: str | None, t0: float, meta: dict) -> None:
        s = self.session
        summary = meta.get("summary") or {}
        info = dict(
            id=rec_id, file=final.name, user=s.user, sid=s.sid, mode=s.mode,
            started=meta.get("started"), duration=round(time.time() - t0, 3),
            scenario=meta.get("scenario"), opponent=meta.get("opponent"), mechanism_id=meta.get("mechanism_id"),
            status=summary.get("status"), ended_by=summary.get("ended_by"),
            human_utility=summary.get("human_utility"), agent_utility=summary.get("agent_utility"),
            support_agent=meta.get("support_agent"), questionnaire=bool(meta.get("questionnaire")),
            assistant=meta.get("assistant"), assistant_group=meta.get("assistant_group"),
            opponent_group=meta.get("opponent_group"),
            size=final.stat().st_size,
        )
        try:
            from hani2 import projects
            from hani2.config import experiment_name

            with projects.use_study(getattr(s, "study_ref", None)):
                info["experiment"] = experiment_name()
            info.update(projects.stamp(getattr(s, "study_ref", None)))
        except Exception:
            pass
        final.with_name(f"{rec_id}.json").write_text(json.dumps(_clean(info), indent=1), encoding="utf-8")

    def close(self) -> None:
        self.finalize()
        with _REG_LOCK:
            if _REGISTRY.get(self.sid) is self:
                _REGISTRY.pop(self.sid, None)

    # ------------------------------------------------------------------ #
    # What the browser saw and did                                       #
    # ------------------------------------------------------------------ #
    def outbound(self, msg: dict) -> int:
        """A message is about to be sent to the browser; returns its sequence number."""
        try:
            with self.lock:
                self.seq += 1
                seq = self.seq
                m = msg.get("type")
                if m == "state":
                    st = _clean(msg.get("state") or {})
                    prev = self.last_state
                    self.last_state = st
                    if prev is None or self.n_states % KEYFRAME_EVERY == 0:
                        self._write("out", m="state", seq=seq, full=st)
                    else:
                        self._write("out", m="state", seq=seq, delta=diff(prev, st))
                    self.n_states += 1
                elif m == "tool":
                    tid = str(msg.get("id"))
                    view = _clean({k: v for k, v in msg.items() if k != "type"})
                    prev = self.last_tools.get(tid)
                    self.last_tools[tid] = view
                    if prev is None or not isinstance(prev, dict):
                        self._write("out", m="tool", seq=seq, id=tid, full=view)
                    else:
                        d = diff(prev, view)
                        if d:
                            self._write("out", m="tool", seq=seq, id=tid, delta=d)
                else:
                    self._write("out", m=m, seq=seq, msg=_clean({k: v for k, v in msg.items() if k != "type"}))
                return seq
        except Exception:
            traceback.print_exc()
            return -1

    def inbound(self, msg: dict) -> None:
        t = msg.get("type")
        if t == "telemetry":
            self.telemetry(msg)
            return
        if t == "ping":
            return
        self._write("in", msg=_clean(msg))

    def telemetry(self, msg: dict) -> None:
        events = msg.get("events") or []
        if not isinstance(events, list):
            return
        for e in events:
            if isinstance(e, list) and len(e) > 2 and e[1] == "vp":
                self.last_viewport = list(e[1:])
        self._write("tel", sent=msg.get("sent"), ev=_clean(events[:5000]))

    # ------------------------------------------------------------------ #
    # What happened                                                       #
    # ------------------------------------------------------------------ #
    def turn(self) -> None:
        """The human's turn began (the opponent has answered)."""
        self._write("turn")

    def event(self, event_type: str, **fields: Any) -> None:
        self._write("ev", type=event_type, **{k: _clean(v) for k, v in fields.items() if v is not None})

    def scenario(self) -> None:
        try:
            rec = scenario_record(self.session)
            info = getattr(self.session, "information", None)
            if info is not None and info.split:  # who knew what, with the past negotiations themselves
                rec["information"] = {**info.record(), "past": info.past, "market": info.market}
            self.meta["scenario"] = rec.get("name")
            self._write("scenario", **rec)
        except Exception:
            traceback.print_exc()

    def start(self) -> None:
        s = self.session
        m = s.mechanism
        nmi = getattr(m, "nmi", None)
        sa = s.support_agent
        attribution = dict(s.ss.get("assistant_attribution") or {})
        attribution["opponent_group"] = s.ss.get("opponent_group") or ""
        self.meta.update(mechanism_id=getattr(m, "id", None), opponent=s.ss.get("last_partner_type"),
                         support_agent=bool(sa is not None and getattr(sa, "user_enabled", True)),
                         **{k: attribution.get(k, "") for k in ("assistant", "assistant_group", "opponent_group")})
        self._write(
            "start", mechanism_id=getattr(m, "id", None), opponent=s.ss.get("last_partner_type"),
            assignment=_clean(attribution),
            human_id=s.ss.get("human_id"), human_index=s.human_index, round=s.round_number,
            practice=bool(s.ss.get("is_practice_round")), deadline=s.deadline,
            n_steps=getattr(nmi, "n_steps", None), time_limit=getattr(nmi, "time_limit", None),
            support_agent=_support_info(s), autopilot=bool(s.autopilot_active),
            condition=_condition(s),
            models=_models_info(s),
            settings=_clean(dict(s.admin_prefs)), prefs=_clean(dict(s.prefs)),
        )

    def action(self, response: Any, actor: str) -> None:
        try:
            from negmas import ResponseType

            s = self.session
            rt = response.response
            offer = response.outcome
            data = response.data if isinstance(getattr(response, "data", None), dict) else None
            text = (data or {}).get("text") if data else None
            if rt == ResponseType.ACCEPT_OFFER:
                kind = "accept"
            elif rt == ResponseType.END_NEGOTIATION:
                kind = "end"
            elif offer is None:
                kind = "text" if text else "wait"
            else:
                kind = "offer"
            m = s.mechanism
            self._write("act", actor=actor, type=kind, offer=_clean(list(offer)) if offer is not None else None,
                        values=s.outcome_to_dict(offer) if offer is not None else None, text=_trunc(text),
                        utility=s.utility(offer) if offer is not None else None,
                        step=getattr(getattr(m, "state", None), "step", None))
        except Exception:
            traceback.print_exc()

    def draft(self, values: dict, by: str, utility: float | None, text: str | None = None, via: str = "editor") -> None:
        self._write("draft", by=by, via=via, values=_clean(dict(values)), utility=_clean(utility),
                    **({"text": _trunc(text)} if text is not None else {}))

    def chat(self, msg: dict) -> None:
        self._write("chat", **{k: _trunc(_clean(v)) for k, v in msg.items()})

    def function_call(self, name: str, args: dict, result: Any, latency: float) -> None:
        r = _clean(result)
        txt = json.dumps(r, default=str)
        if len(txt) > 4000:
            r = {"ok": (result or {}).get("ok") if isinstance(result, dict) else None, "truncated": txt[:4000]}
        self._write("fn", name=name, args=_clean(args), result=r, latency=round(latency, 4))

    def llm(self, *, role: str, model: str | None, messages: list | None, response: Any, latency: float,
            error: str | None = None, usage: dict | None = None, cost: float | None = None,
            tools: bool = False) -> None:
        msgs = _clean(messages or [])
        with self.lock:
            prev = self.llm_prefix.get(role) or []
            n = len(prev)
            prefix = n if n and len(msgs) >= n and msgs[:n] == prev else 0
            self.llm_prefix[role] = msgs
        new = [{**m, "content": _trunc(m.get("content"))} if isinstance(m, dict) else m for m in msgs[prefix:]]
        self._write("llm", role=role, model=model, latency=round(latency, 4), prefix=prefix, messages=new,
                    n_messages=len(msgs), response=_clean(response), error=error, usage=_clean(usage or {}),
                    cost=_clean(cost), tools=tools)

    def finish(self, row: dict | None, summary: dict) -> None:
        s = self.session
        m = s.mechanism
        rows = []
        try:
            for r in m.full_trace:
                t, rel, step, neg, offer, responses, state, text, data = (list(r) + [None] * 9)[:9]
                rows.append(dict(t=_clean(t), rel=_clean(rel), step=_clean(step), negotiator=str(neg),
                                 offer=_clean(list(offer)) if offer is not None else None,
                                 values=s.outcome_to_dict(offer) if offer is not None else None,
                                 responses=_clean(responses), state=str(state) if state is not None else None,
                                 text=_trunc(text if isinstance(text, str) else None),
                                 data=_clean(data) if isinstance(data, dict) else None))
        except Exception:
            traceback.print_exc()
        self._write("trace", rows=rows)
        self.meta["summary"] = _clean(summary)
        state = getattr(m, "state", None)
        self._write("result", summary=_clean(summary), row=_clean(row or {}),
                    agreement=_clean(list(state.agreement)) if state is not None and state.agreement is not None else None)

    def questionnaire(self, spec: dict | None, answers: dict, shown_at: str | None) -> None:
        self.meta["questionnaire"] = True
        self._write("questionnaire", spec=_clean(spec or {}), answers=_clean(answers), shown_at=shown_at)

    def mark(self, _kind: str, /, **fields: Any) -> None:
        self._write(_kind, **{k: _clean(v) for k, v in fields.items()})


def _models_info(s: Any) -> dict:
    """The model chain entries the session uses (no secrets)."""
    try:
        from hani2.model_chain import models_of

        m = models_of(s)
        return m.records() if m is not None else {}
    except Exception:  # noqa: BLE001
        return {}


def _condition(s: Any) -> dict:
    try:
        return _clean(s.ablation_condition())
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        return {}


def _support_info(s: Any) -> dict | None:
    sa = s.support_agent
    if sa is None:
        return None
    try:
        from hani2.model_chain import models_of

        m = models_of(s)
        res = m.peek("assistant") if m is not None else None
        st = sa.settings or {}
        provider, model = (res.provider, res.model) if res is not None and res.ok else (st.get("provider"), st.get("model"))
        return dict(cls=f"{type(sa).__module__}.{type(sa).__qualname__}", name=getattr(sa, "name", None),
                    enabled=bool(getattr(sa, "user_enabled", True)), provider=provider, model=model,
                    connection=res.connection.name if res is not None and res.connection else "")
    except Exception:
        return {"cls": type(sa).__name__}


def scenario_record(s: Any, max_outcomes: int = 100_000) -> dict:
    """The scenario as a self-contained record: issues, every outcome with each
    party's utility, reserved values and the human's seat."""
    sc = s.scenario
    os_ = sc.outcome_space
    try:
        n = int(os_.cardinality)
    except Exception:
        n = -1
    exhaustive = 0 < n <= max_outcomes
    try:
        outcomes = list(os_.enumerate_or_sample(max_cardinality=max_outcomes))
    except Exception:
        outcomes = []
    utils = []
    for u in sc.ufuns:
        col = []
        for o in outcomes:
            try:
                v = float(u(o))
                col.append(round(v, 8) if math.isfinite(v) else None)
            except Exception:
                col.append(None)
        utils.append(col)
    reserved = []
    for u in sc.ufuns:
        try:
            r = float(u.reserved_value)
            reserved.append(r if math.isfinite(r) else None)
        except Exception:
            reserved.append(None)
    ufun_json = []
    try:
        from negmas.serialization import serialize

        ufun_json = [_clean(serialize(u)) for u in sc.ufuns]
    except Exception:
        pass
    return dict(
        name=s._scenario_name(), info=_clean(s.ss.get("scenario_info") or {}), title=(sc.info or {}).get("title"),
        human_index=s.human_index, human_id=s.ss.get("human_id"), parties=[str(u.name) for u in sc.ufuns],
        issues=_clean(s.issues_spec()), issue_names=[i.name for i in s.issues],
        exhaustive=exhaustive, n_outcomes=n, outcomes=_clean([list(o) for o in outcomes]), utilities=utils,
        reserved=reserved, ufuns=ufun_json, evaluation=_clean(s.ss.get("scenario_evaluation")),
    )


# --------------------------------------------------------------------------- #
# Hooks used by the rest of the app                                            #
# --------------------------------------------------------------------------- #
def on_log_event(session_id: str | None, event_type: str, fields: dict) -> None:
    r = get(session_id)
    if r is not None:
        r.event(event_type, **fields)


def record_llm_call(kwargs: dict, resp: Any, latency: float, error: str | None = None) -> None:
    """Called for every language-model call (see :mod:`hani2.llm_logging`)."""
    r = current()
    if r is None:
        return
    try:
        content, usage, cost, tool_calls = None, {}, None, None
        if resp is not None:
            try:
                msg = resp.choices[0].message
                content = msg.content or ""
                tcs = getattr(msg, "tool_calls", None)
                if tcs:
                    tool_calls = [{"name": tc.function.name, "arguments": tc.function.arguments} for tc in tcs]
            except Exception:
                content = str(resp)
            u = getattr(resp, "usage", None)
            if u is not None:
                for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    v = getattr(u, k, None) if not isinstance(u, dict) else u.get(k)
                    if v is not None:
                        usage[k] = int(v)
            hidden = getattr(resp, "_hidden_params", None) or {}
            if isinstance(hidden, dict) and isinstance(hidden.get("response_cost"), (int, float)):
                cost = float(hidden["response_cost"])  # e.g. what a harness reported
            else:
                try:
                    import litellm

                    cost = float(litellm.completion_cost(completion_response=resp))
                except Exception:
                    cost = None
        response = {"content": _trunc(content)}
        if tool_calls:
            response["tool_calls"] = tool_calls
        r.llm(role=LLM_ROLE.get(), model=kwargs.get("model"), messages=kwargs.get("messages"), response=response,
              latency=latency, error=error, usage=usage, cost=cost, tools=bool(kwargs.get("tools")))
    except Exception:
        traceback.print_exc()
