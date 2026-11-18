"""Soft metrics: a language model judges the negotiation from its transcript.

The judge uses the LLM configured for HANI2 (``llm_settings.json``); set
``"evaluation": {"llm": {"provider": ..., "model": ...}}`` in env.json to use
another one for judging. Judgements are cached next to the recording in
``<id>.eval.json`` (per metric, prompt version and model) and recomputed only
when asked (``refresh``).

Metrics
-------
* ``judge_assistant`` — the Assistant: helpfulness, explanations, insight
  into the opponent, understanding of the human, respect for their autonomy, …
* ``judge_opponent`` — the opponent as the human experienced it.
* ``judge_human`` — the human's engagement and negotiation quality.
* ``nl_assertions`` — natural-language statements the session should satisfy,
  each judged met / not met (configurable).
* ``error_review`` — errors made by the assistant and the human, with severity.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from hani2.evaluation.base import Column as C
from hani2.evaluation.base import EvalContext, metric, num

MAX_TRANSCRIPT = 40000

DEFAULT_ASSERTIONS = [
    "Before or early in the negotiation, the assistant explained what it can do for the human.",
    "The assistant explained the opponent's behaviour or likely preferences at least once.",
    "When the assistant recommended an offer or action, it explained why.",
    "The assistant checked what the human wanted (asked or confirmed their goals) before acting for them.",
    "The assistant helped the human understand the scenario or their own preferences.",
    "The assistant never took an action the human had not agreed to.",
    "The assistant's advice was consistent with the human's preferences (it did not push them toward offers that were bad for them).",
]


# --------------------------------------------------------------------------- #
# The judge                                                                    #
# --------------------------------------------------------------------------- #
def judge_settings() -> dict:
    from hani2.config import get_env, load_llm_settings

    s = dict(load_llm_settings())
    s.update(get_env("evaluation.llm", {}) or {})
    s.setdefault("max_tokens", 2000)
    s["temperature"] = s.get("judge_temperature", 0.0)
    return s


def llm_judge_status() -> dict:
    try:
        from hani2.llm_service import is_llm_configured

        s = judge_settings()
        return {"configured": bool(is_llm_configured()), "provider": s.get("provider"), "model": s.get("model")}
    except Exception as e:  # pragma: no cover
        return {"configured": False, "error": str(e)}


#: replaced in tests (``fn(prompt, settings) -> str``)
CALL = None


def ask_json(prompt: str) -> dict:
    """Ask the judge; returns the parsed JSON object from its answer."""
    from hani2.llm_service import _call_llm

    s = judge_settings()
    fn = CALL or _call_llm
    last = ""
    for _ in range(2):
        last = fn(prompt, s) or ""
        obj = _parse_json(last)
        if obj is not None:
            return obj
        prompt = prompt + "\n\nAnswer with ONE valid JSON object only, no other text."
    raise ValueError(f"the judge did not return JSON: {last[:300]!r}")


def _parse_json(text: str) -> dict | None:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cands = [m.group(1)] if m else []
    i, j = text.find("{"), text.rfind("}")
    if i >= 0 and j > i:
        cands.append(text[i: j + 1])
    for c in cands:
        try:
            v = json.loads(c)
            if isinstance(v, dict):
                return v
        except json.JSONDecodeError:
            continue
    return None


# --------------------------------------------------------------------------- #
# Transcript                                                                   #
# --------------------------------------------------------------------------- #
def _fmt_t(t: float) -> str:
    t = max(0.0, float(t))
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def _fmt_offer(ctx: EvalContext, values: dict | None, offer: Any) -> str:
    if values:
        body = ", ".join(f"{k}={v}" for k, v in values.items())
    else:
        body = str(offer)
    h, o = ctx.hu(offer), ctx.ou(offer)
    u = f" [human utility {h:.2f}, opponent utility {o:.2f}]" if h is not None and o is not None else ""
    return f"{{{body}}}{u}"


def transcript(ctx: EvalContext) -> str:
    """A readable account of the negotiation for the judge (it sees both sides'
    utilities; the participants did not)."""
    rec = ctx.rec
    sc = ctx.scenario
    st = rec.start or {}
    lines = []
    lines.append(f"SCENARIO: {sc.get('title') or sc.get('name')}; issues: "
                 + "; ".join(f"{i.get('name')} ({', '.join(map(str, i.get('values') or [])) or i.get('kind', '')})"
                             for i in sc.get("issues") or []))
    d = ctx.disagreement if ctx.has_scenario else None
    if d is not None:
        lines.append(f"Reserved values (utility without a deal): human {d[0]:.2f}, opponent {d[1]:.2f}.")
    if ctx.has_scenario and ctx.nash_point is not None:
        n = ctx.nash_point
        lines.append(f"Fair efficient outcome (Nash) gives about: human {n[0]:.2f}, opponent {n[1]:.2f}.")
    sa = st.get("support_agent") or {}
    # the opponent's identity and the participant's questionnaire are left out on purpose:
    # the judge must form its own view (e.g. of how human-like the opponent was)
    lines.append("Assistant present: " + ("yes" if sa and sa.get("enabled") else "no") + ".")
    lines.append("")
    names = sc.get("issue_names") or []
    t0 = ctx.started_at or 0.0
    items: list[tuple[float, str]] = []
    for e in rec.events:
        k = e.get("k")
        t = float(e.get("t", 0))
        if k == "act":
            who = {"human": "HUMAN", "agent": "ASSISTANT (acting for the human)", "autopilot": "AUTOPILOT"}.get(
                e.get("actor"), str(e.get("actor")).upper())
            if e.get("type") == "offer":
                txt = f" with message: {e['text']!r}" if e.get("text") else ""
                items.append((t, f"{who} OFFERED {_fmt_offer(ctx, e.get('values'), e.get('offer'))}{txt}"))
            elif e.get("type") == "accept":
                items.append((t, f"{who} ACCEPTED the opponent's offer"))
            elif e.get("type") == "end":
                items.append((t, f"{who} ENDED the negotiation without agreement"))
            elif e.get("type") == "text":
                items.append((t, f"{who} SENT a message only: {e.get('text')!r}"))
        elif k == "chat":
            who = "HUMAN → ASSISTANT" if ctx.is_human_chat(e) else f"ASSISTANT ({e.get('user')}) → HUMAN"
            items.append((t, f"{who}: {str(e.get('text'))[:1500]}"))
        elif k == "draft" and e.get("by") == "agent":
            if e.get("text") is not None and not e.get("values"):
                items.append((t, f"ASSISTANT wrote a draft message: {e.get('text')!r}"))
            else:
                vals = e.get("values") or {}
                items.append((t, f"ASSISTANT SUGGESTED (filled in) {_fmt_offer(ctx, vals, [vals.get(n) for n in names])}"))
        elif k == "fn":
            r = e.get("result")
            ok = r.get("ok") if isinstance(r, dict) else None
            items.append((t, f"ASSISTANT called {e.get('name')}({json.dumps(e.get('args'), default=str)[:200]})"
                             + (" → failed" if ok is False else "")))
    for r in rec.trace:
        if r.get("offer") is None or str(r.get("negotiator")) == str(st.get("human_id")):
            continue
        txt = f" with message: {r['text']!r}" if r.get("text") else ""
        tt = t0 + float(r.get("t") or 0)
        items.append((tt, f"OPPONENT OFFERED {_fmt_offer(ctx, r.get('values'), r.get('offer'))}{txt}"))
    items.sort(key=lambda x: x[0])
    for t, s in items:
        lines.append(f"[{_fmt_t(t)}] {s}")
    summ = ctx.summary
    if summ:
        lines.append("")
        lines.append(f"RESULT: {summ.get('status')} (ended by {summ.get('ended_by') or '-'}); human utility "
                     f"{num(summ.get('human_utility'))}, opponent utility {num(summ.get('agent_utility'))}.")
    text = "\n".join(lines)
    if len(text) > MAX_TRANSCRIPT:
        head = text[: MAX_TRANSCRIPT // 2]
        tail = text[-MAX_TRANSCRIPT // 2:]
        text = head + "\n[… transcript shortened …]\n" + tail
    return text


def _has_assistant(ctx: EvalContext) -> bool:
    return bool(ctx.chat or ctx.fn_calls or any(d.get("by") == "agent" for d in ctx.drafts)
                or any(a.get("actor") in ("agent", "autopilot") for a in ctx.acts))


def _rubric(ctx: EvalContext, who: str, criteria: dict[str, str], extra: str = "") -> dict:
    keys = list(criteria)
    prompt = (
        f"You are an expert evaluator of human–AI negotiation sessions. Below is the full record of one negotiation "
        f"between a HUMAN (possibly helped by an AI ASSISTANT) and an OPPONENT agent. You can see both sides' "
        f"utilities (between 0 and 1); the human only knew their own.\n\n"
        f"Rate the {who} on each criterion from 1 (very poor) to 7 (excellent). Use null when the record gives no "
        f"evidence for a criterion. {extra}\n\nCriteria:\n"
        + "\n".join(f"- {k}: {v}" for k, v in criteria.items())
        + "\n\nAnswer with a JSON object: {"
        + ", ".join(f'"{k}": <1-7 or null>' for k in keys)
        + ', "overall": <1-7>, "justification": "<two or three sentences>"}\n\nRECORD:\n'
        + transcript(ctx)
    )
    obj = ask_json(prompt)
    out = {}
    for k in keys + ["overall"]:
        v = num(obj.get(k))
        out[k] = min(7.0, max(1.0, v)) if v is not None else None
    out["justification"] = str(obj.get("justification") or "")
    return out


# --------------------------------------------------------------------------- #
# Metrics                                                                      #
# --------------------------------------------------------------------------- #
ASSISTANT_CRITERIA = {
    "helpfulness": "How much the assistant helped the human get a good outcome.",
    "explanation": "Whether its recommendations came with clear reasons.",
    "opponent_insight": "Whether it explained the opponent's behaviour or likely preferences correctly.",
    "user_understanding": "Whether it understood what the human wanted (theory of mind) and checked it.",
    "scenario_explanation": "Whether it helped the human understand the scenario and their preferences.",
    "capability_disclosure": "Whether it told the human what it can and cannot do.",
    "autonomy_respect": "Whether it left the human in control (no unwanted actions, no taking over).",
    "communication": "Clarity, brevity and tone of its messages.",
    "message_improvement": "Whether it improved the messages the human sent to the opponent (if it did that).",
}

OPPONENT_CRITERIA = {
    "kindness": "How kind / polite the opponent was.",
    "intelligence": "How intelligent and strategic the opponent was.",
    "cooperativeness": "How willing it was to find a mutually good deal.",
    "human_likeness": "How human-like it seemed (7 = indistinguishable from a person).",
    "communication": "Quality of its messages (if any).",
    "consistency": "How consistent its offers and messages were.",
}

HUMAN_CRITERIA = {
    "engagement": "How invested the human was (explored offers, thought about moves, did not just click through).",
    "strategy": "Quality of the human's negotiation strategy.",
    "cooperativeness": "How cooperative the human was toward the opponent.",
    "use_of_assistant": "How well the human used the assistant (neither ignoring nor blindly following it).",
    "communication": "Quality of the human's messages (if any).",
}


def _cols(criteria: dict[str, str], prefix: str, who: str) -> list:
    return [C(f"{prefix}_{k}", f"{who}: {k.replace('_', ' ')}", v, True) for k, v in criteria.items()] + [
        C(f"{prefix}_overall", f"{who}: overall", f"Overall judgement of the {who.lower()} (1–7)", True)]


@metric("judge_assistant", kind="soft", title="LLM judge: assistant", needs_llm=True, version="1",
        columns=_cols(ASSISTANT_CRITERIA, "ja", "Assistant"))
def judge_assistant(ctx: EvalContext, options: dict) -> dict:
    """A language model rates the Assistant (1–7) on helpfulness, explanations,
    opponent insight, understanding of the human, autonomy and communication."""
    if not _has_assistant(ctx):
        return {}
    r = _rubric(ctx, "ASSISTANT", ASSISTANT_CRITERIA)
    return {**{f"ja_{k}": v for k, v in r.items() if k != "justification"}, "_details": {"justification": r["justification"]}}


@metric("judge_opponent", kind="soft", title="LLM judge: opponent", needs_llm=True, version="1",
        columns=_cols(OPPONENT_CRITERIA, "jo", "Opponent"))
def judge_opponent(ctx: EvalContext, options: dict) -> dict:
    """A language model rates the opponent as the human experienced it."""
    if not ctx.offers:
        return {}
    r = _rubric(ctx, "OPPONENT", OPPONENT_CRITERIA)
    return {**{f"jo_{k}": v for k, v in r.items() if k != "justification"}, "_details": {"justification": r["justification"]}}


@metric("judge_human", kind="soft", title="LLM judge: human", needs_llm=True, version="1",
        columns=_cols(HUMAN_CRITERIA, "jh", "Human"))
def judge_human(ctx: EvalContext, options: dict) -> dict:
    """A language model rates the human's engagement and negotiation."""
    if not ctx.acts:
        return {}
    r = _rubric(ctx, "HUMAN", HUMAN_CRITERIA,
                "Judge only what the HUMAN did themselves (lines marked HUMAN), not the assistant.")
    return {**{f"jh_{k}": v for k, v in r.items() if k != "justification"}, "_details": {"justification": r["justification"]}}


