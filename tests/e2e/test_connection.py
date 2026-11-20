"""Browser-level checks of the live connection: reconnects, heartbeats and failed requests."""

from __future__ import annotations

import re
import uuid

import pytest

from .conftest import sync_api

expect = sync_api.expect
pytestmark = pytest.mark.e2e

WS = re.compile(r"/api/ws/")


class Proxy:
    """Sits between the page and the server's websocket: records what the page sends, can drop or
    inject server messages and can close the page's socket (which then reconnects)."""

    def __init__(self, page):
        self.sent: list[str] = []
        self.routes: list = []
        self.mute = False  # True: the server's messages no longer reach the page (a dead connection)
        self.refuse = False  # True: new connections are closed at once (the server is unreachable)
        page.route_web_socket(WS, self._handle)

    def _handle(self, ws):
        if self.refuse:
            ws.close()
            return
        server = ws.connect_to_server()
        self.routes.append(ws)
        ws.on_message(lambda m: (self.sent.append(m), server.send(m)))
        server.on_message(lambda m: None if self.mute else ws.send(m))

    def count(self, text: str) -> int:
        return sum(text in m for m in self.sent)


def wait_until(p, cond, timeout_ms: int = 10000):
    for _ in range(timeout_ms // 100):
        if cond():
            return
        p.wait_for_timeout(100)
    raise AssertionError("condition not met in time")


def logged_in(new_page):
    p = new_page()
    name = "e2e" + uuid.uuid4().hex[:8]
    r = p.request.post("/api/auth/register", data={"username": name, "password": "secret1", "confirm": "secret1",
                                                   "consent": True})
    assert r.ok, r.text()
    return p


def test_page_view_is_sent_once_not_on_every_reconnect(new_page):
    p = logged_in(new_page)
    proxy = Proxy(p)
    p.goto("/app")
    expect(p.get_by_role("button", name="Start negotiation")).to_be_visible()
    wait_until(p, lambda: proxy.count('"page_view"'))
    assert proxy.count('"page_view"') == 1
    proxy.routes[-1].close()
    expect(p.get_by_text("Reconnecting")).to_be_visible()
    expect(p.get_by_text("Reconnecting")).to_have_count(0)
    assert len(proxy.routes) == 2
    p.wait_for_timeout(500)
    assert proxy.count('"page_view"') == 1


def test_a_failed_session_request_can_be_retried(new_page):
    p = logged_in(new_page)
    p.route("**/api/session", lambda r: r.fulfill(status=503, json={"detail": "Server busy"}))
    p.goto("/app")
    expect(p.get_by_text("Server busy")).to_be_visible()
    p.unroute("**/api/session")
    p.get_by_role("button", name="Try again").click()
    expect(p.get_by_role("button", name="Start negotiation")).to_be_visible()


def test_start_while_disconnected_says_so(new_page):
    p = logged_in(new_page)
    proxy = Proxy(p)
    p.goto("/app")
    expect(p.get_by_role("button", name="Start negotiation")).to_be_visible()
    proxy.refuse = True
    proxy.routes[-1].close()
    expect(p.get_by_text("Reconnecting")).to_be_visible()
    p.get_by_role("button", name="Start negotiation").click()
    expect(p.get_by_text("Not connected")).to_be_visible()
    proxy.refuse = False
    expect(p.get_by_text("Reconnecting")).to_have_count(0, timeout=30000)
    p.get_by_role("button", name="Start negotiation").click()
    expect(p.get_by_role("button", name="Counter-offer").or_(p.get_by_role("button", name="Send offer")).first).to_be_visible()
