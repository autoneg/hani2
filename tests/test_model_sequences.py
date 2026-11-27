"""Named model sequences: built-ins, per-name merge across the settings / project / study layers,
disabling and overriding, purposes that name a sequence, thinking / effort parameters, session
pinning, the Assistant's ``model_choice`` and ``own_models`` abilities, tools, the CLI and the admin
API. No network: model calls are faked."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hani2 import connections as conns
from hani2 import model_chain as mc
from hani2 import projects

SECRET = "sk-own-SECRET-0123456789abcdef"


def write(home, rel, data):
    p = home / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture
def calls(monkeypatch):
    import litellm

    seen = []

    def fake(**kw):
        seen.append(kw)
        msg = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)

    monkeypatch.setattr(litellm, "completion", fake)
    return seen


@pytest.fixture
def study(hani2_home):
    projects.create_project("P1", full_name="P", kind="assistant")
    projects.create_study("P1/s1", type="online", title="S")
    return hani2_home


# --------------------------------------------------------------------------- #
# Built-ins and parsing                                                        #
# --------------------------------------------------------------------------- #
def test_builtin_sequences(hani2_home):
    names = mc.sequence_names()
    assert names[:2] == ["default", "judge"]
    assert {"tiny", "offline", "small", "medium", "large"} <= set(names)
    for n in ("tiny", "offline"):  # only the local Ollama server
        ch, src, why = mc.sequence_chain(n)
        assert src.id == "builtin" and not why and ch
        assert {e.connection for e in ch} == {"ollama-local"}
    tiny = mc.resolve("tools", sequence="tiny")
    assert tiny.ok and tiny.model == "qwen3:0.6b" and tiny.connection.name == "ollama-local"
    assert tiny.record()["sequence"] == "tiny" and tiny.key == "tools@tiny"


def test_parse_models_keys_and_errors():
    p = mc.parse_models({"default": ["ollama:a"], "judge": "strict",
                         "sequences": {"strict": [{"provider": "ollama", "model": "j", "params": {"effort": "high"}}],
                                       "small": {"entries": ["ollama:s"], "description": "cheap"},
                                       "large": {"disabled": True}, "medium": None}})
    assert p.refs == {"judge": "strict"} and p.chains["default"][0].model == "a"
    assert p.sequences["small"].description == "cheap" and p.sequences["large"].disabled and p.sequences["medium"].disabled
    for bad in ({"sequences": {"default": {"disabled": True}}}, {"sequences": {"x y": ["ollama:a"]}},
                {"sequences": {"s": []}}, {"sequences": {"s": {"entries": ["ollama:a"], "bogus": 1}}},
                {"judge": "judge"}, {"sequences": {"s": [{"provider": "openai", "model": "m", "api_key": "k"}]}}):
        assert mc.check_chains(bad), bad
    # a sequence named under "sequences" with a purpose name is that purpose's chain
    assert mc.parse_models({"sequences": {"judge": ["ollama:j"]}}).chains["judge"][0].model == "j"


# --------------------------------------------------------------------------- #
# Layers: per-name merge, override, disable                                    #
# --------------------------------------------------------------------------- #
def test_sequences_merge_per_name_across_layers(study):
    home = study
    write(home, "settings/models.json", {"sequences": {"house": ["ollama:global-house"], "large": ["ollama:global-large"]}})
    write(home, "projects/P1/models.json", {"sequences": {"house": ["ollama:project-house"]}})
    write(home, "projects/P1/studies/s1/models.json", {"sequences": {"large": {"disabled": True},
                                                                      "mine": ["ollama:study-mine"]}})
    assert mc.resolve("tools", sequence="large").model == "global-large"  # global overrides the built-in
    with projects.use_study("P1/s1"):
        assert mc.resolve("tools", sequence="house").model == "project-house"  # project beats global
        assert mc.resolve("tools", sequence="mine").model == "study-mine"
        r = mc.resolve("tools", sequence="large")
        assert not r.ok and "disabled" in r.error and "study:P1/s1" in r.error
        assert "large" not in mc.sequence_names() and "large" in mc.sequence_names(include_disabled=True)
        eff = {d["name"]: d for d in mc.effective_sequences()}
        assert eff["large"]["disabled"] and eff["house"]["source"] == "project:P1" and eff["tiny"]["builtin"]
        # a layer with only sequences does not hide the purposes' chains of the layers below
        assert mc.chain_for("assistant")[1].id != "study:P1/s1"
    r = mc.resolve("tools", sequence="nope")
    assert not r.ok and "no model sequence named 'nope'" in r.error


def test_purpose_names_a_sequence(study):
    home = study
    write(home, "settings/models.json", {"default": ["ollama:base"],
                                         "sequences": {"strict": [{"provider": "ollama", "model": "judge-m",
                                                                   "params": {"temperature": 0}}]}})
    write(home, "projects/P1/studies/s1/models.json", {"judge": "strict", "assistant": "small"})
    with projects.use_study("P1/s1"):
        ch, src = mc.chain_for("judge")
        assert [e.model for e in ch] == ["judge-m"] and src.id == "study:P1/s1"
        assert mc.resolve("assistant").model == "qwen3:4b-instruct"  # small: only the local entry has credentials
        assert mc.effective_chains()["judge"]["sequence"] == "strict"
        assert mc.resolve("text").model == "base"  # unaffected purposes keep the default chain
    # a purpose naming a missing or disabled sequence fails visibly (no silent fall-through)
    write(home, "projects/P1/studies/s1/models.json", {"assistant": "smal"})
    with projects.use_study("P1/s1"):
        r = mc.resolve("assistant")
        assert not r.ok and "names the model sequence 'smal'" in r.error and r.source == "study:P1/s1"
        assert mc.unknown_refs({"assistant": "smal"}) and not mc.unknown_refs({"assistant": "small"})
        assert mc.unknown_refs({"assistant": "x", "sequences": {"x": {"disabled": True}}})
    # a cycle is refused, not followed forever
    write(home, "settings/models.json", {"default": ["ollama:base"], "assistant": "loop",
                                         "sequences": {"loop": ["ollama:x"]}})
    assert mc.resolve("assistant").model == "x"


# --------------------------------------------------------------------------- #
# Parameters                                                                   #
# --------------------------------------------------------------------------- #
def test_thinking_and_effort_per_provider():
    tk = mc.thinking_kwargs
    assert tk("ollama", "qwen3:4b", False, None) == {"think": False}
    assert tk("ollama", "qwen3:4b", True, None) == {"think": True}
    assert tk("ollama", "gpt-oss:20b", None, "high") == {"reasoning_effort": "high"}
    assert tk("anthropic", "claude-opus-5-5", 2048, None) == {"thinking": {"type": "enabled", "budget_tokens": 2048}}
    assert tk("anthropic", "claude-opus-5-5", True, None) == {"reasoning_effort": "medium"}
    assert tk("openai", "gpt-5", None, "low") == {"reasoning_effort": "low"}
    assert tk("openai", "gpt-5", False, None) == {}
    assert tk("openai", "gpt-5", "high", None) == {"reasoning_effort": "high"}
    assert tk("openai", "gpt-5", "false", None) == {}


def test_entry_parameters_reach_the_call(hani2_home, calls):
    write(hani2_home, "settings/models.json", {"sequences": {"think": [
        {"connection": "ollama-local", "model": "qwen3:8b", "params": {"thinking": False, "temperature": 0.3,
                                                                     "top_p": 0.9, "max_tokens": 100}}]}})
    mc.completion("tools", [{"role": "user", "content": "hi"}], sequence="think")
    kw = calls[-1]
    assert kw["model"] == "ollama_chat/qwen3:8b" and kw["think"] is False and kw["temperature"] == 0.3
    assert kw["top_p"] == 0.9 and "thinking" not in kw


# --------------------------------------------------------------------------- #
# Sessions, the Assistant and tools                                            #
# --------------------------------------------------------------------------- #
def test_session_pins_each_sequence_and_records_it(hani2_home, calls, monkeypatch):
    from hani2.testing import make_session

    monkeypatch.setenv("HANI2_MODELS", "ollama:asst-model")
    s = make_session()
    sa = s.support_agent
    assert sa.capabilities.has("model_choice") and not sa.capabilities.has("own_models")  # the defaults
    assert {d["name"] for d in sa.model_sequences()} >= {"default", "judge", "tiny", "offline", "small"}
    assert sa.use_model_sequence("tiny") == {"ok": True, "sequence": "tiny", "model": "ollama-local:qwen3:0.6b"}
    sa._complete([], False)
    assert calls[-1]["model"] == "ollama_chat/qwen3:0.6b"
    assert s.models.peek("assistant", "tiny").sequence == "tiny"
    assert s.models.peek("assistant").model == "asst-model"  # the purpose's own pin is kept
    assert sa.ask_llm("hello", sequence="offline") == "ok" and calls[-1]["model"] == "ollama_chat/qwen3:4b-instruct"
    assert not sa.use_model_sequence("nope")["ok"] and sa.model_sequence == "tiny"
    assert sa.use_model_sequence("")["ok"] and sa.model_sequence == ""
    sa._complete([], False)
    assert calls[-1]["model"] == "ollama_chat/asst-model"
    rec = json.loads(s.models.attribution()["llm_models"])
    assert rec["assistant@tiny"]["sequence"] == "tiny" and rec["assistant"]["sequence"] == ""
    # a tool asks for a sequence by name
    from hani2.llm_service import complete

    assert complete("x", session=s, sequence="tiny") == "ok" and calls[-1]["model"] == "ollama_chat/qwen3:0.6b"
    assert s.models.peek("tools", "tiny") is not None


def test_model_choice_can_be_withheld(hani2_home, calls):
    from hani2.testing import make_session

    s = make_session(assistant_settings={"capabilities": {"model_choice": False}})
    sa = s.support_agent
    assert not sa.use_model_sequence("tiny")["ok"]
    sa.model_sequence = "tiny"  # set by a subclass: ignored without the capability
    assert sa._sequence() == ""
    with pytest.raises(PermissionError):
        sa.ask_llm("x", sequence="tiny")
    names = [f["function"]["name"] for f in sa.dispatcher.schemas()]
    assert "use_model_sequence" not in names and "define_model_sequence" not in names


def test_own_models_off_by_default_and_secret_when_on(hani2_home, calls):
    from hani2 import events as ev
    from hani2.support_agent.capabilities import ADMIN_ONLY_CAPABILITIES
    from hani2.testing import make_session

    assert {"own_models", "model_choice"} <= ADMIN_ONLY_CAPABILITIES
    s = make_session()
    assert not s.support_agent.define_model_sequence("mine", ["ollama:x"])["ok"]
    assert "define_model_sequence" not in [f["function"]["name"] for f in s.support_agent.dispatcher.schemas()]

    s = make_session(assistant_settings={"capabilities": {"own_models": True}})
    sa = s.support_agent
    assert "define_model_sequence" in [f["function"]["name"] for f in sa.dispatcher.schemas()]
    assert not sa.define_model_sequence("small", ["ollama:x"])["ok"]  # the study's names are taken
    r = sa.define_model_sequence("mine", [{"provider": "openai", "model": "gpt-own", "api_key": SECRET,
                                           "api_base": "https://my.server/v1", "params": {"effort": "low"}}],
                                 "my own server")
    assert r["ok"] and SECRET not in json.dumps(r)
    assert any(d["name"] == "mine" and d["source"] == "assistant" for d in sa.model_sequences())
    assert sa.ask_llm("hi", sequence="mine") == "ok"
    kw = calls[-1]
    assert kw["api_key"] == SECRET and kw["api_base"] == "https://my.server/v1" and kw["reasoning_effort"] == "low"
    # the key never reaches records, events or error texts
    assert SECRET not in json.dumps(s.models.records(), default=str)
    assert SECRET not in conns.redact(f"failed with {SECRET}")
    # the language model can define one too (its own keyless server)
    out = sa.dispatcher.execute("define_model_sequence", {"name": "mine2", "entries": [
        {"provider": "ollama", "model": "own-small", "api_base": "http://own.example:11434"}]})
    assert out["ok"]
    assert sa.dispatcher.execute("use_model_sequence", {"name": "mine2"})["ok"]
    sa._complete([], False)
    assert calls[-1]["model"] == "ollama_chat/own-small" and calls[-1]["api_base"] == "http://own.example:11434"
    lst = sa.dispatcher.execute("list_model_sequences", {})
    assert lst["current"] == "mine2" and any(x["name"] == "mine2" for x in lst["sequences"])
    # with only own_models, a study sequence cannot be chosen
    assert not sa.use_model_sequence("tiny")["ok"]


def test_own_entries_never_use_the_servers_keys(hani2_home, calls, monkeypatch):
    from hani2.testing import make_session

    server_key = "sk-server-SECRET-0123456789abcdef"
    monkeypatch.setenv("OPENAI_API_KEY", server_key)
    monkeypatch.setenv("SOME_SERVER_VAR", server_key)
    conns.add({"name": "oa", "provider": "openai", "auth": "api_key"}, api_key=server_key)
    s = make_session(assistant_settings={"capabilities": {"own_models": True}})
    sa = s.support_agent
    # an address of its own without a key: nothing is sent to sign in
    assert sa.define_model_sequence("evil", [{"provider": "openai", "model": "m",
                                              "api_base": "https://attacker.example/v1"}])["ok"]
    sa.ask_llm("hi", sequence="evil")
    assert "api_key" not in calls[-1] and server_key not in json.dumps(calls[-1], default=str)
    # the server's environment, the admin's connections and plain entries are refused
    for entries in ([{"provider": "openai", "model": "m", "api_key_env": "SOME_SERVER_VAR"}],
                    ["openai:gpt-5"], [{"provider": "openai", "model": "gpt-5"}],
                    [{"connection": "oa", "model": "gpt-5", "api_key": "sk-x-0123456789abcdef"}],
                    [{"provider": "claude-code", "model": "x", "api_key": "sk-x-0123456789abcdef"}]):
        r = sa.define_model_sequence("evil2", entries)
        assert not r["ok"], entries


def test_own_key_never_reaches_results_events_or_recordings(hani2_home, calls, monkeypatch):
    import csv
    import gzip

    from hani2.testing import make_session

    monkeypatch.setenv("HANI2_RECORD", "1")
    s = make_session(assistant_settings={"capabilities": {"own_models": True, "model_choice": True}})
    sa = s.support_agent
    assert sa.define_model_sequence("mine", [{"provider": "openai", "model": "gpt-own", "api_key": SECRET}])["ok"]
    assert sa.use_model_sequence("mine")["ok"]
    sa._complete([], False)
    assert calls[-1]["api_key"] == SECRET
    s.start()
    s.wait_for_turn()
    s.end()
    s.wait_until_done()
    s.close()
    found = []
    for f in hani2_home.rglob("*"):
        if not f.is_file():
            continue
        data = f.read_bytes()
        if SECRET.encode() in data:
            found.append(str(f))
        if f.suffix in (".gz", ".hrec"):
            try:
                if SECRET.encode() in gzip.decompress(data):
                    found.append(str(f))
            except OSError:
                pass
    assert not found
    assert SECRET not in json.dumps(s.snapshot(), default=str)
    rows = [r for f in hani2_home.rglob("results.csv") for r in csv.DictReader(open(f))]
    # the results name the entry of the sequence the Assistant used for its replies
    assert rows and rows[0]["assistant_llm"] == "assistant-mine-1:gpt-own"
    assert json.loads(rows[0]["llm_models"])["assistant@mine"]["sequence"] == "mine"
    assert list(hani2_home.rglob("*.hrec*"))


def test_assistant_class_sequence_is_chosen_at_start_and_attributed(hani2_home, calls, monkeypatch):
    from hani2.support_agent.runtime import SupportAgent
    from hani2.testing import make_session

    monkeypatch.setattr(SupportAgent, "model_sequence", "tiny")
    monkeypatch.setenv("HANI2_MODELS", "ollama:asst-model")
    s = make_session()
    assert s.models.peek("assistant", "tiny") is not None and s.models.peek("assistant") is None
    assert s.models.attribution()["assistant_llm"] == "ollama-local:qwen3:0.6b"


# --------------------------------------------------------------------------- #
# CLI and admin API                                                            #
# --------------------------------------------------------------------------- #
def test_cli_lists_and_resolves_sequences(hani2_home):
    from hani2.cli import app

    r = CliRunner().invoke(app, ["models", "list"])
    assert r.exit_code == 0 and "Named sequences:" in r.output and "tiny (from builtin)" in r.output
    r = CliRunner().invoke(app, ["models", "resolve", "--sequence", "tiny", "--json"])
    assert r.exit_code == 0 and json.loads(r.output)["tiny"]["model"] == "qwen3:0.6b"


@pytest.fixture
def admin(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        yield c
    hub.sessions.clear()


def test_admin_sequences(admin, study):
    body = {"judge": "strict", "sequences": {"strict": {"entries": ["ollama:j"], "description": "d"},
                                             "large": {"disabled": True}}}
    assert admin.put("/api/admin/models?layer=project:P1", json=body).status_code == 200
    g = admin.get("/api/admin/models?layer=study:P1/s1").json()
    seqs = {d["name"]: d for d in g["sequences"]}
    assert seqs["strict"]["source"] == "project:P1" and seqs["large"]["disabled"] and seqs["tiny"]["builtin"]
    assert {d["name"]: d for d in g["inherited_sequences"]}["large"]["disabled"]
    assert g["effective"]["judge"]["sequence"] == "strict" and "tiny" in g["builtin_sequences"]
    r = admin.post("/api/admin/models/resolve?layer=study:P1/s1", json={}).json()
    assert r["purposes"]["judge"]["model"] == "j" and r["sequences"]["tiny"]["model"] == "qwen3:0.6b"
    assert r["sequences"]["large"]["status"] == "none"
    # an unsaved draft
    r = admin.post("/api/admin/models/resolve?layer=settings",
                   json={"chains": {"assistant": "d1", "sequences": {"d1": ["ollama:draft"]}}}).json()
    assert r["purposes"]["assistant"]["model"] == "draft" and r["sequences"]["d1"]["model"] == "draft"
    assert admin.put("/api/admin/models?layer=settings", json={"sequences": {"bad name": ["ollama:x"]}}).status_code == 400
    # a purpose may not name a sequence that does not exist, or is disabled, at the layer
    r = admin.put("/api/admin/models?layer=study:P1/s1", json={"assistant": "smal"})
    assert r.status_code == 400 and "smal" in r.text
    assert admin.put("/api/admin/models?layer=study:P1/s1", json={"assistant": "large"}).status_code == 400
    assert admin.put("/api/admin/models?layer=study:P1/s1", json={"assistant": "tiny"}).status_code == 200
