"""Model chains, connections and providers: parsing, precedence, resolution, probes, secrets,
conflicts, CLI, admin endpoints and every consumer of the resolved entry. No network: probes
and model calls are faked."""

import json
import os
import stat
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hani2 import connections as conns
from hani2 import model_chain as mc
from hani2 import projects

SECRET = "sk-test-SECRET-0123456789abcdef"


def write(home, rel, data):
    p = home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data) if not isinstance(data, str) else data)
    return p


def reply(text="ok", tool_calls=None):
    msg = SimpleNamespace(content=text, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


@pytest.fixture
def calls(monkeypatch):
    """Capture litellm.completion calls (answers "ok")."""
    import litellm

    seen = []

    def fake(**kw):
        seen.append(kw)
        return reply("ok")

    monkeypatch.setattr(litellm, "completion", fake)
    return seen


@pytest.fixture
def study(hani2_home):
    projects.create_project("P1", full_name="P", kind="assistant")
    projects.create_study("P1/s1", type="online", title="S")
    return hani2_home


@pytest.fixture
def probe_on(monkeypatch):
    monkeypatch.setenv("HANI2_MODEL_PROBE", "on")
    conns.forget_probes()
    yield
    conns.forget_probes()


# --------------------------------------------------------------------------- #
# Parsing                                                                      #
# --------------------------------------------------------------------------- #
def test_parse_simple_entries_split_on_first_colon():
    ch = mc.parse_chain("anthropic:claude-sonnet-5-5, ollama:qwen3:4b ,openai:gpt-5")
    assert [(e.provider, e.model) for e in ch] == [("anthropic", "claude-sonnet-5-5"), ("ollama", "qwen3:4b"),
                                                   ("openai", "gpt-5")]
    with pytest.raises(mc.ChainError):
        mc.parse_chain("nonsense")
    with pytest.raises(mc.ChainError):
        mc.parse_chain("nowhere:model")


def test_duplicates_allowed_and_identified_by_position():
    ch = mc.parse_chain([{"provider": "ollama", "model": "m", "params": {"temperature": 0.1}},
                         {"provider": "ollama", "model": "m", "params": {"temperature": 0.9}},
                         "ollama:m"])
    assert len(ch) == 3 and ch[0].params != ch[1].params


def test_secret_params_are_refused():
    with pytest.raises(mc.ChainError, match="connection"):
        mc.parse_entry({"provider": "openai", "model": "gpt-5", "params": {"api_key": "x"}})
    with pytest.raises(mc.ChainError):
        mc.parse_entry({"provider": "openai", "model": "gpt-5", "extra_headers": {"a": "b"}})
    with pytest.raises(mc.ChainError, match="purpose"):
        mc.parse_chains({"nonsense": []})


def test_old_single_model_keys_are_a_one_entry_chain(hani2_home):
    write(hani2_home, "settings/assistant_settings.json", {"provider": "anthropic", "model": "claude-opus-5-5",
                                                           "api_key_env": "MY_KEY", "temperature": 0.2})
    ch, src = mc.chain_for("assistant")
    assert src.id == "legacy" and src.implicit
    assert len(ch) == 1 and ch[0].model == "claude-opus-5-5" and ch[0].inline.provider == "anthropic"
    assert ch[0].params["temperature"] == 0.2


def test_old_remote_ollama_gets_the_local_fallback_entry(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_BASE", "https://ollama.com")
    ch, _ = mc.chain_for("assistant")
    assert [e.inline.base for e in ch] == ["https://ollama.com", "http://localhost:11434"]
    assert ch[0].inline.provider == "ollama_cloud"


def test_connection_and_provider_disagree(hani2_home):
    conns.add({"name": "mine", "provider": "openai", "auth": "api_key_env", "api_key_env": "X"})
    with pytest.raises(mc.ChainError, match="give only the connection"):
        mc.parse_entry({"connection": "mine", "provider": "anthropic", "model": "m"})


# --------------------------------------------------------------------------- #
# Precedence                                                                   #
# --------------------------------------------------------------------------- #
def test_precedence_study_project_start_settings_legacy(study, monkeypatch):
    home = study
    ref = projects.parse_ref("P1/s1")
    write(home, "settings/models.json", {"default": ["openai:gpt-settings"], "assistant": ["openai:gpt-asst"]})
    assert mc.chain_for("assistant")[0][0].model == "gpt-asst"
    assert mc.chain_for("judge")[0][0].model == "gpt-settings"
    monkeypatch.setenv("HANI2_MODELS", "openai:gpt-start")
    ch, src = mc.chain_for("assistant")
    assert (ch[0].model, src.id) == ("gpt-start", "start")  # the start list beats the settings
    write(home, "projects/P1/models.json", ["openai:gpt-project"])
    with projects.use_study(ref):
        assert mc.chain_for("assistant")[0][0].model == "gpt-project"
        write(home, "projects/P1/studies/s1/models.json", {"default": ["openai:gpt-study"]})
        ch, src = mc.chain_for("assistant")
        # the study wins over everything, the start list included; its default beats per-purpose chains below
        assert (ch[0].model, src.id) == ("gpt-study", "study:P1/s1")
    # outside the study: the start list
    assert mc.chain_for("assistant")[0][0].model == "gpt-start"


def test_old_keys_in_a_study_folder_count_at_that_layer(study, monkeypatch):
    home = study
    write(home, "settings/models.json", ["openai:gpt-settings"])
    write(home, "projects/P1/studies/s1/assistant_settings.json", {"provider": "anthropic", "model": "claude-haiku-5-5"})
    with projects.use_study("P1/s1"):
        ch, src = mc.chain_for("assistant")
        assert src.id == "study:P1/s1" and ch[0].model == "claude-haiku-5-5"
        assert mc.chain_for("opponent")[0][0].model == "gpt-settings"


def test_start_entry_uses_the_first_connection_of_the_provider(hani2_home, monkeypatch):
    conns.add({"name": "ollama-cloud-1", "provider": "ollama_cloud", "auth": "api_key"}, api_key=SECRET)
    monkeypatch.setenv("HANI2_MODELS", "ollama_cloud:gpt-oss:120b")
    res = mc.resolve("assistant")
    assert res.ok and res.connection.name == "ollama-cloud-1" and res.model == "gpt-oss:120b"


# --------------------------------------------------------------------------- #
# Resolution and probes                                                        #
# --------------------------------------------------------------------------- #
def test_resolution_skips_unavailable_entries(hani2_home, monkeypatch, probe_on):
    monkeypatch.setenv("GOOD_KEY", "k-123456789")
    conns.add({"name": "nokey", "provider": "openai", "auth": "api_key_env", "api_key_env": "MISSING_KEY"})
    conns.add({"name": "good", "provider": "openai", "auth": "api_key_env", "api_key_env": "GOOD_KEY"})
    monkeypatch.setattr(conns, "_http_get", lambda url, headers=None, params=None: {"data": [{"id": "gpt-5"}]})
    write(hani2_home, "settings/models.json", ["nokey:gpt-5", "ghost:gpt-5", "good:gpt-4", "good:gpt-5"])
    res = mc.resolve("assistant")
    assert res.ok and res.index == 3 and res.connection.name == "good"
    reasons = [s["reason"] for s in res.skipped]
    assert "MISSING_KEY" in reasons[0] and "no connection named 'ghost'" in reasons[1] and "not offered" in reasons[2]
    rec = res.record()
    assert rec["position"] == 4 and rec["source"] == "settings" and rec["status"] == "ok"


def test_nothing_available_fails_for_an_explicit_chain(hani2_home, probe_on):
    write(hani2_home, "settings/models.json", ["openai:gpt-5"])
    res = mc.resolve("assistant")
    assert not res.ok and "no model of the assistant chain" in res.error
    with pytest.raises(mc.NoModelAvailable):
        mc.completion("assistant", [{"role": "user", "content": "x"}], resolution=res)


def test_old_settings_are_used_unverified_when_the_check_fails(hani2_home, monkeypatch, probe_on):
    def down(*a, **k):
        raise ConnectionError("refused")

    monkeypatch.setattr(conns, "_http_get", down)
    res = mc.resolve("assistant")
    assert res.ok and res.status == "unverified" and res.skipped


def test_remote_ollama_without_the_model_falls_to_local(hani2_home, monkeypatch, probe_on):
    monkeypatch.setenv("OLLAMA_API_BASE", "https://ollama.com")
    monkeypatch.setenv("OLLAMA_API_KEY", "ok-key-123456")

    def tags(url, headers=None, params=None):
        return {"models": [{"name": "gpt-oss:120b"}]} if "ollama.com" in url else {"models": [{"name": "qwen3:4b-instruct"}]}

    monkeypatch.setattr(conns, "_http_get", tags)
    res = mc.resolve("assistant")
    assert res.ok and res.connection.name == "ollama-local" and res.status == "ok"


def test_probe_is_cached_and_times_out(hani2_home, monkeypatch, probe_on):
    n = []

    def slow(url, headers=None, params=None):
        n.append(url)
        import httpx

        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(conns, "_http_get", slow)
    c = conns.get("ollama")
    p1 = conns.probe(c, "m")
    p2 = conns.probe(c, "m")
    assert not p1.ok and "no answer" in p1.reason and p2 is p1 and len(n) == 1
    conns.probe(c, "m", fresh=True)
    assert len(n) == 2
    monkeypatch.setenv("HANI2_MODEL_PROBE_TIMEOUT", "0.5")
    assert conns.probe_timeout() == 0.5


def test_probe_off_checks_only_credentials(hani2_home, monkeypatch):
    monkeypatch.setattr(conns, "_http_get", lambda *a, **k: pytest.fail("no network with probes off"))
    assert conns.probe(conns.get("ollama"), "m").ok
    assert not conns.probe(conns.get("anthropic"), "m").ok  # no ANTHROPIC_API_KEY


# --------------------------------------------------------------------------- #
# Calls                                                                        #
# --------------------------------------------------------------------------- #
def test_litellm_kwargs_from_the_entry(hani2_home, monkeypatch):
    conns.add({"name": "claude", "provider": "anthropic", "auth": "api_key"}, api_key=SECRET)
    write(hani2_home, "settings/models.json", [{"connection": "claude", "model": "claude-sonnet-5-5",
                                                "params": {"temperature": 0.5, "max_tokens": 99, "effort": "low",
                                                           "top_p": 0.9, "seed": 3}}])
    kw = mc.litellm_kwargs(mc.resolve("assistant"))
    assert kw["model"] == "anthropic/claude-sonnet-5-5" and kw["api_key"] == SECRET
    assert kw["reasoning_effort"] == "low" and kw["max_tokens"] == 99 and kw["seed"] == 3
    assert "temperature" not in kw and "top_p" not in kw  # Claude 5 models refuse sampling parameters


def test_hard_failure_moves_to_the_next_entry(hani2_home, monkeypatch):
    import litellm

    write(hani2_home, "settings/models.json", ["ollama:first", "ollama:second"])
    seen = []

    def fake(**kw):
        seen.append(kw["model"])
        if kw["model"].endswith("first"):
            raise litellm.APIConnectionError(message="model 'first' not found", llm_provider="ollama", model="first")
        return reply("hello")

    monkeypatch.setattr(litellm, "completion", fake)
    models = mc.SessionModels()
    r = mc.completion("text", [{"role": "user", "content": "x"}], models=models)
    assert r.choices[0].message.content == "hello"
    assert seen == ["ollama_chat/first", "ollama_chat/second"]
    assert models.pinned["text"].model == "second"
    assert [c["action"] for c in models.changes] == ["model_resolved", "model_fallback"]
    # a bad request does not advance
    def bad(**kw):
        raise ValueError("invalid json schema")

    monkeypatch.setattr(litellm, "completion", bad)
    with pytest.raises(ValueError):
        mc.completion("text", [{"role": "user", "content": "x"}], models=models)
    assert models.pinned["text"].model == "second"


# --------------------------------------------------------------------------- #
# Consumers                                                                    #
# --------------------------------------------------------------------------- #
def test_assistant_uses_the_resolved_entry(hani2_home, calls, monkeypatch):
    from hani2.testing import make_session

    monkeypatch.setenv("HANI2_MODELS", "ollama:asst-model")
    s = make_session()
    assert s.models.peek("assistant").model == "asst-model"  # chosen at session start
    s.support_agent._complete([], False)
    assert calls[-1]["model"] == "ollama_chat/asst-model" and calls[-1]["api_base"] == "http://localhost:11434"
    assert s.support_agent.model().model == "asst-model"


def test_session_without_a_model_shows_an_error(hani2_home, probe_on, monkeypatch):
    from hani2 import events as ev
    from hani2.testing import make_session

    write(hani2_home, "settings/models.json", ["anthropic:claude-sonnet-5-5"])
    s = make_session()
    assert s.model_error and "No language model" in s.model_error
    assert s.snapshot()["model_error"] == s.model_error


def test_opponent_gets_the_entry(hani2_home, monkeypatch):
    from negmas_llm import OllamaNegotiator

    from hani2.agents import make_agent

    conns.add({"name": "oa", "provider": "openai", "auth": "api_key"}, api_key=SECRET)
    write(hani2_home, "settings/models.json", {"default": ["ollama:x"],
                                               "opponent": [{"connection": "oa", "model": "gpt-5",
                                                             "params": {"temperature": 0.4, "max_tokens": 77}}]})
    models = mc.SessionModels()
    a = make_agent(OllamaNegotiator, {"name": "o"}, models=models)
    assert (a.provider, a.model, a.api_key, a.temperature, a.max_tokens) == ("openai", "gpt-5", SECRET, 0.4, 77)
    assert models.pinned["opponent"].connection.name == "oa"
    b = make_agent("LLMBoulwareTBNegotiator", {"name": "p"})  # a meta negotiator wrapping an LLM layer
    found = []

    def walk(o, d=0):
        if d > 4 or o is None:
            return
        if getattr(o, "llm_kwargs", None) is not None and getattr(o, "model", None):
            found.append((o.provider, o.model))
        for n in ("_llm", "llm", "_inner", "inner", "_base", "base_negotiator", "_negotiator"):
            c = getattr(o, n, None)
            if c is not None and not isinstance(c, (str, int, float, dict, list)):
                walk(c, d + 1)

    walk(b)
    assert ("openai", "gpt-5") in found


def test_tools_and_text_use_the_session_entry(hani2_home, calls, monkeypatch):
    from hani2 import llm_service
    from hani2.testing import make_session

    write(hani2_home, "settings/models.json", {"default": ["ollama:base"], "tools": ["ollama:tool-model"],
                                               "text": ["ollama:text-model"]})
    s = make_session()
    tool = s.tools[0]
    assert tool.ask_llm("hi") == "ok"
    assert calls[-1]["model"] == "ollama_chat/tool-model"
    assert s.models.peek("tools").model == "tool-model"
    llm_service.extract_outcome_from_text("I offer you everything", s.issues, context=s.llm_context())
    assert calls[-1]["model"] == "ollama_chat/text-model" and s.models.peek("text") is not None
    # explicit provider/model still calls that model directly
    llm_service.complete("x", provider="openai", model="gpt-direct")
    assert calls[-1]["model"] == "openai/gpt-direct"


def test_judge_uses_its_chain_and_the_cache_key_has_the_entry(hani2_home, calls):
    from hani2.evaluation import llm_judge

    write(hani2_home, "settings/models.json", {"default": ["ollama:base"], "judge": [
        {"provider": "ollama", "model": "judge-m", "params": {"temperature": 0.7, "top_k": 3}}]})
    llm_judge.CALL = None
    try:
        llm_judge.ask_json("say {}")
    except ValueError:
        pass
    assert calls[-1]["model"] == "ollama_chat/judge-m" and calls[-1]["temperature"] == 0.0 and calls[-1]["top_k"] == 3
    k1 = llm_judge.cache_key("m", "1", {})
    write(hani2_home, "settings/models.json", {"judge": [{"provider": "ollama", "model": "judge-m",
                                                          "params": {"top_k": 4}}]})
    assert llm_judge.cache_key("m", "1", {}) != k1 and "judge-m" in k1


# --------------------------------------------------------------------------- #
# Secrets                                                                      #
# --------------------------------------------------------------------------- #
def test_secrets_are_private_and_masked(hani2_home):
    conns.add({"name": "k", "provider": "anthropic", "auth": "api_key"}, api_key=SECRET,
              headers={"X-Team": "hdr-secret-value"})
    sec = hani2_home / "settings/secrets/connections.json"
    assert stat.S_IMODE(sec.stat().st_mode) == 0o600
    assert SECRET not in (hani2_home / "settings/connections.json").read_text()
    pub = json.dumps(conns.public(conns.get("k")))
    assert SECRET not in pub and "hdr-secret-value" not in pub
    assert SECRET not in conns.redact(f"error with {SECRET} and Bearer abcdefghijklmnopqrstuvwxyz")
    assert "abcdefghijklmnop" not in conns.redact("Bearer abcdefghijklmnopqrstuvwxyz")


def test_secrets_never_reach_results_events_or_recordings(hani2_home, calls, monkeypatch):
    from hani2.testing import make_session

    monkeypatch.setenv("HANI2_RECORD", "1")
    conns.add({"name": "k", "provider": "openai", "auth": "api_key"}, api_key=SECRET)
    write(hani2_home, "settings/models.json", ["k:gpt-5"])
    s = make_session()
    s.support_agent._complete([], False)
    assert calls[-1]["api_key"] == SECRET
    s.start()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    s.close()
    found = []
    for f in hani2_home.rglob("*"):
        if f.is_file() and "secrets" not in f.parts:
            try:
                data = f.read_bytes()
            except OSError:
                continue
            if SECRET.encode() in data:
                found.append(str(f))
            if f.suffix in (".gz", ".hrec"):
                import gzip

                try:
                    if SECRET.encode() in gzip.decompress(data):
                        found.append(str(f))
                except OSError:
                    pass
    assert not found
    assert SECRET not in json.dumps(s.snapshot(), default=str)
    import csv

    rows = [r for f in hani2_home.rglob("results.csv") for r in csv.DictReader(open(f))]
    assert rows and rows[0]["assistant_llm"] == "k:gpt-5" and rows[0]["assistant_llm_entry"] == "settings#1"
    assert json.loads(rows[0]["llm_models"])["assistant"]["connection"] == "k"
    recs = list(hani2_home.rglob("*.hrec*"))
    assert recs


# --------------------------------------------------------------------------- #
# Conflicts                                                                    #
# --------------------------------------------------------------------------- #
def test_conflicts_refuse_bad_model_lists(hani2_home):
    from hani2 import conflicts

    assert conflicts.env_problems({"HANI2_MODELS": "nonsense"})
    assert not conflicts.env_problems({"HANI2_MODELS": "ollama:qwen3:4b"})
    p = conflicts.cli_problems(models="ollama:a", env={"HANI2_MODELS": "ollama:b"})
    assert p and "disagree" in p[0]
    assert not conflicts.cli_problems(models="ollama:a", env={"HANI2_MODELS": "ollama:a"})
    write(hani2_home, "settings/models.json", {"bogus": []})
    assert any("models.json" in x for x in conflicts.settings_problems())


def test_cli_refuses_a_bad_models_flag(hani2_home):
    from hani2.cli import app

    r = CliRunner().invoke(app, ["--models", "nonsense", "info"])
    assert r.exit_code != 0 and "provider:model" in r.output


# --------------------------------------------------------------------------- #
# CLI                                                                          #
# --------------------------------------------------------------------------- #
def test_cli_connections_and_models(study, monkeypatch):
    from hani2.cli import app

    run = CliRunner()
    r = run.invoke(app, ["connections", "add", "oc", "--provider", "ollama_cloud", "--auth", "api_key"],
                   input=SECRET + "\n")
    assert r.exit_code == 0, r.output
    r = run.invoke(app, ["connections", "list"])
    assert "oc" in r.output and SECRET not in r.output
    write(study, "projects/P1/studies/s1/models.json", ["oc:gpt-oss:120b"])
    r = run.invoke(app, ["models", "resolve", "--study", "P1/s1", "--purpose", "assistant"])
    assert r.exit_code == 0 and "oc:gpt-oss:120b" in r.output and "study:P1/s1" in r.output
    r = run.invoke(app, ["models", "list", "--study", "P1/s1", "--json"])
    assert json.loads(r.output)["assistant"]["source"] == "study:P1/s1"
    r = run.invoke(app, ["connections", "add", "x", "--provider", "anthropic", "--auth", "subscription"])
    assert r.exit_code != 0 and "does not permit" in r.output
    assert run.invoke(app, ["connections", "remove", "oc"]).exit_code == 0


# --------------------------------------------------------------------------- #
# Admin API                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture
def admin(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        yield c
    hub.sessions.clear()


def test_admin_connections_mask_keys(admin, hani2_home):
    r = admin.post("/api/admin/connections", json={"name": "claude", "provider": "anthropic", "auth": "api_key",
                                                   "api_key": SECRET})
    assert r.status_code == 200 and SECRET not in r.text
    lst = admin.get("/api/admin/connections")
    assert SECRET not in lst.text and any(c["name"] == "claude" and c["credentials"] for c in lst.json()["connections"])
    assert admin.post("/api/admin/connections?layer=project:X", json={"name": "a", "provider": "ollama"}).status_code == 400
    assert admin.post("/api/admin/connections", json={"name": "b", "provider": "anthropic",
                                                      "auth": "subscription"}).status_code == 400
    # changing without a key keeps the stored key
    assert admin.put("/api/admin/connections/claude", json={"provider": "anthropic", "auth": "api_key",
                                                            "label": "Main"}).status_code == 200
    assert conns.api_key(conns.get("claude")) == SECRET
    assert admin.get("/api/admin/providers").json()["providers"][0]["id"] == "anthropic"
    assert admin.delete("/api/admin/connections/claude").status_code == 200
    assert admin.delete("/api/admin/connections/claude").status_code == 404


def test_admin_models_layers(admin, study):
    home = study
    body = {"default": ["ollama:a", {"provider": "ollama", "model": "a", "params": {"temperature": 0.1}}]}
    assert admin.put("/api/admin/models?layer=study:P1/s1", json=body).status_code == 200
    assert json.loads((home / "projects/P1/studies/s1/models.json").read_text()) == body
    g = admin.get("/api/admin/models?layer=study:P1/s1").json()
    assert g["effective"]["assistant"]["source"] == "study:P1/s1" and g["inherited"]["assistant"]["source"] == "legacy"
    # a study-bound console must name the layer
    assert admin.put("/s/P1/s1/api/admin/models", json=body).status_code == 409
    assert admin.put("/api/admin/models?layer=settings", json={"default": [{"provider": "openai", "model": "x",
                                                                            "params": {"api_key": "k"}}]}).status_code == 400
    # the generic settings endpoint validates too
    assert admin.put("/api/admin/settings/models?layer=settings", json={"bogus": []}).status_code == 400
    assert admin.get("/api/admin/settings/models?layer=study:P1/s1").json()["effective"]["judge"]["source"] \
        == "study:P1/s1"
    r = admin.post("/api/admin/models/resolve?layer=study:P1/s1", json={}).json()
    assert r["purposes"]["assistant"]["model"] == "a" and r["purposes"]["assistant"]["position"] == 1
    r = admin.post("/api/admin/models/resolve?layer=settings", json={"chains": ["ollama:draft"]}).json()
    assert r["purposes"]["text"]["model"] == "draft"
    r = admin.post("/api/admin/models/test-entry", json={"entry": "ollama:z"}).json()
    assert r["status"] in ("ok", "unverified") and r["model"] == "z"
    # an empty body removes the layer's chain
    assert admin.put("/api/admin/models?layer=study:P1/s1", json={}).status_code == 200
    assert not (home / "projects/P1/studies/s1/models.json").exists()


# --------------------------------------------------------------------------- #
# Subscription sign-ins are not offered (see tests/test_harness.py)            #
# --------------------------------------------------------------------------- #
def test_subscription_presets_are_gone(hani2_home):
    from hani2 import providers as prov

    assert not prov.PROVIDERS["github_copilot"].offered and "subscription" not in prov.PROVIDERS["openai"].auth


# --------------------------------------------------------------------------- #
# Review follow-ups                                                            #
# --------------------------------------------------------------------------- #
def test_a_failed_call_with_no_next_entry_shows_no_sticky_banner(hani2_home, monkeypatch):
    import litellm

    from hani2.testing import make_session

    monkeypatch.setenv("HANI2_MODELS", "ollama:only")

    def down(**kw):
        raise litellm.APIConnectionError(message="connection refused", llm_provider="ollama", model="only")

    monkeypatch.setattr(litellm, "completion", down)
    s = make_session()
    with pytest.raises(Exception):
        s.support_agent._complete([], False)
    assert not s.model_error and s.models.peek("assistant").model == "only"


def test_study_settings_without_a_model_are_not_a_chain(study, monkeypatch):
    write(study, "projects/P1/studies/s1/assistant_settings.json", {"mode": "off"})
    monkeypatch.setenv("HANI2_MODELS", "ollama:start")
    with projects.use_study("P1/s1"):
        assert mc.chain_for("assistant")[1].id == "start"


def test_an_assistants_own_settings_name_its_model_without_a_chain(hani2_home, calls):
    from hani2.testing import make_session

    s = make_session(assistant_settings={"provider": "openai", "model": "gpt-own"})
    s.support_agent._complete([], False)
    assert calls[-1]["model"] == "openai/gpt-own"
    write(hani2_home, "settings/models.json", ["ollama:chain"])
    s = make_session(assistant_settings={"provider": "openai", "model": "gpt-own"})
    s.support_agent._complete([], False)
    assert calls[-1]["model"] == "ollama_chat/chain"  # a chain wins over the old keys


def test_claude5_through_any_provider_drops_sampling_and_forced_tools(hani2_home, calls, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key-123456789")
    write(hani2_home, "settings/models.json", [{"provider": "openrouter", "model": "anthropic/claude-opus-5-5",
                                                "params": {"temperature": 0.3}}])
    mc.completion("assistant", [{"role": "user", "content": "x"}], tools=[{"type": "function"}], tool_choice="required")
    assert "temperature" not in calls[-1] and calls[-1]["tool_choice"] == "auto"
    assert mc.forced_tools_ok("claude-opus-5") and mc.forced_tools_ok("gpt-5")
    assert not mc.forced_tools_ok("claude-sonnet-5-5") and not mc.forced_tools_ok("claude-fable-5-2")


def test_a_bare_list_models_file_reads_as_the_default_chain(admin, hani2_home):
    write(hani2_home, "settings/models.json", ["ollama:a"])
    g = admin.get("/api/admin/settings/models?layer=settings")
    assert g.status_code == 200 and g.json()["own"] == {"default": ["ollama:a"]}
    assert admin.get("/api/admin/models?layer=settings").json()["own"] == {"default": ["ollama:a"]}
    assert admin.patch("/api/admin/settings/models?layer=settings", json={"judge": ["ollama:j"]}).status_code == 200
    assert json.loads((hani2_home / "settings/models.json").read_text()) == {"default": ["ollama:a"],
                                                                            "judge": ["ollama:j"]}


def test_llm_opponent_keys_never_reach_files(hani2_home, monkeypatch):
    import litellm

    from hani2.testing import make_session

    monkeypatch.setenv("HANI2_RECORD", "1")
    monkeypatch.setenv("HANI2_LLM_LOG", "1")
    conns.add({"name": "k", "provider": "openai", "auth": "api_key"}, api_key=SECRET,
              headers={"X-Org": "hdr-secret-value-1"})
    write(hani2_home, "settings/models.json", ["k:gpt-5"])
    seen = []

    def leaky(**kw):
        seen.append(kw)
        raise litellm.BadRequestError(message=f"bad key {SECRET} hdr-secret-value-1", llm_provider="openai",
                                      model="gpt-5")

    monkeypatch.setattr(litellm, "completion", leaky)
    from hani2 import llm_logging

    llm_logging._installed = False
    llm_logging.install(force=True)
    s = make_session(opponent="LLMBoulwareTBNegotiator")
    s.start()
    s.wait_for_turn(timeout=10) if "timeout" in s.wait_for_turn.__code__.co_varnames else s.wait_for_turn()
    s.end()
    s.wait_until_done()
    s.close()
    assert any(kw.get("api_key") == SECRET for kw in seen)  # the opponent did get the key
    found = []
    import gzip

    for f in hani2_home.rglob("*"):
        if f.is_file() and "secrets" not in f.parts:
            data = f.read_bytes()
            try:
                data += gzip.decompress(data)
            except OSError:
                pass
            if SECRET.encode() in data or b"hdr-secret-value-1" in data:
                found.append(str(f))
    assert not found, found


def test_every_fallback_is_tried_once_in_order_even_by_concurrent_callers(hani2_home, monkeypatch):
    import threading

    import litellm

    write(hani2_home, "settings/models.json", ["ollama:a", "ollama:b", "ollama:c"])
    tried: dict[str, list[str]] = {}
    both_on_a = threading.Barrier(2, timeout=10)

    def down(**kw):
        model = kw["model"].split("/")[-1]
        tried.setdefault(threading.current_thread().name, []).append(model)
        if model == "a":
            both_on_a.wait()  # both callers fail on the first entry before either falls back
        raise litellm.APIConnectionError(message="connection refused", llm_provider="ollama", model=model)

    monkeypatch.setattr(litellm, "completion", down)
    models = mc.SessionModels()
    models.get("text")
    errors: list[BaseException] = []

    def call():
        try:
            mc.completion("text", [{"role": "user", "content": "x"}], models=models)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=call, name=f"caller{i}") for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert len(errors) == 2 and all(isinstance(e, litellm.APIConnectionError) for e in errors)
    assert tried == {"caller0": ["a", "b", "c"], "caller1": ["a", "b", "c"]}
    # the session's entry only moves forward, one entry at a time, and keeps the last one
    fallbacks = [(c["previous"]["model"], c.get("model")) for c in models.changes if c["action"] == "model_fallback"]
    assert [p for p, n in fallbacks if n] == ["a", "b"]
    assert models.pinned["text"].model == "c"


def test_hard_failure_uses_classes_and_status_codes_before_a_narrow_text_match():
    import litellm

    hard = [
        litellm.NotFoundError(message="nope", llm_provider="openai", model="x"),
        litellm.AuthenticationError(message="bad key", llm_provider="openai", model="x"),
        litellm.RateLimitError(message="slow down", llm_provider="openai", model="x"),
        type("ProxyError", (Exception,), {"status_code": 503})("upstream down"),
        type("ProxyError", (Exception,), {"status_code": 401})("unauthorised"),
        type("ProxyError", (Exception,), {"status_code": 404})("<html>404 Not Found</html>"),
        TimeoutError("timed out"),
        RuntimeError("model 'llama3' not found, try pulling it first"),
        RuntimeError("The model `gpt-x` does not exist or you do not have access to it."),
        RuntimeError("Model not found"),
        RuntimeError("connect: connection refused"),
    ]
    soft = [
        ValueError("tool 'lookup' not found"),
        RuntimeError("the model called function 'quote' which was not found"),
        litellm.BadRequestError(message="user said: my file was not found", llm_provider="openai", model="x"),
        type("ProxyError", (Exception,), {"status_code": 400})("key 'model' not found in payload"),
        KeyError("not found"),
        RuntimeError("404 page not found"),
        FileNotFoundError("prompt.txt"),
        ModuleNotFoundError("no module named 'foo'"),
        ValueError("invalid json schema"),
    ]
    assert [mc.hard_failure(e) for e in hard] == [True] * len(hard)
    assert [mc.hard_failure(e) for e in soft] == [False] * len(soft)
