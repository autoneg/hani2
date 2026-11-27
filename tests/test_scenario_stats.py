"""Scenario statistics (hani2.scenario_stats): computed in a child process, cached next to the
scenario, Pareto frontier kept only up to a size, failures and slow scenarios recorded and ignored."""

import json
import shutil
import threading
import time
from pathlib import Path

import pytest

from hani2 import scenario_stats as ss
from hani2 import scenario_store as store
from hani2.config import DEFAULT_SCENARIOS

from conftest import write_settings


@pytest.fixture
def trade(tmp_path) -> Path:
    d = tmp_path / "Trade"
    shutil.copytree(DEFAULT_SCENARIOS / "Trade", d)
    return d


def _wait(pred, timeout=60.0):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_compute_caches_negmas_stats_next_to_the_scenario(trade):
    from negmas import Scenario

    r = ss.compute(trade)
    assert r["status"] == "ok" and r["cache"] == "disk"
    assert r["n_outcomes"] == 40 and r["pareto_cached"] and r["pareto_size"] > 0
    assert (trade / ss.STATS_FILE).is_file() and (trade / ss.META_FILE).is_file()
    assert not (trade / ss.LOCK_FILE).exists()
    assert not [p for p in trade.iterdir() if ".tmp" in p.name]
    # negmas reads its own stats file back, and the scenario is still one scenario folder
    s = Scenario.load(trade)
    assert s.stats is not None and len(s.stats.pareto_utils) == r["pareto_size"]
    assert ss.content_fingerprint(s) == r["content"]
    assert store.pool_of(trade) == [trade]
    hit = ss.read_cached(trade)
    assert hit["status"] == "ok" and hit["stats"]["opposition"] == pytest.approx(r["stats"]["opposition"])
    v = ss.view(hit, "Seller")
    assert [x["name"] for x in v["roles"]] == ["Buyer", "Seller"] and v["roles"][1]["human"]
    assert {s["key"] for s in v["solutions"]} >= {"nash", "kalai", "ks", "max_welfare"}
    nash = next(s for s in v["solutions"] if s["key"] == "nash")["points"][0]
    assert set(nash["utilities"]) == {"Buyer", "Seller"} and set(nash["outcome"]) == {"Quantity", "Price"}
    json.dumps(v, allow_nan=False)  # browser-safe


def test_the_pareto_frontier_is_kept_only_for_small_scenarios(trade, hani2_home):
    write_settings(hani2_home, "env.json", {"scenario_stats": {"pareto_max_outcomes": 10}})
    r = ss.compute(trade)
    assert r["status"] == "ok" and r["pareto_cached"] is False and r["pareto_size"] > 0
    hit = ss.read_cached(trade)
    assert not hit["stats"].get("pareto_utils")  # every other statistic is cached
    assert hit["stats"]["nash_utils"]
    v = ss.view(hit)
    assert v["pareto"] == [] and v["pareto_size"] == r["pareto_size"]


def test_the_default_pareto_limit_is_a_million(hani2_home):
    assert ss.settings()["pareto_max_outcomes"] == 1_000_000 == ss.DEFAULT_PARETO_MAX_OUTCOMES


def test_too_slow_and_too_large_are_recorded_and_not_retried(trade, hani2_home):
    write_settings(hani2_home, "env.json", {"scenario_stats": {"timeout": 0.01}})
    r = ss.compute(trade)
    assert r["status"] == "timeout" and "stopped" in r["message"]
    assert not (trade / ss.STATS_FILE).exists()
    # recorded: asking again gives the failure at once instead of computing again
    assert ss.request(folder=trade)["status"] == "timeout"
    write_settings(hani2_home, "env.json", {"scenario_stats": {"max_outcomes": 10}})
    r = ss.compute(trade)
    assert r["status"] == "too_large" and "40 outcomes" in r["message"]
    assert ss.view(r)["status"] == "too_large"


def test_a_broken_scenario_fails_without_raising(tmp_path):
    d = tmp_path / "Broken"
    d.mkdir()
    (d / "Broken.yml").write_text("not: a scenario\n", encoding="utf-8")
    r = ss.compute(d)
    assert r["status"] == "failed" and r["message"]
    assert ss.read_cached(d)["status"] == "failed"


def test_editing_the_scenario_makes_the_cache_stale(trade):
    ss.compute(trade)
    seller = trade / "Seller.yml"
    seller.write_text(seller.read_text(encoding="utf-8").replace("0.0", "0.25", 1), encoding="utf-8")
    assert ss.read_cached(trade) is None
    s = store._load_dir(trade)  # HANI2 never loads the cache into Scenario.stats
    assert s is not None and s.stats is None


def test_saving_a_changed_scenario_drops_its_stats(trade):
    ss.compute(trade)
    s = store._load_dir(trade)
    s.ufuns[0].reserved_value = 0.5
    store.save_scenario(s, trade)
    assert not (trade / ss.STATS_FILE).exists() and not (trade / ss.META_FILE).exists()


def test_request_computes_in_the_background_once(trade):
    done = threading.Event()
    got = []
    first = ss.request(folder=trade, on_done=lambda r: (got.append(r), done.set()))
    assert first["status"] == "pending"
    assert ss.request(folder=trade)["status"] == "pending"  # under way: not started twice
    assert done.wait(60) and got[0]["status"] == "ok"
    assert ss.request(folder=trade)["status"] == "ok"
    assert ss.request(folder=trade, with_stats=False).get("stats") is None


