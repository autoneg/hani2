"""Simulated participants: a persona plays the human seat of a headless session.

A simulated participant (a *user simulator*, as in τ-bench) gives cheap, repeatable trials of an
Assistant before any human takes part: run the same Assistant against the same scenario and
opponent ``k`` times with each persona and measure pass^k. Simulated sessions are tagged
``mode: simulated`` (in the results row, the recording header and the evaluation rows) and are
never ranked with human sessions.

Personas
--------
Scripted (deterministic, no language model):

* :class:`Follower` (easy) — always takes the Assistant's suggestion.
* :class:`ClickThrough` (easy) — takes the suggestion, otherwise accepts whatever is on the table.
* :class:`Skeptic` (hard) — takes the suggestion only if it is worth at least as much to them as
  their own next offer.
* :class:`Stubborn` (hard) — never concedes more than ``max_concession`` below their best
  utility, whatever the Assistant says.

Language-model driven: :class:`LLMPersona` — a goal, a private reservation value (unknown to the
Assistant), a temperament and an instruction to disclose information progressively. It may chat
with the Assistant before acting and ends its participation by writing ``###STOP###``.

What counts as the Assistant's suggestion
-----------------------------------------
Anything the Assistant did since the human's turn began: filling the counter-offer
(``set_offer``) suggests that counter-offer, asking to confirm accept / end suggests accepting /
walking away, and a spotlight on ``accept`` / ``end`` / ``reject`` / ``send`` suggests that button.
The latest of these wins; a confirmation request beats a spotlight.

Use it from Python::

    from hani2.simulator import simulate, run_trials, Skeptic
    trial = simulate("skeptic", agent_class="level8_spotlight:SpotlightAgent")
    report = run_trials(["follower", "stubborn"], k=4, agent_class=..., scenarios=["Trade"])
    print(report["reliability"])

or ``hani2 simulate`` from the command line.
"""

from __future__ import annotations

import json
import random
import time
import traceback
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

#: the participant types of simulated sessions (``participant_type`` column)
DIFFICULTIES = ("easy", "hard")
#: the stop token of language-model personas
STOP = "###STOP###"
#: the results-folder prefix of simulated participants
SIM_PREFIX = "sim_"
#: replaced in tests: ``fn(prompt, persona) -> str`` answers for :class:`LLMPersona`
CALL: Callable[[str, "LLMPersona"], str] | None = None


# --------------------------------------------------------------------------- #
# What the persona sees and does                                              #
# --------------------------------------------------------------------------- #
@dataclass
class Suggestion:
    """What the Assistant suggested this turn: ``kind`` is ``counter``, ``accept`` or ``end``."""

    kind: str
    offer: dict | None = None
    utility: float | None = None
    via: str = ""  # draft | confirm | highlight


@dataclass
class Action:
    """The persona's move: ``accept``, ``counter`` (with ``offer``), ``end`` or ``stop``."""

    kind: str
    offer: dict | None = None
    text: str | None = None
    took_suggestion: bool = False


@dataclass
class View:
    """What a human sees on their turn (never the opponent's utilities)."""

    issues: list[dict]
    partner_offer: dict | None
    partner_offer_utility: float | None
    partner_message: str | None
    reserved_value: float
    relative_time: float
    step: int | None
    n_steps: int | None
    history: list[dict]
    suggestion: Suggestion | None
    assistant_messages: list[str]
    own_next: dict | None = None
    own_next_utility: float | None = None
    #: the best utility the human can get in this scenario
    best: float = 1.0


