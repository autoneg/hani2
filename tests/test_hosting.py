"""Self-hosted Assistants and opponents (hani2.hosting): specs, the registry, the host's isolation and
authentication, the adapters through headless negotiations, failures and the self-hosted mode."""

import csv
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from negmas.sao import AspirationNegotiator

from hani2 import projects
from hani2.hosting import make_app, protocol, registry, run_host
from hani2.hosting.server import OpponentRunner, SessionStore, opponent_factory
from hani2.testing import make_session

TOKEN = "team-secret"
EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "support_agent_tutorial"


def results_rows(s):
    f = s.ss["user_path"] / "results.csv"
    with open(f) as fh:
        return list(csv.DictReader(fh))


def play_out(s, n=12):
    s.start()
    for _ in range(n):
        if not s.wait_for_turn(20) or s.phase != "running":
            break
        s.send_counter("hello")
    if s.phase == "running" and s.wait_for_turn(20) and s.is_my_turn():
        s.end()
    assert s.wait_until_done(60)


# --------------------------------------------------------------------------- #
# Specs                                                                        #
# --------------------------------------------------------------------------- #
def test_specs():
    assert protocol.is_remote_spec("remote:teamA") and protocol.is_remote_spec("remote+https://h:1/x")
    assert protocol.is_remote_spec({"url": "https://h:1"}) and not protocol.is_remote_spec("negmas.sao.X")
    assert protocol.is_direct_address("remote+http://h:1") and not protocol.is_direct_address("remote:teamA")
    assert protocol.spec_from_mapping({"url": "https://h:9", "token_env": "T"}) == "remote+https://h:9#token_env=T"
    assert protocol.normalise_spec({"name": "teamA"}) == "remote:teamA"
    # recorded and shown without the address details or token variables
    assert protocol.recorded_spec("remote+https://h.example:9/p/q#token_env=T") == "remote+h.example:9"
    assert protocol.short_label("remote:teamA") == "teamA"
    from hani2.agents import client_spec_allowed, short_name

    assert short_name("remote:teamA") == "teamA"
    assert client_spec_allowed("remote:teamA")
    assert not client_spec_allowed("remote+https://evil.example:80")  # a visitor's URL never names a host


def test_direct_address_token_from_env(monkeypatch):
    monkeypatch.setenv("TEAM_T", "abc")
    ep = protocol.parse_direct("remote+https://h.example:8443/agent#token_env=TEAM_T&timeout=7")
    assert ep.url == "https://h.example:8443/agent" and ep.token == "abc" and ep.timeout == 7
    assert "abc" not in str(ep.public())


def test_outcome_checks():
    from negmas import make_issue
    from negmas.outcomes import make_os

    os_ = make_os([make_issue(5, "q"), make_issue(["a", "b"], "c")])
    assert protocol.check_outcome([2, "b"], os_) == (2, "b")
    assert protocol.check_outcome({"q": 2.0, "c": "a"}, os_) == (2, "a")
    with pytest.raises(protocol.HostedError):
        protocol.check_outcome([9, "a"], os_)
    with pytest.raises(protocol.HostedError):
        protocol.check_outcome({"q": 1}, os_)


# --------------------------------------------------------------------------- #
# Registry and the self-hosted mode                                            #
# --------------------------------------------------------------------------- #
def test_registry_keeps_tokens_private():
    projects.create_project("P", kind="assistant")
    e, tok = registry.add("P", "teamA", "assistant", "https://a.example:9000", team="Team A")
    assert tok.startswith("h2t_") and e["token"] == tok
    pub = registry.public(registry.get("P", "teamA"))
    assert "token" not in pub and pub["has_token"] and pub["spec"] == "remote:teamA"
    with pytest.raises(ValueError):
        registry.add("P", "teamA", "assistant", "https://b.example")
    registry.add("P", "teamA", "assistant", "https://b.example", replace=True)
    assert registry.get("P", "teamA")["token"] == tok  # replacing keeps the token
    ep = registry.resolve("remote:teamA", project="P", kind="assistant")
    assert ep.url == "https://b.example" and ep.token == tok and ep.name == "remote:teamA"
    with pytest.raises(protocol.HostedError):
        registry.resolve("remote:teamA", project="P", kind="opponent")
    registry.set_enabled("P", "teamA", False)
    with pytest.raises(protocol.HostedError, match="switched off"):
        registry.resolve("remote:teamA", project="P")
    with pytest.raises(protocol.HostedError, match="no hosted agent"):
        registry.resolve("remote:nobody", project="P")
    assert registry.remove("P", "teamA") and registry.entries("P") == []
    for bad in (("bad name", "assistant", "https://x"), ("ok", "robot", "https://x"), ("ok", "assistant", "ftp://x")):
        with pytest.raises(ValueError):
            registry.add("P", *bad)