def test_a_scenario_changed_in_memory_is_computed_and_cached_in_memory(trade):
    ss.compute(trade)
    s = store._load_dir(trade)
    s.ufuns[0].reserved_value = 0.9  # e.g. a forced value on disagreement for this session
    assert ss.lookup(s, trade) is None  # the disk cache is of the saved scenario
    done = threading.Event()
    ss.request(s, trade, on_done=lambda r: done.set())
    assert done.wait(60)
    hit = ss.lookup(s, trade)
    assert hit["status"] == "ok" and hit["cache"] == "memory"
    assert max(hit["reserved_values"]) == pytest.approx(0.9)


def test_bundled_samples_are_never_written_to():
    folder = DEFAULT_SCENARIOS / "Trade"
    assert not ss.writable(folder)
    done = threading.Event()
    assert ss.request(folder=folder, force=True, on_done=lambda r: done.set())["status"] == "pending"
    assert done.wait(60)
    assert ss.lookup(folder=folder)["cache"] == "memory"
    assert not (folder / ss.STATS_FILE).exists() and not (folder / ss.META_FILE).exists()


def test_switched_off(trade, hani2_home):
    write_settings(hani2_home, "env.json", {"scenario_stats": {"enabled": False}})
    assert ss.request(folder=trade)["status"] == "disabled"
    assert not (trade / ss.META_FILE).exists()


def test_a_session_starts_the_stats_of_its_saved_scenario(hani2_home):
    from hani2.testing import make_session

    from test_scenario_format import _gen

    _gen(None, ["Lease"], 1, seed=3)
    slot = store.base_dir() / "Lease" / "0000Lease"
    make_session(scenario_type="Lease", n_steps=4)
    assert _wait(lambda: ss.read_cached(slot) is not None)
    assert ss.read_cached(slot)["status"] == "ok"


def test_hani2_never_loads_the_cache_into_scenario_stats(trade):
    ss.compute(trade)
    s = store._load_dir(trade)
    assert s is not None and s.stats is None


def test_a_forced_recompute_is_not_hidden_by_the_old_cache(trade):
    ss.compute(trade)
    done = threading.Event()
    assert ss.request(folder=trade, force=True, on_done=lambda r: done.set())["status"] == "pending"
    if not done.is_set():
        assert ss.request(folder=trade)["status"] == "pending"
    assert done.wait(60)


def test_a_session_on_a_saved_scenario_uses_the_disk_cache(hani2_home):
    from hani2.testing import make_session

    from test_scenario_format import _gen

    _gen(None, ["Lease"], 1, seed=3)
    slot = store.base_dir() / "Lease" / "0000Lease"
    ss.compute(slot)
    s = make_session(scenario_type="Lease", n_steps=4, is_admin=True)
    assert s.ss["scenario_dir"] == str(slot)
    hit = ss.lookup(s.scenario, slot)
    assert hit is not None and hit["cache"] == "disk" and hit["status"] == "ok"
    t = next(t for t in s.tools if t.name == "Scenario Stats")
    assert any(c.get("type") == "stats" for c in t.render())  # at once, from the disk


def test_the_tool_does_not_show_the_saved_scenario_for_a_changed_one(hani2_home):
    from hani2 import projects
    from hani2.testing import make_session

    from test_scenario_format import _gen

    _gen(None, ["Lease"], 1, seed=3)
    slot = store.base_dir() / "Lease" / "0000Lease"
    projects.create_project("P", defaults={"force_reserved_value": 0.77})
    projects.create_study("P/s")
    s = make_session(scenario_type="Lease", n_steps=4, is_admin=True, study="P/s")
    t = next(t for t in s.tools if t.name == "Scenario Stats")
    assert _wait(lambda: any(c.get("type") == "stats" for c in t.render()))
    assert float(s.scenario.ufuns[s.ss["human_index"]].reserved_value) == pytest.approx(0.77)
    assert s.ss["scenario_dir"] == str(slot)
    assert ss.read_cached(slot) is not None  # the saved scenario's stats are on disk ...
    hit = ss.lookup(s.scenario, slot)  # ... but the tool shows those of the changed one
    assert hit is not None and hit["cache"] == "memory"
    assert any(x == pytest.approx(0.77) for x in hit["reserved_values"])


def test_the_tool_is_admin_only_and_shows_the_stats(hani2_home):
    from hani2.testing import make_session

    def tool(sess):
        return next((t for t in sess.tools if t.name == "Scenario Stats"), None)

    assert tool(make_session(user="p")) is None
    s = make_session(user="a", is_admin=True)
    t = tool(s)
    assert t is not None

    def ready():
        return any(c.get("type") == "stats" for c in t.render())

    assert _wait(ready)
    text = json.dumps(t.render(), default=str)
    assert "Bargaining solutions" in text and "Pareto frontier" in text and "Opposition" in text
    t.on_action("recompute", {})
    assert _wait(ready)


def test_admin_api_shows_the_stats_of_a_described_scenario(hani2_home):
    from fastapi.testclient import TestClient

    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        d = c.get("/api/admin/scenarios/Trade?layer=settings").json()
        assert _wait(lambda: c.get(f"/api/admin/scenarios/stats/{d['plot_token']}").json()["status"] == "ok")
        v = c.get(f"/api/admin/scenarios/stats/{d['plot_token']}").json()
        assert v["n_outcomes"] == d["n_outcomes"] and v["solutions"] and v["pareto"]
        assert any(r["human"] for r in v["roles"])
        assert c.get(f"/api/admin/scenarios/stats/{d['plot_token']}?force=true").json()["status"] in ("pending", "ok")
    hub.sessions.clear()
