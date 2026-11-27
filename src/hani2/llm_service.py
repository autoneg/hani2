"""
LLM Service for outcome extraction and text generation.

This module provides:
- Extracting structured outcomes from natural language text
- Generating natural language descriptions from structured outcomes
- Context-aware negotiation assistance using utility functions and history
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from negmas import Outcome
from negmas.outcomes import Issue, OutcomeSpace
from negmas.serialization import serialize

if TYPE_CHECKING:
    from negmas.preferences import UtilityFunction

from hani2.config import load_llm_settings


@dataclass
class NegotiationContext:
    """
    Full context for LLM-powered negotiation assistance.

    This provides all the information an LLM needs to help with negotiation:
    - The outcome space (what can be negotiated)
    - The human's utility function (their preferences)
    - The history of offers exchanged
    - The current offer being rejected (if any)
    """

    issues: list[Issue]
    outcome_space: OutcomeSpace | None = None
    ufun: UtilityFunction | None = None
    history: list[dict] | None = None
    current_offer: Outcome | None = None  # Opponent's offer we're responding to
    #: the session's language models (:class:`hani2.model_chain.SessionModels`)
    models: Any = None

    def get_outcome_space_json(self) -> str:
        """Serialize outcome space to JSON for LLM context."""
        if self.outcome_space is None:
            return "{}"
        try:
            return json.dumps(
                serialize(self.outcome_space, shorten_type_field=True), indent=2
            )
        except Exception:
            return "{}"

    def get_ufun_json(self) -> str:
        """Serialize utility function to JSON for LLM context."""
        if self.ufun is None:
            return "{}"
        try:
            return json.dumps(serialize(self.ufun, shorten_type_field=True), indent=2)
        except Exception:
            return "{}"

    def get_history_text(self, max_turns: int = 20) -> str:
        """Format negotiation history for LLM context."""
        if not self.history:
            return "No negotiation history yet."

        lines = []
        for turn in self.history[-max_turns:]:
            role = turn.get("role", "unknown")
            text = turn.get("text", "")
            outcome = turn.get("outcome")
            response_type = turn.get("response_type", "")

            outcome_str = ""
            if outcome is not None:
                if isinstance(outcome, (list, tuple)):
                    outcome_str = (
                        f" [Offer: {dict(zip([i.name for i in self.issues], outcome))}]"
                    )
                else:
                    outcome_str = f" [Offer: {outcome}]"

            response_str = f" ({response_type})" if response_type else ""
            text_str = f": {text}" if text else ""

            lines.append(f"- {role}{response_str}{text_str}{outcome_str}")

        return "\n".join(lines) if lines else "No negotiation history yet."

    def get_last_n_offers(self, n: int = 5) -> str:
        """Get the last N offers from history."""
        if not self.history:
            return "No offers yet."

        offers = []
        for turn in reversed(self.history):
            outcome = turn.get("outcome")
            if outcome is not None:
                role = turn.get("role", "unknown")
                if isinstance(outcome, (list, tuple)):
                    outcome_dict = dict(zip([i.name for i in self.issues], outcome))
                else:
                    outcome_dict = outcome
                offers.append(f"- {role}: {outcome_dict}")
                if len(offers) >= n:
                    break

        if not offers:
            return "No offers yet."
        return "\n".join(reversed(offers))

    def get_last_offer(self) -> str:
        """Get the most recent offer from history."""
        if not self.history:
            return "No offers yet."

        for turn in reversed(self.history):
            outcome = turn.get("outcome")
            if outcome is not None:
                role = turn.get("role", "unknown")
                if isinstance(outcome, (list, tuple)):
                    outcome_dict = dict(zip([i.name for i in self.issues], outcome))
                else:
                    outcome_dict = outcome
                return f"{role}: {outcome_dict}"
        return "No offers yet."

    def get_ufun_description(self) -> str:
        """Get a human-readable description of the utility function."""
        if self.ufun is None:
            return "No utility function defined."

        lines = ["Your preferences:"]

        # Try to extract preference information
        try:
            # Check for linear utility function
            if hasattr(self.ufun, "weights") and hasattr(self.ufun, "values"):
                weights = self.ufun.weights
                for i, issue in enumerate(self.issues):
                    if i < len(weights):
                        lines.append(f"- {issue.name}: weight = {weights[i]:.2f}")
            elif hasattr(self.ufun, "outcome_utilities"):
                # Mapping ufun - show best outcomes
                utils = self.ufun.outcome_utilities
                if utils:
                    sorted_outcomes = sorted(
                        utils.items(), key=lambda x: x[1], reverse=True
                    )
                    lines.append("Best outcomes for you:")
                    for outcome, util in sorted_outcomes[:5]:
                        if isinstance(outcome, (list, tuple)):
                            outcome_dict = dict(
                                zip([i.name for i in self.issues], outcome)
                            )
                        else:
                            outcome_dict = outcome
                        lines.append(f"  - {outcome_dict}: utility = {util:.2f}")
            else:
                # Fallback - just note that preferences exist
                lines.append(
                    "(Complex preference structure - see ufun_json for details)"
                )
        except Exception:
            lines.append("(Could not parse preference details)")

        return "\n".join(lines)

    def get_current_offer_text(self) -> str:
        """Format the current offer being responded to."""
        if self.current_offer is None:
            return "No current offer to respond to."

        lines = []
        for issue, value in zip(self.issues, self.current_offer):
            lines.append(f"- {issue.name}: {value}")
        return "\n".join(lines)

    def get_current_offer_utility(self) -> float | None:
        """Get utility of current offer if ufun is available."""
        if self.ufun is None or self.current_offer is None:
            return None
        try:
            return float(self.ufun(self.current_offer))
        except Exception:
            return None


@dataclass
class ExtractionResult:
    """Result of extracting an outcome from text."""

    has_offer: bool
    outcome: Outcome | None
    confidence: float
    reasoning: str
    error: str | None = None


@dataclass
class GenerationResult:
    """Result of generating text from an outcome."""

    text: str
    error: str | None = None


def _get_api_key(settings: dict) -> str | None:
    """Get API key from environment variable specified in settings."""
    env_var = settings.get("api_key_env", "OPENAI_API_KEY")
    return os.getenv(env_var)


def _format_issues_description(issues: list[Issue]) -> str:
    """Format issues for prompt inclusion."""
    lines = []
    for issue in issues:
        if hasattr(issue, "min_value") and hasattr(issue, "max_value"):
            lines.append(
                f"- {issue.name}: numeric value from {issue.min_value} to {issue.max_value}"
            )
        elif hasattr(issue, "all"):
            options = list(issue.all)
            if len(options) <= 10:
                lines.append(f"- {issue.name}: one of {options}")
            else:
                lines.append(
                    f"- {issue.name}: one of {options[:5]}... ({len(options)} options)"
                )
        else:
            lines.append(f"- {issue.name}")
    return "\n".join(lines)


def _format_outcome_description(outcome: Outcome, issues: list[Issue]) -> str:
    """Format an outcome for prompt inclusion."""
    if outcome is None:
        return "No offer (empty)"

    lines = []
    for issue, value in zip(issues, outcome):
        lines.append(f"- {issue.name}: {value}")
    return "\n".join(lines)


def _format_utility_context(
    my_outcome: Outcome,
    rejected_outcome: Outcome | None,
    my_utility: float | None,
    rejected_utility: float | None,
) -> str:
    """
    Format utility context in a way that doesn't reveal exact utility values
    but provides useful guidance for crafting persuasive messages.
    """
    lines = []

    if my_utility is not None:
        # Describe utility qualitatively
        if my_utility >= 0.8:
            lines.append("Your proposed offer is very favorable to you.")
        elif my_utility >= 0.6:
            lines.append("Your proposed offer is reasonably good for you.")
        elif my_utility >= 0.4:
            lines.append(
                "Your proposed offer represents a moderate compromise for you."
            )
        else:
            lines.append(
                "Your proposed offer involves significant concessions on your part."
            )

    if rejected_outcome is not None and rejected_utility is not None:
        # Describe why we're rejecting
        if rejected_utility < 0.3:
            lines.append(
                "The opponent's offer is quite unfavorable to you - you need to push for better terms."
            )
        elif rejected_utility < 0.5:
            lines.append("The opponent's offer doesn't meet your needs well enough yet.")
        elif rejected_utility < 0.7:
            lines.append(
                "The opponent's offer is acceptable but you believe you can do better."
            )
        else:
            lines.append(
                "The opponent's offer is actually quite good for you, but you're exploring alternatives."
            )

        # Provide guidance on negotiation dynamics
        if my_utility is not None and rejected_utility is not None:
            diff = my_utility - rejected_utility
            if diff > 0.3:
                lines.append(
                    "There's a significant gap between what you want and what they offered."
                )
            elif diff > 0.1:
                lines.append(
                    "You're making progress but need to close the gap further."
                )
            elif diff > 0:
                lines.append("You're getting close to a potential agreement.")
            else:
                lines.append(
                    "Consider whether your counter-offer truly improves your position."
                )

    return "\n".join(lines) if lines else "No utility context available."


def _build_full_context(ctx: NegotiationContext | None) -> dict[str, str]:
    """
    Build a dictionary of all context variables for prompt formatting.

    This provides comprehensive negotiation context to any LLM prompt including:
    - Issues description
    - Outcome space (JSON)
    - Utility function (JSON and description)
    - Negotiation history
    - Last N offers
    - Current offer being responded to
    """
    if ctx is None:
        return {
            "issues_description": "No issues defined.",
            "outcome_space_json": "{}",
            "ufun_json": "{}",
            "ufun_description": "No utility function defined.",
            "negotiation_history": "No history available.",
            "last_offer": "No offers yet.",
            "last_5_offers": "No offers yet.",
            "last_10_offers": "No offers yet.",
            "current_offer_description": "No current offer.",
            "current_offer_utility": "Unknown",
        }

    # Calculate current offer utility if possible
    current_util = ctx.get_current_offer_utility()
    current_util_str = f"{current_util:.2%}" if current_util is not None else "Unknown"

    return {
        "issues_description": _format_issues_description(ctx.issues),
        "outcome_space_json": ctx.get_outcome_space_json(),
        "ufun_json": ctx.get_ufun_json(),
        "ufun_description": ctx.get_ufun_description(),
        "negotiation_history": ctx.get_history_text(),
        "last_offer": ctx.get_last_offer(),
        "last_5_offers": ctx.get_last_n_offers(5),
        "last_10_offers": ctx.get_last_n_offers(10),
        "current_offer_description": ctx.get_current_offer_text(),
        "current_offer_utility": current_util_str,
    }


def chain_settings(purpose: str = "text", models: Any = None, sequence: str = "", **params: Any) -> dict:
    """Settings for :func:`_call_llm` that use the ``purpose`` model chain, or the named model
    ``sequence`` (prompts from ``llm_settings.json``; ``models``: the session's
    :class:`~hani2.model_chain.SessionModels`)."""
    return {**load_llm_settings(), "_purpose": purpose, "_models": models, "_params": params,
            "_sequence": sequence or ""}


def _one_off_entry(settings: dict):
    """An entry for explicit old-style ``provider``/``model`` settings (not from a chain)."""
    from hani2 import model_chain

    entries = model_chain.legacy_entries(settings, "llm", "text")
    if not entries:
        raise ValueError("no model given")
    return model_chain.resolve("text", chain=entries, source=model_chain.Source("call", {}, implicit=True))


def _call_llm(prompt: str, settings: dict | None = None) -> str:
    """Send ``prompt`` to the language model and return the reply text.

    With ``settings`` from :func:`chain_settings` (or none) the model comes from the model chain
    (:mod:`hani2.model_chain`); explicit ``provider``/``model`` settings call that model directly."""
    from hani2 import model_chain

    settings = chain_settings() if settings is None else settings
    messages = [{"role": "user", "content": prompt}]
    if "_purpose" in settings:
        params = {k: v for k, v in (settings.get("_params") or {}).items() if v is not None}
        response = model_chain.completion(settings["_purpose"], messages, models=settings.get("_models"),
                                          resolution=settings.get("_resolution"), params=params,
                                          sequence=settings.get("_sequence") or "")
    else:
        res = _one_off_entry(settings)
        response = model_chain.completion("text", messages, resolution=res)
    result = response.choices[0].message.content
    if result is None:
        raise ValueError("LLM returned empty response")
    return result


def _parse_extraction_response(response: str, issues: list[Issue]) -> ExtractionResult:
    """Parse the LLM response for outcome extraction."""
    # Try to extract JSON from the response
    try:
        # the reply nests the outcome object, so decode from the first brace (not a flat-object regex)
        text = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
        start = text.find("{")
        data = json.JSONDecoder().raw_decode(text[start:])[0] if start != -1 else json.loads(text)
        if not isinstance(data, dict):
            raise json.JSONDecodeError("not an object", text, 0)
    except json.JSONDecodeError:
        return ExtractionResult(
            has_offer=False,
            outcome=None,
            confidence=0.0,
            reasoning="Failed to parse LLM response as JSON",
            error=f"Invalid JSON: {response[:200]}",
        )

    has_offer = data.get("has_offer", False)
    confidence = float(data.get("confidence", 0.0))
    reasoning = data.get("reasoning", "")

    if not has_offer or data.get("outcome") is None:
        return ExtractionResult(
            has_offer=False, outcome=None, confidence=confidence, reasoning=reasoning
        )

    # Parse the outcome
    outcome_data = data["outcome"]
    outcome_values = []

    for issue in issues:
        value = outcome_data.get(issue.name)
        if value is None:
            # Try case-insensitive match
            for key, val in outcome_data.items():
                if key.lower() == issue.name.lower():
                    value = val
                    break

        if value is None:
            return ExtractionResult(
                has_offer=False,
                outcome=None,
                confidence=confidence,
                reasoning=f"Missing value for issue: {issue.name}",
                error=f"Incomplete outcome: missing {issue.name}",
            )

        # Convert value to appropriate type
        if hasattr(issue, "min_value"):
            try:
                if isinstance(issue.min_value, int):
                    value = int(float(value))
                else:
                    value = float(value)
            except (ValueError, TypeError):
                return ExtractionResult(
                    has_offer=False,
                    outcome=None,
                    confidence=0.0,
                    reasoning=f"Invalid numeric value for {issue.name}: {value}",
                    error=f"Type conversion failed for {issue.name}",
                )

        outcome_values.append(value)

    return ExtractionResult(
        has_offer=True,
        outcome=tuple(outcome_values),
        confidence=confidence,
        reasoning=reasoning,
    )


def extract_outcome_from_text(
    text: str,
    issues: list[Issue],
    context: NegotiationContext | None = None,
    settings: dict | None = None,
) -> ExtractionResult:
    """
    Extract a structured outcome from natural language text.

    Args:
        text: The natural language message to analyze
        issues: List of negotiation issues
        context: Full negotiation context (ufun, outcome space, history)
        settings: Optional LLM settings override

    Returns:
        ExtractionResult with the extracted outcome or error information
    """
    if not text or not text.strip():
        return ExtractionResult(
            has_offer=False, outcome=None, confidence=1.0, reasoning="Empty message"
        )

    if settings is None:
        settings = chain_settings("text", getattr(context, "models", None))

    # Build full context
    full_context = _build_full_context(context)

    try:
        prompt = settings["extraction_prompt"].format(**full_context, message=text)
    except KeyError:
        # Fallback for simpler prompts
        prompt = settings["extraction_prompt"].format(
            issues_description=full_context["issues_description"], message=text
        )

    try:
        response = _call_llm(prompt, settings)
        return _parse_extraction_response(response, issues)
    except Exception as e:
        return ExtractionResult(
            has_offer=False,
            outcome=None,
            confidence=0.0,
            reasoning="LLM call failed",
            error=str(e),
        )


def generate_text_from_outcome(
    outcome: Outcome,
    issues: list[Issue],
    context: NegotiationContext | None = None,
    rejected_outcome: Outcome | None = None,
    my_utility: float | None = None,
    rejected_utility: float | None = None,
    settings: dict | None = None,
) -> GenerationResult:
    """
    Generate natural language text from a structured outcome.

    This function generates persuasive negotiation text that:
    - Proposes the given outcome
    - Explains why the rejected offer (if any) isn't acceptable
    - Uses negotiation theory to persuade the opponent
    - Has access to full utility function and negotiation history

    Args:
        outcome: The structured outcome tuple (our counter-offer)
        issues: List of negotiation issues
        context: Full negotiation context (ufun, outcome space, history)
        rejected_outcome: The opponent's offer we're rejecting (optional, overrides context.current_offer)
        my_utility: Our utility for our proposed outcome (optional, computed from context if not provided)
        rejected_utility: Our utility for the rejected outcome (optional, computed from context if not provided)
        settings: Optional LLM settings override

    Returns:
        GenerationResult with the generated text or error information
    """
    if outcome is None:
        return GenerationResult(text="", error="No outcome provided")

    if settings is None:
        settings = chain_settings("text", getattr(context, "models", None))

    # Use rejected_outcome from parameter or context
    actual_rejected = (
        rejected_outcome
        if rejected_outcome is not None
        else (context.current_offer if context else None)
    )

    # Compute utilities from context if not provided
    if context and context.ufun:
        if my_utility is None:
            try:
                my_utility = float(context.ufun(outcome))
            except Exception:
                pass
        if rejected_utility is None and actual_rejected is not None:
            try:
                rejected_utility = float(context.ufun(actual_rejected))
            except Exception:
                pass

    # Build all context for the prompt
    full_context = _build_full_context(context)

    outcome_desc = _format_outcome_description(outcome, issues)
    rejected_desc = (
        _format_outcome_description(actual_rejected, issues)
        if actual_rejected
        else "None"
    )
    utility_context = _format_utility_context(
        outcome, actual_rejected, my_utility, rejected_utility
    )

    # Merge specific fields with full context
    prompt_vars = {
        **full_context,
        "outcome_description": outcome_desc,
        "rejected_outcome_description": rejected_desc,
        "utility_context": utility_context,
    }

    try:
        prompt = settings["generation_prompt"].format(**prompt_vars)
    except KeyError as e:
        # Fallback if prompt doesn't use all variables
        prompt = settings["generation_prompt"].format(
            issues_description=full_context["issues_description"],
            outcome_description=outcome_desc,
            rejected_outcome_description=rejected_desc,
            utility_context=utility_context,
        )

    try:
        response = _call_llm(prompt, settings)
        # Clean up the response
        text = response.strip()
        # Remove quotes if the entire response is quoted
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        return GenerationResult(text=text)
    except Exception as e:
        return GenerationResult(text="", error=str(e))


def is_llm_configured(purpose: str = "text") -> bool:
    """Whether the ``purpose`` model chain has an entry with credentials (no network check)."""
    from hani2 import model_chain

    ch, _src = model_chain.chain_for(purpose)
    for e in ch:
        c, _why = model_chain.connection_of(e)
        if c is not None and __import__("hani2.connections", fromlist=["x"]).has_credentials(c)[0]:
            return True
    return False


@dataclass
class InstructionResult:
    """Result of generating a response from an instruction."""

    text: str | None
    outcome: Outcome | None
    reasoning: str
    error: str | None = None


def generate_from_instruction(
    instruction: str,
    issues: list[Issue],
    context: NegotiationContext | None = None,
    history: list[dict] | None = None,
    output_mode: str = "both",  # "text_only", "outcome_only", "both"
    settings: dict | None = None,
) -> InstructionResult:
    """
    Generate a negotiation response (text and/or outcome) from a natural language instruction.

    Args:
        instruction: Natural language instruction describing what to respond with
        issues: List of negotiation issues
        context: Full negotiation context (ufun, outcome space, history)
        history: Optional list of past negotiation turns (deprecated, use context.history)
        output_mode: What to generate - "text_only", "outcome_only", or "both"
        settings: Optional LLM settings override

    Returns:
        InstructionResult with generated text and/or outcome
    """
    if not instruction or not instruction.strip():
        return InstructionResult(
            text=None,
            outcome=None,
            reasoning="Empty instruction",
            error="No instruction provided",
        )

    if settings is None:
        settings = chain_settings("text", getattr(context, "models", None))

    # Build full context
    full_context = _build_full_context(context)

    # Use history from context if available, otherwise use parameter
    if context and context.history:
        history_str = full_context["negotiation_history"]
    elif history:
        history_lines = []
        for turn in history[-10:]:  # Last 10 turns
            role = turn.get("role", "unknown")
            text = turn.get("text", "")
            outcome = turn.get("outcome", "")
            history_lines.append(
                f"- {role}: {text} {f'[Offer: {outcome}]' if outcome else ''}"
            )
        history_str = "\n".join(history_lines) if history_lines else "No history yet"
    else:
        history_str = "No history yet"

    prompt_template = settings.get("instruction_prompt", "")
    if not prompt_template:
        # Fallback prompt
        prompt_template = """Generate a negotiation response based on this instruction: "{instruction}"
