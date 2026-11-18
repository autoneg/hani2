"""Harness connections (Claude Code, Codex, pi) and the subscription sign-ins that are no longer
offered. No network and no real harness: pi and Codex are fake processes (``tests/fake_harness``),
the Claude Agent SDK is a fake ``query``."""

import json
import os
import stat
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from hani2 import connections as conns
from hani2 import harness
from hani2 import model_chain as mc
from hani2.harness import base as hb

FAKE = Path(__file__).parent / "fake_harness"
KEY = "sk-ant-api-HARNESS-0123456789abcdef"
OKEY = "sk-proj-HARNESS-0123456789abcdef"
#: variables a harness must never see (sign-ins of the server's user, other keys)
FORBIDDEN = ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_OAUTH_TOKEN", "CODEX_API_KEY",
             "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "AWS_ACCESS_KEY_ID", "GEMINI_API_KEY",
             "CLAUDE_CONFIG_DIR", "CODEX_HOME", "PI_CODING_AGENT_DIR")


def _exe(tmp_path: Path, script: str) -> str:
    """An executable that runs ``tests/fake_harness/<script>`` with this Python (its log path is
    written into it: a harness's environment holds nothing HANI2 did not choose)."""
    p = tmp_path / f"bin-{script}"
    log = tmp_path / "harness.log"
    p.write_text(f"#!/bin/sh\nFAKE_HARNESS_LOG={log} exec {sys.executable} {FAKE / script} \"$@\"\n")
    p.chmod(0o755)
    return str(p)


@pytest.fixture
def fakes(tmp_path, monkeypatch):
    """Fake harness executables, a log of their command lines, and secrets of the server's user
    in the environment (which must not reach a harness)."""
    log = tmp_path / "harness.log"
    monkeypatch.setenv("HANI2_PI_PATH", _exe(tmp_path, "fake_pi.py"))
    monkeypatch.setenv("HANI2_CODEX_PATH", _exe(tmp_path, "fake_codex.py"))
    for v in FORBIDDEN:
        monkeypatch.setenv(v, "user-secret-must-not-leak-123456")
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("OPENAI_API_KEY", OKEY)
    hb._VERSIONS.clear()
    yield log
    hb._VERSIONS.clear()


def runs(log: Path) -> list[dict]:
    """The fake harness runs (``--version`` checks left out)."""
    out = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return [r for r in out if "--version" not in r["argv"]]


def assert_isolated(run: dict, home: Path, *, key_var: str | None, key: str | None) -> None:
    env = run["env"]
    for v in FORBIDDEN:
        if v in env:
            assert env[v] != "user-secret-must-not-leak-123456", v
    assert env["HOME"].startswith(str(home / "settings" / "secrets")), env["HOME"]
    assert stat.S_IMODE(os.stat(env["HOME"]).st_mode) == 0o700
    if key_var:
        assert env[key_var] == key
    other_keys = [k for k in env if k.endswith("_API_KEY") and k != key_var]
    assert not other_keys, other_keys
    # an empty, temporary working folder outside the settings folder
    assert "hani2-harness-" in run["cwd"] and not run["cwd"].startswith(str(home))


# --------------------------------------------------------------------------- #
# Subscription sign-ins: not offered                                           #
# --------------------------------------------------------------------------- #
def test_subscription_sign_ins_are_not_offered(hani2_home):
    from hani2 import providers as prov

    with pytest.raises(conns.ConnectionError_, match="not offered"):
        conns.add({"name": "gh", "provider": "github_copilot", "auth": "subscription"})
    with pytest.raises(conns.ConnectionError_, match="not offered"):
        conns.add({"name": "cg", "provider": "openai", "auth": "subscription"})
    assert not any("subscription" in p.auth for p in prov.PROVIDERS.values())
    assert prov.PROVIDERS["github_copilot"].offered is False
    t = {p["id"]: p for p in prov.table()}
    assert t["github_copilot"]["not_offered"] and t["openai"]["sources"]
    with pytest.raises(conns.ConnectionError_, match="not offered"):
        conns.start_login("anthropic")
    # entries that name the old subscription providers say why they are skipped
    r = mc.resolve("assistant", chain=mc.parse_chain("chatgpt:gpt-5.5,copilot:gpt-5"), source=mc.Source("t", {}))
    assert not r.ok and r.skipped[0]["reason"].count("not offered") == 1 and "not offered" in r.skipped[1]["reason"]