def test_hosted_block_checks():
    assert registry.check_hosted_block({"assistants": True, "timeout": 20}) == []
    assert registry.check_hosted_block({"assistants": "yes"})
    assert registry.check_hosted_block({"timeout": 0})
    assert registry.check_hosted_block({"speed": 1})
    assert projects.file_problems({"defaults": {"hosted": {"opponents": 3}}}, "defaults")


def test_self_hosted_mode_fills_the_assistant_pool():
    from hani2 import assignment

    projects.create_project("SH", kind="assistant")
    projects.create_study("SH/live", type="online")
    f = projects.project_dir("SH") / projects.PROJECT_FILE
    d = projects.read_yaml(f)
    d["hosted"] = {"assistants": True}
    projects.write_yaml(f, d)
    ref = projects.StudyRef("SH", "live")
    assert registry.hosted_pool("assistant", ref) == []
    registry.add("SH", "teamA", "assistant", "https://a.example")
    registry.add("SH", "teamB", "assistant", "https://b.example")
    registry.add("SH", "teamC", "assistant", "https://c.example", enabled=False)
    registry.add("SH", "opp", "opponent", "https://o.example")
    assert registry.hosted_pool("assistant", ref) == ["remote:teamA", "remote:teamB"]
    assert registry.hosted_pool("opponent", ref) == []  # opponents are not self-hosted in this project

    class S:  # the parts of a session assistant_pool reads
        study_ref = ref
        query: dict = {}
        is_admin = False
        study = None
        round_plan = None

    with projects.use_study(ref):
        choice = assignment.assistant_pool(S(), {})
    assert choice.pool == ["remote:teamA", "remote:teamB"] and not choice.error


# --------------------------------------------------------------------------- #
# The host: authentication and isolation                                       #
# --------------------------------------------------------------------------- #
def test_host_needs_a_token_and_checks_it():
    with pytest.raises(ValueError):
        make_app("opponent", "AspirationNegotiator")
    c = TestClient(make_app("opponent", "AspirationNegotiator", token=TOKEN, version="2.1"))
    assert c.get("/health").json() == {"ok": True}
    assert c.get("/info").status_code == 401
    assert c.get("/info", headers={"Authorization": "Bearer wrong"}).status_code == 401
    info = c.get("/info", headers={"Authorization": f"Bearer {TOKEN}"}).json()
    assert info["protocol"] == protocol.PROTOCOL and info["kind"] == "opponent" and info["version"] == "2.1"


def _setup(name="opp", seed=0):
    from negmas import LinearAdditiveUtilityFunction as U, make_issue
    from negmas.outcomes import make_os

    os_ = make_os([make_issue(10, "price"), make_issue(5, "qty")])
    import random

    random.seed(seed)
    u = U.random(os_, reserved_value=0.1)
    return os_, u, {"name": name, "ufun": protocol.encode_ufun(u), "outcome_space": protocol.encode_outcome_space(os_),
                    "n_steps": 20, "time_limit": None}


class Recorder(AspirationNegotiator):
    """Remembers, per instance, the steps it was asked at (shared state would mix them)."""

    seen: dict[int, list[int]] = {}

    def __call__(self, state, dest=None):
        Recorder.seen.setdefault(id(self), []).append(state.step)
        time.sleep(0.01)
        return super().__call__(state, dest)


