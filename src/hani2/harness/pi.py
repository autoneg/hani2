"""The pi harness (``pi --mode rpc``), for API-key providers and local Ollama only.

pi is open source and can sign in to subscriptions (Claude Pro/Max, ChatGPT, GitHub Copilot and
others) through OAuth. HANI2 never lets it: every call gets a new, empty agent folder
(``PI_CODING_AGENT_DIR``, with ``auth.json`` = ``{}``, removed afterwards) and an isolated ``HOME``, so the server user's stored pi logins (``~/.pi/agent/auth.json``) are never read;
only one API key reaches it, in the upstream provider's usual variable; and upstreams that would
need OAuth are refused (:data:`UPSTREAMS` lists those allowed).

Every call starts one pi process (the system prompt and HANI2's functions change between calls)
with: ``--mode rpc --offline --no-session -ne -e pi_bridge.ts --no-tools [--tools <HANI2 functions>]
--no-mcp --no-skills --no-prompt-templates --no-themes --no-context-files --no-approve``. The
bridge extension sets the request's system prompt to HANI2's and forwards each function call to
HANI2 over RPC (an extension UI ``input`` request), where the Assistant's dispatcher runs it.

Sources (checked 2026-11-18): pi 1.4.0's ``pi --help`` and its bundled docs ``docs/rpc.md``,
``docs/extensions.md``, ``docs/providers.md``, ``docs/models.md``, ``docs/environment-variables.md``;
https://github.com/earendil-works/pi. The upstream providers' own terms apply to their keys
(for Anthropic: https://code.claude.com/docs/en/legal-and-compliance — API keys, never Claude plan
credentials).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from hani2.harness.base import (
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

BRIDGE = Path(__file__).with_name("pi_bridge.ts")

#: upstream providers pi may call here: ``{pi provider: (key variable, label)}``. Providers whose
#: only sign-in is OAuth (``openai-codex``, ``github-copilot``) are not listed; for the others pi's
#: OAuth sign-in is never available, because the agent folder holds no login.
UPSTREAMS: dict[str, tuple[str, str]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "Anthropic (API key)"),
    "openai": ("OPENAI_API_KEY", "OpenAI (API key)"),
    "google": ("GEMINI_API_KEY", "Google Gemini (API key)"),
    "mistral": ("MISTRAL_API_KEY", "Mistral (API key)"),
    "groq": ("GROQ_API_KEY", "Groq (API key)"),
    "deepseek": ("DEEPSEEK_API_KEY", "DeepSeek (API key)"),
    "openrouter": ("OPENROUTER_API_KEY", "OpenRouter (API key)"),
    "ollama": ("", "Ollama server (no key; local models)"),
}


class Pi(HarnessAdapter):
    id = "pi"
    label = "pi"
    tools = True
    upstreams = UPSTREAMS
    default_upstream = "anthropic"
    default_models = {"anthropic": "claude-haiku-5-5", "openai": "gpt-5-mini", "google": "gemini-2.5-flash",
                      "mistral": "mistral-small-latest", "groq": "llama-3.3-70b-versatile", "deepseek": "deepseek-chat",
                      "openrouter": "openai/gpt-5-mini", "ollama": "qwen3:4b-instruct"}
    sources = ("https://github.com/earendil-works/pi",
               "pi 1.4.0 docs: rpc.md, extensions.md, providers.md, environment-variables.md",
               "https://code.claude.com/docs/en/legal-and-compliance")
    auth_reason = ("pi can sign in to personal subscriptions (Claude, ChatGPT, Copilot) by OAuth; serving "
                   "participants from them is not allowed, so pi gets an isolated agent folder with no login and "
                   "one API key, or a local Ollama server.")

    def status(self) -> dict[str, Any]:
        return cli_version(find_cli(("pi",), "HANI2_PI_PATH"))

    def check_model(self, c: Any, model: str) -> str:
        from hani2 import harness

        if "/" in model and model.split("/", 1)[0] in UPSTREAMS and model.split("/", 1)[0] != harness.upstream_of(c):
            return f"{model!r} names another provider than this connection's ({harness.upstream_of(c)})"
        return ""

    # ------------------------------------------------------------------ #
    def _agent_dir(self, c: Any, model: str, workdir: Path) -> Path:
        """A fresh, empty agent folder for this call (inside the call's own temporary folder, so
        concurrent calls never share it); it never holds a login."""
        from hani2 import harness

        agent = private_dir(workdir / ".pi-agent")
        # never a stored login: pi reads auth.json before any key in the environment
        (agent / "auth.json").write_text("{}", encoding="utf-8")
        up = harness.upstream_of(c)
        models_file = agent / "models.json"
        if up == "ollama":
            base = (c.base_url or "http://localhost:11434").rstrip("/")
            models_file.write_text(json.dumps({"providers": {"ollama": {
                "baseUrl": f"{base}/v1", "api": "openai-completions", "apiKey": "ollama",
                "models": [{"id": self._model_id(c, model)}]}}}), encoding="utf-8")
        return agent

    @staticmethod
    def _model_id(c: Any, model: str) -> str:
        from hani2 import harness

        up = harness.upstream_of(c)
        return model[len(up) + 1:] if model.startswith(f"{up}/") else model

    def build(self, c: Any, model: str, *, system: str, prompt: str, workdir: Path, limits: Limits,
              tools: list[dict] | None = None, params: dict | None = None) -> dict[str, Any]:
        from hani2 import harness

        exe = find_cli(("pi",), "HANI2_PI_PATH")
        if not exe:
            raise HarnessUnavailable("pi is not installed (not on PATH; or set HANI2_PI_PATH)")
        home = harness.home_of(c)
        agent = self._agent_dir(c, model, workdir)
        up = harness.upstream_of(c)
        (workdir / "system.txt").write_text(system or "", encoding="utf-8")
        specs = tool_specs(tools or [])
        (workdir / "tools.json").write_text(json.dumps(specs), encoding="utf-8")
        argv = [exe, "--mode", "rpc", "--offline", "--no-session", "--no-extensions", "--extension", str(BRIDGE),
                "--no-tools"]
        if specs:
            argv += ["--tools", ",".join(s["name"] for s in specs)]
        argv += ["--no-mcp", "--no-skills", "--no-prompt-templates", "--no-themes", "--no-context-files",
                 "--no-approve", "--system-prompt", "You are a helpful assistant.",
                 "--model", f"{up}/{self._model_id(c, model)}"]
        effort = (params or {}).get("effort") or (params or {}).get("reasoning_effort") or (params or {}).get("thinking")
        if effort:
            argv += ["--thinking", str(effort)]
        extra = {"PI_CODING_AGENT_DIR": str(agent), "PI_OFFLINE": "1", "PI_TELEMETRY": "0", "PI_SKIP_VERSION_CHECK": "1",
                 "HANI2_PI_SYSTEM_FILE": str(workdir / "system.txt"), "HANI2_PI_TOOLS_FILE": str(workdir / "tools.json"),
                 "HANI2_PI_TOOL_TIMEOUT_MS": str(int(limits.timeout * 1000))}
        key = harness.secret_for(c)
        if key:
            extra[UPSTREAMS[up][0]] = key
        return {"argv": argv, "env": child_env(home, extra), "cwd": str(workdir), "prompt": prompt}

    # ------------------------------------------------------------------ #
    def _run(self, c: Any, model: str, messages: list[dict], params: dict[str, Any], tools: list[dict] | None,
             execute: Execute | None) -> HarnessReply:
        from hani2.harness.jsonl import JsonlProcess

        limits = Limits.from_params(params, tools=bool(tools))
        system, rest = split_system(messages)
        prompt = render_prompt(rest)
        if prompt[:1] in ("/", "!", "@"):
            prompt = " " + prompt  # never a pi command, shell escape or file reference
        reply = HarnessReply(text="", meta={"harness": "pi"})
        with empty_workdir() as wd:
            spec = self.build(c, model, system=system, prompt=prompt, workdir=wd, limits=limits, tools=tools,
                              params=params)
            deadline = time.time() + limits.timeout
            with JsonlProcess(spec["argv"], env=spec["env"], cwd=spec["cwd"], label="pi") as proc:
                proc.send({"id": "hani2-prompt", "type": "prompt", "message": prompt})
                turns, aborted = 0, False
                while True:
                    try:
                        msg = proc.next(deadline)
                    except HarnessTimeout:
                        proc.send({"id": "hani2-abort", "type": "abort"})
                        raise
                    t = msg.get("type")
                    if t == "response" and msg.get("id") == "hani2-prompt" and not msg.get("success", True):
                        raise HarnessError(f"pi refused the prompt: {_short(msg.get('error'))}")
                    elif t == "turn_start":
                        turns += 1
                        if turns > limits.max_turns and not aborted:
                            aborted = True
                            proc.send({"id": "hani2-abort", "type": "abort"})
                    elif t == "extension_ui_request":
                        self._answer(proc, msg, execute, reply)
                    elif t == "message_end":
                        m = msg.get("message") or {}
                        if m.get("role") == "assistant":
                            if m.get("stopReason") == "error":
                                raise HarnessError(f"pi: the model call failed: {_short(m.get('errorMessage'))}")
                            text = "".join(b.get("text", "") for b in m.get("content") or []
                                           if isinstance(b, dict) and b.get("type") == "text")
                            if text.strip():
                                reply.text = text
                            _add_usage(reply, m.get("usage") or {})
                    elif t == "agent_settled":
                        break
        return reply

    def _answer(self, proc: Any, msg: dict, execute: Execute | None, reply: HarnessReply) -> None:
        """Answer one extension UI request: a HANI2 function call, or nothing (cancel)."""
        if msg.get("method") == "input" and msg.get("title") == "hani2_function_call" and execute is not None:
            try:
                call = json.loads(msg.get("placeholder") or "{}")
            except json.JSONDecodeError:
                call = {}
            name, args = str(call.get("name") or ""), call.get("arguments") or {}
            result = safe_execute(execute, name, args)
            reply.calls.append(ToolCall(id=str(call.get("id") or ""), name=name,
                                        arguments=args if isinstance(args, dict) else {}, result=result))
            proc.send({"type": "extension_ui_response", "id": msg.get("id"), "value": json.dumps(result, default=str)})
        elif msg.get("method") in ("input", "select", "confirm", "editor"):
            proc.send({"type": "extension_ui_response", "id": msg.get("id"), "cancelled": True})

    def complete(self, c: Any, model: str, messages: list[dict], params: dict[str, Any]) -> HarnessReply:
        return self._run(c, model, messages, params, None, None)

    def run_tools(self, c: Any, model: str, messages: list[dict], tools: list[dict], execute: Execute,
                  params: dict[str, Any]) -> HarnessReply:
        return self._run(c, model, messages, params, tools, execute)


def _short(x: Any) -> str:
    from hani2.connections import redact

    return redact(str(x or "unknown error"))[:300]


def _add_usage(reply: HarnessReply, u: dict) -> None:
    reply.usage["input_tokens"] = reply.usage.get("input_tokens", 0) + int(u.get("input") or 0)
    reply.usage["output_tokens"] = reply.usage.get("output_tokens", 0) + int(u.get("output") or 0)
    cost = (u.get("cost") or {}).get("total") if isinstance(u.get("cost"), dict) else None
    if isinstance(cost, (int, float)):
        reply.cost_usd = (reply.cost_usd or 0.0) + float(cost)
