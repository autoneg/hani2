"""Slow language-model calls never hold the session lock.

The Assistant's ``submit_counter_offer`` may call the model while sending (``auto_extract`` /
``auto_generate``). The participant must be able to edit the draft and see snapshots meanwhile,
and a result computed for a draft that has since changed must not be sent.
"""

import threading

import pytest

from hani2.llm_service import ExtractionResult, GenerationResult
from hani2.testing import make_session


class SlowModel:
    """A fake model call that blocks until the test releases it."""

    def __init__(self, result):
        self.result = result
        self.entered = threading.Event()
        self.release = threading.Event()

    def __call__(self, *args, **kwargs):
        self.entered.set()
        assert self.release.wait(10), "the test never released the model"
        return self.result


def _session(monkeypatch, pref: str, result):
    s = make_session(support_settings={"autonomy": "full"})
    s.admin_prefs[pref] = True
    s.start()
    assert s.wait_for_turn()
    model = SlowModel(result(s))
    import hani2.llm_service as llm

    name = "extract_outcome_from_text" if pref == "auto_extract" else "generate_text_from_outcome"
    monkeypatch.setattr(llm, name, model)
    return s, model


def _extraction(s):
    return ExtractionResult(has_offer=True, outcome=s.human_ufun.best(), confidence=1.0, reasoning="")


def _generation(s):
    return GenerationResult(text="A fair split for both of us.")


def _in_thread(fn):
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("r", fn()), daemon=True)
    t.start()
    return t, out


def _assistant_sends(s, **args):
    return _in_thread(lambda: s.support_agent.dispatcher.execute("submit_counter_offer", args))


@pytest.mark.parametrize("pref,result,args", [
    ("auto_extract", _extraction, {"message": "I want the best deal"}),
    ("auto_generate", _generation, {}),
])
def test_the_interface_stays_responsive_while_the_model_runs(monkeypatch, pref, result, args):
    s, model = _session(monkeypatch, pref, result)
    if pref == "auto_generate":
        s.set_draft_text("")
    n = len(s.history)
    sender, out = _assistant_sends(s, **args)
    assert model.entered.wait(5)
    # the model is still thinking: other actions on the session complete right away
    done = threading.Event()

    def other_actions():
        s.snapshot()
        s.add_chat("You", "still here?")
        s.toast("hello")
        done.set()

    _in_thread(other_actions)
    responsive = done.wait(2)
    model.release.set()
    sender.join(10)
    assert responsive, "a session action blocked while the language model was running"
    assert out["r"]["ok"] and out["r"]["submitted"], out["r"]
    assert s.wait(lambda: len(s.history) > n, 10)


def test_a_draft_changed_during_the_model_call_is_not_sent(monkeypatch):
    s, model = _session(monkeypatch, "auto_extract", _extraction)
    n = len(s.history)
    sender, out = _assistant_sends(s, message="I want the best deal")
    assert model.entered.wait(5)
    # the participant edits the offer while the model reads the message
    t, edit = _in_thread(lambda: s.set_draft_text("wait, let me rethink this"))
    t.join(2)
    assert "r" in edit, "editing the draft blocked while the language model was running"
    model.release.set()
    sender.join(10)
    assert out["r"]["ok"] is False and "changed" in out["r"]["error"], out["r"]
    assert s.is_my_turn() and len(s.history) == n  # nothing went out
    assert s.draft_text == "wait, let me rethink this"  # and the participant's edit stands