Issues: {issues_description}
History: {history}

Return JSON with: {{"text": "message", "outcome": {{"issue": value}} or null, "reasoning": "explanation"}}"""

    try:
        prompt = prompt_template.format(
            **full_context, history=history_str, instruction=instruction
        )
    except KeyError:
        # Fallback for simpler prompts
        prompt = prompt_template.format(
            issues_description=full_context["issues_description"],
            history=history_str,
            instruction=instruction,
        )

    try:
        response = _call_llm(prompt, settings)
        return _parse_instruction_response(response, issues, output_mode)
    except Exception as e:
        return InstructionResult(
            text=None, outcome=None, reasoning="LLM call failed", error=str(e)
        )


def _number(value: Any) -> float | None:
    """A number from a model's value: 3200, "3200", "$3,200/month"."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group()) if m else None


def _match_issue_value(issue: Issue, value: Any) -> Any:
    """The issue's own option for a value a model wrote, or ``None`` when it has none.

    Discrete issues (numeric or categorical) match exactly, then by text (ignoring case and
    spaces), then by number. Continuous issues take the number, clipped to the issue's range."""
    try:
        options = list(issue.all)
    except Exception:  # noqa: BLE001 - a continuous issue
        options = None
    if options is None:
        x = _number(value)
        if x is None:
            return None
        lo, hi = float(issue.min_value), float(issue.max_value)
        x = min(max(x, lo), hi)
        return round(x) if isinstance(issue.min_value, int) else x
    if value in options:
        return value
    key = " ".join(str(value).split()).lower()
    for o in options:
        if " ".join(str(o).split()).lower() == key:
            return o
    x = _number(value)
    if x is not None:
        for o in options:
            if isinstance(o, (int, float)) and not isinstance(o, bool) and float(o) == x:
                return o
    return None


