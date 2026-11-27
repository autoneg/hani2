"""The Scenario Stats tool: every negmas statistic of the scenario being negotiated (admins only by default)."""

from __future__ import annotations

import threading
from typing import Any

from hani2 import scenario_stats
from hani2.tools import ui
from hani2.tools.base import Tool


def _num(x: Any, digits: int = 3) -> Any:
    return round(x, digits) if isinstance(x, float) else x


def _outcome_text(o: dict | None) -> str:
    return ", ".join(f"{k}: {v}" for k, v in (o or {}).items()) if o else "—"


class ScenarioStatsTool(Tool):
    """Every negmas statistic of the scenario being negotiated (see :mod:`hani2.scenario_stats`)."""

    name = "Scenario Stats"
    description = "Every negmas statistic of this scenario: opposition, utility ranges, the Pareto frontier and the bargaining solutions."
    groups = ("information",)
    icon = "sigma"
    pane = "lower"
    timing = "load"
    admin_only = True
    order = 40
    help = """
    Every statistic negmas computes for this scenario: its size, how opposed the roles are
    (opposition), each role's utility range, the share of outcomes better than no deal for
    everybody (rational fraction), the bargaining solutions (Nash, Kalai, modified Kalai, KS,
    modified KS, maximum welfare, maximum relative welfare) and the Pareto frontier.

    **Computed in the background.** The statistics are computed once per scenario, away from the
    negotiation, and kept next to the scenario; the tool shows them as soon as they are ready. A
    scenario too large or too slow to compute (the limits are the ``scenario_stats`` settings) is
    skipped, and the tool says why.

    Only administrators get this tool unless it is opened to everybody (Tool settings).
    """
    agent_hint = "The scenario's negmas statistics (Pareto frontier, Nash and Kalai points, opposition)."

    def __init__(self, *a: Any, **kw: Any) -> None:
        super().__init__(*a, **kw)
        self._result: dict | None = None
        self._for: int | None = None  # id() of the scenario the result is for
        self._version = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    def scenario_loaded(self, session_state: dict[str, Any], scenario: Any) -> None:
        self._ask()

    def _ask(self, force: bool = False) -> None:
        s = self.scenario
        if s is None:
            return
        with self._lock:
            self._version += 1
            version = self._version
            self._for = id(s)
            self._result = {"status": "pending"}

        def done(result: dict) -> None:
            with self._lock:
                if self._version != version:
                    return  # a newer scenario (or a recompute) took over
                self._result = result
            self.refresh()

        r = scenario_stats.request(s, self.session_state.get("scenario_dir"), force=force, on_done=done)
        with self._lock:
            if self._version == version and r.get("status") != "pending":
                self._result = r

    def on_action(self, action: str, payload: dict[str, Any]) -> None:
        if action == "recompute":
            self._ask(force=True)
            self.refresh()

    # ------------------------------------------------------------------ #
    def render(self) -> list[ui.Component]:
        s = self.scenario
        if s is None:
            return [ui.text_block("No scenario yet.", muted=True)]
        if self._for != id(s):
            self._ask()
        with self._lock:
            result = dict(self._result or {"status": "pending"})
        human = str(getattr(self.human_ufun, "name", "") or "") or None
        v = scenario_stats.view(result, human)
        status = v.get("status")
        again = ui.button("Compute again", "recompute", icon="refresh-cw", tooltip="Compute the statistics again")
        if status == "pending":
            return [ui.alert("Computing the scenario statistics in the background…", "info")]
        if status != "ok":
            kind = "warning" if status in ("timeout", "too_large", "disabled") else "error"
            title = {"timeout": "Too slow to compute", "too_large": "Too large to compute",
                     "disabled": "Switched off", "failed": "Could not compute"}.get(str(status), "Not available")
            comps: list[ui.Component] = [ui.alert(str(v.get("message") or ""), kind, title=title)]
            if status != "disabled":
                comps.append(again)
            return comps
        roles = [r["name"] for r in v["roles"]]

        def label(role: str) -> str:
            return f"{role} (you)" if any(r["name"] == role and r["human"] for r in v["roles"]) else role

        comps = [ui.stats(
            ui.stat("Outcomes", f"{v['n_outcomes']:,}" if isinstance(v.get("n_outcomes"), int) else "—"),
            ui.stat("Issues", v.get("n_issues")),
            ui.stat("Opposition", _num(v.get("opposition")), hint="0: no conflict, 1: fully opposed"),
            ui.stat("Rational fraction", f"{v['rational_fraction']:.0%}" if isinstance(v.get("rational_fraction"), float) else "—",
                    hint="outcomes better than no deal for everybody"),
            ui.stat("Pareto frontier", v.get("pareto_size"), hint="outcomes"),
        )]
        reserved = {r["name"]: r.get("reserved_value") for r in v["roles"]}
        comps.append(ui.card(
            ui.table([{"Role": label(r["role"]), "Lowest utility": _num(r["min"]), "Highest utility": _num(r["max"]),
                       "No deal": _num(reserved.get(r["role"]))} for r in v.get("utility_ranges") or []],
                     sortable=False),
            title="Utility ranges", collapsible=True))
        rows = []
        for sol in v.get("solutions") or []:
            for k, p in enumerate(sol["points"]):
                rows.append({"Solution": sol["label"] + (f" #{k + 1}" if len(sol["points"]) > 1 else ""),
                             **{label(r): _num(p["utilities"].get(r)) for r in roles},
                             "Welfare": _num(p.get("welfare")), "Outcome": _outcome_text(p.get("outcome"))})
        comps.append(ui.card(ui.table(rows, sortable=False) if rows else ui.text_block("None.", muted=True),
                             title="Bargaining solutions", collapsible=True))
        pareto = [{**{label(r): _num(p["utilities"].get(r)) for r in roles}, "Welfare": _num(p.get("welfare")),
                   "Outcome": _outcome_text(p.get("outcome"))} for p in v.get("pareto") or []]
        notes = []
        if v.get("pareto_truncated"):
            notes.append(f"The first {len(pareto)} of {v.get('pareto_size')} points.")
        if v.get("pareto_cached") is False:
            notes.append(f"Not kept with the scenario: it has more than {v.get('pareto_max_outcomes'):,} outcomes.")
        comps.append(ui.card(
            ui.table(pareto, page_size=10, searchable=True) if pareto else ui.text_block("Empty.", muted=True),
            ui.text_block(" ".join(notes), muted=True) if notes else None,
            title=f"Pareto frontier ({v.get('pareto_size')})", collapsible=True, collapsed=True))
        foot = [f"Computed {v['computed_at']}" if v.get("computed_at") else None,
                f"in {v['seconds']:.2f} s" if isinstance(v.get("seconds"), (int, float)) else None,
                {"disk": "cached with the scenario", "memory": "cached in memory"}.get(str(v.get("cache")))]
        comps.append(ui.row(ui.text_block(", ".join(x for x in foot if x) + ".", muted=True), again, align="center"))
        return comps
