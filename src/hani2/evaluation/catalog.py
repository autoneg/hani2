"""The catalogue of what HANI2 measures: every metric column in a **group** of similar
measures, which columns and questionnaires are **validated**, and what each predefined
questionnaire measures and where it comes from.

One source of truth for the docs page (``docs/guide/metric-catalog.md``, written by
``scripts/make_metric_catalog.py``), the admin API (``GET /api/admin/criteria`` carries
``group`` and ``validated`` per criterion and the ordered ``groups``; the questionnaire
library carries ``validated`` and ``url``) and the pickers of the app.

**Validated** means: a test computes the value on a small hand-worked example (known
offers, utilities, timings, answers) and checks it against a value derived by hand from
the definition, or, for a questionnaire, checks its items, anchors, reversed items and
scale scoring against the source instrument. A range check does not count.
``tests/test_metric_catalog.py`` fails when a validated entry names a test that does not
exist or does not mention it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

# --------------------------------------------------------------------------- #
# Groups                                                                       #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    description: str


#: the groups, in the order the docs and the pickers show them
GROUPS: tuple[Group, ...] = (
    Group("outcome", "Outcome and utility",
          "Whether there was a deal and what it was worth to each side: agreement, utilities, advantages, targets."),
    Group("efficiency", "Efficiency and welfare",
          "How much value the deal created and how close it is to the best deals: welfare, Pareto distance and optimality."),
    Group("fairness", "Fairness",
          "How evenly the gains were shared: distances to the Nash and Kalai–Smorodinsky solutions, the Nash product, the "
          "fairness gap."),
    Group("rules", "Task success and rules",
          "Whether the task was done within its rules: task success, constraints, deals below the reservation value, "
          "failures."),
    Group("process", "Process and timing",
          "How the negotiation went in time: offers, steps, messages, durations, decision times."),
    Group("behaviour", "Negotiation behaviour",
          "What kind of moves each side made: concessions, nice or selfish moves, theory-of-mind indicators."),
    Group("assistant", "Assistant use",
          "How the human used the Assistant and how the Assistant behaved: messages, suggestions and their adoption, "
          "who acted, response times, function calls, engagement flags."),
    Group("activity", "Attention and activity",
          "What the participant did with mouse, keyboard and window: clicks, keys, scrolls, idle and away time."),
    Group("subjective", "Questionnaires (subjective)",
          "The participant's own answers: questionnaire scales and items, after each negotiation or after the session."),
    Group("judge", "Language-model judgements",
          "Ratings and checks by a language-model judge: the Assistant, the opponent and the human, natural-language "
          "assertions, error review."),
    Group("scores", "Combined scores",
          "Scores that combine criteria into one number in [0, 1]: the built-in HAN and HI scores and the project's own."),
    Group("cost", "LLM usage and cost",
          "Language-model calls, tokens, cost, latency and errors of the Assistant and the opponent."),
    Group("simulation", "Simulated participants",
          "Measures of games played by a simulated participant (persona): goal met, valid trial, conformance."),
    Group("context", "Scenario and condition",
          "What describes the game rather than measures it: scenario statistics, difficulty factors, the ablation "
          "condition, practice."),
)
GROUP_IDS = tuple(g.id for g in GROUPS)
_GROUP = {g.id: g for g in GROUPS}
#: the group of columns of metrics registered outside HANI2 (plugins) that name none
FALLBACK_GROUP = "context"

#: the group of every column of a metric (the default for its columns)
METRIC_GROUP: dict[str, str] = {
    "outcome": "outcome",
    "optimality": "efficiency",
    "scenario_stats": "context",
    "length": "process",
    "timing": "process",
    "llm_usage": "cost",
    "dynamics": "behaviour",
    "activity": "activity",
    "system_use": "assistant",
    "engagement_flags": "assistant",
    "assistant_interaction": "assistant",
    "simulation": "simulation",
    "dual_control": "rules",
    "judge_assistant": "judge",
    "judge_opponent": "judge",
    "judge_human": "judge",
    "nl_assertions": "judge",
    "error_review": "judge",
    "questionnaire": "subjective",
    "factors": "context",
    "rule_checks": "rules",
    "task_judge": "rules",
    "task_success": "rules",
    "scores": "scores",
    "condition": "context",
}

#: columns that belong elsewhere than their metric's group
COLUMN_GROUP: dict[str, str] = {
    "welfare": "efficiency",
    "practice": "context",
    "nash_distance": "fairness",
    "kalai_distance": "fairness",
    "nash_product_ratio": "fairness",
    "fairness_gap": "fairness",
    "target_attainment": "outcome",
    "reached_target": "outcome",
    "constraint_violated": "rules",
    "human_offer_pareto_distance": "behaviour",
    "questionnaire_seconds": "process",
}

#: the group by criterion source, for criteria that are not metric columns
SOURCE_GROUP = {"questionnaire": "subjective", "subjective": "subjective", "score": "scores", "soft": "judge"}


def _owner() -> dict[str, str]:
    from hani2.evaluation.base import REGISTRY

    out: dict[str, str] = {}
    for m in REGISTRY.values():
        for c in [*m.columns, *getattr(m, "patterns", [])]:
            out.setdefault(c.name, m.name)
    return out


def group_of(cid: str, metric: str = "", source: str = "") -> str:
    """The group of a criterion or column: its own entry, else its metric's, else by its id
    (``q_*``, ``scale_*``, ``post_*`` are questionnaire answers) or source."""
    if cid in COLUMN_GROUP:
        return COLUMN_GROUP[cid]
    metric = metric or _owner().get(cid, "")
    if metric in METRIC_GROUP:
        return METRIC_GROUP[metric]
    bare = cid[5:] if cid.startswith("post_") else cid
    if bare.startswith(("q_", "scale_")):
        return "subjective"
    return SOURCE_GROUP.get(source, FALLBACK_GROUP)


def group_info(gid: str) -> Group:
    return _GROUP.get(gid) or _GROUP[FALLBACK_GROUP]


def groups_payload() -> list[dict[str, str]]:
    """The ordered groups as the API sends them."""
    return [{"id": g.id, "title": g.title, "description": g.description} for g in GROUPS]


def ungrouped_columns() -> list[str]:
    """Built-in metric columns whose metric has no group (``tests/test_metric_catalog.py`` keeps it empty)."""
    from hani2.evaluation.base import REGISTRY

    return [f"{m.name}.{c.name}" for m in REGISTRY.values() for c in [*m.columns, *getattr(m, "patterns", [])]
            if m.name not in METRIC_GROUP and c.name not in COLUMN_GROUP]


# --------------------------------------------------------------------------- #
# Validation                                                                   #
# --------------------------------------------------------------------------- #
VALIDATED_TOOLTIP = "validated against a hand-computed example"
VALIDATED_SOURCE_TOOLTIP = "validated against the source instrument"
_T = "tests/validation/"

#: the test that validates each column on a hand-worked example (``file::function``); the
#: function's source names the column. Columns not listed are not validated (see NOT_VALIDATED).
VALIDATED: dict[str, str] = {}


def _validated(test: str, *columns: str) -> None:
    for c in columns:
        VALIDATED.setdefault(c, test)


_O, _P, _A = _T + "test_validate_outcome.py::", _T + "test_validate_process.py::", _T + "test_validate_assistant.py::"
_S, _SC = _T + "test_validate_subjective.py::", _T + "test_validate_scores.py::"
_validated(_T + "test_validate_questionnaires.py::test_felt_heard_single_item_scale", "scale_felt_heard",
           "scale_felt_heard_norm")
_validated(_O + "test_outcome_docs_example_agreement_on_F", "agreement", "human_utility", "opponent_utility",
           "human_advantage", "opponent_advantage", "welfare", "practice")
_validated(_O + "test_optimality_docs_example_agreement_on_F", "pareto_distance", "pareto_optimal", "nash_distance",
           "kalai_distance", "welfare_optimality", "nash_product_ratio", "fairness_gap")
_validated(_O + "test_scenario_stats_docs_example", "n_outcomes", "zopa_fraction", "pareto_size", "opposition")
_validated(_O + "test_factors_target_attainment_below_target_and_constraint_hit", "target_attainment",
           "reached_target", "constraint_violated")
_validated(_O + "test_rule_checks_human_accepts_below_reservation", "irrational_accept", "opponent_irrational_accept",
           "opponent_failed", "infrastructure_failure")
_validated(_O + "test_rule_checks_irrational_suggestions_counts_assistant_drafts", "irrational_suggestions")
_validated(_O + "test_task_success_all_components_hold", "task_success", "task_targets_met", "task_rules_ok",
           "task_components")
_validated(_O + "test_condition_team_human_acts_only", "oracle", "opponent_info_tools", "autopilot_share")
_validated(_P + "test_length_trace_without_result_fields", "n_offers", "n_human_offers", "n_opponent_offers",
           "n_steps", "relative_time", "negotiation_seconds", "session_seconds", "n_text_messages")
_validated(_P + "test_llm_usage_mixed_roles", "llm_calls", "llm_tokens", "llm_cost_usd", "llm_latency_mean",
           "llm_error_rate", "support_llm_calls", "support_tokens", "opponent_llm_calls", "opponent_tokens")
_validated(_P + "test_dynamics_documented_example", *(f"{s}_move_{t}" for s in ("human", "opponent") for t in
           ("silent", "nice", "fortunate", "unfortunate", "concession", "selfish")), "human_concession",
           "human_offer_pareto_distance", "tom_reflect_index", "tom_other_trend")
_validated(_P + "test_dynamics_suggestions", *(f"suggested_move_{t}" for t in
           ("silent", "nice", "fortunate", "unfortunate", "concession", "selfish")))
_validated(_P + "test_timing_screen_states", "decision_time_mean", "decision_time_median", "decision_time_min",
           "time_to_first_action", "load_to_start_seconds", "questionnaire_seconds")
_validated(_P + "test_activity_documented_example", "n_clicks", "n_keys", "mouse_distance", "n_scrolls",
           "idle_fraction", "hidden_seconds", "n_blur", "has_telemetry")
_validated(_A + "test_system_use_documented_example", "n_user_messages", "n_assistant_messages", "n_suggestions",
           "suggestion_adoption", "suggestions_ignored", "drafts_explored", "drafts_per_action", "n_tool_interactions",
           "n_tools_used", "n_tab_changes", "actions_by_human", "actions_by_agent", "actions_by_autopilot")
_validated(_A + "test_engagement_flags_click_through", "never_acted", "click_through", "always_follows",
           "never_follows")
_validated(_A + "test_assistant_interaction_documented_example", "assistant_response_seconds", "unanswered_messages",
           "unsolicited_messages", "max_assistant_streak", "fn_calls", "fn_success_rate")
_validated(_A + "test_simulation_stubborn_documented_example", "sim_goal_met", "sim_valid", "sim_turns",
           "sim_take_rate", "sim_violations", "sim_stopped")
_validated(_A + "test_dual_control_both_broken", "information_split", "constraints_met", "n_constraint_violations")
_validated(_S + "test_questionnaire_bundled_form_scales", "questionnaire_answered",
           *(f"scale_{k}{n}" for k in ("satisfaction", "appreciation", "ueq_pragmatic", "ueq_hedonic", "tam_usefulness",
                                       "intention_to_use", "opponent_kindness", "opponent_intelligence",
                                       "opponent_humanlike", "relationship") for n in ("", "_norm")))
_validated(_S + "test_questionnaire_mixed_ranges_and_types", "scale_<name>", "scale_<name>_norm", "q_<id>")
_validated(_SC + "test_scores_han_outcome", "han_outcome", "han_outcome_coverage")
_validated(_SC + "test_scores_han_interaction_full_row", "han_interaction", "han_interaction_coverage")
_validated(_SC + "test_scores_hi_outcome_and_utility", "hi_outcome", "hi_outcome_coverage", "utility",
           "utility_coverage")
_validated(_SC + "test_scores_hi_assistant_full_row", "hi_assistant", "hi_assistant_coverage")
_validated(_SC + "test_scores_hi_team_full_row", "hi_team", "hi_team_coverage")
_validated(_SC + "test_scores_hi_interaction_full_row", "hi_interaction", "hi_interaction_coverage")
#: the rules of user-defined scores and the normalisers, validated on hand-computed examples
SCORE_RULES_VALIDATED_BY = _SC + "test_defined_score_three_components_catalogue_defaults"


#: warnings about the source of a measure or questionnaire whose scoring may be validated but whose items
#: are not checked against the published instrument (shown as warnings in the docs and, for questionnaires,
#: on the admin Study forms page; never to participants)
TAM_WARNING = ("The TAM items have not been checked against the published instrument (Davis, 1989): no readable "
               "copy of the item sheet was found. The scoring of the scale is validated; the wording of its items "
               "is not, so results may not be comparable with published TAM scores.")
SOURCE_WARNINGS: dict[str, str] = {"scale_tam_usefulness": TAM_WARNING, "scale_tam_usefulness_norm": TAM_WARNING}
QUESTIONNAIRE_WARNINGS: dict[str, str] = {
    "tam_usefulness": TAM_WARNING, "tam_usefulness_short": TAM_WARNING, "tam_ease": TAM_WARNING,
    "evaluation": "Its `tam_usefulness` scale uses TAM items. " + TAM_WARNING,
}


#: why a column is not validated (shown in the docs)
NOT_VALIDATED: dict[str, str] = {}
_JUDGED = ("The rating is a language-model judgement, which no hand-computed example can check; only the parsing, "
           "clamping and aggregation of the judge's answer are tested ({test}).")
for _metric, _test in (("judge_assistant", "test_judge_assistant_rating_parsing_and_clamping"),
                       ("judge_opponent", "test_judge_opponent_rating_parsing_and_clamping"),
                       ("judge_human", "test_judge_human_rating_parsing_and_clamping"),
                       ("nl_assertions", "test_nl_assertions_share_of_applicable"),
                       ("error_review", "test_error_review_counts_by_source_and_severity"),
                       ("task_judge", "test_task_judge_shares")):
    NOT_VALIDATED[_metric] = _JUDGED.format(test=f"{_T}test_validate_subjective.py::{_test}")


def not_validated_reason(cid: str, metric: str = "") -> str:
    """Why a column is not validated (empty when it is, or when there is nothing to say)."""
    if validation_of(cid):
        return ""
    return NOT_VALIDATED.get(cid) or NOT_VALIDATED.get(metric or _owner().get(cid, ""), "")


def validation_of(cid: str) -> str:
    """The validating test of a column or criterion, or ``""``. Questionnaire answers of a
    project's own forms (``q_*``, ``scale_*``, ``post_*``) are computed by the validated rules of
    the ``questionnaire`` metric (the ``q_<id>`` and ``scale_<name>`` patterns)."""
    if cid in VALIDATED:
        return VALIDATED[cid]
    bare = cid[5:] if cid.startswith("post_") else cid
    if bare.startswith("scale_"):
        return VALIDATED.get("scale_<name>_norm" if bare.endswith("_norm") else "scale_<name>", "")
    if bare.startswith("q_"):
        return VALIDATED.get("q_<id>", "")
    return ""


# --------------------------------------------------------------------------- #
# Questionnaires                                                               #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class QuestionnaireInfo:
    measures: str  #: what it measures, in one sentence
    citation: str = ""  #: the source, in words (empty for HANI2's own items)
    url: str = ""  #: a link to the source (only where certain)
    validated_by: str = ""  #: the test that checks it against the source instrument
    note: str = ""  #: adaptations, what was checked, or why it is not validated
    competition: str = ""  #: the competition that asked these questions (its own section in the docs)


_Q = _T + "test_validate_questionnaires.py::"

#: what each bundled questionnaire (library set or named form) measures, where it comes from, and its validation
QUESTIONNAIRES: dict[str, QuestionnaireInfo] = {
    "subjective_value": QuestionnaireInfo(
        "Subjective value of a negotiation: feelings about the instrumental outcome, the self, the process and the "
        "relationship.",
        "Curhan, Elfenbein & Xu (2006). What do people value when they negotiate? Mapping the domain of subjective value "
        "in negotiation. Journal of Personality and Social Psychology 91, 493–512.",
        "https://www.subjectivevalue.com/", _Q + "test_svi_matches_source",
        "Checked against the authors' item document: the 16 items, their 1/7 anchors, items 3 and 5 reversed, four "
        "4-item subscales averaged. Worded for one opponent (the inventory says counterpart(s)); the midpoint anchors "
        "are not shown. The inventory's optional Global score (the mean of the four subscales) and Rapport score "
        "(Process and Relationship) are not columns: define them as scores with equal weights."),
    "sus": QuestionnaireInfo(
        "Perceived usability of the negotiation interface (0–100).",
        "Brooke (1996). SUS: a “quick and dirty” usability scale. In Jordan et al. (eds.), Usability Evaluation in "
        "Industry. Taylor & Francis.", "", _Q + "test_sus_matches_source",
        "Checked: the 10 items, the 5-point agreement anchors, even items reversed, and that the standard score "
        "2.5 × Σ(contributions) equals 100 × scale_sus_norm. “System” is kept as in the original."),
    "ueq_s": QuestionnaireInfo(
        "User experience of the Assistant: pragmatic quality (supportive, easy, efficient, clear) and hedonic quality "
        "(exciting, interesting, inventive, leading edge).",
        "Schrepp, Hinderks & Thomaschewski (2017). Design and evaluation of a short version of the User Experience "
        "Questionnaire (UEQ-S). IJIMAI 4(6), 103–108.", "https://doi.org/10.9781/ijimai.2017.09.001",
        _Q + "test_ueq_s_matches_source",
        "Checked against the UEQ-S item sheet and the UEQ handbook: the 8 items in order, negative pole left, items 1–4 "
        "pragmatic and 5–8 hedonic, each scale the mean of its items. HANI2 scores 1–7; subtract 4 for the "
        "handbook's −3…+3."),
    "ueq_eval": QuestionnaireInfo(
        "Usability of the Assistant with eight items of the full UEQ, as two scales (ueq_pragmatic, ueq_hedonic).",
        "Laugwitz, Held & Schrepp (2008). Construction and evaluation of a user experience questionnaire. USAB 2008, "
        "LNCS 5298, 63–76.", "https://www.ueq-online.org/", "",
        "Not validated as a UEQ scale: the items are UEQ items 2, 5, 11, 12, 13, 20, 21 and 22 and the positive-left "
        "ones are reversed (tested; the handbook confirms the poles of item 21, while the positive-left order of items "
        "5 and 12 could not be checked against a copy of the full questionnaire). The UEQ has six scales, not these "
        "two: ueq_hedonic "
        "mixes a Stimulation item (valuable) with an Attractiveness item (good), and the UEQ handbook counts "
        "Attractiveness as neither pragmatic nor hedonic."),
    "tam_usefulness": QuestionnaireInfo(
        "Perceived usefulness of the Assistant (Technology Acceptance Model).",
        "Davis (1989). Perceived usefulness, perceived ease of use, and user acceptance of information technology. MIS "
        "Quarterly 13(3), 319–340.", "https://doi.org/10.2307/249008", "",
        "Not validated: not yet checked against the published items (no readable copy of the item sheet was found). "
        "The six items follow Davis's usefulness items, "
        "reworded for a negotiation assistant, with agree–disagree anchors."),
    "tam_usefulness_short": QuestionnaireInfo(
        "Perceived usefulness of the Assistant, two items (Technology Acceptance Model).",
        "Davis (1989). Perceived usefulness, perceived ease of use, and user acceptance of information technology. MIS "
        "Quarterly 13(3), 319–340.", "https://doi.org/10.2307/249008", "",
        "Not validated: a two-item selection of the usefulness items, reworded; not yet checked against the "
        "published items (no readable copy of the item sheet was found)."),
    "tam_ease": QuestionnaireInfo(
        "Perceived ease of use of the Assistant (Technology Acceptance Model).",
        "Davis (1989). Perceived usefulness, perceived ease of use, and user acceptance of information technology. MIS "
        "Quarterly 13(3), 319–340.", "https://doi.org/10.2307/249008", "",
        "Not validated: not yet checked against the published items (no readable copy of the item sheet was found). "
        "The six items follow Davis's ease-of-use "
        "items, reworded for a negotiation assistant, with agree–disagree anchors."),
    "trust_in_automation": QuestionnaireInfo(
        "Trust in the Assistant (Checklist for Trust between People and Automation).",
        "Jian, Bisantz & Drury (2000). Foundations for an empirically determined scale of trust in automated systems. "
        "International Journal of Cognitive Ergonomics 4(1), 53–71.", "https://doi.org/10.1207/S15327566IJCE0401_04",
        _Q + "test_trust_in_automation_matches_source",
        "Checked against the checklist's 12 items as reproduced in McGrath et al. (2025, Frontiers in Artificial "
        "Intelligence, Table 1): wording, 1 = not at all … 7 = extremely, items 1–5 reverse scored, the trust score the "
        "mean of the 12. Adapted: “the system” is worded as “the assistant”."),
    "nasa_tlx": QuestionnaireInfo(
        "Workload of the task: mental, physical and temporal demand, performance, effort and frustration (raw TLX; "
        "lower is better).",
        "Hart & Staveland (1988). Development of NASA-TLX (Task Load Index): results of empirical and theoretical "
        "research. In Hancock & Meshkati (eds.), Human Mental Workload. Advances in Psychology 52, 139–183.",
        "https://doi.org/10.1016/S0166-4115%2808%2962386-9", _Q + "test_nasa_tlx_matches_source",
        "Checked against the NASA-TLX rating sheet: the six questions and their anchors (Very low … Very high; "
        "Performance from Perfect to Failure, so every item runs towards more workload), scored as the raw TLX (the "
        "unweighted mean of the six, without the pairwise weighting) and lower-is-better. Adapted: 7 answer points "
        "instead of the sheet's 21 gradations, so values are not on the 0–100 scale (100 × the _norm column is "
        "comparable)."),
    "attention_check": QuestionnaireInfo(
        "Whether the participant reads the questions (an instructed-response item).", "", "", "",
        "Own item; there is no source instrument."),
    "ai_experience": QuestionnaireInfo("Familiarity with AI assistants and expected reliance on one.", "", "", "",
                                       "Own items; there is no source instrument."),
    "assistant_reliance": QuestionnaireInfo(
        "How much the participant used, followed and trusted the Assistant, and who gets the credit.", "", "", "",
        "Own items; there is no source instrument."),
    "demographics": QuestionnaireInfo("Age range, gender, education and English level.", "", "", "",
                                      "Common demographic items; there is no source instrument."),
    "intention_to_use": QuestionnaireInfo("Intention to use the Assistant again and feeling heard by it.", "", "", "",
                                          "Own items; there is no source instrument."),
    "negotiation_experience": QuestionnaireInfo(
        "How often the participant negotiates and whether they had training (the participant type).", "", "", "",
        "Own items; there is no source instrument."),
    "opponent_perception": QuestionnaireInfo(
        "How kind, intelligent and human-like the opponent seemed, and the relationship with it.", "", "", "",
        "Own items (the relationship items are inspired by the Subjective Value Inventory); there is no source "
        "instrument."),
    "outcome_appreciation": QuestionnaireInfo("Satisfaction with the outcome and enjoyment of the negotiation.", "",
                                              "", "", "Own items; there is no source instrument."),
    "session_feedback": QuestionnaireInfo(
        "The whole session: how the Assistants differed and helped, the interface, technical problems, comments.", "",
        "", "", "Own items; there is no source instrument."),
    # the questionnaires of human-agent negotiation competitions, as asked
    "HAN2026-PreSession": QuestionnaireInfo(
        "HAN 2026, once before the first session: negotiation experience, familiarity with AI, own skill and the "
        "skill expected of the opponents.",
        "Questionnaires of the HAN 2026 human-agent negotiation competition.", "", "", "Not validated: the questions as asked in HAN 2026 (from the competition's form files), not a validated instrument; typos are kept as asked.", "HAN 2026"),
    "HAN2026-PostNegotiation": QuestionnaireInfo(
        "HAN 2026, after each negotiation: the opponent's strategy, intelligence and skill, employability, "
        "engagement, its messages, time pressure and satisfaction with the outcome.",
        "Questionnaires of the HAN 2026 human-agent negotiation competition.", "", "", "Not validated: the questions as asked in HAN 2026 (from the competition's form files), not a validated instrument; typos are kept as asked.", "HAN 2026"),
    "HAN2026-PostSession": QuestionnaireInfo(
        "HAN 2026, after each session: ease of use, engagement and the usefulness of each interface tool.",
        "Questionnaires of the HAN 2026 human-agent negotiation competition.", "", "", "Not validated: the questions as asked in HAN 2026 (from the competition's form files), not a validated instrument; typos are kept as asked.", "HAN 2026"),
    "HAN2025-PreStudy": QuestionnaireInfo(
        "HAN 2025, once before any negotiation: background, expertise and expectations about the system and AI "
        "negotiators.",
        "Human-Agent Negotiation League Pre-study Questionnaire (HAN 2025).", "https://forms.gle/c4tNxYof1Gm7ezmC7", "",
        "Not validated: the questions of the competition's Google Form as asked, not a validated instrument; converted to HANI2 question types (see the description).", "HAN 2025"),
    "HAN2025-PostSession": QuestionnaireInfo(
        "HAN 2025, after every session: enjoyment, ease, the opponent's human-likeness, intelligence, speed and "
        "predictability, support and expectations about AI negotiators.",
        "Human-Agent Negotiation League Post-session Questionnaire (HAN 2025).", "https://forms.gle/qT8VtQYrV5RuodML6",
        "", "Not validated: the questions of the competition's Google Form as asked, not a validated instrument; converted to HANI2 question types (see the description).", "HAN 2025"),
    "HAN2025-PostStudy": QuestionnaireInfo(
        "HAN 2025, once after the whole competition: the post-session questions, understanding of the scenario, "
        "comments and strategy.",
        "Human-Agent Negotiation League Post-study Questionnaire (HAN 2025).", "https://forms.gle/HEmb2CpruFD8aUvt8",
        "", "Not validated: the questions of the competition's Google Form as asked, not a validated instrument; converted to HANI2 question types (see the description).", "HAN 2025"),
    "ANAC-HAL2018-PostNegotiation": QuestionnaireInfo(
        "ANAC 2018 Human-Agent League, after each negotiation: likeability of the agent (satisfaction with the "
        "agreement, liking the opponent, would negotiate again).",
        "Mell, Gratch, Aydoğan, Baarslag & Jonker (2019). The likeability-success tradeoff: results of the 2nd annual "
        "human-agent automated negotiating agents competition. ACII 2019.", "https://doi.org/10.1109/ACII.2019.8925437",
        "", "Not validated: the questions as reported in the competition's results paper, with its 7-point answers; the paper gives no anchor labels. The three items form the paper's likeability score (hal_likeability).", "ANAC 2018"),
    "ANAC-HAL2017-PostNegotiation": QuestionnaireInfo(
        "ANAC 2017 Human-Agent League, after the negotiation: likeability of the agent (satisfaction with the "
        "agreement, liking the opponent, would negotiate again).",
        "Mell, Gratch, Baarslag, Aydoğan & Jonker (2018). Results of the first annual human-agent league of the "
        "automated negotiating agents competition. IVA '18, 23–28.", "https://doi.org/10.1145/3267851.3267907", "",
        "Not validated: the questions as reported in the competition's results paper, with its 7-point answers; the paper gives no anchor labels. The three items form the paper's likeability score (hal_likeability).", "ANAC 2017"),
    # the bundled named forms (``HANI2_PER_NEG_YAML=evaluation``, ``"pre_questionnaire": "expertise"``)
    "evaluation": QuestionnaireInfo(
        "The evaluation questionnaire after each negotiation: satisfaction, enjoyment, UEQ items, TAM usefulness, "
        "intention to use, feeling heard, and the view of the opponent.", "", "", "",
        "A combination of own items and the ueq_eval and tam_usefulness_short selections (see those)."),
    "expertise": QuestionnaireInfo("Negotiation experience before the first negotiation (the participant type).", "",
                                   "", "", "Own items; there is no source instrument."),
    "per_negotiation": QuestionnaireInfo("A minimal example form: satisfaction with the outcome and the opponent's "
                                         "cooperativeness.", "", "", "", "Own items; there is no source instrument."),
}


def questionnaire_info(qid: str) -> QuestionnaireInfo | None:
    return QUESTIONNAIRES.get(qid)


def questionnaire_payload(qid: str) -> dict[str, Any]:
    """What the questionnaire library API adds to a set: ``measures``, ``citation``, ``url``,
    ``validated``, ``validated_by``, ``validation_note`` and ``warning`` (a source warning from
    :data:`QUESTIONNAIRE_WARNINGS`, or ``""``; empty for sets HANI2 does not know). Admin-only: the
    participant's form never carries any of these."""
    info = QUESTIONNAIRES.get(qid)
    if info is None:
        return {"validated": False, "warning": ""}
    return {"measures": info.measures, "citation": info.citation, "url": info.url,
            "validated": bool(info.validated_by), "validated_by": info.validated_by, "validation_note": info.note,
            "warning": questionnaire_warning(qid)}


