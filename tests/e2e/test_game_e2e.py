"""A game study in two browsers: the person / AI choice, pairing, and an invited guest's hand-off."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path

import pytest

from .conftest import Page, _context, _start, _stop, sync_api

expect = sync_api.expect
pytestmark = pytest.mark.e2e

SECRET = "e2e-game-secret-0123456789abcdef"
STUDY = "game/play"


def _game_home(home: Path) -> None:
    study = home / "projects" / "game" / "studies" / "play"
    (study / "results").mkdir(parents=True, exist_ok=True)
    (home / "projects" / "game" / "project.yaml").write_text(
        "full_name: A game\nkind: none\ndefaults:\n  opponents: [human+assistant, human, BoulwareTBNegotiator]\n"
        "  questionnaires: false\n  counted_time_limit: 600\n")
    (study / "study.yaml").write_text("type: online\ntitle: The game\n")
    (study / "results" / "groups").mkdir(parents=True, exist_ok=True)
    (study / "results" / "groups" / "inv_people.json").write_text(json.dumps(
        {"agents": ["human+assistant", "human"], "ai_fallback": False}))  # a people-only invitation
    (study / "env.json").write_text(json.dumps({"negotiation": {
        "human_opponents_first": True, "human_opponent_choice": True, "human_opponent_codes": False,
        "human_opponent_wait": 300}}))
    p = home / "settings" / "env.json"
    env = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    env.setdefault("auth", {})["sso"] = {"scmlweb": {"guest_studies": [STUDY]}}
    p.write_text(json.dumps(env), encoding="utf-8")


@pytest.fixture(scope="module")
def game_server(tmp_path_factory):
    home = tmp_path_factory.mktemp("e2e_game_home")
    url, proc, log = _start(home, ["--no-assistant"], {"HANI2_SSO_SCMLWEB_SECRET": SECRET}, _game_home)
    yield url
    _stop(proc, log)


def _player(browser, url):
    ctx = _context(browser, url)
    p = Page(ctx.new_page(), url)
    name = "gm" + uuid.uuid4().hex[:8]
    r = p.request.post("/api/auth/register", data={"username": name, "password": "secret1", "confirm": "secret1",
                                                   "consent": True})
    assert r.ok, r.text()
    return ctx, p


def test_two_players_choose_a_person_and_meet(e2e_browser, game_server):
    (ca, a), (cb, b) = _player(e2e_browser, game_server), _player(e2e_browser, game_server)
    try:
        a.goto(f"/app?study={STUDY}")
        expect(a.get_by_test_id("opponent-choice")).to_be_visible()
        expect(a.get_by_test_id("people-waiting")).to_contain_text("Nobody is waiting")
        a.get_by_role("button", name="Play a person").click()
        expect(a.get_by_test_id("ai-instead")).to_be_visible()  # waiting: an AI is always offered
        b.goto(f"/app?study={STUDY}")
        expect(b.get_by_test_id("people-waiting")).to_contain_text("1 person is waiting now")
        b.get_by_role("button", name="Play a person").click()
        expect(b.get_by_test_id("ai-instead")).to_have_count(0)  # paired at once
        a.get_by_role("button", name="Start negotiation").click()
        b.get_by_role("button", name="Start negotiation").click()
        wa, wb = a.get_by_text("Waiting for your opponent…"), b.get_by_text("Waiting for your opponent…")
        for _ in range(150):
            if wa.count() or wb.count():
                break
            a.wait_for_timeout(100)
        assert wa.count() + wb.count() == 1, "exactly one side waits for the other"
        assert not a.errors and not b.errors, a.errors + b.errors
    finally:
        ca.close()
        cb.close()


def test_an_invited_guest_signs_in_and_plays_an_ai_now(e2e_browser, game_server):
    from hani2 import sso

    ctx = _context(e2e_browser, game_server)
    p = Page(ctx.new_page(), game_server)
    try:
        now = int(time.time())
        token = sso.sign({"iss": "scmlweb", "aud": "hani2", "sub": f"invite-{uuid.uuid4().hex[:6]}", "iat": now,
                          "exp": now + 60, "jti": uuid.uuid4().hex, "guest": True, "invited_by": 789,
                          "name": "Sam"}, SECRET)
        nxt = f"/app?study={STUDY}&opponent_choice=1"
        p.goto(f"/api/sso/scmlweb?token={token}&next={nxt.replace('&', '%26').replace('?', '%3F')}")
        expect(p.get_by_test_id("opponent-choice")).to_be_visible()
        p.get_by_role("button", name="Play an AI opponent now").click()
        expect(p.get_by_test_id("opponent-choice")).to_have_count(0)
        p.get_by_role("button", name="Start negotiation").click()
        expect(p.get_by_role("button", name=re.compile(r"^End"))).to_be_visible()
        # the guest opens nothing but the game
        assert p.request.post("/api/session", data={"mode": "main"}).status == 403
        assert p.request.get("/api/admin/results").status in (401, 403)
        assert not p.errors, p.errors
    finally:
        ctx.close()


def test_a_people_only_invitation_offers_no_ai(e2e_browser, game_server):
    ctx, p = _player(e2e_browser, game_server)
    try:
        p.goto(f"/app?study={STUDY}&group=inv_people&opponent_choice=1")
        start = p.get_by_role("button", name="Start negotiation")
        expect(start).to_be_visible()
        expect(p.get_by_test_id("opponent-choice")).to_have_count(0)  # no person / AI screen
        expect(p.get_by_test_id("ai-instead")).to_have_count(0)
        start.click()
        expect(p.get_by_test_id("waiting-for-person")).to_contain_text("starts as soon as they are ready")
        expect(p.get_by_test_id("ai-instead")).to_have_count(0)
        expect(p.get_by_text("Play an AI opponent", exact=False)).to_have_count(0)
        assert not p.errors, p.errors
    finally:
        ctx.close()
