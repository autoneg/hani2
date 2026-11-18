"""The Codex CLI harness (``codex exec --json``): plain completion only, for the operator's own
purposes (the evaluation judge, the console's Test), with an OpenAI API key only.

Usage rules (checked 2026-11-18):

* https://learn.chatgpt.com/docs/auth (where developers.openai.com/codex/auth redirects): "Use API
  key authentication for programmatic Codex CLI workflows, such as CI/CD jobs. Don't expose Codex
  execution in untrusted or public environments." and "API keys are still the recommended default
  for automation."
* https://learn.chatgpt.com/docs/app-server: "App-server authentication has never been permitted for
  commercial or hosted services."
* https://openai.com/policies/sign-in-with-chatgpt-terms/: ChatGPT-plan requests "must originate from
  the user's local runtime or a remote runtime only that user controls"; prohibited: "Using one
  user's subscription to fulfill another user's requests."

What HANI2 enforces:

* **API key only, never a ChatGPT login.** ``CODEX_HOME`` and ``HOME`` point to an empty folder under
  ``settings/secrets/<name>/`` (so ``~/.codex/auth.json`` is never read) and the model provider is a
  custom one (``model_providers.hani2``) that reads ``OPENAI_API_KEY`` (``env_key``) with
  ``requires_openai_auth = false``; ``forced_login_method = "api"``. No app-server (its
  authentication is not permitted for hosted services): one ``codex exec`` per call.
* **Not for participants.** Participants' text is an untrusted, public input ("Don't expose Codex
  execution in untrusted or public environments"), so Codex serves only :data:`PURPOSES`.
* **No tools at all**, so no Assistant functions: every built-in tool HANI2 found is turned off
  (``--disable shell_tool``, ``unified_exec``, ``view_image``, ``goals``, ``multi_agent``, … ,
  ``web_search = "disabled"``, ``tools.experimental_request_user_input.enabled = false``), and the
  model entry is taken from Codex's bundled catalog (``codex debug models --bundled``) with its
  ``apply_patch`` tool and code-mode tools removed (``model_catalog_json``; a model that is not in
  the bundled catalog is refused). A read-only sandbox and ``approval_policy = "never"`` stay as a
  backstop. No user config (``--ignore-user-config``, ``--ignore-rules``), no AGENTS.md
  (``project_doc_max_bytes = 0``), no session files (``--ephemeral``), an empty working folder.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from hani2.harness.base import (
    HarnessAdapter,
    HarnessError,
    HarnessReply,
    HarnessTimeout,
    HarnessUnavailable,
    Limits,
    child_env,
    cli_version,
    empty_workdir,
    find_cli,
    private_dir,
    render_prompt,
    split_system,
)

PURPOSES = ("judge", "test")
#: features that bring a built-in tool (or a network fetch) with them
DISABLE = ("shell_tool", "unified_exec", "view_image", "goals", "multi_agent", "multi_agent_v2", "apps", "plugins",
           "hooks", "memories", "image_generation", "browser_use", "computer_use", "tool_suggest", "sleep_tool",
           "skill_search", "code_mode", "code_mode_only", "code_mode_host")
_CATALOG: dict[str, Any] = {}
_CLOCK = threading.Lock()


class Codex(HarnessAdapter):
    id = "codex"
    label = "Codex CLI"
    tools = False
    purposes = PURPOSES
    upstreams = {"openai": ("OPENAI_API_KEY", "OpenAI (API key)")}
    default_upstream = "openai"
    default_models = {"openai": "gpt-5.5"}
    sources = ("https://learn.chatgpt.com/docs/auth", "https://learn.chatgpt.com/docs/app-server",
               "https://openai.com/policies/sign-in-with-chatgpt-terms/")
    auth_reason = ("OpenAI recommends API keys for automation and does not permit ChatGPT-plan sign-in or "
                   "app-server authentication for hosted services; it also says not to expose Codex execution "
                   "in untrusted or public environments, so Codex is used only for the judge and the console's "
                   "Test, without any tools.")

    def status(self) -> dict[str, Any]:
        return cli_version(find_cli(("codex",), "HANI2_CODEX_PATH"))

    # ------------------------------------------------------------------ #
    def _bundled(self, exe: str) -> list[dict]:
        with _CLOCK:
            hit = _CATALOG.get(exe)
            if hit is not None:
                return hit
        import tempfile

        with tempfile.TemporaryDirectory(prefix="hani2-codex-cat-") as home:
            env = {"PATH": child_env(Path(home), {})["PATH"], "HOME": home, "CODEX_HOME": home}
            try:
                r = subprocess.run([exe, "debug", "models", "--bundled"], capture_output=True, text=True,
                                   timeout=30, env=env, cwd=home)
                models = json.loads(r.stdout).get("models") or []
            except Exception as e:  # noqa: BLE001
                raise HarnessUnavailable(f"Codex: cannot read its bundled model catalog ({type(e).__name__})") from None
        with _CLOCK:
            _CATALOG[exe] = models
        return models

    def check_model(self, c: Any, model: str) -> str:
        exe = find_cli(("codex",), "HANI2_CODEX_PATH")
        if not exe:
            return ""  # the credentials check says so
        try:
            slugs = {m.get("slug") for m in self._bundled(exe)}
        except HarnessUnavailable as e:
            return str(e)
        if model not in slugs:
            return (f"Codex: {model!r} is not in Codex's bundled model catalog, so HANI2 cannot make sure it runs "
                    f"without tools (known: {', '.join(sorted(s for s in slugs if s))})")
        return ""

    def _catalog(self, exe: str, model: str, home: Path) -> Path:
        """A catalog with only ``model``, every tool it would bring removed."""
        entry = next((m for m in self._bundled(exe) if m.get("slug") == model), None)
        if entry is None:
            raise HarnessUnavailable(f"Codex: {model!r} is not in Codex's bundled model catalog, so HANI2 cannot "
                                     "make sure it runs without tools")
        entry = {**entry, "apply_patch_tool_type": None, "tool_mode": None, "multi_agent_version": None,
                 "experimental_supported_tools": []}
        f = home / "catalog.json"
        f.write_text(json.dumps({"models": [entry]}))
        return f

    def build(self, c: Any, model: str, *, system: str, prompt: str, workdir: Path, limits: Limits,
              tools: list[dict] | None = None, params: dict | None = None) -> dict[str, Any]:
        from hani2 import harness

        if tools:
            raise HarnessUnavailable("Codex runs without tools here (completion only)")
        exe = find_cli(("codex",), "HANI2_CODEX_PATH")
        if not exe:
            raise HarnessUnavailable("the codex CLI is not installed (not on PATH; or set HANI2_CODEX_PATH)")
        home = harness.home_of(c)
        codex_home = private_dir(home / "codex-home")
        for f in ("auth.json", "config.toml"):  # never a stored login or user config
            if (codex_home / f).exists():
                (codex_home / f).unlink()
        catalog = self._catalog(exe, model, workdir)  # per call: concurrent calls may use other models
        (workdir / "instructions.md").write_text(system or "You are a helpful assistant.")
        cfg = {
            "model_provider": '"hani2"',
            "model_providers.hani2.name": '"OpenAI (API key)"',
            "model_providers.hani2.base_url": '"https://api.openai.com/v1"',
            "model_providers.hani2.env_key": '"OPENAI_API_KEY"',
            "model_providers.hani2.requires_openai_auth": "false",
            "model_providers.hani2.wire_api": '"responses"',
            "forced_login_method": '"api"',
            "approval_policy": '"never"',
            "web_search": '"disabled"',
            "tools.experimental_request_user_input.enabled": "false",
            "skills.bundled.enabled": "false",
            "skills.include_instructions": "false",
            "project_doc_max_bytes": "0",
            "include_permissions_instructions": "false",
            "include_environment_context": "false",
            "include_collaboration_mode_instructions": "false",
            "include_apps_instructions": "false",
            "check_for_update_on_startup": "false",
            "model_catalog_json": json.dumps(str(catalog)),
            "model_instructions_file": json.dumps(str(workdir / "instructions.md")),
        }
        effort = (params or {}).get("effort") or (params or {}).get("reasoning_effort")
        if effort in ("minimal", "low", "medium", "high", "xhigh"):
            cfg["model_reasoning_effort"] = json.dumps(effort)
        argv = [exe, "exec", "--json", "--strict-config", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
                "--ignore-rules", "-s", "read-only", "-m", model, "-C", str(workdir)]
        for k, v in cfg.items():
            argv += ["-c", f"{k}={v}"]
        for f in DISABLE:
            argv += ["--disable", f]
        argv.append("-")  # the prompt comes on stdin (never in argv)
        env = child_env(home, {"CODEX_HOME": str(codex_home), "OPENAI_API_KEY": harness.secret_for(c)})
        return {"argv": argv, "env": env, "cwd": str(workdir), "prompt": prompt}

    def complete(self, c: Any, model: str, messages: list[dict], params: dict[str, Any]) -> HarnessReply:
        from hani2.connections import redact

        limits = Limits.from_params(params, tools=False)
        system, rest = split_system(messages)
        prompt = render_prompt(rest)
        reply = HarnessReply(text="", meta={"harness": self.id})
        with empty_workdir() as wd:
            spec = self.build(c, model, system=system, prompt=prompt, workdir=wd, limits=limits, params=params)
            t0 = time.time()
            try:
                r = subprocess.run(spec["argv"], input=prompt, capture_output=True, text=True, env=spec["env"],
                                   cwd=spec["cwd"], timeout=limits.timeout)
            except subprocess.TimeoutExpired:
                raise HarnessTimeout(f"Codex: no answer within {limits.timeout:g}s") from None
            reply.meta["seconds"] = round(time.time() - t0, 2)
            errors = []
            for line in r.stdout.splitlines():
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                t = ev.get("type")
                item = ev.get("item") or {}
                if t == "item.completed" and item.get("type") == "agent_message":
                    reply.text = str(item.get("text") or "")
                elif t == "item.completed" and item.get("type") not in ("agent_message", "reasoning", None):
                    # a tool ran although none should exist: refuse the answer
                    raise HarnessError(f"Codex used a built-in tool ({item.get('type')}); answer discarded")
                elif t == "turn.completed":
                    u = ev.get("usage") or {}
                    reply.usage = {"input_tokens": int(u.get("input_tokens") or 0),
                                   "output_tokens": int(u.get("output_tokens") or 0)}
                elif t in ("turn.failed", "error"):
                    errors.append(str((ev.get("error") or {}).get("message") or ev.get("message") or t))
            if errors and not reply.text:
                raise HarnessError(f"Codex: {redact('; '.join(errors))[:300]}")
            if r.returncode != 0 and not reply.text:
                raise HarnessError(f"Codex exited with {r.returncode}: {redact(r.stderr.strip()[-300:])}")
        return reply