def questionnaire_warning(qid: str) -> str:
    """The source warning of a bundled questionnaire (plain text, for the app), or ``""``."""
    return QUESTIONNAIRE_WARNINGS.get(qid, "").replace("`", "")


def form_warnings(question_ids: Iterable[str], sets: dict[str, dict]) -> list[dict[str, str]]:
    """The source warnings of the bundled library sets (``sets``: :func:`hani2.questionnaires.library`) whose
    questions appear in a form with these question ids: ``[{"set", "title", "warning"}]``. Sets sharing
    questions (``tam_usefulness_short`` is two of ``tam_usefulness``'s items) are told apart: a set is left
    out when another one matches more of the form, or the same questions as a larger share of itself."""
    ids = set(question_ids)
    hits: dict[str, tuple[set, float, dict]] = {}
    for sid, s in sets.items():
        w = questionnaire_warning(sid) if s.get("source") == "bundled" else ""
        own = {q.get("id") for q in s.get("questions") or []}
        if w and ids & own:
            hits[sid] = (ids & own, len(ids & own) / len(own), {"set": sid, "title": str(s.get("title") or sid),
                                                                "warning": w})

    def beaten(a: str) -> bool:
        ma, fa, _ = hits[a]
        return any(b != a and (ma < mb or (ma == mb and fb > fa)) for b, (mb, fb, _) in hits.items())

    return [hits[k][2] for k in hits if not beaten(k)]


def validation_entries() -> Iterable[tuple[str, str]]:
    """Every (entry, test) pair the registry claims: ``tests/test_metric_catalog.py`` checks each."""
    yield from VALIDATED.items()
    for k, q in QUESTIONNAIRES.items():
        if q.validated_by:
            yield k, q.validated_by