def test_stored_subscription_connections_load_disabled(hani2_home):
    f = hani2_home / "settings" / "connections.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"connections": [{"name": "gh", "provider": "github_copilot", "auth": "subscription"},
                                             {"name": "cg", "provider": "openai", "auth": "subscription"}]}))
    gh, cg = conns.get("gh"), conns.get("cg")
    assert gh.disabled and cg.disabled and "not offered" in cg.disabled
    assert conns.has_credentials(gh) == (False, gh.disabled)
    with pytest.raises(conns.ConnectionError_):
        conns.call_kwargs(cg)
    (hani2_home / "settings" / "models.json").write_text(json.dumps(["gh:gpt-5", "cg:gpt-5.5"]))
    r = mc.resolve("assistant")
    assert not r.ok and all("not offered" in s["reason"] for s in r.skipped)
    assert conns.public(gh)["disabled"]
    assert conns.remove("gh") and conns.get("gh") is None


def test_no_login_in_cli_or_api(hani2_home, monkeypatch):
    from hani2.cli import app as cli
    from hani2.server import app, hub

    r = CliRunner().invoke(cli, ["connections", "login", "x"])
    assert r.exit_code != 0
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        assert c.post("/api/admin/connections/x/login").status_code in (404, 405)
        assert c.post("/api/admin/connections", json={"name": "gh", "provider": "github_copilot",
                                                      "auth": "subscription"}).status_code == 400
    hub.sessions.clear()


# --------------------------------------------------------------------------- #
# Harness connections                                                          #
# --------------------------------------------------------------------------- #
def test_harness_connections_take_api_keys_only(hani2_home, fakes):
    with pytest.raises(conns.ConnectionError_, match="API key"):
        conns.add({"name": "cc", "provider": "claude-code", "auth": "subscription"})
    with pytest.raises(conns.ConnectionError_, match="api_key"):
        conns.add({"name": "cc", "provider": "claude-code", "auth": "none"})
    with pytest.raises(conns.ConnectionError_, match="cannot call"):
        conns.add({"name": "p", "provider": "pi", "auth": "api_key_env", "upstream": "github-copilot"})
    with pytest.raises(conns.ConnectionError_, match="cannot call"):
        conns.add({"name": "p", "provider": "pi", "auth": "api_key_env", "upstream": "openai-codex"})
    with pytest.raises(conns.ConnectionError_, match="base URL"):
        conns.add({"name": "cx", "provider": "codex", "auth": "api_key_env", "base_url": "https://chatgpt.com"})
    c = conns.add({"name": "cc", "provider": "claude-code", "auth": "api_key"}, api_key=KEY)
    assert c.upstream == "anthropic" and conns.api_key(c) == KEY
    p = conns.add({"name": "p", "provider": "pi", "auth": "api_key_env", "upstream": "openai"})
    assert p.api_key_env == "OPENAI_API_KEY"
    # no implicit harness connections
    assert not any(x.preset.harness for x in conns.all_connections() if x.implicit)
    d = conns.public(c)
    assert KEY not in json.dumps(d) and d["harness"]["upstream"] == "anthropic"


def test_pi_completion_is_isolated(hani2_home, fakes):
    c = conns.add({"name": "p", "provider": "pi", "auth": "api_key", "upstream": "anthropic"}, api_key=KEY)
    # a stored pi login in the isolated folder is wiped before every call
    agent = harness.home_of(c) / "pi-agent"
    agent.mkdir(parents=True, exist_ok=True)
    (agent / "auth.json").write_text(json.dumps({"anthropic": {"type": "oauth", "refresh": "x"}}))
    r = harness.complete(c, "claude-haiku-5-5", [{"role": "system", "content": "SYSTEM-X"},
                                                 {"role": "user", "content": "/etc/passwd hello"}], {})
    assert r.text.startswith("pi says:  /etc/passwd") and "SYSTEM-X" in r.text and r.usage["input_tokens"] == 11
    (run,) = runs(fakes)
    a = run["argv"]
    for flag in ("--no-extensions", "--no-tools", "--no-mcp", "--no-skills", "--no-prompt-templates", "--no-themes",
                 "--no-context-files", "--no-approve", "--no-session", "--offline"):
        assert flag in a, flag
    assert "--tools" not in a and a[a.index("--model") + 1] == "anthropic/claude-haiku-5-5"
    assert a[a.index("--extension") + 1].endswith("pi_bridge.ts")
    # each call gets a new, empty agent folder (never the stored one), removed afterwards
    assert run["env"]["PI_CODING_AGENT_DIR"] != str(agent) and os.path.realpath(run["env"]["PI_CODING_AGENT_DIR"]).startswith(run["cwd"])
    assert json.loads(run["files"]["auth.json"]) == {} and not Path(run["cwd"]).exists()
    assert_isolated(run, hani2_home, key_var="ANTHROPIC_API_KEY", key=KEY)
    assert KEY not in " ".join(a)