def test_store_keeps_one_instance_per_session_and_reaps_idle_ones():
    store = SessionStore(idle_timeout=60, max_sessions=2)
    f = opponent_factory(Recorder)
    _, _, s1 = _setup(seed=1)
    _, _, s2 = _setup(seed=2)
    store.add("n1", OpponentRunner(f, s1))
    store.add("n2", OpponentRunner(f, s2))
    with pytest.raises(OverflowError):
        store.add("n3", OpponentRunner(f, s1))
    r1, r2 = store.get("n1")["runner"], store.get("n2")["runner"]
    assert r1.negotiator is not r2.negotiator and r1.negotiator.ufun is not r2.negotiator.ufun
    assert r1.negotiator.ufun((1, 1)) != r2.negotiator.ufun((1, 1)) or r1.negotiator.ufun((5, 3)) != r2.negotiator.ufun((5, 3))
    for step in range(3):  # interleaved steps of two negotiations
        for r in (r1, r2):
            r.step({"state": {"step": step, "relative_time": step / 20}})
    assert Recorder.seen[id(r1.negotiator)] == [0, 1, 2] and Recorder.seen[id(r2.negotiator)] == [0, 1, 2]
    assert store.reap(now=time.time() + 3600) == ["n1", "n2"] and len(store) == 0


def test_two_concurrent_negotiations_against_one_host_share_no_state():
    projects.create_project("default") if not projects.project_exists("default") else None
    Recorder.seen.clear()
    app = make_app("opponent", Recorder, token=TOKEN)
    peak = []
    with run_host(app) as url:
        registry.add("default", "rec", "opponent", url, token=TOKEN)
        sessions = [make_session(user=f"u{i}", opponent="remote:rec", n_steps=12) for i in range(2)]

        stop = threading.Event()

        def watch():
            while not stop.is_set():
                peak.append(len(app.state.store))
                time.sleep(0.01)

        w = threading.Thread(target=watch, daemon=True)
        w.start()
        threads = [threading.Thread(target=play_out, args=(s,)) for s in sessions]
        for t in threads:
            t.start()
        for t in threads:
            t.join(90)
        stop.set()
        w.join(5)
        time.sleep(0.5)
        assert len(app.state.store) == 0  # both host sessions were closed at the end
    assert max(peak) == 2  # both negotiations ran on the host at the same time
    assert len(Recorder.seen) == 2  # one instance per negotiation
    for steps in Recorder.seen.values():
        assert steps == sorted(steps) and len(steps) == len(set(steps))  # never another negotiation's turns
    for s in sessions:
        row = results_rows(s)[-1]
        assert row["agent_type"] == "remote:rec" and row["hosted_failures"] == "0"
        assert s.ss["hosted_opponent"]["failures"] == 0


def test_hosted_opponent_reaches_agreements_and_records_attribution():
    app = make_app("opponent", "BoulwareTBNegotiator", token=TOKEN, version="1.2",
                   model={"provider": "acme", "model": "rules-1"})
    with run_host(app) as url:
        registry.add("default", "teamx", "opponent", url, token=TOKEN)
        s = make_session(opponent="remote:teamx", n_steps=10)
        play_out(s, 9)
    row = results_rows(s)[-1]
    assert row["agent_type"] == "remote:teamx"
    assert row["opponent_llm"] == "remote:acme/rules-1" and row["opponent_llm_entry"] == "hosted:teamx@1.2"
    assert row["opponent_version"] == "1.2" and row["hosted_failures"] == "0"
    assert url not in "".join(str(v) for v in row.values()) and TOKEN not in "".join(str(v) for v in row.values())


def test_an_unreachable_host_does_not_hang_the_negotiation():
    from hani2.hosting.testing import free_port

    registry.add("default", "gone", "opponent", f"http://127.0.0.1:{free_port()}", token=TOKEN, timeout=1)
    s = make_session(opponent="remote:gone", n_steps=30)
    t0 = time.time()
    play_out(s, 6)
    assert time.time() - t0 < 30
    row = results_rows(s)[-1]
    assert int(row["hosted_failures"]) >= 3 and row["status"] != "success"  # it walked away: the game counts
    assert any("not answering" in m.get("message", "") for m in s.hub.of_type("toast"))


class Slow(AspirationNegotiator):
    def __call__(self, state, dest=None):
        time.sleep(3)
        return super().__call__(state, dest)


def test_a_slow_host_times_out():
    with run_host(make_app("opponent", Slow, token=TOKEN)) as url:
        registry.add("default", "slow", "opponent", url, token=TOKEN, timeout=0.5)
        s = make_session(opponent="remote:slow", n_steps=30)
        play_out(s, 5)
        assert "did not answer within" in s.ss["hosted_opponent"]["error"]


