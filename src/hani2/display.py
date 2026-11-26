"""How a scenario shows offers.

Offers appear in four places, and a scenario can shape each of them:

=============  ======================================  ==============================
Method         Where                                    Default
=============  ======================================  ==============================
``text``       one line: toasts, the result, the        ``Issue: value, Issue: value``
               Assistant, logs, tools, the history
               when the participant prefers text
``history``    the offer in a history bubble            issue chips (or ``text``)
``on_table``   the "Offer on the table" card             ``text``
``controls``   the counter-offer editor                 one field per issue
=============  ======================================  ==============================

Every method except ``text`` returns a list of :mod:`hani2.tools.ui`
components, or ``None`` to keep the default. A scenario changes only what it
needs:

* **No code** — keys in the scenario's ``_info.yaml``: ``offer_template``
  (the text line, e.g. ``"{Quantity} items at {Price}"``), ``issue_format``
  (a format string per issue, e.g. ``"${:,}"``), ``value_labels`` (shown names
  of issue values) and ``issue_widget`` (the control of an issue: ``buttons``,
  ``select``, ``slider`` or ``number``).
* **Python** — a ``display.py`` next to the scenario (or a ``display`` passed
  to :func:`hani2.scenarios.registry.register`) with a subclass of
  :class:`OfferDisplay` that overrides any of the methods.

Custom controls are a view of the same draft (``{issue: value}``) the default
editor edits. An input whose ``name`` is an issue name sets that issue; any
other input calls :meth:`OfferDisplay.on_input`, and a button calls
:meth:`OfferDisplay.on_action`. Both return the issue values to change.
:func:`hani2.tools.ui.issue` places the default control of one issue inside a
custom layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from negmas import Outcome, Scenario

__all__ = [
    "DefaultOutcomeDisplay",
    "OfferContext",
    "OfferDisplay",
    "OutcomeDisplay",
    "format_value",
    "merge_display_info",
    "value_key",
]

#: The surfaces an offer is shown on.
SURFACES = ("text", "history", "table", "controls")


def value_key(value: Any) -> str:
    """A value as a lookup key, the way the browser writes it (``100.0`` → ``"100"``),
    so labels match whether a value is stored as an int or a float."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def format_value(info: dict[str, Any] | None, issue: str, value: Any) -> str:
    """A value as the participant reads it: its ``value_labels`` entry, else
    the issue's ``issue_format`` applied to it, else ``str(value)``."""
    info = info or {}
    labels = (info.get("value_labels") or {}).get(issue) or {}
    if isinstance(labels, dict):
        for k, shown in labels.items():
            if value_key(k) == value_key(value):
                return str(shown)
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # 100.0 → "$100", not "$100.0"
    fmt = (info.get("issue_format") or {}).get(issue)
    if fmt:
        try:
            return str(fmt).format(value)
        except (ValueError, TypeError, IndexError, KeyError):
            pass
    return str(value)


#: Display keys that map issue names to settings; an override merges into them per issue.
PER_ISSUE_KEYS = ("issue_format", "value_labels", "issue_widget")


def merge_display_info(info: dict[str, Any] | None, overrides: dict[str, Any] | None) -> dict[str, Any]:
    """``info`` (a scenario's ``_info.yaml``) with a session's display ``overrides`` on top:
    ``offer_template`` is replaced; ``issue_format``, ``value_labels`` and ``issue_widget``
    merge per issue (an issue mapped to ``None`` falls back to the scenario's setting)."""
    out = dict(info or {})
    for k, v in (overrides or {}).items():
        if k in PER_ISSUE_KEYS and isinstance(v, dict):
            merged = dict(out.get(k) or {})
            for issue, x in v.items():
                if x is None:
                    continue
                if k == "value_labels" and isinstance(x, dict) and isinstance(merged.get(issue), dict):
                    x = {**merged[issue], **x}
                merged[issue] = x
            out[k] = merged
        elif v is not None:
            out[k] = v
    return out


@dataclass
class OfferContext:
    """What a display method knows besides the offer itself.

    ``surface`` is where the offer is shown (``text``, ``history``, ``table``
    or ``controls``); ``from_human`` whether the participant made it (always
    true for ``controls``); ``utility`` what it is worth to the participant
    (``None`` for an incomplete draft); ``role`` the participant's role (the
    name of their utility function); ``opponent_offer`` the opponent's current
    offer (``{issue: value}``) if any.
    """

    scenario: Scenario
    surface: str = "text"
    from_human: bool = False
    is_done: bool = False
    role: str = ""
    utility: float | None = None
    reserved_value: float = 0.0
    is_my_turn: bool = True
    step: int | None = None
    opponent_offer: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    #: the session's overrides of the scenario's display keys (see :func:`merge_display_info`)
    overrides: dict[str, Any] = field(default_factory=dict)

    @property
    def info(self) -> dict[str, Any]:
        if self.overrides:
            return merge_display_info(self.scenario.info, self.overrides)
        return self.scenario.info or {}

    @property
    def issues(self) -> list:
        return list(self.scenario.outcome_space.issues)  # type: ignore[attr-defined]

    @property
    def issue_names(self) -> list[str]:
        return [i.name for i in self.issues]

    def fmt(self, issue: str, value: Any) -> str:
        """``value`` of ``issue`` as the participant reads it (see :func:`format_value`)."""
        return format_value(self.info, issue, value)

    def outcome(self, offer: dict[str, Any] | None) -> Outcome | None:
        """The offer as a negmas outcome (a tuple in issue order)."""
        if offer is None:
            return None
        return tuple(offer.get(n) for n in self.issue_names)

    def as_dict(self, outcome: Outcome | dict | None) -> dict[str, Any] | None:
        """The offer as ``{issue: value}``."""
        if outcome is None or isinstance(outcome, dict):
            return outcome  # type: ignore[return-value]
        return dict(zip(self.issue_names, outcome))


