"""The Assistant the documentation screenshots run with (no language model needed).

It is the level 10 tutorial agent (it adds the Deal Compass and operates the Utility-based
Selector) plus a rough opponent model: when the negotiation starts it assumes the opponent wants
the opposite of the participant on every issue, and shares that guess with
``set_opponent_estimate``. That unlocks the Negotiation Plot for participants (marked as an
estimate) and the opponent columns of the Utility-based Selector.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples" / "support_agent_tutorial"))

from level10_toolsmith import ToolsmithAgent


def opposite_estimate(session) -> dict:
    """An estimate of the opponent: every option valued the other way round from the human, and the
    issues' importance in reverse order (what matters least to the human matters most to the
    opponent), so that some deals are good for both."""
    hu = session.human_ufun
    values, weights = {}, {}
    funs = getattr(hu, "values", None) or []
    ws = getattr(hu, "weights", None) or []
    for i, issue in enumerate(session.scenario.outcome_space.issues):
        fun = funs[i] if i < len(funs) else None
        weights[issue.name] = float(ws[i]) if i < len(ws) else 1.0
        try:
            options = list(issue.all)
        except Exception:  # noqa: BLE001 - a continuous issue
            values[issue.name] = "decreasing"
            continue
        values[issue.name] = {str(o): 1.0 - float(fun(o)) if fun is not None else 0.5 for o in options}
    names = list(weights)
    ranked = sorted(names, key=lambda n: weights[n])
    by_rank = sorted(weights.values(), reverse=True)
    weights = {n: by_rank[i] for i, n in enumerate(ranked)}
    return {"weights": weights, "values": values, "reserved_value": 0.25}


class DocsAssistant(ToolsmithAgent):
    name = "Assistant"

    def on_event(self, event_name: str, nmi=None) -> None:
        if event_name == "negotiation_started" and self.user_enabled:
            self.set_opponent_estimate(opposite_estimate(self.session))
        super().on_event(event_name, nmi)