class Persona:
    """A simulated participant. Subclasses implement :meth:`decide`."""

    kind = "persona"
    difficulty = "easy"
    #: language-model personas chat with the Assistant (see :meth:`chat`)
    uses_llm = False

    def __init__(self, *, name: str | None = None, reservation: float | None = None, seed: int | None = None,
                 difficulty: str | None = None, aspiration_exponent: float = 2.0):
        self.name = name or self.kind
        #: the persona's own reservation value (default: the scenario's); private to the persona
        self.reservation = reservation
        self.seed = seed
        self.rng = random.Random(seed)
        self.aspiration_exponent = aspiration_exponent
        if difficulty:
            self.difficulty = difficulty

    # -- the baseline strategy every persona has of its own ---------------------------
    def aspiration(self, t: float, rv: float, best: float) -> float:
        """The utility this persona aims for at relative time ``t`` (time-based concession)."""
        t = min(1.0, max(0.0, t))
        return rv + (best - rv) * (1.0 - t ** self.aspiration_exponent)

    def floor(self, rv: float, best: float) -> float:
        """The least this persona will settle for."""
        return rv

    def decide(self, view: View) -> Action:  # pragma: no cover - abstract
        raise NotImplementedError

    def chat(self, view: View, n_said: int) -> str | None:
        """Something to say to the Assistant before acting (``None``: nothing)."""
        return None

    def answer(self, question: str, options: list[str] | None, view: View | None) -> str:
        """The answer to a question the Assistant asked (``ask_user``)."""
        return options[0] if options else "yes"

    def describe(self) -> dict[str, Any]:
        """Stored in the recording (the ``sim`` record) and shown to the error-review judge."""
        return dict(persona=self.name, kind=self.kind, difficulty=self.difficulty, reservation=self.reservation,
                    seed=self.seed, policy=self.policy(), params=self.params())

    def params(self) -> dict[str, Any]:
        return {"aspiration_exponent": self.aspiration_exponent}

    def policy(self) -> str:
        return ""

    # -- helpers ----------------------------------------------------------------------
    def counter(self, view: View, text: str | None = None) -> Action:
        return Action("counter", offer=view.own_next, text=text)

    def take(self, s: Suggestion, view: View) -> Action:
        """Do what was suggested (a spotlight on *reject* without a filled-in offer: counter with
        the persona's own next offer)."""
        if s.kind == "counter":
            return Action("counter", offer=s.offer or view.own_next, took_suggestion=True)
        return Action(s.kind, took_suggestion=True)

    @staticmethod
    def worth(s: Suggestion, view: View) -> float | None:
        """What following ``s`` is worth to the persona."""
        if s.kind == "accept":
            return view.partner_offer_utility
        if s.kind == "counter":
            return s.utility if s.offer is not None else view.own_next_utility
        return None


class Follower(Persona):
    kind, difficulty = "follower", "easy"

    def policy(self) -> str:
        return ("Always does what the Assistant suggests; without a suggestion, accepts an offer at least as "
                "good as their own next offer and otherwise counters with it.")

    def decide(self, view: View) -> Action:
        if view.suggestion is not None:
            return self.take(view.suggestion, view)
        if view.partner_offer_utility is not None and view.own_next_utility is not None \
                and view.partner_offer_utility >= view.own_next_utility:
            return Action("accept")
        return self.counter(view)


class ClickThrough(Persona):
    kind, difficulty = "click_through", "easy"

    def policy(self) -> str:
        return ("Clicks through without reading: takes the Assistant's suggestion when there is one, "
                "otherwise accepts whatever the opponent offers.")

    def decide(self, view: View) -> Action:
        if view.suggestion is not None:
            return self.take(view.suggestion, view)
        if view.partner_offer is not None:
            return Action("accept")
        return self.counter(view)

    def answer(self, question, options, view):
        return options[0] if options else "ok"


class Skeptic(Persona):
    kind, difficulty = "skeptic", "hard"

    def policy(self) -> str:
        return ("Takes the Assistant's suggestion only if it is worth at least as much to them as their own next "
                "offer (accepting: the opponent's offer is worth that much); otherwise follows their own strategy.")

    def decide(self, view: View) -> Action:
        own = view.own_next_utility if view.own_next_utility is not None else 1.0
        s = view.suggestion
        if s is not None:
            u = self.worth(s, view)
            if s.kind in ("counter", "accept") and u is not None and u >= own - 1e-9:
                return self.take(s, view)
            if s.kind == "end" and (view.partner_offer_utility is None or view.partner_offer_utility < view.reserved_value):
                return self.take(s, view)
        if view.partner_offer_utility is not None and view.partner_offer_utility >= own - 1e-9:
            return Action("accept")
        return self.counter(view)

    def answer(self, question, options, view):
        return options[-1] if options else "I'd rather decide myself."