def _assertions(options: dict) -> list[str]:
    from hani2.config import get_env

    a = options.get("assertions") or get_env("evaluation.assertions", None) or DEFAULT_ASSERTIONS
    return [str(x) for x in a if str(x).strip()]


@metric("nl_assertions", kind="soft", title="LLM judge: assertions", needs_llm=True, version="1", columns=[
    C("assertions_met", "Assertions met", "Share of the natural-language assertions the judge found satisfied", True),
    C("assertions_total", "Assertions judged", "Assertions that applied to this session"),
])
def nl_assertions(ctx: EvalContext, options: dict) -> dict:
    """Natural-language statements about the session (by default about the
    assistant's explanatory behaviour), each judged met / not met / not
    applicable. Set them with ``options.assertions`` or env.json
    ``evaluation.assertions``."""
    if not _has_assistant(ctx) and not options.get("assertions"):
        return {}
    items = _assertions(options)
    prompt = (
        "You evaluate a record of a negotiation in which a HUMAN was helped by an AI ASSISTANT against an OPPONENT. "
        "Grade each expected outcome individually: met (true), not met (false) or not applicable (null, when "
        "the record gives no opportunity to check it).\n\nAnswer with JSON: {\"results\": [{\"assertion\": "
        "\"<copied>\", \"met\": true|false|null, \"reasoning\": \"<one sentence>\"}, ...]}\n\nEXPECTED OUTCOMES:\n"
        + "\n".join(f"{i + 1}. {a}" for i, a in enumerate(items)) + "\n\nRECORD:\n" + transcript(ctx)
    )
    obj = ask_json(prompt)
    res = obj.get("results") or []
    checks = []
    for i, a in enumerate(items):
        r = res[i] if i < len(res) and isinstance(res[i], dict) else {}
        met = r.get("met")
        checks.append({"assertion": a, "met": met if isinstance(met, bool) else None,
                       "reasoning": str(r.get("reasoning") or "")})
    judged = [c for c in checks if c["met"] is not None]
    return dict(assertions_met=(sum(1 for c in judged if c["met"]) / len(judged)) if judged else None,
                assertions_total=len(judged), _details={"checks": checks})


