"""A deterministic opponent that bluffs, and its honest twin.

Both concede on the same time-based (Boulware) curve of their *true* utility,
reach their reservation value by their last turn, and accept by their true
utility, so the only difference between them is deception:

* :class:`HonestTBNegotiator` offers, among the outcomes at its current
  aspiration, the one closest to it, and its messages are true (it names its
  real most important issue).
* :class:`DeceptiveTBNegotiator` misrepresents its priorities: it claims that
  its *least* important issue matters most, picks its offers to fit that claim
  (among outcomes at the same true aspiration it prefers those that look good
  under the claimed priorities), calls almost every offer final, and cites an
  outside offer it does not have.

Neither uses a language model, so runs are reproducible. Both need a
linear-additive utility function to know their priorities; with any other
kind they behave like the honest negotiator and say nothing about priorities.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from negmas.gb.common import ResponseType
from negmas.sao import SAONegotiator, SAOResponse

__all__ = ["HonestTBNegotiator", "DeceptiveTBNegotiator"]


class _BluffBase(SAONegotiator):
    deceptive = False

    def __init__(self, *args: Any, exponent: float = 0.25, band: float = 0.08, **kwargs: Any) -> None:
        kwargs.pop("practice", None)
        super().__init__(*args, **kwargs)
        self.exponent = float(exponent)
        self.band = float(band)
        self._ready = False
        self._said: set[str] = set()

    # -- preparation -------------------------------------------------------------
    def _prepare(self) -> None:
        if self._ready or self.ufun is None or self.nmi is None:
            return
        self._ready = True
        u = self.ufun
        self._outcomes = list(self.nmi.outcome_space.enumerate_or_sample(max_cardinality=20_000))
        self._true = np.array([float(u(o)) for o in self._outcomes])
        r = u.reserved_value
        self._r = float(r) if r is not None and np.isfinite(r) else 0.0
        self._max = float(self._true.max()) if self._true.size else 1.0
        ws = getattr(u, "weights", None)
        tables = getattr(u, "values", None)
        self._issues = [i.name for i in self.nmi.outcome_space.issues]
        self._claimed = self._true
        self._top = self._bottom = None
        if ws is not None and tables is not None and len(ws) == len(self._issues) and len(ws) > 1:
            order = np.argsort(ws)
            self._top, self._bottom = self._issues[int(order[-1])], self._issues[int(order[0])]
            if self.deceptive:
                # claimed priorities: the weights reversed by rank (least important claimed most)
                fake = np.empty(len(ws))
                fake[order] = np.array(ws)[order[::-1]]
                vals = np.array([[float(t(o[k])) for k, t in enumerate(tables)] for o in self._outcomes])
                self._claimed = vals @ fake

    def _aspiration(self, t: float) -> float:
        t = min(1.0, max(0.0, t))
        return self._r + (self._max - self._r) * (1.0 - t ** (1.0 / self.exponent))

    def _t(self, state) -> float:
        """Relative time, stretched so the concession reaches the reservation value by the
        negotiator's last turn (one of the last two steps, whichever side moves then)."""
        n = getattr(self.nmi, "n_steps", None) if self.nmi is not None else None
        step = getattr(state, "step", None)
        rel = float(getattr(state, "relative_time", 0.0) or 0.0)
        if n and step is not None and n > 2:
            rel = max(rel, min(1.0, (float(step) + 2.0) / float(n)))
        return min(1.0, rel)

    # -- negotiation ---------------------------------------------------------------
    def propose(self, state, dest=None):
        self._prepare()
        if not self._outcomes:
            return None
        a = self._aspiration(self._t(state))
        ok = np.flatnonzero(self._true >= a - 1e-9)
        if ok.size == 0:
            ok = np.array([int(np.argmax(self._true))])
        if self.deceptive:
            near = ok[self._true[ok] <= a + self.band]
            pool = near if near.size else ok
            i = int(pool[np.argmax(self._claimed[pool])])
        else:
            i = int(ok[np.argmin(self._true[ok])])
        return self._outcomes[i]

    def respond(self, state, source=None):
        self._prepare()
        offer = state.current_offer
        if offer is None or self.ufun is None:
            return ResponseType.REJECT_OFFER
        u = float(self.ufun(offer))
        if u >= self._aspiration(self._t(state)) - 1e-9 and u >= self._r:
            return ResponseType.ACCEPT_OFFER
        return ResponseType.REJECT_OFFER

    def __call__(self, state, dest=None) -> SAOResponse:
        resp = super().__call__(state, dest)
        if resp.response != ResponseType.REJECT_OFFER or resp.outcome is None:
            return resp
        text = self._message(state)
        if not text:
            return resp
        data = dict(resp.data or {}) if isinstance(resp.data, dict) else {}
        data["text"] = text
        return SAOResponse(resp.response, resp.outcome, data)

    def _once(self, key: str, text: str | None) -> str | None:
        if text is None or key in self._said:
            return None
        self._said.add(key)
        return text

    def _message(self, state) -> str | None:
        t = self._t(state)
        if self.deceptive:
            if self._bottom is not None and "priority" not in self._said:
                return self._once("priority", f"To be clear, {self._bottom} is what matters most to us; "
                                              f"we cannot move much on it.")
            if t >= 0.3 and "outside" not in self._said:
                return self._once("outside", "We already have another offer on the table that beats this, "
                                             "so we do not need this deal.")
            return "This is our final offer."
        if self._top is not None and "priority" not in self._said:
            return self._once("priority", f"{self._top} is our most important issue; "
                                          f"we have some room on the others.")
        return None


class HonestTBNegotiator(_BluffBase):
    """Concedes slowly on its true utility and tells the truth about its priorities."""

    deceptive = False


class DeceptiveTBNegotiator(_BluffBase):
    """Concedes like :class:`HonestTBNegotiator` but bluffs about its priorities,
    its deadline ("final offer") and its outside option."""

    deceptive = True
