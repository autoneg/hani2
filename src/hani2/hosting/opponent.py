"""``RemoteOpponent``: a negmas negotiator that forwards every turn to a hosted opponent.

To the mechanism and the session it is an ordinary :class:`negmas.sao.SAONegotiator`. It opens one host
session per negotiation (a random id), sends the negotiation state on each of its turns with a time
limit, and closes the host session at the end. A host that fails or times out does not hang the
negotiation: the turn passes without a counter-offer, the human sees one notice, and after
``max_failures`` failures in a row the opponent walks away (the game still counts: a team cannot drop
bad games by timing out).
"""

from __future__ import annotations

import math
import threading
import traceback
import uuid
import weakref
from typing import Any

from negmas import ResponseType
from negmas.sao import SAONegotiator, SAOResponse, SAOState

from hani2.hosting.client import HostedClient
from hani2.hosting.protocol import (PROTOCOL, Endpoint, HostedError, check_outcome, encode_outcome_space,
                                    encode_state, encode_ufun, issue_names, json_safe, model_label, recorded_spec)

_CLASSES: dict[str, type] = {}


def _finite(x: Any) -> Any:
    try:
        return x if x is not None and math.isfinite(float(x)) else None
    except (TypeError, ValueError):
        return None


class RemoteOpponent(SAONegotiator):
    """An opponent that runs on a team's own host (see :mod:`hani2.hosting`)."""

    #: the hosted spec (``remote:<name>`` or a direct address) of the bound subclass
    spec: str = ""
    #: marks hosted agents (the session attaches itself to them)
    is_remote = True

    def __init__(self, *args: Any, endpoint: Endpoint | None = None, max_failures: int | None = None, **kwargs: Any):
        kwargs.pop("model", None)
        kwargs.pop("provider", None)
        super().__init__(*args, **kwargs)
        from hani2.hosting import registry

        self.endpoint = endpoint or registry.resolve(self.spec, kind="opponent")
        hs = registry.hosted_settings()
        self.max_failures = int(max_failures or hs.get("max_failures") or 3)
        self._client: HostedClient | None = None
        self.session_id = "o-" + uuid.uuid4().hex
        self._seq = 0
        self._opened = False
        self._closed = False
        self._failures = 0
        self.failures_total = 0
        self.last_error = ""
        self.reported_model = ""
        self.declared_version = ""
        self._session_ref: Any = None
        self._notified = False

    # -- the session --------------------------------------------------------
    def attach(self, session: Any) -> None:
        """The session to notify (a toast on the first failure) and to record attribution in."""
        self._session_ref = weakref.ref(session)
        self._record()

    def _session(self) -> Any:
        return self._session_ref() if self._session_ref is not None else None

    def _record(self) -> None:
        s = self._session()
        if s is None:
            return
        try:
            s.ss["hosted_opponent"] = {"name": recorded_spec(self.spec) or self.endpoint.name, "model": self.reported_model,
                                       "version": self.declared_version, "failures": self.failures_total,
                                       "error": self.last_error}
        except Exception:  # noqa: BLE001
            pass

    def _notify(self, message: str) -> None:
        print(f"[hani2] hosted opponent {self.endpoint.name}: {message}")
        s = self._session()
        if s is None or self._notified:
            return
        self._notified = True
        try:
            s.toast(f"The opponent's host is not answering ({message}). The negotiation goes on; "
                    "the opponent passes its turn.", "warning", source="system")
        except Exception:  # noqa: BLE001
            pass

    # -- the host -----------------------------------------------------------
    @property
    def client(self) -> HostedClient:
        if self._client is None:
            self._client = HostedClient(self.endpoint)
        return self._client

    def _note(self, reply: dict) -> None:
        if reply.get("model"):
            self.reported_model = model_label(reply["model"])
        if reply.get("version"):
            self.declared_version = str(reply["version"])[:60]

    def _setup(self) -> dict:
        nmi = self.nmi
        return json_safe({
            "protocol": PROTOCOL, "name": self.name, "ufun": encode_ufun(self.ufun),
            "outcome_space": encode_outcome_space(nmi.outcome_space), "issues": issue_names(nmi.outcome_space),
            "n_steps": _finite(nmi.n_steps), "time_limit": _finite(nmi.time_limit),
            "reserved_value": _finite(getattr(self.ufun, "reserved_value", None)),
        })

    def _open(self) -> None:
        if self._opened:
            return
        reply = self.client.create(self.session_id, "opponent", self._setup())
        if reply.get("ok") is False:
            raise HostedError(f"the hosted agent {self.endpoint.name} refused the negotiation: "
                              f"{str(reply.get('error') or '')[:200]}")
        self._opened = True
        self._note(reply)
        self._record()

    def on_negotiation_start(self, state: SAOState) -> None:
        super().on_negotiation_start(state)
        try:
            self._open()
        except HostedError as e:
            self._fail(str(e))

    def _fail(self, message: str) -> SAOResponse:
        self._failures += 1
        self.failures_total += 1
        self.last_error = message
        self._record()
        self._notify(message)
        if self._failures >= self.max_failures:
            return SAOResponse(ResponseType.END_NEGOTIATION, None, None)
        return SAOResponse(ResponseType.REJECT_OFFER, None, None)

    def __call__(self, state: SAOState, dest: str | None = None) -> SAOResponse:
        try:
            self._open()
            self._seq += 1
            reply = self.client.step(self.session_id, {"seq": self._seq, "state": encode_state(state, self.id)})
            resp = self._response(reply, state)
        except HostedError as e:
            return self._fail(str(e))
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._fail(f"{type(e).__name__}: {e}")
        self._failures = 0
        return resp

    def _response(self, reply: dict, state: SAOState) -> SAOResponse:
        self._note(reply)
        kind = str(reply.get("response") or "").lower()
        text = reply.get("text")
        data = reply.get("data") if isinstance(reply.get("data"), dict) else {}
        data = {k: v for k, v in json_safe(data).items() if k != "text"}
        if text is not None:
            data["text"] = str(text)[:4000]
        data = data or None
        if kind in ("accept", "accept_offer"):
            return SAOResponse(ResponseType.ACCEPT_OFFER, state.current_offer, data)
        if kind in ("end", "end_negotiation"):
            return SAOResponse(ResponseType.END_NEGOTIATION, None, data)
        if kind in ("reject", "reject_offer", "counter", "offer", ""):
            outcome = check_outcome(reply.get("outcome"), self.nmi.outcome_space)
            if kind == "" and outcome is None and data is None:
                raise HostedError(f"the hosted agent {self.endpoint.name} sent no response")
            return SAOResponse(ResponseType.REJECT_OFFER, outcome, data)
        raise HostedError(f"the hosted agent {self.endpoint.name} sent an unknown response {kind!r}")

    def on_negotiation_end(self, state: SAOState) -> None:
        super().on_negotiation_end(state)
        self.close()

    def close(self) -> None:
        """End the host session (in the background: the end of a negotiation never waits for a host)."""
        if self._closed:
            return
        self._closed = True
        client, opened = self._client, self._opened

        def _end() -> None:
            try:
                if opened and client is not None:
                    client.end(self.session_id)
            except HostedError:
                pass
            finally:
                if client is not None:
                    client.close()

        threading.Thread(target=_end, daemon=True, name="hosted-close").start()


def remote_opponent_class(spec: Any) -> type:
    """A :class:`RemoteOpponent` subclass bound to ``spec`` (one per spec; the endpoint is looked up
    when an opponent is made, so a changed registry entry applies to the next negotiation)."""
    from hani2.hosting.protocol import normalise_spec, short_label

    spec = str(normalise_spec(spec)).strip()
    k = _CLASSES.get(spec)
    if k is None:
        safe = "".join(ch if ch.isalnum() else "_" for ch in short_label(spec))[:40]
        k = type(f"Remote_{safe}", (RemoteOpponent,), {"spec": spec, "__module__": __name__})
        _CLASSES[spec] = k
    return k
