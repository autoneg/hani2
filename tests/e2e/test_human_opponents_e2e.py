"""Two browsers negotiating with each other (human opponents, see hani2.matches)."""

from __future__ import annotations

import re
import uuid

import pytest

from .conftest import Page, _context, _start, _stop, sync_api

expect = sync_api.expect
pytestmark = pytest.mark.e2e

ACCEPT = re.compile(r"^Accept")


@pytest.fixture(scope="module")
def human_server(tmp_path_factory):
    """A server whose participants have no Assistant and face other participants alone."""
    home = tmp_path_factory.mktemp("e2e_human_home")
    url, proc, log = _start(home, ["--opponents", "human", "--no-assistant"])
    yield url
    _stop(proc, log)


def _participant(browser, url):
    ctx = _context(browser, url)
    p = Page(ctx.new_page(), url)
    name = "hh" + uuid.uuid4().hex[:8]
    r = p.request.post("/api/auth/register", data={"username": name, "password": "secret1", "confirm": "secret1",
                                                   "consent": True})
    assert r.ok, r.text()
    return ctx, p


def test_two_participants_negotiate_with_each_other(e2e_browser, human_server):
    code = uuid.uuid4().hex[:6]
    (ca, a), (cb, b) = _participant(e2e_browser, human_server), _participant(e2e_browser, human_server)
    try:
        a.goto(f"/app?match={code}")
        b.goto(f"/app?match={code}")
        a.get_by_role("button", name="Start negotiation").click()
        expect(a.get_by_text("Waiting for the other participant…")).to_be_visible()
        b.get_by_role("button", name="Start negotiation").click()
        # one side moves first; the other waits for it
        wa, wb = a.get_by_text("Waiting for your opponent…"), b.get_by_text("Waiting for your opponent…")
        for _ in range(150):
            if wa.count() or wb.count():
                break
            a.wait_for_timeout(100)
        assert wa.count() + wb.count() == 1, "exactly one side waits for the other"
        mover, other = (b, a) if wa.count() else (a, b)
        if not mover.locator("[data-anchor=send]").get_by_role("button", name="Send offer").count():
            mover.get_by_role("button", name="Counter-offer").click()
        box = mover.get_by_placeholder(re.compile("Explain your offer"))
        if box.count():
            box.fill("Hello from the other side")
        mover.locator("[data-anchor=send]").get_by_role("button", name="Send offer").click()
        expect(other.get_by_role("button", name=ACCEPT).first).to_be_enabled()
        if box.count():
            expect(other.get_by_text("Hello from the other side")).to_be_visible()
        expect(mover.get_by_text("Waiting for your opponent…")).to_be_visible()
        other.get_by_role("button", name=ACCEPT).first.click()
        other.get_by_role("button", name="Accept offer").click()
        expect(other.get_by_text("Agreement reached").first).to_be_visible()
        expect(mover.get_by_text("Agreement reached").first).to_be_visible()
        assert not a.errors and not b.errors, a.errors + b.errors
    finally:
        ca.close()
        cb.close()