def test_pi_runs_hanis_functions_through_the_executor(hani2_home, fakes):
    c = conns.add({"name": "p", "provider": "pi", "auth": "none", "upstream": "ollama",
                   "base_url": "http://localhost:11434"})
    tools = [{"type": "function", "function": {"name": "get_offer", "description": "d", "parameters": {"type": "object"}}}]
    seen = []
    r = harness.run_tools(c, "qwen3:4b", [{"role": "user", "content": "go"}], tools,
                          lambda n, a: seen.append((n, a)) or {"ok": True, "price": 7}, {})
    assert seen == [("get_offer", {"probe": True})] and '"price": 7' in r.text
    (run,) = runs(fakes)
    assert run["argv"][run["argv"].index("--tools") + 1] == "get_offer"
    models = json.loads(run["files"]["models.json"])
    assert models["providers"]["ollama"]["baseUrl"] == "http://localhost:11434/v1"
    assert_isolated(run, hani2_home, key_var=None, key=None)
    # Ollama cloud models need the server's account sign-in: refused for a harness
    with pytest.raises(harness.HarnessUnavailable, match="cloud"):
        harness.complete(c, "gpt-oss:120b-cloud", [{"role": "user", "content": "x"}])


def test_codex_completion_is_isolated_and_tool_free(hani2_home, fakes):
    c = conns.add({"name": "cx", "provider": "codex", "auth": "api_key_env"})
    home = harness.home_of(c) / "codex-home"
    home.mkdir(parents=True, exist_ok=True)
    (home / "auth.json").write_text('{"tokens": {"access_token": "chatgpt-login"}}')  # a ChatGPT login: removed
    r = harness.complete(c, "gpt-5-mini", [{"role": "system", "content": "JUDGE-SYS"},
                                           {"role": "user", "content": "rate this"}])
    assert r.text == "codex says: rate this | JUDGE-SYS" and r.usage == {"input_tokens": 9, "output_tokens": 3}
    run = [x for x in runs(fakes) if x["argv"][:1] == ["exec"]][0]
    a = run["argv"]
    for flag in ("--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--strict-config"):
        assert flag in a
    assert a[a.index("-s") + 1] == "read-only" and a[-1] == "-"  # the prompt on stdin, never in argv
    disabled = {a[i + 1] for i, x in enumerate(a) if x == "--disable"}
    assert {"shell_tool", "unified_exec", "view_image", "multi_agent", "plugins", "apps", "hooks"} <= disabled
    cfg = dict(x.split("=", 1) for x in a if "=" in x and not x.startswith("-"))
    assert cfg["model_provider"] == '"hani2"' and cfg["model_providers.hani2.env_key"] == '"OPENAI_API_KEY"'
    assert cfg["model_providers.hani2.requires_openai_auth"] == "false" and cfg["forced_login_method"] == '"api"'
    assert cfg["web_search"] == '"disabled"' and cfg["project_doc_max_bytes"] == "0"
    cat = json.loads(run["files"]["catalog"])["models"]
    assert [m["slug"] for m in cat] == ["gpt-5-mini"] and cat[0]["apply_patch_tool_type"] is None
    assert run["env"]["CODEX_HOME"] == str(home) and not (home / "auth.json").exists()
    assert_isolated(run, hani2_home, key_var="OPENAI_API_KEY", key=OKEY)
    assert OKEY not in " ".join(a)
    # no tools at all, and a model the bundled catalog does not know is refused
    assert not harness.supports_tools(c)
    with pytest.raises(harness.HarnessUnavailable):
        harness.run_tools(c, "gpt-5-mini", [{"role": "user", "content": "x"}], [], lambda n, a: None)
    with pytest.raises(harness.HarnessUnavailable, match="bundled"):
        harness.complete(c, "gpt-unknown", [{"role": "user", "content": "x"}])


