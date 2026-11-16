"""Outcome display helpers (how an outcome is rendered as text / a table row).

Scenarios may ship a ``display.py`` defining a subclass of
:class:`DefaultOutcomeDisplay` to render offers in domain language
(e.g. "5 items at 120$").
"""

from __future__ import annotations

from typing import Any, Protocol

from negmas import Outcome, Scenario

__all__ = ["OutcomeDisplay", "DefaultOutcomeDisplay"]


class OutcomeDisplay(Protocol):
    def str(self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool) -> str: ...

    def table(
        self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool
    ) -> list[dict[str, Any]]: ...


class DefaultOutcomeDisplay:
    def str(self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool) -> str:
        if outcome is None:
            return "❓"
        names = [_.name for _ in scenario.outcome_space.issues]  # type: ignore
        return ", ".join(f"{k}: {v}" for k, v in zip(names, outcome))

    def table(
        self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool
    ) -> list[dict[str, Any]]:
        names = [_.name for _ in scenario.outcome_space.issues]  # type: ignore
        return [dict(zip(names, outcome))] if outcome else []
