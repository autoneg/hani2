"""The Assistant / Opponent names, and the old names that must keep working.

The Assistant was called the "support agent" and the opponent the "partner".
New names are used everywhere; the old code-facing names stay as aliases.
"""

import json
import os
import re
from pathlib import Path

import pytest
from conftest import write_settings
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
_ENV_VARS = ("HANI2_ASSISTANT", "HANI2_ASSISTANT_CLASS", "HANI2_SUPPORT_AGENT", "HANI2_SUPPORT_AGENT_CLASS")


@pytest.fixture
def clean_env():
    yield
    for v in _ENV_VARS:
        os.environ.pop(v, None)


# --------------------------------------------------------------------------- #
# Python names                                                                 #
# --------------------------------------------------------------------------- #
def test_assistant_and_support_agent_are_the_same_class():
    from hani2.assistant import Assistant
    from hani2.assistant import SupportAgent as SA2
    from hani2.support_agent import Assistant as A2
    from hani2.support_agent import SupportAgent
    from hani2.support_agent.runtime import Assistant as A3

    assert Assistant is SupportAgent is A2 is A3 is SA2


def test_assistant_submodules_are_the_support_agent_modules():
    import hani2.assistant.autopilot
    import hani2.assistant.capabilities
    import hani2.assistant.runtime
    import hani2.assistant.settings
    import hani2.assistant.tools
    import hani2.support_agent.autopilot
    import hani2.support_agent.capabilities
    import hani2.support_agent.runtime
    import hani2.support_agent.settings
    import hani2.support_agent.tools

    for name in ("autopilot", "capabilities", "runtime", "settings", "tools"):
        assert getattr(hani2.assistant, name) is getattr(hani2.support_agent, name)
    from hani2.assistant.settings import load_assistant_settings
    from hani2.support_agent.settings import load_support_agent_settings

    assert load_assistant_settings is load_support_agent_settings


def test_old_settings_function_names():
    from hani2.support_agent import settings as st

    assert st.DEFAULT_SUPPORT_AGENT_SETTINGS is st.DEFAULT_ASSISTANT_SETTINGS
    assert st.parse_support_agent_choice is st.parse_assistant_choice
    assert st.support_agent_mode is st.assistant_mode
    assert st.support_agent_enabled is st.assistant_enabled
    assert st.save_support_agent_settings is st.save_assistant_settings


def test_make_session_old_and_new_keyword_names():
    from hani2.testing import make_session

    s = make_session(opponent="ConcederTBNegotiator", assistant_settings={"autonomy": "semi"})
    assert s.support_agent is not None and s.support_agent.settings["autonomy"] == "semi"
    s = make_session(partner="ConcederTBNegotiator", support_settings={"mode": "off"})
    assert s.support_agent is None


# --------------------------------------------------------------------------- #
# Environment variables                                                        #
# --------------------------------------------------------------------------- #
def test_env_vars_new_old_and_new_wins(monkeypatch):
    from hani2.support_agent.settings import assistant_mode, load_assistant_settings

    monkeypatch.setenv("HANI2_SUPPORT_AGENT", "off")
    assert assistant_mode() == "off"
    monkeypatch.setenv("HANI2_ASSISTANT", "auto")
    assert assistant_mode() == "auto"  # the new name wins
    monkeypatch.delenv("HANI2_SUPPORT_AGENT")
    assert assistant_mode() == "auto"

    monkeypatch.setenv("HANI2_SUPPORT_AGENT_CLASS", "old.module:Old")
    assert load_assistant_settings()["agent_class"] == "old.module:Old"
    monkeypatch.setenv("HANI2_ASSISTANT_CLASS", "new.module:New")
    assert load_assistant_settings()["agent_class"] == "new.module:New"


# --------------------------------------------------------------------------- #
# Settings files                                                               #
# --------------------------------------------------------------------------- #
def test_bundled_default_has_the_new_name():
    from hani2.config import DEFAULT_SETTINGS_DIR

    assert (DEFAULT_SETTINGS_DIR / "assistant_settings.json").exists()
    assert not (DEFAULT_SETTINGS_DIR / "support_agent_settings.json").exists()


