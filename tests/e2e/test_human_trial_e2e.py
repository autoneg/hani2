"""``hani2 human-trial``: two tabs of ONE browser negotiate with each other (see hani2.trial)."""

from __future__ import annotations

import csv
import re
import time

import pytest

from hani2 import trial

from .conftest import Page, _context, _start, _stop, sync_api

expect = sync_api.expect
pytestmark = pytest.mark.e2e

ACCEPT = re.compile(r"^Accept")


@pytest.fixture(scope="module")
def trial_server(tmp_path_factory):
    home = tmp_path_factory.mktemp("e2e_trial_home")
    made: list[trial.Trial] = []
    url, proc, log = _start(home, [], setup_home=lambda h: made.append(trial.prepare(h)))
    yield url, made[0]
    _stop(proc, log)


def test_two_tabs_of_one_browser_negotiate_with_each_other(e2e_browser, trial_server):
    url, t = trial_server
    ctx = _context(e2e_browser, url)  # one browser context: both tabs share its cookies
    a, b = Page(ctx.new_page(), url), Page(ctx.new_page(), url)
    try:
        a.goto(t.path(0))
        b.goto(t.path(1))
        expect(a.get_by_text("another participant").first).to_be_visible()
        a.get_by_role("button", name="Start negotiation").click()
        expect(a.get_by_text("Waiting for the other participant…")).to_be_visible()
        b.get_by_role("button", name="Start negotiation").click()
        # whose turn it is: End is enabled only on that side ("Waiting for your opponent…" can also
        # flash on the mover while its first turn is being set up, so it does not tell the sides apart)
        ea = a.locator("[data-anchor=end]").get_by_role("button")
        eb = b.locator("[data-anchor=end]").get_by_role("button")

        def turns() -> tuple[bool, bool]:
            return (ea.count() > 0 and ea.first.is_enabled(), eb.count() > 0 and eb.first.is_enabled())

        for _ in range(150):
            if sum(turns()) == 1:
                break
            a.wait_for_timeout(100)
        ta, tb = turns()
        assert ta != tb, "exactly one side has the turn"
        mover, other = (a, b) if ta else (b, a)
        if not mover.locator("[data-anchor=send]").get_by_role("button", name="Send offer").count():
            mover.get_by_role("button", name="Counter-offer").click()
        mover.locator("[data-anchor=send]").get_by_role("button", name="Send offer").click()
        expect(other.get_by_role("button", name=ACCEPT).first).to_be_enabled()
        other.get_by_role("button", name=ACCEPT).first.click()
        other.get_by_role("button", name="Accept offer").click()
        expect(other.get_by_text("Agreement reached").first).to_be_visible()
        expect(mover.get_by_text("Agreement reached").first).to_be_visible()
        assert not a.errors and not b.errors, a.errors + b.errors
    finally:
        ctx.close()
    rows = []
    for _ in range(50):
        rows = [r for f in (t.study_dir / "results").glob("*/results.csv") for r in csv.DictReader(f.open())]
        if len(rows) == 2:
            break
        time.sleep(0.1)
    assert len(rows) == 2
    assert {r["opponent_kind"] for r in rows} == {"human"}
    assert rows[0]["match_id"] and rows[0]["match_id"] == rows[1]["match_id"]
