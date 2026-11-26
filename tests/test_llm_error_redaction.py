"""Language-model error text never reaches the browser raw.

Provider errors can echo API keys, Bearer tokens or internal URLs. Participants see a generic
message, admins a redacted one, and the full text goes only to the server log.
"""

import hani2.llm_service as llm
from hani2 import connections as conns
from hani2.testing import make_session

KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWx1234"
RAW = f"AuthenticationError: Incorrect API key provided: {KEY} (Authorization: Bearer tok_abcdefghijklmnop)"


def _boom(*args, **kwargs):
    raise RuntimeError(RAW)


def test_llm_error_generic_for_participants_redacted_for_admins(capsys):
    short = conns.llm_error(RuntimeError(RAW), admin=False)
    assert short.startswith(conns.LLM_ERROR_MESSAGE) and "AuthenticationError" in short  # a summary
    assert KEY not in short and "tok_abcdefghijklmnop" not in short
    shown = conns.llm_error(RuntimeError(RAW), admin=True)
    assert KEY not in shown and "tok_abcdefghijklmnop" not in shown
    assert "AuthenticationError" in shown
    assert KEY in capsys.readouterr().err  # the full text is logged server-side


def test_llm_error_masks_stored_secrets(monkeypatch):
    stored = "my-internal-secret-value-42"
    monkeypatch.setattr(conns, "secret_values", lambda: [stored])
    assert stored not in conns.llm_error(f"failed with {stored}", admin=True)


def _extract_error(monkeypatch, is_admin):
    monkeypatch.setattr(llm, "_call_llm", _boom)
    s = make_session(is_admin=is_admin)
    s.draft_text = "I offer everything"
    r = s.extract_offer_from_text()
    assert not r["ok"]
    return r["error"]


def test_extraction_failure_is_generic_for_participants(monkeypatch):
    err = _extract_error(monkeypatch, False)
    assert err.startswith(conns.LLM_ERROR_MESSAGE) and KEY not in err


def test_extraction_failure_is_redacted_for_admins(monkeypatch):
    err = _extract_error(monkeypatch, True)
    assert KEY not in err and "Incorrect API key" in err


def _assistant_error(monkeypatch, is_admin):
    s = make_session(is_admin=is_admin)
    a = s.support_agent
    posted: list[str] = []
    monkeypatch.setattr(a, "post", lambda text, user=None: posted.append(str(text)))
    monkeypatch.setattr(a, "_harness_turn", lambda *args, **kw: False)
    monkeypatch.setattr(a, "_complete", _boom)
    a._run_turn(user_text="help me")
    assert posted
    return posted[-1]


def test_assistant_turn_failure_is_generic_for_participants(monkeypatch):
    msg = _assistant_error(monkeypatch, False)
    assert conns.LLM_ERROR_MESSAGE in msg and KEY not in msg


def test_assistant_turn_failure_is_redacted_for_admins(monkeypatch):
    msg = _assistant_error(monkeypatch, True)
    assert KEY not in msg and "Incorrect API key" in msg


def _instruction_tool_status(monkeypatch, is_admin):
    from hani2.tools.builtin import ResponseGeneratorTool

    monkeypatch.setattr(llm, "_call_llm", _boom)
    s = make_session(is_admin=is_admin)
    s.support_agent.user_enabled = False  # the tool's own prompt (the Assistant's is below)
    tool = ResponseGeneratorTool(s.ss)
    tool.values["instruction"] = "ask for more"
    tool._generate()
    return tool.status


def _assistant_suggestion_status(monkeypatch, is_admin):
    from types import SimpleNamespace

    from hani2.tools.builtin import ResponseGeneratorTool

    s = make_session(is_admin=is_admin)
    a = s.support_agent
    monkeypatch.setattr(a, "model", lambda: SimpleNamespace(ok=True, is_harness=False))
    monkeypatch.setattr(a, "_complete", _boom)
    tool = ResponseGeneratorTool(s.ss)
    tool.values["instruction"] = "ask for more"
    tool._generate()
    return tool.status


def test_assistant_suggestion_failure_is_generic_for_participants(monkeypatch):
    status = _assistant_suggestion_status(monkeypatch, False)
    assert status.startswith("Error: ") and conns.LLM_ERROR_MESSAGE.split(".")[0] in status and KEY not in status


def test_assistant_suggestion_failure_is_redacted_for_admins(monkeypatch):
    status = _assistant_suggestion_status(monkeypatch, True)
    assert KEY not in status and "Incorrect API key" in status


def test_instruction_tool_failure_is_generic_for_participants(monkeypatch):
    status = _instruction_tool_status(monkeypatch, False)
    assert status.startswith(f"Error: {conns.LLM_ERROR_MESSAGE}") and KEY not in status


def test_instruction_tool_failure_is_redacted_for_admins(monkeypatch):
    status = _instruction_tool_status(monkeypatch, True)
    assert KEY not in status and "Incorrect API key" in status


def test_error_summary_is_short_and_drops_urls():
    long = "APIConnectionError: could not reach https://internal.example:8443/v1/chat?key=abc " + "x" * 300
    s = conns.error_summary(long + "\nTraceback line two")
    assert len(s) <= 120 and "internal.example" not in s and "line two" not in s and s.startswith("APIConnectionError")
