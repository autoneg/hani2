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


@pytest.fixture(scope="session")
def e2e_browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"no Chromium for Playwright (run: playwright install chromium): {e}")
        yield b
        b.close()


@pytest.fixture(scope="session")
def server(tmp_path_factory):
    """The base URL of a fresh server: its own home, a fixed non-LLM opponent, no Assistant."""
    home = tmp_path_factory.mktemp("e2e_home")
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HANI2_", "PROLIFIC_", "SCMLWEB_"))}
    env.update(HANI2_HOME=str(home), HANI2_MODEL_PROBE="off", PYTHONUNBUFFERED="1")
    cli = [sys.executable, "-m", "hani2.cli"]
    subprocess.run([*cli, "setup"], env=env, check=True, capture_output=True)
    env["HANI2_SSO_SCMLWEB_SECRET"] = SSO_SECRET  # a hand-off provider for the sign-in-from-a-website test
    _add_sso_provider(home)
    log = (home / "server.log").open("w")
    proc = subprocess.Popen([*cli, "--no-browser", "--port", str(port), "--opponents", "BoulwareTBNegotiator",
                             "--no-assistant"], env=env, stdout=log, stderr=subprocess.STDOUT)
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
    yield url
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


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
