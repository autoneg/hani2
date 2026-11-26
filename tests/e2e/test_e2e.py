"""Browser-level checks of the main flows (see conftest.py for how to run them)."""

from __future__ import annotations

import re
import uuid

import pytest

from .conftest import sync_api

expect = sync_api.expect
pytestmark = pytest.mark.e2e

ACCEPT = re.compile(r"^Accept")


def start(p):
    p.get_by_role("button", name="Start negotiation").click()
    expect(p.get_by_role("button", name="Counter-offer").or_(p.get_by_role("button", name="Send offer")).first).to_be_visible()


def wait_for_my_turn_with_an_offer(p):
    """Wait until the opponent's offer is on the table and Accept is enabled (send a counter if we move first)."""
    accept = p.get_by_role("button", name=ACCEPT).first
    for _ in range(3):
        try:
            expect(accept).to_be_enabled(timeout=5000)
            return accept
        except AssertionError:
            send_counter(p, "Let us start here.")
    expect(accept).to_be_enabled()
    return accept


def send_counter(p, message: str):
    if not p.get_by_role("button", name="Send offer").count():
        p.get_by_role("button", name="Counter-offer").click()
    box = p.get_by_placeholder(re.compile("Explain your offer"))
    if box.count():
        box.fill(message)
    p.get_by_role("button", name="Send offer").click()


def test_login_page_shows_and_default_user_can_log_in(new_page):
    p = new_page()
    p.goto("/")
    expect(p.get_by_role("button", name="Log in")).to_be_visible()
    p.get_by_label("Username").fill("user")
    p.get_by_label("Password").fill("wrong")
    p.get_by_role("button", name="Log in").click()
    expect(p.get_by_role("button", name="Start negotiation")).to_have_count(0)
    p.get_by_label("Password").fill("userpass")
    p.get_by_role("button", name="Log in").click()
    expect(p.get_by_role("button", name="Start negotiation")).to_be_visible()


def test_registration_form_creates_an_account(new_page):
    import uuid

    p = new_page()
    p.goto("/")
    p.get_by_text("Create one").click()
    name = "reg" + uuid.uuid4().hex[:8]
    p.get_by_label("Full name").fill("E2E Tester")
    p.get_by_label("Username").fill(name)
    p.get_by_label("Email", exact=True).fill(f"{name}@example.org")
    p.get_by_label("Repeat email").fill(f"{name}@example.org")
    p.get_by_label("Password", exact=True).fill("secret1")
    p.get_by_label("Repeat password").fill("secret1")
    consent = p.get_by_role("checkbox")
    if consent.count():
        consent.first.check()
    p.get_by_role("button", name="Create account").click()
    expect(p.get_by_role("button", name="Start negotiation")).to_be_visible()
    assert p.request.get("/api/auth/me").json()["user"] == name


def test_counter_offer_with_message_appears_in_the_history(user_page):
    p = user_page
    start(p)
    send_counter(p, "How about this, friend?")
    expect(p.get_by_text("How about this, friend?")).to_be_visible()
    wait_for_my_turn_with_an_offer(p)  # the opponent answered


def test_accepting_an_offer_reaches_an_agreement(user_page):
    p = user_page
    start(p)
    wait_for_my_turn_with_an_offer(p).click()
    p.get_by_role("button", name="Accept offer").click()
    expect(p.get_by_text("Agreement reached").first).to_be_visible()
    expect(p.get_by_role("button", name="Next negotiation")).to_be_visible()


def test_ending_without_agreement(user_page):
    p = user_page
    start(p)
    wait_for_my_turn_with_an_offer(p)
    p.get_by_role("button", name=re.compile(r"^End")).first.click()
    p.get_by_role("button", name="End negotiation").click()
    expect(p.get_by_role("button", name="Next negotiation")).to_be_visible()
    expect(p.get_by_text("Agreement reached")).to_have_count(0)


def test_next_negotiation_renders_every_tool(user_page):
    """Regression: after a round, the next scenario's tools rendered with the old scenario's caches."""
    p = user_page
    for _ in range(2):
        start(p)
        wait_for_my_turn_with_an_offer(p).click()
        p.get_by_role("button", name="Accept offer").click()
        p.get_by_role("button", name="Next negotiation").click()
        expect(p.get_by_role("button", name="Start negotiation")).to_be_visible()
        expect(p.get_by_text("failed to render")).to_have_count(0)