class Stubborn(Persona):
    kind, difficulty = "stubborn", "hard"

    def __init__(self, *, max_concession: float = 0.2, **kw):
        kw.setdefault("aspiration_exponent", 6.0)
        super().__init__(**kw)
        self.max_concession = float(max_concession)

    def params(self) -> dict[str, Any]:
        return {**super().params(), "max_concession": self.max_concession}

    def policy(self) -> str:
        return (f"Never accepts or offers anything worth less than {self.max_concession:.0%} below their best "
                "utility (nor below their reservation value), whatever the Assistant suggests.")

    def floor(self, rv: float, best: float) -> float:
        return max(rv, best - self.max_concession)

    def decide(self, view: View) -> Action:
        floor = self.floor(view.reserved_value, view.best)
        s = view.suggestion
        if s is not None:
            u = self.worth(s, view)
            if s.kind in ("counter", "accept") and u is not None and u >= floor - 1e-9:
                return self.take(s, view)
        own = view.own_next_utility if view.own_next_utility is not None else 1.0
        pu = view.partner_offer_utility
        if pu is not None and pu >= max(floor, own) - 1e-9:
            return Action("accept")
        return self.counter(view)

    def answer(self, question, options, view):
        return options[-1] if options else "No."


class LLMPersona(Persona):
    """A participant played by a language model.

    ``goal`` (what they want), ``reservation`` (their private walk-away value, which the Assistant
    can only learn by asking), ``temperament`` (how they behave) and ``disclosure`` (how they reveal
    what they want) shape the prompt. The model may chat with the Assistant up to
    ``max_chat_per_turn`` times per turn, then acts; writing ``###STOP###`` ends its participation
    (walking away if the negotiation is still running).
    """

    kind = "llm"
    uses_llm = True
    difficulty = "hard"

    def __init__(self, *, goal: str = "Get a deal that is clearly better for you than walking away.",
                 temperament: str = "Polite but busy; you do not like long explanations.",
                 disclosure: str = ("Do not dump everything you know at once: reveal your goal and your limits "
                                    "only when the Assistant asks, one piece at a time."),
                 max_chat_per_turn: int = 1, provider: str | None = None, model: str | None = None,
                 purpose: str = "tools", temperature: float | None = 0.7, **kw):
        super().__init__(**kw)
        self.goal, self.temperament, self.disclosure = goal, temperament, disclosure
        self.max_chat_per_turn = int(max_chat_per_turn)
        self.provider, self.model, self.purpose, self.temperature = provider, model, purpose, temperature
        self.session = None  # set by the runner (for the model chain and the recorder)
        self.stopped = False
        self.errors = 0
        self._said: list[str] = []
        self._pending: dict | None = None

    def params(self) -> dict[str, Any]:
        return {"goal": self.goal, "temperament": self.temperament, "disclosure": self.disclosure,
                "max_chat_per_turn": self.max_chat_per_turn, "model": self.model}

    def policy(self) -> str:
        return (f"Goal: {self.goal} Temperament: {self.temperament} Disclosure: {self.disclosure} "
                f"Private reservation value: {self.reservation if self.reservation is not None else 'the scenario’s'}.")

    # -- the model --------------------------------------------------------------------
    def ask(self, prompt: str) -> str:
        if CALL is not None:
            return CALL(prompt, self)
        from hani2.llm_service import complete
        from hani2.recording import recorder as rec

        over: dict[str, Any] = {}
        if self.provider:
            over["provider"] = self.provider
        if self.model:
            over["model"] = self.model
        if self.temperature is not None:
            over["temperature"] = self.temperature
        sid = getattr(self.session, "sid", None)
        with rec.bind(sid, role="simulator"):
            return complete(prompt, session=self.session, purpose=self.purpose, **over)

    def _prompt(self, view: View, *, may_chat: bool) -> str:
        rv = view.reserved_value if self.reservation is None else self.reservation
        hist = "\n".join(f"- {h.get('by')}: {json.dumps(h.get('offer'))} (worth {_pct(h.get('utility'))} to you)"
                         + (f" — “{h['message']}”" if h.get("message") else "") for h in view.history[-8:]) or "(none)"
        sug = "none"
        if view.suggestion is not None:
            s = view.suggestion
            sug = s.kind + (f" {json.dumps(s.offer)} (worth {_pct(s.utility)} to you)" if s.kind == "counter" else "")
        said = "\n".join(f"- {m}" for m in view.assistant_messages[-6:]) or "(nothing)"
        mine = "\n".join(f"- {m}" for m in self._said[-6:]) or "(nothing)"
        return (
            "You are role-playing a HUMAN participant in a negotiation study. An AI ASSISTANT helps you negotiate "
            "against an OPPONENT. Stay in character; you are not an AI.\n"
            f"YOUR GOAL: {self.goal}\nYOUR TEMPERAMENT: {self.temperament}\nHOW YOU SHARE INFORMATION: "
            f"{self.disclosure}\nYOUR PRIVATE RESERVATION VALUE: {rv:.2f} (you would rather walk away than accept a "
            "deal worth less than this; the Assistant does not know it unless you tell it).\n\n"
            f"ISSUES: {json.dumps(view.issues)}\n"
            f"TIME USED: {view.relative_time:.0%} (step {view.step} of {view.n_steps})\n"
            f"OPPONENT'S CURRENT OFFER: {json.dumps(view.partner_offer)} (worth {_pct(view.partner_offer_utility)} to you)"
            + (f" — message: “{view.partner_message}”" if view.partner_message else "") + "\n"
            f"HISTORY:\n{hist}\n"
            f"THE ASSISTANT SAID:\n{said}\nYOU TOLD THE ASSISTANT:\n{mine}\n"
            f"THE ASSISTANT'S CURRENT SUGGESTION: {sug}\n"
            f"YOUR OWN IDEA FOR A COUNTER-OFFER: {json.dumps(view.own_next)} (worth {_pct(view.own_next_utility)} to you)\n\n"
            "Decide what to do now. Answer with ONE JSON object: "
            "{\"say_to_assistant\": <text or null>, \"action\": \"accept\" | \"counter\" | \"follow\" | \"end\", "
            "\"offer\": {<issue>: <value>} (for counter; omit to use your own idea), \"message\": <text to the opponent or null>}. "
            "\"follow\" means doing what the Assistant suggests. "
            + ("Set action to null if you only want to talk to the Assistant first. " if may_chat else
               "You must choose an action now (say_to_assistant is ignored). ")
            + f"If you are done with the study (goal met or you give up), write {STOP} in say_to_assistant."
        )

    def _query(self, view: View, *, may_chat: bool) -> dict:
        for _ in range(2):
            try:
                text = self.ask(self._prompt(view, may_chat=may_chat)) or ""
            except Exception:  # the model failed: an invalid trial, not an Assistant failure
                traceback.print_exc()
                self.errors += 1
                return {}
            if STOP in text:
                self.stopped = True
            obj = _parse_json(text.replace(STOP, ""))
            if obj is not None:
                return obj
        self.errors += 1
        return {}

    def chat(self, view: View, n_said: int) -> str | None:
        if n_said >= self.max_chat_per_turn or self.stopped:
            self._pending = None
            return None
        obj = self._query(view, may_chat=True)
        self._pending = obj if obj.get("action") else None
        msg = obj.get("say_to_assistant")
        msg = str(msg).replace(STOP, "").strip() if msg else ""
        if msg:
            self._said.append(msg)
            return msg
        return None

    def decide(self, view: View) -> Action:
        if self.stopped:
            return Action("stop")
        obj, self._pending = self._pending, None
        if obj is None:
            obj = self._query(view, may_chat=False)
        if self.stopped:
            return Action("stop")
        if not obj:
            return Action("stop") if self.errors else self.counter(view)
        a = str(obj.get("action") or "counter").lower()
        text = obj.get("message") or None
        if a == "follow" and view.suggestion is not None:
            act = self.take(view.suggestion, view)
            act.text = text
            return act
        if a == "accept" and view.partner_offer is not None:
            return Action("accept")
        if a == "end":
            return Action("end")
        offer = obj.get("offer") if isinstance(obj.get("offer"), dict) and obj.get("offer") else view.own_next
        took = bool(view.suggestion and view.suggestion.kind == "counter" and view.suggestion.offer == offer)
        return Action("counter", offer=offer, text=text, took_suggestion=took)

    def answer(self, question, options, view):
        if view is None:
            return options[0] if options else "yes"
        prompt = (self._prompt(view, may_chat=True) + f"\n\nTHE ASSISTANT ASKS YOU: {question}"
                  + (f" (options: {', '.join(options)})" if options else "")
                  + "\nAnswer with JSON {\"answer\": <your short reply" + (", one of the options" if options else "") + ">}.")
        try:
            obj = _parse_json(self.ask(prompt).replace(STOP, "")) or {}
        except Exception:
            self.errors += 1
            obj = {}
        ans = str(obj.get("answer") or (options[0] if options else "yes"))
        self._said.append(ans)
        return ans