def test_old_settings_file_is_read_and_new_one_wins(hani2_home):
    from hani2.support_agent.settings import load_assistant_settings

    write_settings(hani2_home, "support_agent_settings.json", {"autonomy": "semi", "temperature": 0.9})
    s = load_assistant_settings()
    assert s["autonomy"] == "semi" and s["temperature"] == 0.9
    write_settings(hani2_home, "assistant_settings.json", {"autonomy": "suggest"})
    s = load_assistant_settings()
    assert s["autonomy"] == "suggest"  # new file wins
    assert s["temperature"] == 0.9  # keys only in the old file still apply


def test_settings_layer_order_with_an_experiment(hani2_home, tmp_path, monkeypatch):
    from hani2.support_agent.settings import load_assistant_settings

    monkeypatch.setenv("HANI2_EXPERIMENTS", str(tmp_path / "exps"))
    monkeypatch.setenv("HANI2_EXPERIMENT", "x")
    exp = tmp_path / "exps" / "x"
    exp.mkdir(parents=True)
    write_settings(hani2_home, "support_agent_settings.json", {"a": 1, "b": 1, "c": 1, "d": 1})
    write_settings(hani2_home, "assistant_settings.json", {"b": 2, "c": 2, "d": 2})
    (exp / "support_agent_settings.json").write_text(json.dumps({"c": 3, "d": 3}), encoding="utf-8")
    s = load_assistant_settings()
    assert (s["a"], s["b"], s["c"], s["d"]) == (1, 2, 3, 3)
    (exp / "assistant_settings.json").write_text(json.dumps({"d": 4}), encoding="utf-8")
    s = load_assistant_settings()
    assert (s["a"], s["b"], s["c"], s["d"]) == (1, 2, 3, 4)


def test_setup_keeps_an_existing_old_settings_file(hani2_home):
    from hani2.setup import run_setup

    write_settings(hani2_home, "support_agent_settings.json", {"autonomy": "semi"})
    run_setup(quiet=True)
    sdir = hani2_home / "settings"
    assert not (sdir / "assistant_settings.json").exists()
    from hani2.support_agent.settings import load_assistant_settings

    assert load_assistant_settings()["autonomy"] == "semi"


def test_setup_creates_the_new_settings_file(hani2_home):
    from hani2.setup import run_setup

    run_setup(quiet=True)
    sdir = hani2_home / "settings"
    assert (sdir / "assistant_settings.json").exists()
    assert not (sdir / "support_agent_settings.json").exists()


def test_admin_settings_kind_new_and_old(hani2_home, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        s = c.get("/api/admin/settings/assistant").json()
        s["autonomy"] = "semi"
        assert c.put("/api/admin/settings/assistant", json=s).status_code == 200
        assert (hani2_home / "settings" / "assistant_settings.json").exists()
        assert c.get("/api/admin/settings/support_agent").json()["autonomy"] == "semi"
        s["autonomy"] = "suggest"
        assert c.put("/api/admin/settings/support_agent", json=s).status_code == 200
        assert not (hani2_home / "settings" / "support_agent_settings.json").exists()  # saving writes the new file
        assert c.get("/api/admin/settings/assistant").json()["autonomy"] == "suggest"


# --------------------------------------------------------------------------- #
# Autopilot driver                                                             #
# --------------------------------------------------------------------------- #
def test_old_autopilot_driver_name(hani2_home):
    from hani2.support_agent.autopilot import ASSISTANT_DRIVER, SUPPORT_AGENT_DRIVER, load_autopilot_settings

    assert ASSISTANT_DRIVER == SUPPORT_AGENT_DRIVER == "Assistant"
    write_settings(hani2_home, "autopilot_settings.json",
                   {"driver": "Support Agent", "allowed_drivers": ["Support Agent", "AspirationNegotiator"]})
    s = load_autopilot_settings()
    assert s["driver"] == "Assistant" and s["allowed_drivers"] == ["Assistant", "AspirationNegotiator"]


# --------------------------------------------------------------------------- #
# Command line                                                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("args", [["--assistant", "off"], ["--support-agent", "off"],
                                  ["--no-assistant"], ["--no-support-agent"]])