def test_repeated_step_returns_the_stored_reply():
    c = TestClient(make_app("opponent", Recorder, token=TOKEN))
    h = {"Authorization": f"Bearer {TOKEN}"}
    _, _, setup = _setup()
    assert c.post("/sessions", json={"session_id": "s1", "kind": "opponent", "setup": setup}, headers=h).json()["ok"]
    Recorder.seen.clear()
    body = {"seq": 1, "state": {"step": 0}}
    r1 = c.post("/sessions/s1/step", json=body, headers=h).json()
    r2 = c.post("/sessions/s1/step", json=body, headers=h).json()
    assert r1 == r2 and sum(len(v) for v in Recorder.seen.values()) == 1  # acted once
    assert c.post("/sessions/nope/step", json=body, headers=h).status_code == 404
    assert c.delete("/sessions/s1", headers=h).json() == {"ok": True}


# --------------------------------------------------------------------------- #
# Assistants                                                                   #
# --------------------------------------------------------------------------- #
@pytest.fixture
def tutorial_path():
    sys.path.insert(0, str(EXAMPLES))
    yield
    sys.path.remove(str(EXAMPLES))


def test_hosted_rule_based_assistant(tutorial_path):
    app = make_app("assistant", "level2_rules:RulesAgent", token=TOKEN, version="0.3",
                   model={"provider": "none", "model": "rules"})
    with run_host(app) as url:
        registry.add("default", "coach", "assistant", url, token=TOKEN)
        s = make_session(agent_class="remote:coach")
        assert type(s.support_agent).__name__ == "Remote_coach" and not s.assistant_error
        s.start()
        s.wait_for_turn()
        s.user_chat("what do you think?")
        s.wait_agent_idle()
        said = [m["text"] for m in s.chat if m["user"] == "Assistant"]
        assert len([t for t in said if t.startswith("Opponent offer")]) == 1, said
        assert s.ss["hosted_assistant"]["model"] == "none/rules" and s.ss["hosted_assistant"]["version"] == "0.3"
        s.end()
        s.wait_until_done()
    row = results_rows(s)[-1]
    assert row["assistant"] == "remote:coach" and row["assistant_llm"] == "remote:none/rules"
    assert row["assistant_llm_entry"] == "hosted:coach@0.3" and row["assistant_version"] == "0.3"


def test_hosted_llm_assistant_runs_its_functions_in_the_real_session(scripted):
    """The host's language model calls functions; HANI2 runs them in the session, with its capabilities."""
    app = make_app("assistant", "hani2.support_agent.runtime:SupportAgent", token=TOKEN)
    with run_host(app) as url:
        registry.add("default", "llm", "assistant", url, token=TOKEN)
        s = make_session(agent_class="remote:llm", support_settings={"autonomy": "suggest"})
        s.start()
        s.wait_for_turn()
        issue = s.issues[0]
        v = list(issue.all)[-1]
        llm = scripted(("get_negotiation_state", {}), ("set_offer", {"outcome": {issue.name: v}}),
                       ("highlight", {"target": f"issue:{issue.name}", "message": "Look"}),
                       ("submit_counter_offer", {"message": "fair?"}), "Prepared your counter-offer.")
        s.user_chat("help me")
        s.wait_agent_idle()
        assert s.draft[issue.name] == v  # set_offer ran in the session
        assert any(h["target"] == f"issue:{issue.name}" for h in s.highlights)
        assert s.is_my_turn()  # suggest autonomy (enforced by HANI2): nothing was sent
        assert s.chat[-1]["text"] == "Prepared your counter-offer."
        assert "accept_offer" in llm.calls[0]["tools"]  # the host's model saw HANI2's functions


def test_hosted_assistant_cannot_exceed_its_capabilities(scripted):
    app = make_app("assistant", "hani2.support_agent.runtime:SupportAgent", token=TOKEN)
    with run_host(app) as url:
        registry.add("default", "llm2", "assistant", url, token=TOKEN)
        s = make_session(agent_class="remote:llm2", support_settings={"capabilities": {"fill_offer": False}})
        s.start()
        s.wait_for_turn()
        issue = s.issues[0]
        before = dict(s.draft)
        v = [x for x in issue.all if x != before.get(issue.name)][0]
        scripted(("set_offer", {"outcome": {issue.name: v}}), "ok")
        s.user_chat("set it")
        s.wait_agent_idle()
        assert s.draft.get(issue.name) == before.get(issue.name)  # refused by HANI2's dispatcher
        # and a direct action naming a function is refused the same way
        sa = s.support_agent
        res = sa._run_call({"function": "set_offer", "arguments": {"outcome": {issue.name: v}}}, set(), "chat")
        assert res["ok"] is False and "fill_offer" in res["error"]