class OfferDisplay:
    """The default way to show offers; subclass it and override what you need.

    ``offer`` / ``draft`` arguments are ``{issue name: value}`` dicts with the
    stored values (a draft may hold ``None`` for issues not chosen yet).
    """

    #: The control of each issue in the default editor (``buttons``, ``select``,
    #: ``slider``, ``number``); the scenario's ``issue_widget`` adds to it.
    widgets: ClassVar[dict[str, str]] = {}

    # -- the four surfaces ------------------------------------------------
    def text(self, offer: dict[str, Any] | None, ctx: OfferContext) -> str:
        """One line. Default: ``offer_template`` if the scenario has one, else
        ``Issue: value, …`` with :meth:`OfferContext.fmt` values."""
        if offer is None:
            return "❓"
        shown = {k: ctx.fmt(k, v) for k, v in offer.items()}
        template = ctx.info.get("offer_template")
        if template:
            try:
                return str(template).format_map(shown)
            except (KeyError, ValueError, IndexError):
                pass
        return ", ".join(f"{k}: {v}" for k, v in shown.items())

    def history(self, offer: dict[str, Any], ctx: OfferContext) -> list[dict] | None:
        """The offer in a history bubble, or ``None`` for the default (issue
        chips, or :meth:`text` when the participant prefers text)."""
        return None

    def on_table(self, offer: dict[str, Any], ctx: OfferContext) -> list[dict] | None:
        """The opponent's current offer in the "Offer on the table" card, or
        ``None`` for the default (:meth:`text`)."""
        return None

    def controls(self, draft: dict[str, Any], ctx: OfferContext) -> list[dict] | None:
        """The counter-offer editor, or ``None`` for the default (one field
        per issue). Use :func:`hani2.tools.ui.issue` for a default field."""
        return None

    # -- events from custom controls ----------------------------------------
    def on_input(self, name: str, value: Any, draft: dict[str, Any], ctx: OfferContext) -> dict[str, Any] | None:
        """An input of :meth:`controls` whose name is not an issue changed.
        Return the issue values to set (``{issue: value}``) or ``None``."""
        return None

    def on_action(self, action: str, payload: dict[str, Any], draft: dict[str, Any],
                  ctx: OfferContext) -> dict[str, Any] | None:
        """A button of :meth:`controls` was clicked (``payload`` holds the
        button's payload and the values of the inputs). Return the issue
        values to set or ``None``."""
        return None

    # -- helpers --------------------------------------------------------------
    def str(self, outcome: Outcome | None, scenario: Scenario, is_done: bool = False, from_human: bool = False) -> str:
        """:meth:`text` for a negmas outcome (a tuple in issue order)."""
        ctx = OfferContext(scenario, is_done=is_done, from_human=from_human)
        return self.text(ctx.as_dict(outcome), ctx)

    def widget_for(self, issue: str, ctx: OfferContext) -> str | None:
        w = (ctx.info.get("issue_widget") or {}).get(issue) or self.widgets.get(issue)
        return str(w) if w else None


class DefaultOutcomeDisplay(OfferDisplay):
    """The older interface, still supported: override
    ``str(outcome, scenario, is_done, from_human)`` (``outcome`` is a tuple in
    issue order) to write offers as text. New displays should subclass
    :class:`OfferDisplay` and override :meth:`OfferDisplay.text` instead."""

    def text(self, offer: dict[str, Any] | None, ctx: OfferContext) -> str:
        if type(self).str is DefaultOutcomeDisplay.str:
            return super().text(offer, ctx)
        return self.str(ctx.outcome(offer), ctx.scenario, ctx.is_done, ctx.from_human)

    def str(self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool) -> str:
        ctx = OfferContext(scenario, is_done=is_done, from_human=from_human)
        return OfferDisplay.text(self, ctx.as_dict(outcome), ctx)

    def table(self, outcome: Outcome | None, scenario: Scenario, is_done: bool, from_human: bool) -> list[dict[str, Any]]:
        names = [_.name for _ in scenario.outcome_space.issues]  # type: ignore
        return [dict(zip(names, outcome))] if outcome else []


#: The older name of the display interface.
OutcomeDisplay = OfferDisplay