def test_server_assistant_flags(args, clean_env):
    from hani2.cli import app

    r = CliRunner().invoke(app, [*args, "info"])
    assert r.exit_code == 0, r.output
    assert re.search(r"^assistant\s+off$", r.output, re.M), r.output
    assert os.environ["HANI2_ASSISTANT"] == "off"


def test_old_server_flags_are_hidden_from_help():
    from hani2.cli import app

    out = CliRunner().invoke(app, ["--help"], env={"COLUMNS": "200"}).output
    assert "--assistant" in out and "--no-assistant" in out
    assert "--support-agent" not in out and "--no-support-agent" not in out


@pytest.mark.parametrize("flag", ["--no-assistant", "--no-support-agent"])
def test_experiment_create_off_flags(flag, tmp_path, monkeypatch):
    from hani2.cli import app

    monkeypatch.setenv("HANI2_EXPERIMENTS", str(tmp_path / "exps"))
    r = CliRunner().invoke(app, ["experiment", "create", "comp", flag])
    assert r.exit_code == 0, r.output
    assert json.loads((tmp_path / "exps" / "comp" / "assistant_settings.json").read_text(encoding="utf-8")) == {"mode": "off"}


@pytest.mark.parametrize("flag", ["--assistant", "--support-agent"])
def test_experiment_create_mode_flags(flag, tmp_path, monkeypatch):
    from hani2.cli import app

    monkeypatch.setenv("HANI2_EXPERIMENTS", str(tmp_path / "exps"))
    r = CliRunner().invoke(app, ["experiment", "create", "lab", flag, "auto"])
    assert r.exit_code == 0, r.output
    assert json.loads((tmp_path / "exps" / "lab" / "assistant_settings.json").read_text(encoding="utf-8")) == {"mode": "auto"}


# --------------------------------------------------------------------------- #
# Wording guard                                                                #
# --------------------------------------------------------------------------- #
OLD_WORDING = re.compile(r"support[ -]agent|\bpartners?\b", re.IGNORECASE)
#: a line may keep the old wording when it says why ("old name" notes, wire values)
LINE_MARKERS = ("old name", "wire name")
SUFFIXES = {".ts", ".tsx", ".css", ".md", ".html", ".js", ".json", ".yml", ".yaml"}


def _changelog_lines(path: Path):
    """Only the Unreleased section of the changelog is checked: released
    entries keep the words they were written with."""
    checking = False
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            checking = line.strip().lower() == "## unreleased"
        if checking:
            yield i, line


def _lines(path: Path):
    if path.name == "changelog.md":
        yield from _changelog_lines(path)
    else:
        yield from enumerate(path.read_text(errors="replace").splitlines(), 1)


def _competition_items() -> list[str]:
    """Question texts of the competition questionnaires: kept as the competitions asked them."""
    from hani2 import questionnaires
    from hani2.evaluation import catalog

    return [str(q.get("text")) for sid, s in questionnaires.library().items()
            if (catalog.questionnaire_info(sid) or catalog.QuestionnaireInfo("")).competition for q in s["questions"]]


def test_no_old_wording_in_frontend_and_docs():
    quoted = [t for t in _competition_items() if OLD_WORDING.search(t)]
    bad = []
    for base in (ROOT / "frontend" / "src", ROOT / "docs"):
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix not in SUFFIXES:
                continue
            for i, line in _lines(p):
                if OLD_WORDING.search(line) and not any(m in line.lower() for m in LINE_MARKERS) \
                        and not any(t in line for t in quoted):
                    bad.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()[:120]}")
    assert not bad, "old wording (say 'Assistant' / 'opponent', or mark the line as an old name):\n" + "\n".join(bad)
