"""Parsing of language-model replies (no model is called)."""

from negmas import make_issue

from hani2.llm_service import _parse_extraction_response

ISSUES = [make_issue((1, 10), "Quantity"), make_issue([100.0, 120.0], "Price")]


def test_extraction_reads_the_nested_outcome():
    reply = 'Sure: {"has_offer": true, "outcome": {"Quantity": 5, "Price": 120.0}, "confidence": 0.9, "reasoning": "r"}'
    r = _parse_extraction_response(reply, ISSUES)
    assert r.has_offer and r.confidence == 0.9
    assert tuple(r.outcome) == (5, 120.0)


def test_extraction_handles_fences_and_thinking():
    reply = '<think>{"x": 1}</think>\n```json\n{"has_offer": true, "outcome": {"quantity": 3, "Price": 100}}\n```'
    r = _parse_extraction_response(reply, ISSUES)
    assert r.has_offer and tuple(r.outcome) == (3, 100.0)


def test_extraction_reports_garbage_as_no_offer():
    r = _parse_extraction_response("no json here", ISSUES)
    assert not r.has_offer and r.error


def test_instruction_outcome_matches_categorical_and_labelled_values():
    """Categorical options ("15 June") and labelled numbers ("$3,200/month") reach the outcome."""
    import json

    from negmas.outcomes import make_issue

    from hani2.llm_service import _parse_instruction_response

    issues = [make_issue([2800, 3000, 3200], "Rent"), make_issue(["1 May", "15 June"], "Move-in date"),
              make_issue((0.0, 10.0), "Months")]
    resp = json.dumps({"text": "ok", "outcome": {"Rent": "$3,200/month", "move-in date": "15  june", "Months": 12}})
    assert _parse_instruction_response(resp, issues, "both").outcome == (3200, "15 June", 10.0)
    bad = json.dumps({"text": "ok", "outcome": {"Rent": 3100, "Move-in date": "1 May", "Months": 3}})
    assert _parse_instruction_response(bad, issues, "both").outcome is None  # 3100 is not an option