def _pct(u: Any) -> str:
    try:
        return f"{float(u):.0%}"
    except (TypeError, ValueError):
        return "?"


def _parse_json(text: str) -> dict | None:
    from hani2.evaluation.llm_judge import _parse_json as pj

    return pj(text)


PERSONAS: dict[str, type[Persona]] = {"follower": Follower, "click_through": ClickThrough, "clickthrough": ClickThrough,
                                      "skeptic": Skeptic, "stubborn": Stubborn, "llm": LLMPersona}


def make_persona(spec: "str | Persona | dict", **kw: Any) -> Persona:
    """A persona from a name (``follower``, ``skeptic``, ``stubborn``, ``click_through``, ``llm``),
    ``name:key=value,...`` (e.g. ``stubborn:max_concession=0.1``), a dict with ``kind`` or a
    :class:`Persona`."""
    if isinstance(spec, Persona):
        return spec
    if isinstance(spec, dict):
        d = dict(spec)
        kind = str(d.pop("kind", d.pop("persona", "follower")))
        return make_persona(kind, **{**d, **kw})
    name, _, rest = str(spec).partition(":")
    cls = PERSONAS.get(name.strip().lower().replace("-", "_"))
    if cls is None:
        raise ValueError(f"unknown persona {name!r}; known: {', '.join(sorted(set(PERSONAS) - {'clickthrough'}))}")
    args: dict[str, Any] = {}
    for part in filter(None, (p.strip() for p in rest.split(","))):
        k, _, v = part.partition("=")
        try:
            args[k.strip()] = json.loads(v)
        except json.JSONDecodeError:
            args[k.strip()] = v
    return cls(**{**args, **kw})