class _Text:
    def __init__(self, text):
        self.text = text


class _Assistant:
    def __init__(self, content):
        self.content = content


class _Result:
    def __init__(self, result, is_error=False):
        self.result, self.is_error, self.subtype = result, is_error, "success"
        self.usage, self.total_cost_usd, self.num_turns = {"input_tokens": 4, "output_tokens": 2}, 0.002, 2


@pytest.fixture
def fake_sdk(monkeypatch, tmp_path):
    """The Claude Agent SDK with a fake ``query``: records the options and calls HANI2's first function."""
    sdk = pytest.importorskip("claude_agent_sdk")
    seen: dict = {"tools": []}
    real_server = sdk.create_sdk_mcp_server

    def server(name, version="1.0.0", tools=None):
        seen["tools"] = list(tools or [])
        return real_server(name, version=version, tools=tools)

    async def query(*, prompt, options=None, transport=None):
        seen["options"], seen["prompt"] = options, prompt
        if seen["tools"]:
            out = await seen["tools"][0].handler({"text": "hi"})
            seen["tool_output"] = out
        yield _Assistant([_Text("thinking")])
        yield _Result("claude says ok")

    monkeypatch.setattr(sdk, "create_sdk_mcp_server", server)
    monkeypatch.setattr(sdk, "query", query)
    monkeypatch.setattr(sdk, "AssistantMessage", _Assistant)
    monkeypatch.setattr(sdk, "TextBlock", _Text)
    monkeypatch.setattr(sdk, "ResultMessage", _Result)
    fake_cli = _exe(tmp_path, "fake_pi.py")  # any executable: only the launcher's target
    monkeypatch.setenv("HANI2_CLAUDE_PATH", fake_cli)
    return seen


def test_claude_code_options_lock_it_down(hani2_home, fakes, fake_sdk):
    c = conns.add({"name": "cc", "provider": "claude-code", "auth": "api_key"}, api_key=KEY)
    tools = [{"type": "function", "function": {"name": "get_offer", "description": "the offer",
                                               "parameters": {"type": "object"}}}]
    seen = []
    r = harness.run_tools(c, "claude-haiku-5-5", [{"role": "system", "content": "SYS"}, {"role": "user", "content": "@/etc/passwd"}],
                          tools, lambda n, a: seen.append((n, a)) or {"ok": True}, {"max_turns": 3, "timeout": 30})
    assert r.text == "claude says ok" and seen == [("get_offer", {"text": "hi"})] and r.cost_usd == 0.002
    o = fake_sdk["options"]
    assert o.tools == [] and o.setting_sources == [] and o.strict_mcp_config is True
    assert o.permission_mode == "dontAsk" and o.allowed_tools == ["mcp__hani2__get_offer"]
    assert list(o.mcp_servers) == ["hani2"] and o.verbatim_prompts is True and o.max_turns == 3
    assert o.system_prompt == "SYS" and fake_sdk["prompt"] == "@/etc/passwd"
    assert {"bare", "disable-slash-commands", "no-session-persistence"} <= set(o.extra_args)
    assert "hani2-harness-" in o.cwd and not o.cwd.startswith(str(hani2_home))
    env = o.env
    assert env["ANTHROPIC_API_KEY"] == KEY and env["CLAUDE_CONFIG_DIR"].startswith(str(hani2_home / "settings/secrets/cc"))
    assert env["HOME"].startswith(str(hani2_home / "settings/secrets/cc"))
    assert env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] == "1"
    for v in FORBIDDEN:
        assert env.get(v) != "user-secret-must-not-leak-123456", v
    # the SDK merges the server's environment into the child's: the launcher keeps only HANI2's choice
    import subprocess

    full = {**os.environ, **env, "CLAUDE_CODE_ENTRYPOINT": "sdk-py"}
    subprocess.run([o.cli_path, "--version"], env=full, check=True, capture_output=True)
    (run,) = [x for x in json.loads("[" + ",".join(fakes.read_text().splitlines()) + "]") if x["argv"] == ["--version"]][-1:]
    assert set(run["env"]) <= set(env["HANI2_HARNESS_KEEP"].split(",")) | {"PWD", "SHLVL", "_", "__CF_USER_TEXT_ENCODING", "FAKE_HARNESS_LOG"}
    for v in FORBIDDEN:
        assert run["env"].get(v) != "user-secret-must-not-leak-123456", v
    assert run["env"]["ANTHROPIC_API_KEY"] == KEY and run["env"]["CLAUDE_CODE_ENTRYPOINT"] == "sdk-py"


