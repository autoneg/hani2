import importlib.util
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# CLI tests read plain help and error text. On GitHub Actions (or with FORCE_COLOR / PY_COLORS)
# typer forces a colour terminal, which puts ANSI codes inside option names; it reads these
# variables once, when typer is first imported, so drop them before any test imports it.
for _var in ("GITHUB_ACTIONS", "FORCE_COLOR", "PY_COLORS"):
    os.environ.pop(_var, None)

# the browser tests need Playwright (the e2e extra): without it pytest skips the folder
collect_ignore = [] if importlib.util.find_spec("playwright") else ["e2e"]
sys.path.insert(0, str(ROOT / "examples" / "support_agent_tutorial"))
sys.path.insert(0, str(ROOT / "examples" / "tools"))
sys.path.insert(0, str(ROOT / "examples" / "agent_template"))


@pytest.fixture(autouse=True)
def hani2_home(tmp_path, monkeypatch):
    """Every test gets its own empty HANI2 home (settings, results, events)."""
    monkeypatch.setenv("HANI2_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HANI2_EVENTS", "1")
    # no network: model checks only look at credentials (tests of the checks switch them on)
    monkeypatch.setenv("HANI2_MODEL_PROBE", "off")
    for var in ("HANI2_ASSISTANT", "HANI2_ASSISTANT_CLASS", "HANI2_ASSISTANTS", "HANI2_SUPPORT_AGENT", "HANI2_SUPPORT_AGENT_CLASS", "HANI2_OPPONENTS", "HANI2_AGENTS", "HANI2_TOOLS", "HANI2_EXPERIMENT", "PROLIFIC_N_REQUIRED", "HANI2_PER_NEG_YAML",
                "HANI2_STUDY", "HANI2_EXPERIMENTS", "HANI2_ASSISTANT_ISOLATION", "HANI2_PROJECTS", "HANI2_PUBLIC_URL", "HANI2_ROOT_PATH",
                "PROLIFIC_COMPLETION_URL", "PROLIFIC_COMPLETION_CODE", "PROLIFIC_MAX_MINUTES", "PROLIFIC_PER_NEG_YAML",
                "SCMLWEB_BASE_URL", "SCMLWEB_PROLIFIC_PATH", "HANI_PROLIFIC_SCENARIOS_BASE", "HANI2_SCENARIOS_BASE",
                "HANI2_MODELS", "HANI2_SETTINGS_OVERRIDES", "OLLAMA_API_BASE", "HANI2_OLLAMA_LOCAL_BASE", "HANI2_BIND_HOST"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path / "home"


def write_settings(home: Path, name: str, data) -> None:
    import json

    p = home / "settings" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")


class ScriptedLLM:
    """A fake LLM: returns the queued assistant messages in order."""

    def __init__(self, *messages):
        self.queue = list(messages)
        self.calls = []

    def __call__(self, agent, tools, force_action=False, no_tools=False):
        self.calls.append({"tools": [t["function"]["name"] for t in tools], "force": force_action, "no_tools": no_tools})
        if not self.queue:
            return {"role": "assistant", "content": "done"}
        m = self.queue.pop(0)
        if isinstance(m, str):
            return {"role": "assistant", "content": m}
        name, args = m
        import json
        import uuid

        return {"role": "assistant", "content": "", "tool_calls": [
            {"id": uuid.uuid4().hex[:6], "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


@pytest.fixture
def scripted(monkeypatch):
    """Patch SupportAgent._complete with a ScriptedLLM."""

    def _make(*messages):
        llm = ScriptedLLM(*messages)
        from hani2.support_agent.runtime import SupportAgent

        monkeypatch.setattr(SupportAgent, "_complete", lambda self, tools, force_action=False, no_tools=False: llm(self, tools, force_action, no_tools))
        return llm

    return _make
