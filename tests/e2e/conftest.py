"""End-to-end tests: a real ``hani2`` server in a subprocess, driven by Playwright (Chromium).

Install with ``uv pip install -e ".[dev,e2e]" && .venv/bin/playwright install chromium``, then run
``.venv/bin/pytest tests/e2e``. Without Playwright or its browser every test here is skipped, so
the default ``pytest -q`` needs neither.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

from playwright import sync_api  # tests/conftest.py ignores this folder when Playwright is missing


SSO_SECRET = "e2e-handoff-secret-0123456789"


def _add_sso_provider(home: Path) -> None:
    import json

    p = home / "settings" / "env.json"
    env = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    env.setdefault("auth", {})["sso"] = {"scmlweb": {"login_url": "https://anac.example.org/hani2/sso",
                                                     "label": "ANAC account"}}
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(env), encoding="utf-8")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="package")
def e2e_browser():
    """One Chromium for the browser tests. Package scope, not session: the sync Playwright API keeps an
    event loop running in the main thread while it is open, where ``asyncio.run`` then refuses ("cannot be
    called from a running event loop"); closing it when the e2e folder is done leaves the later tests a
    clean main thread."""
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"no Chromium for Playwright (run: playwright install chromium): {e}")
        yield b
        b.close()


def _start(home: Path, args: list[str], env_extra: dict | None = None, setup_home=None):
    """Start ``hani2`` on a free port with its own ``home``; returns (url, process, log)."""
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HANI2_", "PROLIFIC_", "SCMLWEB_"))}
    env.update(HANI2_HOME=str(home), HANI2_MODEL_PROBE="off", PYTHONUNBUFFERED="1", **(env_extra or {}))
    cli = [sys.executable, "-m", "hani2.cli"]
    subprocess.run([*cli, "setup"], env=env, check=True, capture_output=True)
    if setup_home:
        setup_home(home)
    log = (home / "server.log").open("w")
    proc = subprocess.Popen([*cli, "--no-browser", "--port", str(port), *args], env=env, stdout=log,
                            stderr=subprocess.STDOUT)
    url = f"http://127.0.0.1:{port}"
    for _ in range(120):
        if proc.poll() is not None:
            break
        try:
            urllib.request.urlopen(url + "/api/config", timeout=1)
            break
        except OSError:
            time.sleep(0.25)
    else:
        proc.kill()
    if proc.poll() is not None:
        pytest.fail("the server did not start:\n" + Path(log.name).read_text(encoding="utf-8")[-3000:])
    return url, proc, log


def _stop(proc, log) -> None:
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    """The base URL of a fresh server: its own home, a fixed non-LLM opponent, no Assistant."""
    home = tmp_path_factory.mktemp("e2e_home")
    url, proc, log = _start(home, ["--opponents", "BoulwareTBNegotiator", "--no-assistant"],
                            {"HANI2_SSO_SCMLWEB_SECRET": SSO_SECRET},  # a hand-off provider for the sign-in-from-a-website test
                            _add_sso_provider)
    yield url
    _stop(proc, log)


def _character_settings(home: Path) -> None:
    import json

    p = home / "settings" / "assistant_settings.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    s["presentation"] = {"style": "persona", "choice_default": "panel", "persona_movable": True}
    p.write_text(json.dumps(s), encoding="utf-8")


@pytest.fixture(scope="session")
def character_server(tmp_path_factory):
    """A server whose Assistant (the rule-based level 1 agent, no model needed) is a character."""
    home = tmp_path_factory.mktemp("e2e_character_home")
    hello = Path(__file__).resolve().parents[2] / "examples" / "support_agent_tutorial" / "level1_hello.py"
    url, proc, log = _start(home, ["--opponents", "BoulwareTBNegotiator", "--assistant", f"{hello}:HelloAgent"],
                            setup_home=_character_settings)
    yield url
    _stop(proc, log)


def _varied_look_env(home: Path) -> None:
    import json

    p = home / "settings" / "env.json"
    env = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    env.setdefault("interface", {})["vary_appearance"] = {"assistant": True, "opponent": True}
    p.write_text(json.dumps(env), encoding="utf-8")


@pytest.fixture(scope="session")
def varied_panel_server(tmp_path_factory):
    """Like varied_look_server, with the Assistant in its default style (the header button and panel)."""
    home = tmp_path_factory.mktemp("e2e_varied_panel_home")
    hello = Path(__file__).resolve().parents[2] / "examples" / "support_agent_tutorial" / "level1_hello.py"
    url, proc, log = _start(home, ["--opponents", "BoulwareTBNegotiator", "--assistant", f"{hello}:HelloAgent"],
                            setup_home=_varied_look_env)
    yield url
    _stop(proc, log)


def _varied_look_settings(home: Path) -> None:
    import json

    _character_settings(home)
    p = home / "settings" / "env.json"
    env = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    env.setdefault("interface", {})["vary_appearance"] = {"assistant": True, "opponent": True}
    p.write_text(json.dumps(env), encoding="utf-8")


@pytest.fixture(scope="session")
def varied_look_server(tmp_path_factory):
    """A character server whose Assistant and opponent get a look of their own in each negotiation."""
    home = tmp_path_factory.mktemp("e2e_varied_look_home")
    hello = Path(__file__).resolve().parents[2] / "examples" / "support_agent_tutorial" / "level1_hello.py"
    url, proc, log = _start(home, ["--opponents", "BoulwareTBNegotiator", "--assistant", f"{hello}:HelloAgent"],
                            setup_home=_varied_look_settings)
    yield url
    _stop(proc, log)


def _over_tools_settings(home: Path) -> None:
    import json

    p = home / "settings" / "assistant_settings.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    s["presentation"] = {"style": "both", "place": "tools"}
    p.write_text(json.dumps(s), encoding="utf-8")


@pytest.fixture(scope="session")
def over_tools_server(tmp_path_factory):
    """A server whose Assistant (the level 1 agent, no model needed; header button and character) opens over the tool area."""
    home = tmp_path_factory.mktemp("e2e_over_tools_home")
    hello = Path(__file__).resolve().parents[2] / "examples" / "support_agent_tutorial" / "level1_hello.py"
    url, proc, log = _start(home, ["--opponents", "BoulwareTBNegotiator", "--assistant", f"{hello}:HelloAgent"],
                            setup_home=_over_tools_settings)
    yield url
    _stop(proc, log)


def _weights_switch_settings(home: Path) -> None:
    import json

    p = home / "settings" / "env.json"
    s = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    s.setdefault("tools", {})["weights_chart_switch"] = True
    p.write_text(json.dumps(s), encoding="utf-8")


@pytest.fixture(scope="session")
def weights_switch_server(tmp_path_factory):
    """A server whose participants may switch the issue weights between the bar and the donut."""
    home = tmp_path_factory.mktemp("e2e_weights_switch_home")
    url, proc, log = _start(home, ["--opponents", "BoulwareTBNegotiator", "--no-assistant"],
                            setup_home=_weights_switch_settings)
    yield url
    _stop(proc, log)


@pytest.fixture(scope="session")
def css_server(tmp_path_factory):
    """A server whose Assistant (tests/e2e/css_agent.py, no model needed) sets style sheets."""
    home = tmp_path_factory.mktemp("e2e_css_home")
    agent = Path(__file__).resolve().parent / "css_agent.py"
    url, proc, log = _start(home, ["--opponents", "BoulwareTBNegotiator", "--assistant", f"{agent}:CssAgent"])
    yield url
    _stop(proc, log)


class Page:
    """A Playwright page that collects uncaught page errors (any one fails the test)."""

    def __init__(self, page, base: str):
        self.page, self.base, self.errors = page, base, []
        page.on("pageerror", lambda e: self.errors.append(str(e)))

    def __getattr__(self, name):
        return getattr(self.page, name)

    def goto(self, path: str = "/"):
        return self.page.goto(self.base + path)


def _context(b, server, **kw):
    ctx = b.new_context(base_url=server, **kw)
    ctx.set_default_timeout(15000)
    sync_api.expect.set_options(timeout=15000)
    return ctx


@pytest.fixture
def new_page(e2e_browser, server):
    """``new_page(**context_options)`` → a :class:`Page` in its own browser context (own cookies)."""
    made = []

    def make(**kw):
        ctx = _context(e2e_browser, server, **kw)
        p = Page(ctx.new_page(), server)
        made.append((ctx, p))
        return p

    yield make
    errors = [e for _, p in made for e in p.errors]
    for ctx, _ in made:
        ctx.close()
    assert not errors, f"uncaught errors in the page: {errors}"


@pytest.fixture
def user_page(new_page):
    """A page logged in as a freshly registered user (sessions resume per user: each test gets its own)."""
    p = new_page()
    name = "e2e" + uuid.uuid4().hex[:8]
    r = p.request.post("/api/auth/register", data={"username": name, "password": "secret1", "confirm": "secret1",
                                                   "consent": True})
    assert r.ok, r.text()
    p.username = name
    p.goto("/app")
    return p