def test_cancelled_accept_keeps_negotiating(user_page):
    p = user_page
    start(p)
    wait_for_my_turn_with_an_offer(p).click()
    p.get_by_role("button", name="Cancel").click()
    expect(p.get_by_role("button", name="Accept offer")).to_have_count(0)
    expect(p.get_by_role("button", name=ACCEPT).first).to_be_enabled()


def test_session_resumes_after_reload(user_page):
    p = user_page
    start(p)
    send_counter(p, "Remember me")
    expect(p.get_by_text("Remember me")).to_be_visible()
    p.reload()
    expect(p.get_by_text("Remember me")).to_be_visible()


def test_playground_on_a_phone_has_no_sideways_scroll(new_page):
    """Regression: the Tools tab was ~900px wide on a 390px screen."""
    p = new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    p.goto("/play")
    p.get_by_role("button", name="Start negotiation").click()
    expect(p.get_by_role("navigation", name="Sections")).to_be_visible()
    for tab in ("Tools", "Negotiate"):
        p.get_by_role("navigation", name="Sections").get_by_role("button", name=tab).click()
        p.wait_for_timeout(300)
        width = p.evaluate("[document.documentElement.scrollWidth, document.documentElement.clientWidth]")
        assert width[0] <= width[1] + 1, (tab, width)


def test_participants_cannot_open_the_admin_api(user_page):
    assert user_page.request.get("/api/admin/users").status == 403


ADMIN_PAGES = ("overview results analytics replay projects texts forms scenarios opponents assistants tool-library "
               "general negotiation interface tools connections models llm assistant autopilot users").split()


def test_every_admin_page_loads_without_errors(new_page):
    p = new_page(viewport={"width": 1400, "height": 900})
    console: list[str] = []
    p.on("console", lambda m: m.type == "error" and console.append(m.text))
    r = p.request.post("/api/auth/login", data={"username": "admin", "password": "adminpass"})
    assert r.ok
    for page_id in ADMIN_PAGES:
        p.goto(f"/admin#{page_id}")
        p.reload()
        expect(p.get_by_text("Back to negotiating")).to_be_visible()
        p.wait_for_load_state("networkidle")
        assert not p.errors, (page_id, p.errors)
    assert not console, console


def test_a_signed_link_from_the_website_opens_the_app_logged_in(new_page):
    import time
    import uuid

    from hani2 import sso

    from .conftest import SSO_SECRET

    p = new_page()
    p.goto("/login")
    expect(p.get_by_role("link", name="Continue with your ANAC account")).to_be_visible()
    now = int(time.time())
    sub = uuid.uuid4().hex[:10]
    token = sso.sign({"iss": "scmlweb", "aud": "hani2", "sub": sub, "iat": now, "exp": now + 60,
                      "jti": uuid.uuid4().hex, "name": "Pat"}, SSO_SECRET)
    p.goto(f"/api/sso/scmlweb?token={token}&next=/app")
    expect(p.get_by_role("button", name="Start negotiation")).to_be_visible()
    assert p.request.get("/api/auth/me").json()["user"] == f"anac_{sub}"
    p.goto(f"/api/sso/scmlweb?token={token}&next=/app")  # the same link again: refused
    expect(p.get_by_text("already used")).to_be_visible()


def test_signed_in_playground_records_under_the_account(new_page):
    import time
    import uuid

    from hani2 import sso

    from .conftest import SSO_SECRET

    p = new_page()
    now, sub = int(time.time()), uuid.uuid4().hex[:10]
    token = sso.sign({"iss": "scmlweb", "aud": "hani2", "sub": sub, "iat": now, "exp": now + 60,
                      "jti": uuid.uuid4().hex}, SSO_SECRET)
    p.goto(f"/api/sso/scmlweb?token={token}&next=/play")
    start(p)
    wait_for_my_turn_with_an_offer(p).click()
    p.get_by_role("button", name="Accept offer").click()
    expect(p.get_by_text("Agreement reached").first).to_be_visible()
    p.get_by_role("tab", name="My Results").click()
    expect(p.get_by_text("Agreements").first).to_be_visible()
    import json

    sid = p.request.post("/api/session", data=json.dumps({"mode": "guest", "query": {}}),
                         headers={"content-type": "application/json"}).json()["sid"]
    assert sid == f"play:anac_{sub}"
    guest = new_page()
    guest_sid = guest.request.post("/api/session", data=json.dumps({"mode": "guest", "query": {}}),
                                   headers={"content-type": "application/json"}).json()["sid"]
    assert guest_sid.startswith("guest:")