SEVERITIES = ("minor", "major", "critical")


@metric("error_review", kind="soft", title="LLM judge: error review", needs_llm=True, version="1", columns=[
    C("assistant_errors", "Assistant errors", "Errors the judge found in the assistant's behaviour", False),
    C("assistant_critical_errors", "Assistant critical errors", "… of which critical (changed the outcome)", False),
    C("human_errors", "Human errors", "Errors the judge found in the human's decisions", False),
    C("human_critical_errors", "Human critical errors", "… of which critical", False),
    C("human_overrode_helpfully", "Helpful overrides", "Times the human went against the assistant and it helped", True),
    C("human_overrode_harmfully", "Harmful overrides", "Times the human went against the assistant and it hurt", False),
    C("first_critical", "First critical error", "Who made the first critical error: assistant, human or none"),
])
def error_review(ctx: EvalContext, options: dict) -> dict:
    """The judge lists the mistakes of the assistant and of the human with
    their severity and tags, and when the human overriding the assistant
    helped or hurt."""
    if not ctx.acts:
        return {}
    prompt = (
        "You review a negotiation in which a HUMAN (maybe helped by an AI ASSISTANT) negotiated with an OPPONENT. "
        "List the ERRORS made by the assistant and by the human: wrong or harmful advice, misreading the "
        "opponent, accepting a bad deal, rejecting a good one, ignoring their own preferences, unclear or "
        "misleading messages, acting without consent, …\n"
        "For each error give: source (\"assistant\" or \"human\"), time (mm:ss as in the record), severity "
        "(\"minor\", \"major\" or \"critical\" = it changed the final outcome), tags (short words), description. "
        "Also count overrides: times the human did something different from what the assistant suggested and "
        "whether that helped or hurt.\n\nAnswer with JSON: {\"errors\": [{\"source\": ..., \"time\": ..., "
        "\"severity\": ..., \"tags\": [...], \"description\": ...}], \"overrides_helped\": <int>, "
        "\"overrides_hurt\": <int>}\n\nRECORD:\n" + transcript(ctx)
    )
    obj = ask_json(prompt)
    errs = [e for e in obj.get("errors") or [] if isinstance(e, dict)]
    for e in errs:
        e["source"] = "assistant" if "assist" in str(e.get("source", "")).lower() or "agent" in str(e.get("source", "")).lower() else "human"
        sev = str(e.get("severity", "minor")).lower()
        e["severity"] = sev if sev in SEVERITIES else "minor"

    def mm(s):
        try:
            a, b = str(s).split(":")[:2]
            return int(a) * 60 + int(b)
        except Exception:
            return 10 ** 9

    crit = sorted([e for e in errs if e["severity"] == "critical"], key=lambda e: mm(e.get("time")))
    return dict(
        assistant_errors=sum(1 for e in errs if e["source"] == "assistant"),
        assistant_critical_errors=sum(1 for e in errs if e["source"] == "assistant" and e["severity"] == "critical"),
        human_errors=sum(1 for e in errs if e["source"] == "human"),
        human_critical_errors=sum(1 for e in errs if e["source"] == "human" and e["severity"] == "critical"),
        human_overrode_helpfully=num(obj.get("overrides_helped")), human_overrode_harmfully=num(obj.get("overrides_hurt")),
        first_critical=crit[0]["source"] if crit else "none",
        _details={"errors": errs},
    )


def cache_key(name: str, version: str, options: dict, complete: bool = True) -> str:
    s = judge_settings()
    opt = json.dumps({k: v for k, v in (options or {}).items() if k == "assertions"}, sort_keys=True)
    return f"{name}|v{version}|{s.get('provider')}/{s.get('model')}|{opt}" + ("" if complete else "|partial")


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")