def test_claude_code_and_codex_never_serve_participants(hani2_home, fakes, fake_sdk):
    conns.add({"name": "cc", "provider": "claude-code", "auth": "api_key"}, api_key=KEY)
    conns.add({"name": "cx", "provider": "codex", "auth": "api_key_env"})
    conns.add({"name": "p", "provider": "pi", "auth": "api_key_env", "upstream": "anthropic"})
    chain = mc.parse_chain("cc:claude-haiku-5-5,cx:gpt-5-mini,p:claude-haiku-5-5")
    for purpose in ("assistant", "opponent", "tools", "text"):
        r = mc.resolve(purpose, chain=chain, source=mc.Source("t", {}))
        assert r.connection.name == "p", purpose
        assert "may serve only" in r.skipped[0]["reason"] and len(r.skipped) == 2
        assert purpose == "assistant" or "may serve only" in r.skipped[1]["reason"]
    assert mc.resolve("judge", chain=chain, source=mc.Source("t", {})).connection.name == "cc"
    assert mc.resolve_entry(chain[1]).ok  # the console's Test
    caps = harness.capabilities()
    assert caps["codex"]["assistant_tools"] is False and caps["pi"]["purposes"] is None
    assert caps["claude-code"]["purposes"] == ["judge", "test"]


def test_harness_completion_through_litellm_and_the_chain(hani2_home, fakes):
    """``model_chain.completion`` (text, tools, judge) and negmas-llm opponents call litellm: the
    custom provider routes the call to the harness; function schemas are refused there."""
    conns.add({"name": "p", "provider": "pi", "auth": "api_key", "upstream": "anthropic"}, api_key=KEY)
    (hani2_home / "settings" / "models.json").write_text(json.dumps(["p:claude-haiku-5-5"]))
    r = mc.completion("text", [{"role": "user", "content": "hello"}])
    assert r.choices[0].message.content.startswith("pi says: hello")
    kw = mc.litellm_kwargs(mc.resolve("opponent"))
    assert kw["model"] == "hani2_harness/claude-haiku-5-5" and kw["api_base"] == "hani2-harness://p"
    assert KEY not in json.dumps(kw)
    import litellm

    with pytest.raises(Exception, match="function schemas"):
        litellm.completion(messages=[{"role": "user", "content": "x"}],
                           tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}], **kw)


def test_the_assistant_runs_a_turn_through_a_harness(hani2_home, fakes):
    from hani2.testing import make_session

    conns.add({"name": "p", "provider": "pi", "auth": "none", "upstream": "ollama"})
    os.environ["HANI2_MODELS"] = "p:qwen3:4b"
    try:
        s = make_session()
        a = s.support_agent
        names = [t["function"]["name"] for t in a.dispatcher.schemas()]
        a._run_turn("What is on the table?")
    finally:
        os.environ.pop("HANI2_MODELS", None)
    calls = [m for m in a.messages if m.get("tool_calls")]
    results = [m for m in a.messages if m.get("role") == "tool"]
    assert calls and calls[0]["tool_calls"][0]["function"]["name"] == names[0]
    assert results and results[0]["name"] == names[0]
    assert a.messages[-1]["role"] == "assistant" and a.messages[-1]["content"].startswith(f"called {names[0]}")
    (run,) = runs(fakes)
    assert run["argv"][run["argv"].index("--tools") + 1] == ",".join(names)


def test_ollama_cloud_models_through_a_local_server_are_refused(hani2_home):
    r = mc.resolve("assistant", chain=mc.parse_chain("ollama:gpt-oss:120b-cloud,ollama:qwen3:4b"),
                   source=mc.Source("legacy", {}, implicit=True))
    assert r.model == "qwen3:4b" and "Team plan" in r.skipped[0]["reason"]
    only = mc.resolve("assistant", chain=mc.parse_chain("ollama:gpt-oss:120b-cloud"),
                      source=mc.Source("legacy", {}, implicit=True))
    assert not only.ok  # not even the old settings use it unchecked