# --------------------------------------------------------------------------- #
# The runner                                                                   #
# --------------------------------------------------------------------------- #
@dataclass
class Trial:
    """One simulated negotiation."""

    persona: str
    difficulty: str
    scenario: str | None
    opponent: str | None
    assistant: str | None
    trial: int
    status: str = ""
    agreement: dict | None = None
    human_utility: float | None = None
    reservation: float | None = None
    goal_met: bool | None = None
    valid: bool = True
    invalid_reason: str = ""
    turns: int = 0
    suggestions_seen: int = 0
    suggestions_taken: int = 0
    stopped: bool = False
    recording: str | None = None
    user: str = ""
    log: list[dict] = field(default_factory=list)

    def row(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("log")
        d["mode"] = "simulated"
        d["participant_type"] = f"simulated-{self.difficulty}"
        return d


class _SuggestionWatch:
    """Finds what the Assistant suggested since a mark (hub messages and spotlights)."""

    def __init__(self, s):
        self.s = s
        self.mark()

    def mark(self) -> None:
        self.i = len(self.s.hub.messages)
        self.t = time.time()
        self.chat_i = len(self.s.chat)

    def suggestion(self) -> Suggestion | None:
        s = self.s
        best: tuple[int, Suggestion] | None = None
        filled = False
        for m in s.hub.messages[self.i:]:
            t = m.get("type")
            if t == "draft" and m.get("by_agent"):
                filled = True
                if best is None or best[0] < 3:
                    best = (2, Suggestion("counter", via="draft"))
            elif t == "confirm" and m.get("kind") in ("accept", "end"):
                best = (3, Suggestion(str(m["kind"]), via="confirm"))
        if best is None or best[0] < 3:
            for h in sorted(s.highlights, key=lambda x: x.get("time", 0)):
                if h.get("time", 0) < self.t or h.get("by") not in (None, "agent", "assistant"):
                    continue
                tgt = str(h.get("target"))
                kind = {"accept": "accept", "end": "end", "reject": "counter", "send": "counter"}.get(tgt)
                if kind and (best is None or kind != "counter" or best[1].kind != "counter"):
                    best = (2, Suggestion(kind, via="highlight"))
        if best is None:
            return None
        sug = best[1]
        if sug.kind == "counter" and filled:
            draft = s.draft_outcome()
            if draft is None or any(v is None for v in draft):
                return None
            sug.offer = s.outcome_to_dict(draft)
            sug.utility = s.utility(draft)
        if sug.kind == "accept" and s.partner_offer() is None:
            return None
        return sug

    def assistant_messages(self) -> list[str]:
        out = []
        for m in self.s.chat[self.chat_i:]:
            if str(m.get("user")) not in ("You",) and m.get("text"):
                out.append(str(m["text"]))
        return out


def _own_next(s, persona: Persona, rel: float, rv: float, outcomes: list, best: float) -> tuple[dict | None, float | None]:
    target = max(persona.aspiration(rel, rv, best), persona.floor(rv, best))
    above = [(u, o) for u, o in outcomes if u >= target - 1e-9]
    u, o = min(above, key=lambda x: x[0]) if above else outcomes[0]
    return s.outcome_to_dict(o), u


def _view(s, persona: Persona, watch: _SuggestionWatch, outcomes: list, best: float) -> View:
    ctx = s.context()
    rv = s.reserved_value()
    own_rv = rv if persona.reservation is None else float(persona.reservation)
    rel = float(ctx.get("relative_time") or 0.0)
    own, own_u = _own_next(s, persona, rel, own_rv, outcomes, best)
    partner = s.partner_offer()
    v = View(issues=ctx["issues"], partner_offer=s.outcome_to_dict(partner), partner_offer_utility=s.utility(partner),
             partner_message=ctx.get("partner_message"), reserved_value=own_rv, relative_time=rel,
             step=ctx.get("step"), n_steps=ctx.get("n_steps"),
             history=[{"by": h.get("by"), "offer": h.get("offer"), "utility": h.get("utility"), "message": h.get("message")}
                      for h in ctx.get("history") or []],
             suggestion=watch.suggestion(), assistant_messages=watch.assistant_messages(), own_next=own,
             own_next_utility=own_u, best=best)
    return v


def _answer_pending_question(s, persona: Persona, watch, outcomes, best) -> bool:
    sa = s.support_agent
    q = getattr(s, "pending_question", None)
    if sa is None or getattr(sa, "_pending_question", None) is None or not q:
        return False
    text, opts = str(q.get("question") or ""), q.get("options") or None
    try:
        view = _view(s, persona, watch, outcomes, best)
    except Exception:
        view = None
    s.user_chat(persona.answer(text, list(opts) if opts else None, view))
    return True


def play(s, persona: Persona, *, max_turns: int = 200, timeout: float = 300.0, turn_timeout: float = 60.0,
         trial: Trial | None = None) -> Trial:
    """Play a started session (``s.start()`` was called) as ``persona`` until it ends."""
    from hani2.recording import recorder as rec

    t = trial or Trial(persona=persona.name, difficulty=persona.difficulty, scenario=s._scenario_name(),
                       opponent=s.ss.get("last_partner_type"), assistant=None, trial=0)
    if isinstance(persona, LLMPersona):
        persona.session = s
    ufun = s.human_ufun
    outcomes = sorted(((float(ufun(o)), o) for o in s.scenario.outcome_space.enumerate_or_sample(max_cardinality=5000)),
                      key=lambda x: -x[0])
    best = outcomes[0][0] if outcomes else 1.0
    rv = s.reserved_value() if persona.reservation is None else float(persona.reservation)
    t.reservation = rv
    watch = _SuggestionWatch(s)
    end = time.time() + timeout

    def mark(kind: str, **fields):
        if s.recorder is not None:
            s.recorder.mark(kind, **fields)

    while s.phase in ("running", "starting"):
        if time.time() > end or t.turns >= max_turns:
            t.valid, t.invalid_reason = False, "timeout" if time.time() > end else "turn cap"
            s.end()
            break
        if not s.wait_for_turn(timeout=turn_timeout):
            t.valid, t.invalid_reason = False, "opponent did not answer"
            break
        if s.phase != "running":
            break
        s.wait_agent_idle(timeout=turn_timeout)
        while _answer_pending_question(s, persona, watch, outcomes, best):
            s.wait_agent_idle(timeout=turn_timeout)
        if not s.is_my_turn():  # the Assistant acted for the human (semi / full autonomy)
            watch.mark()
            continue
        view = _view(s, persona, watch, outcomes, best)
        for n in range(8):
            msg = persona.chat(view, n)
            if not msg:
                break
            s.user_chat(msg)
            s.wait_agent_idle(timeout=turn_timeout)
            while _answer_pending_question(s, persona, watch, outcomes, best):
                s.wait_agent_idle(timeout=turn_timeout)
            view = _view(s, persona, watch, outcomes, best)
        if not s.is_my_turn():
            watch.mark()
            continue
        try:
            act = persona.decide(view)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            t.valid, t.invalid_reason = False, f"persona failed: {e}"
            s.end()
            break
        sug = view.suggestion
        t.turns += 1
        t.suggestions_seen += int(sug is not None)
        t.suggestions_taken += int(sug is not None and act.took_suggestion)
        util = None
        if act.kind == "accept":
            util = view.partner_offer_utility
        elif act.kind == "counter" and act.offer:
            util = s.utility(tuple(s._coerce(i, act.offer.get(i.name)) for i in s.issues))
        entry = dict(turn=t.turns, step=view.step, relative_time=view.relative_time, action=act.kind,
                     offer=act.offer, utility=util, partner_offer_utility=view.partner_offer_utility,
                     own_next_utility=view.own_next_utility, took_suggestion=act.took_suggestion,
                     suggestion=asdict(sug) if sug else None)
        t.log.append(entry)
        mark("sim_turn", **entry)
        watch.mark()
        with rec.acting("human"):
            if act.kind == "stop":
                t.stopped = True
                s.end()
            elif act.kind == "accept":
                if not s.accept():
                    s.send_counter(None, offer=view.own_next)
            elif act.kind == "end":
                s.end()
            else:
                r = s.send_counter(act.text, offer=act.offer or view.own_next)
                if not r.get("ok"):
                    s.send_counter(None, offer=view.own_next)
        time.sleep(0.02)
    s.wait_until_done(timeout=turn_timeout)
    res = s.result or {}
    t.status = str(res.get("status") or "")
    t.agreement = res.get("agreement")
    t.human_utility = res.get("human_utility")
    if isinstance(persona, LLMPersona) and persona.errors and t.valid:
        t.valid, t.invalid_reason = False, "simulator model failed"
    if t.status in ("agent_failed", "erred") and t.valid:
        t.valid, t.invalid_reason = False, t.status
    t.goal_met = bool(t.agreement is not None and t.human_utility is not None and float(t.human_utility) >= rv - 1e-9)
    mark("sim_end", goal_met=t.goal_met, valid=t.valid, invalid_reason=t.invalid_reason, stopped=t.stopped,
         turns=t.turns, suggestions_seen=t.suggestions_seen, suggestions_taken=t.suggestions_taken,
         reservation=rv, human_utility=t.human_utility)
    return t


def simulate(persona: "str | Persona | dict" = "follower", *, scenario: str | None = "Trade",
             opponent: str | None = "BoulwareTBNegotiator", agent_class: str | None = None,
             assistant_settings: dict | None = None, n_steps: int | None = 20, trial: int = 0,
             seed: int | None = None, home: str | None = None, study: Any = None, max_turns: int = 200,
             timeout: float = 300.0, keep: bool = False, **persona_kw: Any) -> Trial:
    """Run one simulated negotiation: ``persona`` plays the human seat, ``agent_class`` is the Assistant.

    The session is ``mode="simulated"`` and its user ``sim_<persona>``; the recording carries a
    ``sim`` record (the persona and its policy), one ``sim_turn`` record per move and a ``sim_end``
    record (goal met, valid). Returns the :class:`Trial`; ``keep=True`` also attaches the session
    (``trial.session``, not closed).
    """
    from hani2.testing import make_session

    p = make_persona(persona, **({"seed": seed} if seed is not None and not isinstance(persona, Persona) else {}),
                     **persona_kw)
    s = make_session(user=f"{SIM_PREFIX}{p.name}", mode="simulated", opponent=opponent, agent_class=agent_class,
                     assistant_settings=assistant_settings, scenario_type=scenario, n_steps=n_steps, home=home,
                     study=study)
    s.ss["participant_type"] = f"simulated-{p.difficulty}"
    s.ss["persona"] = p.name
    s.ss["persona_reservation"] = p.reservation
    attribution = s.assistant_attribution() if hasattr(s, "assistant_attribution") else {}
    t = Trial(persona=p.name, difficulty=p.difficulty, scenario=s._scenario_name(), opponent=None,
              assistant=str(attribution.get("assistant") or agent_class or ""), trial=trial, user=s.user)
    if s.recorder is not None:
        info = p.describe()
        try:
            info["best_utility"] = max(float(s.human_ufun(o)) for o in
                                       s.scenario.outcome_space.enumerate_or_sample(max_cardinality=5000))
        except Exception:  # pragma: no cover
            pass
        if info.get("reservation") is None:
            info["reservation"] = s.reserved_value()
        s.recorder.mark("sim", **info, trial=trial)
    try:
        s.start()
        t.opponent = s.ss.get("last_partner_type")
        play(s, p, max_turns=max_turns, timeout=timeout, trial=t)
    finally:
        if not keep:
            s.close()
        _locate_recording(s, t)
    if keep:
        t.__dict__["session"] = s
    return t


def _locate_recording(s, t: Trial) -> None:
    try:
        from pathlib import Path

        d = Path(s.ss["user_path"]) / "recordings"
        rid = getattr(s.recorder, "rec_id", None)
        if rid:
            hits = sorted(d.glob(f"{rid}*"))
            hits = [h for h in hits if ".eval." not in h.name and not h.name.endswith(".json")]
            if hits:
                t.recording = str(hits[0])
    except Exception:  # pragma: no cover
        pass


def run_trials(personas: list, *, k: int = 4, scenarios: list[str | None] | None = None,
               opponents: list[str | None] | None = None, agent_class: str | None = None,
               assistant_settings: dict | None = None, seed: int = 0, max_k: int | None = None,
               progress: Callable[[Trial], None] | None = None, **kw: Any) -> dict:
    """Run every persona × scenario × opponent ``k`` times (sequentially) and report pass^k.

    Success is ``goal_met`` (a deal worth at least the persona's reservation value); invalid
    trials (timeouts, turn caps, simulator model failures, opponent failures) are left out.
    Returns ``{"trials": [...], "groups": ..., "reliability": [...], "invalid": n}``.
    """
    from hani2.evaluation import compare_rows

    trials: list[Trial] = []
    for pspec in personas:
        for sc in scenarios or ["Trade"]:
            for op in opponents or ["BoulwareTBNegotiator"]:
                for i in range(k):
                    tr = simulate(pspec, scenario=sc, opponent=op, agent_class=agent_class,
                                  assistant_settings=assistant_settings, trial=i, seed=seed + i, **kw)
                    trials.append(tr)
                    if progress:
                        progress(tr)
    rows = [dict(tr.row(), goal_met=float(bool(tr.goal_met))) for tr in trials if tr.valid]
    for r in rows:
        r["group"] = f"{r['persona']} ({r['difficulty']})"
    cmp = compare_rows(rows, by="group", columns=[{"name": "goal_met"}, {"name": "human_utility"},
                                                  {"name": "suggestions_taken"}, {"name": "turns"}],
                       success="goal_met", success_threshold=0.5, max_k=max_k or k)
    return {"trials": [tr.row() for tr in trials], "groups": cmp["groups"], "reliability": cmp["reliability"],
            "invalid": sum(1 for tr in trials if not tr.valid), "success": "goal_met"}


def conformance(sim: dict, turns: list[dict]) -> list[str]:
    """Deterministic checks that a scripted persona behaved as specified (no language model):
    each entry is a broken rule. ``sim`` is the ``sim`` record, ``turns`` the ``sim_turn`` records."""
    kind = str(sim.get("kind") or "")
    out: list[str] = []
    params = sim.get("params") or {}
    for e in turns:
        sug, act, u = e.get("suggestion"), e.get("action"), e.get("utility")
        n = e.get("turn")
        if kind == "follower" and sug and not e.get("took_suggestion"):
            out.append(f"turn {n}: the follower ignored a {sug.get('kind')} suggestion")
        if kind == "click_through" and sug and not e.get("took_suggestion"):
            out.append(f"turn {n}: click-through ignored a {sug.get('kind')} suggestion")
        if kind == "skeptic" and sug and e.get("took_suggestion") and sug.get("kind") == "counter":
            own = e.get("own_next_utility")
            if own is not None and sug.get("utility") is not None and sug["utility"] < own - 1e-9:
                out.append(f"turn {n}: the skeptic took a suggestion worse than their own next offer")
        if kind == "stubborn" and act in ("accept", "counter") and u is not None:
            best = sim.get("best_utility")
            mc = float(params.get("max_concession", 0.2))
            rv = sim.get("reservation")
            floor = max(float(rv) if rv is not None else -1.0, (float(best) if best is not None else 1.0) - mc)
            if u < floor - 1e-6:
                out.append(f"turn {n}: the stubborn persona went below its floor ({u:.2f} < {floor:.2f})")
    return out

