"""A negotiation always runs on a normalized scenario: one that is not normalized is
normalized when it starts (a normalized one is used as it is, and ``assume_normalized``
skips the check); the Preferences tools in raw numbers show the original numbers."""

import json
import random

from hani2 import scenario_store as store
from hani2.testing import make_session
from hani2.tools import ufun_views as uv
from hani2.ufun_scale import RAW_ATTR, is_normalized, raw_of


def _env(home, negotiation, tools=None):
    from hani2.config import settings_dir

    settings_dir().mkdir(parents=True, exist_ok=True)
    (settings_dir() / "env.json").write_text(json.dumps({"negotiation": negotiation, "tools": tools or {}}))


RAW = {"simple_scenarios": False, "normalized_scenarios": False}


def _session(**kw):
    random.seed(2)
    return make_session(scenario_type="Grocery", n_steps=6, **kw)


def test_a_raw_scenario_is_normalized_for_the_negotiation(hani2_home, monkeypatch, tmp_path):
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path / "empty"))
    _env(hani2_home, RAW)
    s = _session()
    assert s.ss["scenario_info"].get(store.NORMALIZED_KEY) is False  # generated in points
    assert all(is_normalized(u) for u in s.scenario.ufuns)  # played on 0..1
    h = s.human_ufun
    raw = raw_of(h)
    assert raw is not h and not is_normalized(raw)
    lo, hi = raw.minmax()
    assert abs(raw.reserved_value - (lo + h.reserved_value * (hi - lo))) < 1e-3
    assert 0 <= s.snapshot()["reserved_value"] <= 1


def test_preferences_show_the_original_numbers_in_raw_mode(hani2_home, monkeypatch, tmp_path):
    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path / "empty"))
    _env(hani2_home, RAW, {"preferences_scale": "raw"})
    s = _session()
    raw = raw_of(s.human_ufun)
    summary = uv.preference_summary(s.human_ufun)
    assert "%" not in summary
    texts = json.dumps(uv.render_ufun_view(type("T", (), {"values": {}})(), s.human_ufun))
    assert f"{raw.minmax()[1]:.3g}" in texts  # what the best deal is worth, in points


def test_a_normalized_scenario_is_used_as_it_is(hani2_home):
    random.seed(2)
    sc, _, _ = store.load_scenario("Trade", 0, load_existing=False)
    sc = store.normalize_scenario(sc)
    assert store.normalize_for_play(sc) is sc
    s = make_session(n_steps=6)
    assert not any(hasattr(u, RAW_ATTR) for u in s.scenario.ufuns)


def test_assume_normalized_skips_it(hani2_home, monkeypatch, tmp_path):
    from hani2 import projects

    monkeypatch.setenv("HANI2_SCENARIOS_BASE", str(tmp_path / "empty"))
    projects.create_project("P", defaults={"assume_normalized": True, **RAW})
    projects.create_study("P/a", type="online")
    with projects.use_study("P/a"):
        assert store.assume_normalized() is True
        random.seed(2)
        sc, _, _ = store.load_scenario("Grocery", 0, load_existing=False, simple_mode=False, normalized=False)
        assert store.normalize_for_play(sc) is sc and not all(is_normalized(u) for u in sc.ufuns)
    assert store.assume_normalized() is False