def _parse_instruction_response(
    response: str, issues: list[Issue], output_mode: str
) -> InstructionResult:
    """Parse the LLM response for instruction-based generation."""
    # Clean up response - remove thinking tags if present (qwen3 models)
    cleaned = response.strip()
    if "<think>" in cleaned:
        # Remove everything between <think> and </think>
        cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL).strip()

    # Try to extract JSON from the response
    try:
        # First try to find JSON with nested braces
        # Look for opening { and find the matching closing }
        json_start = cleaned.find("{")
        if json_start != -1:
            brace_count = 0
            json_end = json_start
            for i, char in enumerate(cleaned[json_start:], json_start):
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            json_str = cleaned[json_start:json_end]
            data = json.loads(json_str)
        else:
            data = json.loads(cleaned)
    except json.JSONDecodeError:
        # If we can't parse JSON, treat the whole response as text
        print(f"DEBUG: Could not parse LLM response as JSON: {cleaned[:500]}")
        return InstructionResult(
            text=cleaned if output_mode != "outcome_only" else None,
            outcome=None,
            reasoning="Could not parse structured response, using raw text",
            error=None,
        )

    text = data.get("text", "")
    reasoning = data.get("reasoning", "")
    outcome_data = data.get("outcome")

    print(
        f"DEBUG: Parsed JSON - text: {text[:100] if text else 'None'}, outcome_data: {outcome_data}, reasoning: {reasoning[:100] if reasoning else 'None'}"
    )

    # Parse outcome if present
    outcome = None
    if outcome_data and output_mode != "text_only":
        outcome_values = []
        all_found = True

        for issue in issues:
            value = outcome_data.get(issue.name)
            if value is None:
                # Try case-insensitive match
                for key, val in outcome_data.items():
                    if key.lower() == issue.name.lower():
                        value = val
                        break

            # Also try partial match (issue name contains key or vice versa)
            if value is None:
                for key, val in outcome_data.items():
                    if (
                        key.lower() in issue.name.lower()
                        or issue.name.lower() in key.lower()
                    ):
                        value = val
                        break

            if value is None:
                print(
                    f"DEBUG: Could not find value for issue '{issue.name}' in outcome_data keys: {list(outcome_data.keys())}"
                )
                all_found = False
                break

            value = _match_issue_value(issue, value)
            if value is None:
                all_found = False
                break

            outcome_values.append(value)

        if all_found and outcome_values:
            outcome = tuple(outcome_values)
            print(f"DEBUG: Successfully parsed outcome: {outcome}")

    # Apply output mode filtering
    final_text = text if output_mode != "outcome_only" else None
    final_outcome = outcome if output_mode != "text_only" else None

    return InstructionResult(
        text=final_text, outcome=final_outcome, reasoning=reasoning
    )


