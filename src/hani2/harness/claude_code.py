"""The Claude Code harness, through the Claude Agent SDK (``pip install 'hani2[harness]'``).

Usage rules (checked 2026-11-18):

* https://code.claude.com/docs/en/legal-and-compliance: "Developers building products or services
  that interact with Claude's capabilities, including those using the Agent SDK, should use API key
  authentication through Claude Console or a supported cloud provider. Anthropic does not permit
  third-party developers to offer Claude.ai login into their own applications, or to route requests
  through Free, Pro, Max, or Ultra plan credentials on behalf of their users." The same page, on
  running Claude Code in products or services: "Customers may not pay for, resell, or intermediate
  Claude usage on their end users' behalf. Each end user must authenticate with their own Anthropic
  API key, Claude subscription plan credentials, or 3P inference provider credential".
* https://code.claude.com/docs/en/agent-sdk/overview: "Unless previously approved, Anthropic does
  not allow third party developers to offer claude.ai login or rate limits for their products,
  including agents built on the Claude Agent SDK."

What HANI2 enforces:

* **API key only.** The child runs with ``--bare`` ("Anthropic auth is strictly ANTHROPIC_API_KEY or
  apiKeyHelper via --settings (OAuth and keychain are never read)", ``claude --help``), an isolated
  ``CLAUDE_CONFIG_DIR`` and ``HOME`` under ``settings/secrets/<name>/``, and an environment reduced
  to an allowlist by a launcher (the SDK merges its ``env`` over the server's, so OAuth variables
  such as ``CLAUDE_CODE_OAUTH_TOKEN`` or ``ANTHROPIC_AUTH_TOKEN`` would otherwise reach it).
* **Not for participants (HANI2's conservative reading).** The Agent SDK's licence says the
  Commercial Terms govern it "including when you use it to power products and services that you
  make available to your own customers and end users", which points towards allowing it; but the
  conditions for running Claude Code in products say "Each end user must authenticate with their
  own Anthropic API key, Claude subscription plan credentials, or 3P inference provider
  credential", and study participants cannot. Where the terms leave doubt, HANI2 does not take the
  risk: the harness serves only the purposes the operator uses it for (the evaluation judge, the
  console's Test): :data:`PURPOSES`. For participant-facing purposes use the ``anthropic`` provider
  (the Messages API with an API key). Anthropic's sales team can settle the question for a study.
* **Locked down.** ``tools=[]`` (no built-in tool), ``setting_sources=[]``, ``--strict-mcp-config``
  (only HANI2's in-process server), ``permission_mode="dontAsk"`` with HANI2's functions as the only
  allowed tools, ``verbatim_prompts`` (no ``@file`` expansion, no slash commands),
  ``--disable-slash-commands``, ``--no-session-persistence``, no auto memory, an empty working folder,
  ``max_turns``, ``max_budget_usd`` and a time cap.
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path
from typing import Any

from hani2.harness.base import (
    PASSTHROUGH,
    Execute,
    HarnessAdapter,
    HarnessError,
    HarnessReply,
    HarnessTimeout,
    HarnessUnavailable,
    Limits,
    ToolCall,
    child_env,
    cli_version,
    empty_workdir,
    find_cli,
    private_dir,
    render_prompt,
    safe_execute,
    split_system,
    tool_specs,
)

#: purposes Claude Code may serve here (see the module's docstring)
PURPOSES = ("judge", "test")
#: the in-process MCP server that carries HANI2's functions (tools are ``mcp__hani2__<name>``)
SERVER = "hani2"
EXTRA_MISSING = "the Claude Code harness needs the Claude Agent SDK: pip install 'hani2[harness]'"

#: variables the SDK itself adds to the child's environment (kept by the launcher)
_SDK_VARS = ("CLAUDE_CODE_ENTRYPOINT", "CLAUDE_AGENT_SDK_VERSION")

_LAUNCHER = '''#!{python} -I
# HANI2's launcher for the Claude Code CLI: keeps only the variables HANI2 chose (the Agent SDK
# merges the server's environment into the child's), then runs the CLI. No secret is in argv.
import os, sys
keep = set(filter(None, os.environ.get("HANI2_HARNESS_KEEP", "").split(",")))
env = {{k: v for k, v in os.environ.items() if k in keep}}
os.execve({cli!r}, [{cli!r}, *sys.argv[1:]], env)
'''


def _sdk():
    try:
        import claude_agent_sdk
    except ImportError:
        raise HarnessUnavailable(EXTRA_MISSING) from None
    return claude_agent_sdk


def cli_path() -> str | None:
    """The Claude Code CLI that runs: ``$HANI2_CLAUDE_PATH``, else the SDK's bundled one, else ``claude``."""
    explicit = find_cli((), "HANI2_CLAUDE_PATH")
    if explicit:
        return explicit
    try:
        import claude_agent_sdk

        bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / "claude"
        if bundled.is_file():
            return str(bundled)
    except ImportError:
        pass
    return find_cli(("claude",), "HANI2_CLAUDE_PATH")