def test_hosted_assistant_with_its_own_extra_function(tutorial_path, scripted):
    """A class's own dispatcher functions run on the host; the built-in ones in HANI2."""
    app = make_app("assistant", "level4_tools:ToolCoachAgent", token=TOKEN)
    with run_host(app) as url:
        registry.add("default", "tc", "assistant", url, token=TOKEN)
        s = make_session(agent_class="remote:tc")
        s.start()
        s.wait_for_turn()
        llm = scripted(("assess_partner_offer", {}), "assessed")
        s.user_chat("assess")
        s.wait_agent_idle()
        assert "assess_partner_offer" in llm.calls[0]["tools"]
        assert s.chat[-1]["text"] == "assessed"


def test_an_unreachable_assistant_host_says_so_and_does_not_block():
    from hani2.hosting.testing import free_port

    registry.add("default", "down", "assistant", f"http://127.0.0.1:{free_port()}", token=TOKEN, timeout=1)
    s = make_session(agent_class="remote:down")
    s.start()
    s.wait_for_turn()
    s.user_chat("hello?")
    s.wait_agent_idle()
    assert any("could not answer" in m["text"] for m in s.chat)
    assert s.is_my_turn()  # the negotiation goes on
    assert s.support_agent.failures_total >= 1 and not s.support_agent.busy


def test_an_unregistered_assistant_fails_loudly():
    s = make_session(agent_class="remote:nobody")
    assert s.support_agent is None and "no hosted agent" in (s.assistant_error or "")


def test_self_hosted_mode_fills_the_opponent_pool():
    projects.create_project("SO", kind="opponent")
    projects.create_study("SO/live", type="online")
    f = projects.project_dir("SO") / projects.PROJECT_FILE
    d = projects.read_yaml(f)
    d["hosted"] = {"opponents": True}
    projects.write_yaml(f, d)
    registry.add("SO", "oppA", "opponent", "https://a.example")
    registry.add("SO", "astB", "assistant", "https://b.example")
    s = make_session(study="SO/live", opponent=None, partner=None)
    assert s.opponent_pool() == ["remote:oppA"] and s.opponent_group == "hosted"


# --------------------------------------------------------------------------- #
# The admin console API                                                        #
# --------------------------------------------------------------------------- #
def test_admin_api_registers_checks_and_never_lists_tokens(monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app

    projects.create_project("HP", kind="assistant")
    with TestClient(app) as c:
        assert c.get("/api/admin/projects/HP/hosted").status_code in (401, 403)
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        with run_host(make_app("assistant", "hani2.support_agent.runtime:SupportAgent", token=TOKEN, version="9")) as url:
            r = c.post("/api/admin/projects/HP/hosted", json={"name": "teamA", "kind": "assistant", "url": url,
                                                              "token": TOKEN, "team": "A"})
            assert r.status_code == 200 and "token" not in r.json()  # the admin gave it: not echoed
            chk = c.post("/api/admin/projects/HP/hosted/teamA/check").json()
            assert chk["ok"] and chk["info"]["version"] == "9"
        r = c.post("/api/admin/projects/HP/hosted", json={"name": "teamB", "kind": "opponent", "url": "https://b.example"})
        assert r.json()["token"].startswith("h2t_")  # made by HANI2: shown once
        listed = c.get("/api/admin/projects/HP/hosted").json()
        assert [a["name"] for a in listed["agents"]] == ["teamA", "teamB"]
        assert TOKEN not in str(listed) and r.json()["token"] not in str(listed)
        assert c.put("/api/admin/projects/HP/hosted/teamB/enabled", json={"enabled": False}).json()["ok"]
        assert c.post("/api/admin/projects/HP/hosted", json={"name": "bad name", "url": "https://x"}).status_code == 400
        m = c.put("/api/admin/projects/HP/hosted-mode", json={"assistants": True, "timeout": 20}).json()["mode"]
        assert m["assistants"] is True and m["timeout"] == 20
        assert c.put("/api/admin/projects/HP/hosted-mode", json={"assistants": "yes"}).status_code == 400
        assert registry.hosted_pool("assistant", projects.StudyRef("HP", "x")) == ["remote:teamA"]
        assert c.delete("/api/admin/projects/HP/hosted/teamA").json()["ok"]
