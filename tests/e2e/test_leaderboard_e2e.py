"""The leaderboard pages on a seeded project (tests/e2e/board_seed.py): switching the sort and the games
on the end-user page, a switch the board does not offer is not shown (also to an admin on that page),
visibility (public, signed-in participants, admins), phone width, Admin → Leaderboards with its strata,
and the Leaderboard settings of the project editor."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

from .conftest import Page, _context, _start, _stop, sync_api

expect = sync_api.expect
pytestmark = pytest.mark.e2e
SEED = Path(__file__).with_name("board_seed.py")


def _seed(home: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HANI2_", "PROLIFIC_", "SCMLWEB_"))}
    subprocess.run([sys.executable, str(SEED)], env={**env, "HANI2_HOME": str(home)}, check=True, capture_output=True)


@pytest.fixture(scope="module")
def lb_server(tmp_path_factory):
    home = tmp_path_factory.mktemp("e2e_board_home")
    url, proc, log = _start(home, ["--opponents", "BoulwareTBNegotiator", "--no-assistant"], setup_home=_seed)
    yield url
    _stop(proc, log)


@pytest.fixture
def page(e2e_browser, lb_server):
    """``page(**context_options)`` → a page of its own (own cookies) on the seeded server."""
    made = []

    def make(**kw):
        ctx = _context(e2e_browser, lb_server, **kw)
        p = Page(ctx.new_page(), lb_server)
        made.append((ctx, p))
        return p

    yield make
    errors = [e for _, p in made for e in p.errors]
    for ctx, _ in made:
        ctx.close()
    assert not errors, f"uncaught errors in the page: {errors}"


def _admin(p):
    assert p.request.post("/api/auth/login", data={"username": "admin", "password": "adminpass"}).ok


def _participant(p):
    name = "lb" + uuid.uuid4().hex[:8]
    r = p.request.post("/api/auth/register", data={"username": name, "password": "secret1", "confirm": "secret1",
                                                   "consent": True})
    assert r.ok, r.text()


def _rows(p):
    return p.locator("table[aria-label=Ranking] tbody tr")


def test_switching_the_sort_and_the_games(page):
    p = page(viewport={"width": 1280, "height": 900})
    p.goto("/s/LB/leaderboard")  # public: no sign-in
    expect(p.get_by_role("heading", name="Demo league 2027")).to_be_visible()
    rows = _rows(p)
    expect(rows.first).to_have_attribute("data-entrant", "sub_aurora")
    sort = p.get_by_label("Ranked by")
    assert sort.locator("option").all_inner_texts() == ["Utility", "HI team (provisional)", "Agreement"]
    # ties with the leader read "=2", intervals are shown, and the entrant below the minimums has its reason
    expect(rows.nth(1).locator("[data-rank]")).to_have_text("=2")
    expect(rows.first).to_contain_text("0.52 – 0.74")
    expect(p.locator("[data-unranked]")).to_contain_text("Ember")
    expect(p.locator("[data-unranked]")).to_contain_text("Fewer than 5 counted games")
    text = p.locator("[data-board]").inner_text()
    assert not any(u in text for u in ("p01", "p07", "q03", "e0"))  # no user names, only entrants and counts

    sort.select_option("hi_team")
    expect(p.locator("[data-board]")).to_have_attribute("data-sort", "hi_team")
    expect(rows.first).to_have_attribute("data-entrant", "sub_birch")
    assert "sort=hi_team" in p.url

    sort.select_option("utility")
    expect(rows.first).to_have_attribute("data-entrant", "sub_aurora")
    games = p.get_by_role("group", name="Games")
    games.get_by_role("button", name="Against people").click()
    expect(games.get_by_role("button", name="Against people")).to_have_attribute("aria-pressed", "true")
    expect(rows.first).to_have_attribute("data-entrant", "sub_birch")
    assert "games=people" in p.url
    # the view is in the address: a reload keeps it
    p.reload()
    expect(p.get_by_role("group", name="Games").get_by_role("button", name="Against people")).to_have_attribute("aria-pressed", "true")
    expect(_rows(p).first).to_have_attribute("data-entrant", "sub_birch")
    # a stale link with a value the board does not allow falls back to the defaults
    p.goto("/s/LB/leaderboard?sort=hi_assistant&window=last_7_days")
    expect(_rows(p).first).to_have_attribute("data-entrant", "sub_aurora")
    expect(p.get_by_label("Ranked by")).to_have_value("utility")


def test_a_hidden_switch_is_not_shown(page):
    p = page(viewport={"width": 1280, "height": 900})
    p.goto("/s/LB/leaderboard")
    expect(p.get_by_role("group", name="Games")).to_be_visible()
    expect(p.get_by_role("group", name="Group")).to_be_visible()
    expect(p.get_by_role("group", name="Period")).to_have_count(0)  # window is not in user_options
    assert p.request.get("/api/v1/projects/LB/leaderboard?window=last_7_days").status == 400

    # an admin on the end-user page sees what end users see
    a = page(viewport={"width": 1280, "height": 900})
    _admin(a)
    a.goto("/s/LB/leaderboard")
    expect(a.get_by_role("group", name="Games")).to_be_visible()
    expect(a.get_by_role("group", name="Period")).to_have_count(0)
    assert a.get_by_label("Ranked by").locator("option").count() == 3
    # Admin → Leaderboards shows every switch value (the period too) and every criterion to sort by
    a.goto("/admin#leaderboards")
    board = a.locator("[data-board]")
    expect(board.get_by_role("group", name="Period")).to_be_visible()
    strata = board.get_by_role("group", name="Group")
    expect(strata.get_by_role("button")).to_have_text(["Combined", "Solo", "Paired"])
    strata.get_by_role("button", name="Paired").click()
    expect(strata.get_by_role("button", name="Paired")).to_have_attribute("aria-pressed", "true")
    expect(a.locator("[data-board] table tbody tr").first).to_be_visible()
    assert a.get_by_label("Ranked by").locator("optgroup").count() >= 2  # the board's keys, then criteria
    a.get_by_label("Ranked by").select_option("welfare_optimality")
    expect(board).to_have_attribute("data-sort", "welfare_optimality")
    expect(a.locator("[data-score-weights]").first).to_be_visible()  # the weights in effect
    expect(a.locator("#setting-boards-excluded")).to_be_visible()


def test_visibility(page):
    out = page(viewport={"width": 1280, "height": 900})
    out.goto("/s/LB/play/leaderboard")  # participants: signed-in users only
    expect(out.get_by_role("button", name="Sign in")).to_be_visible()
    expect(out.locator("[data-board]")).to_have_count(0)
    out.goto("/s/LB/leaderboard")  # public
    expect(out.locator("[data-board]")).to_be_visible()

    p = page(viewport={"width": 1280, "height": 900})
    _participant(p)
    p.goto("/s/LB/play/leaderboard")
    expect(p.locator("[data-board]")).to_be_visible()
    expect(p.get_by_role("heading", name="Demo league 2027 · play")).to_be_visible()
    p.goto("/s/LB/lab/leaderboard")  # admins only
    expect(p.get_by_text("This leaderboard is not open to you")).to_be_visible()
    expect(p.locator("[data-board]")).to_have_count(0)

    a = page(viewport={"width": 1280, "height": 900})
    _admin(a)
    a.goto("/s/LB/lab/leaderboard")
    expect(a.locator("[data-board]")).to_be_visible()


def test_phone_width(page):
    p = page(viewport={"width": 390, "height": 844})
    p.goto("/s/LB/leaderboard")
    cards = p.locator("ol[aria-label=Ranking] > li")
    expect(cards.first).to_be_visible()
    expect(cards.first).to_have_attribute("data-entrant", "sub_aurora")
    expect(p.locator("table[aria-label=Ranking]")).to_be_hidden()
    assert p.evaluate("document.documentElement.scrollWidth") <= 390
    p.get_by_role("group", name="Games").get_by_role("button", name="Against AI").click()
    expect(p.get_by_role("group", name="Games").get_by_role("button", name="Against AI")).to_have_attribute("aria-pressed", "true")
    assert p.evaluate("document.documentElement.scrollWidth") <= 390


def test_the_editor_sets_up_a_board(page):
    p = page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    name = "E2EB" + uuid.uuid4().hex[:5]
    assert p.request.put(f"/api/admin/projects/{name}", data={"data": {"kind": "assistant", "year": 2027}}).ok
    p.goto("/admin#projects")
    p.get_by_text(name, exact=True).first.click()
    group = p.locator("#setting-board-settings")
    expect(group).to_be_visible()
    group.get_by_role("switch", name="Project board settings").click()
    group.get_by_role("button", name="About Track").click()
    expect(p.get_by_role("dialog")).to_be_visible()
    p.keyboard.press("Escape")
    group.get_by_label("Visibility", exact=True).select_option("public")
    group.get_by_role("switch", name="Show the period switch").click()
    expect(group.locator("#setting-board-switch-window")).to_contain_text("Last 7 days")
    group.get_by_role("button", name="Choose here").first.click()  # the sort options, from the defaults
    p.get_by_role("button", name="Save", exact=True).click()
    expect(p.get_by_text("Saved project.yaml")).to_be_visible()
    block = p.request.get(f"/api/admin/projects/{name}").json()["defaults"]["leaderboard"]
    assert block["visibility"] == "public" and block["user_options"]["window"] == ["all", "last_7_days"]
    assert block["sort_options"] and block.get("default_sort", block["sort_options"][0]) in block["sort_options"]
    # the end-user page now offers the period switch, and only it
    u = page(viewport={"width": 1280, "height": 900})
    u.goto(f"/s/{name}/leaderboard")
    expect(u.get_by_role("group", name="Period")).to_be_visible()
    expect(u.get_by_role("group", name="Games")).to_have_count(0)
    expect(u.locator("[data-empty]")).to_be_visible()