def test_a_prolific_participant_goes_through_every_study_form(new_page):
    """Consent, pre-questionnaire, one counted negotiation and its questionnaire, the post-session
    questionnaire, then the completion link, all set up for one study through the admin API."""
    import uuid

    admin = new_page()
    assert admin.request.post("/api/auth/login", data={"username": "admin", "password": "adminpass"}).ok
    study = "f" + uuid.uuid4().hex[:6]
    r = admin.request.put(f"/api/admin/projects/E2E/studies/{study}",
                          data={"data": {"type": "prolific", "n_required": 1, "practice": False,
                                         "completion_code": "DONE42"}})
    assert r.ok, r.text()
    layer = f"?layer=study:E2E/{study}"
    q = lambda qid, text: f"title: Form {qid}\nquestions:\n  - {{id: {qid}, text: '{text}', type: likert5, required: true}}\n"
    for form, qid, text in (("pre_questionnaire", "pre_q", "Pre question?"), ("per_negotiation", "neg_q", "Round question?"),
                            ("post_session", "post_q", "Session question?")):
        r = admin.request.put(f"/api/admin/settings/{form}{layer}", data={"text": q(qid, text)})
        assert r.ok, r.text()
    assert admin.request.patch(f"/api/admin/settings/env{layer}", data={"auth": {"participant_consent": True}}).ok

    p = new_page()
    pid = "e2e" + uuid.uuid4().hex[:6]
    p.goto(f"/s/E2E/{study}/play?PROLIFIC_PID={pid}&noautostart=1")
    p.get_by_role("button", name="I agree to take part").click()
    expect(p.get_by_text("Pre question?")).to_be_visible()
    p.get_by_role("button", name="3", exact=True).click()
    p.get_by_role("button", name="Submit answers").click()
    start(p)
    wait_for_my_turn_with_an_offer(p).click()  # accepting counts as an action
    p.get_by_role("button", name="Accept offer").click()
    expect(p.get_by_text("Round question?")).to_be_visible()
    p.get_by_role("button", name="4", exact=True).click()
    p.get_by_role("button", name="Submit answers").click()
    expect(p.get_by_text("Session question?")).to_be_visible()
    p.get_by_role("button", name="5", exact=True).click()
    p.get_by_role("button", name="Submit answers").click()
    link = p.get_by_role("link", name=re.compile("Finish and submit"))
    expect(link).to_have_attribute("href", re.compile("cc=DONE42"))


def test_participant_hides_the_character_and_gets_the_header_button(e2e_browser, character_server):
    from .conftest import Page, _context

    ctx = _context(e2e_browser, character_server)
    p = Page(ctx.new_page(), character_server)
    try:
        name = "e2e" + uuid.uuid4().hex[:8]
        r = p.request.post("/api/auth/register", data={"username": name, "password": "secret1", "confirm": "secret1",
                                                       "consent": True})
        assert r.ok, r.text()
        p.goto("/app")
        character = p.locator("[data-persona]")
        header_button = p.get_by_role("banner").get_by_role("button", name="Assistant", exact=True)
        expect(character).to_be_visible()
        expect(header_button).to_have_count(0)
        # the character steps aside while its conversation is open and comes back when it is closed
        character.click()
        close = p.get_by_role("button", name="Close assistant")
        expect(close).to_be_visible()
        expect(character).to_have_count(0)
        close.click()
        expect(character).to_be_visible()
        p.get_by_role("button", name=re.compile(r"^Hide ")).click()
        expect(character).to_have_count(0)
        expect(header_button).to_be_visible()
        header_button.click()
        p.get_by_role("button", name="Show the character").click()
        expect(character).to_be_visible()
        expect(header_button).to_have_count(0)
        assert not p.errors, p.errors
    finally:
        ctx.close()