def get_llm_status(purpose: str = "text") -> dict[str, Any]:
    """The ``purpose`` chain's first entry with credentials (no network check), for status lines."""
    from hani2 import connections as conns
    from hani2 import model_chain

    ch, src = model_chain.chain_for(purpose)
    first = None
    for e in ch:
        c, _why = model_chain.connection_of(e)
        if c is None:
            continue
        ok, why = conns.has_credentials(c)
        if first is None or ok:
            first = (e, c, ok, why)
        if ok:
            break
    if first is None:
        return {"configured": False, "provider": "", "model": "", "connection": "", "source": src.id if src else "",
                "reason": "no model chain"}
    e, c, ok, why = first
    return {"configured": ok, "provider": c.provider, "model": e.model, "connection": c.name,
            "source": src.id if src else "", "reason": why,
            # old keys
            "api_key_env": c.api_key_env or c.preset.env, "api_key_set": bool(conns.api_key(c)),
            "ollama_base_url": c.base if c.provider in ("ollama", "ollama_cloud") else ""}


def complete(prompt: str, *, system: str | None = None, session: Any = None, purpose: str = "tools",
             sequence: str = "", **overrides: Any) -> str:
    """Send one prompt to the language model and return its reply as text.

    This is the simplest way for a tool (or any other code) to use the language model: the
    ``tools`` model chain (see :mod:`hani2.model_chain`), pinned for ``session`` when given.
    ``sequence`` names a model sequence to use instead (``small``, ``large``, ``offline`` …; see
    :func:`hani2.model_chain.sequence_chain`).
    ``system`` is put before the prompt as instructions; ``temperature``, ``max_tokens`` and other
    keyword arguments tune this call; ``provider`` and ``model`` (with ``api_key_env``,
    ``api_base``) call that model directly instead of the chain.
    Raises an exception when the model cannot be reached or returns nothing.
    """
    from hani2 import model_chain

    text = f"{system.strip()}\n\n{prompt}" if system else prompt
    if overrides.get("provider") or overrides.get("model"):
        settings = {**load_llm_settings(), **overrides}
        return _call_llm(text, settings).strip()
    models = model_chain.models_of(session)
    return _call_llm(text, chain_settings(purpose, models, sequence, **overrides)).strip()