def test_cli_and_admin_harness(hani2_home, fakes, monkeypatch):
    from hani2.cli import app as cli
    from hani2.server import app, hub

    run = CliRunner()
    r = run.invoke(cli, ["connections", "add", "p", "--provider", "pi", "--upstream", "ollama", "--auth", "none"])
    assert r.exit_code == 0, r.output
    r = run.invoke(cli, ["connections", "add", "cc", "--provider", "claude-code", "--auth", "api_key_env"])
    assert r.exit_code == 0, r.output
    r = run.invoke(cli, ["connections", "test", "p", "--model", "qwen3:4b"])
    assert r.exit_code == 0 and "works" in r.output, r.output
    r = run.invoke(cli, ["connections", "providers"])
    assert "github_copilot" in r.output and "not offered" in r.output and "claude-code" in r.output
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        hs = {h["id"]: h for h in c.get("/api/admin/providers").json()["harnesses"]}
        assert hs["pi"]["status"]["found"] and hs["pi"]["assistant_tools"] and not hs["codex"]["assistant_tools"]
        assert hs["claude-code"]["auth"] == ["api_key", "api_key_env"]
        t = c.post("/api/admin/connections/p/test", json={"model": "qwen3:4b"}).json()
        assert t["ok"] and t["reply"].startswith("pi says")
        lst = c.get("/api/admin/connections").json()["connections"]
        assert KEY not in json.dumps(lst) and any(x["name"] == "cc" and x["harness"]["upstream"] == "anthropic" for x in lst)
    hub.sessions.clear()


def test_harness_errors_are_redacted(hani2_home, fakes, monkeypatch):
    c = conns.add({"name": "p", "provider": "pi", "auth": "api_key", "upstream": "anthropic"}, api_key=KEY)
    monkeypatch.setenv("HANI2_PI_PATH", "/nonexistent/pi")
    hb._VERSIONS.clear()
    assert not conns.has_credentials(c)[0]
    err = harness.base.safe_execute(lambda n, a: (_ for _ in ()).throw(RuntimeError(f"boom {KEY}")), "f", {})
    assert KEY not in json.dumps(err)


def test_entry_params_reach_the_harness_and_opponents_drop_ufun_tools(hani2_home, fakes):
    from types import SimpleNamespace

    from hani2.agents import apply_model

    conns.add({"name": "p", "provider": "pi", "auth": "none", "upstream": "ollama"})
    (hani2_home / "settings" / "models.json").write_text(json.dumps(
        [{"connection": "p", "model": "qwen3:4b", "params": {"effort": "low", "timeout": 30}}]))
    mc.completion("text", [{"role": "user", "content": "hi"}])
    (run,) = runs(fakes)
    assert run["argv"][run["argv"].index("--thinking") + 1] == "low"
    # an LLM opponent through a harness reasons in text: its utility tools are turned off
    opp = SimpleNamespace(llm_kwargs={}, provider="ollama", model="x", use_ufun_tools=True, api_base=None)
    apply_model(opp, mc.resolve("opponent"))
    assert opp.use_ufun_tools is False and opp.provider == "hani2_harness" and opp.api_base == "hani2-harness://p"
    assert harness.default_model(conns.get("p")) == "qwen3:4b-instruct"
    assert conns.public(conns.get("p"))["harness"]["assistant_tools"] is True


def test_a_harness_reports_its_cost_to_the_recording(hani2_home, fakes, monkeypatch):
    from hani2.recording import recorder
    from hani2.support_agent.runtime import _harness_response

    seen = {}

    class R:
        def llm(self, **kw):
            seen.update(kw)

    monkeypatch.setattr(recorder, "current", lambda: R())
    rep = harness.HarnessReply(text="ok", usage={"input_tokens": 3, "output_tokens": 1}, cost_usd=0.004)
    recorder.record_llm_call({"model": "hani2_harness/m", "messages": []}, _harness_response(rep), 0.1)
    assert seen["cost"] == 0.004 and seen["usage"]["prompt_tokens"] == 3