class ClaudeCode(HarnessAdapter):
    id = "claude-code"
    label = "Claude Code"
    tools = True
    purposes = PURPOSES
    upstreams = {"anthropic": ("ANTHROPIC_API_KEY", "Anthropic (API key from the Claude Console)")}
    default_upstream = "anthropic"
    default_models = {"anthropic": "claude-haiku-5-5"}
    extra = "harness"
    sources = ("https://code.claude.com/docs/en/legal-and-compliance",
               "https://code.claude.com/docs/en/agent-sdk/overview",
               "https://code.claude.com/docs/en/headless#start-faster-with-bare-mode")
    auth_reason = ("Anthropic does not permit third-party applications to offer claude.ai login or to route "
                   "requests through Claude plan credentials; the Agent SDK must use an API key. Its terms for "
                   "running Claude Code in a product also say end users must not be served on the operator's "
                   "behalf, so it is used only for the judge and the console's Test.")

    def status(self) -> dict[str, Any]:
        try:
            import claude_agent_sdk  # noqa: F401
        except ImportError:
            return {"found": False, "path": "", "version": "", "error": EXTRA_MISSING}
        info = dict(cli_version(cli_path()))
        try:
            from claude_agent_sdk import __version__ as sdk_version

            info["sdk"] = sdk_version
            if info.get("version"):
                info["version"] = f"{info['version']} (Agent SDK {sdk_version})"
        except ImportError:  # pragma: no cover
            pass
        return info

    def check_model(self, c: Any, model: str) -> str:
        return "" if model.startswith("claude") or model in ("opus", "sonnet", "haiku", "fable") else \
            f"{model!r} is not a Claude model"

    # ------------------------------------------------------------------ #
    def _launcher(self, c: Any) -> Path:
        from hani2 import harness

        cli = cli_path()
        if not cli:
            raise HarnessUnavailable("the Claude Code CLI was not found (install 'hani2[harness]', which bundles it)")
        f = harness.home_of(c) / "claude-launcher.py"
        text = _LAUNCHER.format(python=sys.executable, cli=cli)
        if not f.exists() or f.read_text(encoding="utf-8") != text:
            f.write_text(text, encoding="utf-8")
            f.chmod(0o700)
        return f

    def build(self, c: Any, model: str, *, system: str, prompt: str, workdir: Path, limits: Limits,
              tools: list[dict] | None = None, params: dict | None = None, execute: Execute | None = None,
              calls: list[ToolCall] | None = None) -> dict[str, Any]:
        """``{options, prompt}``: the :class:`claude_agent_sdk.ClaudeAgentOptions` of one call."""
        from hani2 import harness

        sdk = _sdk()
        home = harness.home_of(c)
        config = private_dir(home / "claude-config")
        extra = {"CLAUDE_CONFIG_DIR": str(config), "ANTHROPIC_API_KEY": harness.secret_for(c),
                 "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                 "CLAUDE_CODE_SKIP_PROMPT_HISTORY": "1", "ENABLE_CLAUDEAI_MCP_SERVERS": "false",
                 "DISABLE_AUTOUPDATER": "1", "DISABLE_TELEMETRY": "1"}
        env = child_env(home, extra)
        env["HANI2_HARNESS_KEEP"] = ",".join(sorted({*env, *_SDK_VARS, "HANI2_HARNESS_KEEP"}))
        specs = tool_specs(tools or [])
        servers: dict[str, Any] = {}
        allowed: list[str] = []
        if specs:
            servers[SERVER] = sdk.create_sdk_mcp_server(SERVER, tools=[self._tool(sdk, s, execute, calls)
                                                                      for s in specs])
            allowed = [f"mcp__{SERVER}__{s['name']}" for s in specs]
        effort = (params or {}).get("effort") or (params or {}).get("reasoning_effort")
        opts: dict[str, Any] = dict(
            tools=[], allowed_tools=allowed, setting_sources=[], strict_mcp_config=True, mcp_servers=servers,
            permission_mode="dontAsk", system_prompt=system or "You are a helpful assistant.", model=model,
            max_turns=limits.max_turns, cwd=str(workdir), env=env, cli_path=str(self._launcher(c)),
            extra_args={"bare": None, "disable-slash-commands": None, "no-session-persistence": None},
            verbatim_prompts=True,
        )
        if limits.max_budget_usd:
            opts["max_budget_usd"] = limits.max_budget_usd
        if effort in ("low", "medium", "high", "xhigh", "max"):
            opts["effort"] = effort
        return {"options": sdk.ClaudeAgentOptions(**opts), "prompt": prompt, "env": env, "cwd": str(workdir)}

    @staticmethod
    def _tool(sdk: Any, spec: dict, execute: Execute | None, calls: list[ToolCall] | None) -> Any:
        schema = dict(spec["parameters"] or {})
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})  # the SDK reads a dict without "properties" as {name: type}

        async def handler(args: dict) -> dict:
            if execute is None:  # pragma: no cover - functions are offered only with an executor
                return {"content": [{"type": "text", "text": "not available"}], "is_error": True}
            result = safe_execute(execute, spec["name"], args)
            if calls is not None:
                calls.append(ToolCall(id="", name=spec["name"], arguments=dict(args or {}), result=result))
            return {"content": [{"type": "text", "text": json.dumps(result, default=str)}]}

        return sdk.tool(spec["name"], spec["description"] or spec["name"], schema)(handler)

    # ------------------------------------------------------------------ #
    def _run(self, c: Any, model: str, messages: list[dict], params: dict[str, Any], tools: list[dict] | None,
             execute: Execute | None) -> HarnessReply:
        sdk = _sdk()
        limits = Limits.from_params(params, tools=bool(tools))
        system, rest = split_system(messages)
        prompt = render_prompt(rest)
        reply = HarnessReply(text="", meta={"harness": self.id})
        with empty_workdir() as wd:
            spec = self.build(c, model, system=system, prompt=prompt, workdir=wd, limits=limits, tools=tools,
                              params=params, execute=execute, calls=reply.calls)

            async def go() -> None:
                texts: list[str] = []
                async for m in sdk.query(prompt=spec["prompt"], options=spec["options"]):
                    if isinstance(m, sdk.AssistantMessage):
                        t = "".join(b.text for b in m.content if isinstance(b, sdk.TextBlock))
                        if t.strip():
                            texts.append(t)
                    elif isinstance(m, sdk.ResultMessage):
                        if m.is_error:
                            from hani2.connections import redact

                            raise HarnessError(f"Claude Code: {redact(m.result or m.subtype)[:300]}")
                        u = m.usage or {}
                        reply.usage = {"input_tokens": int(u.get("input_tokens") or 0),
                                       "output_tokens": int(u.get("output_tokens") or 0)}
                        reply.cost_usd = m.total_cost_usd
                        reply.meta["turns"] = m.num_turns
                        if isinstance(m.result, str) and m.result.strip():
                            texts.append(m.result)
                reply.text = texts[-1] if texts else ""

            async def capped() -> None:
                try:
                    await asyncio.wait_for(go(), timeout=limits.timeout)
                except TimeoutError:
                    raise HarnessTimeout(f"Claude Code: no answer within {limits.timeout:g}s") from None

            _run_coro(capped())
        return reply

    def complete(self, c: Any, model: str, messages: list[dict], params: dict[str, Any]) -> HarnessReply:
        return self._run(c, model, messages, params, None, None)

    def run_tools(self, c: Any, model: str, messages: list[dict], tools: list[dict], execute: Execute,
                  params: dict[str, Any]) -> HarnessReply:
        return self._run(c, model, messages, params, tools, execute)


def _run_coro(coro: Any) -> Any:
    """Run ``coro`` to the end on its own event loop (in a helper thread when this thread has one)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    out: dict[str, Any] = {}

    def target() -> None:
        try:
            out["v"] = asyncio.run(coro)
        except BaseException as e:  # noqa: BLE001
            out["e"] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join()
    if "e" in out:
        raise out["e"]
    return out.get("v")


__all__ = ["PASSTHROUGH", "PURPOSES", "ClaudeCode"]
