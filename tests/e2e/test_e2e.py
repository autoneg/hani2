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
    expect(p.get_by_role("button", name="Counter-offer").or_(p.locator("[data-anchor=send]").get_by_role("button", name="Send offer")).first).to_be_visible()


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
    """Send an offer with a message once it is our turn. The opponent may move first: its offer then
    arrives while we look, and the page shows Counter-offer instead of the composer."""
    send = p.locator("[data-anchor=send]").get_by_role("button", name="Send offer")
    counter = p.get_by_role("button", name="Counter-offer")
    box = p.get_by_placeholder(re.compile("Explain your offer"))
    for _ in range(300):
        if counter.count() and counter.first.is_enabled():
            counter.first.click()
        if send.count() and send.first.is_enabled() and (not box.count() or box.first.is_enabled()):
            break
        p.wait_for_timeout(100)
    if box.count():
        box.fill(message)
    expect(send).to_be_enabled()
    send.click()


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


def test_each_tool_pane_keeps_one_help_button_while_negotiating(new_page):
    """Regression (issue #1): the "?" (About <tool>) button multiplied in every pane on each turn."""
    p = new_page(viewport={"width": 1400, "height": 900})
    p.goto("/play")
    start(p)
    counts = "() => [...document.querySelectorAll('[role=tablist]')].map(t => t.querySelectorAll('button[aria-label^=\"About \"]').length)"
    for i in range(4):
        send_counter(p, f"Turn {i}")
        expect(p.get_by_text(f"Turn {i}")).to_be_visible()
        p.wait_for_timeout(500)  # let the opponent's reply and the tool renders arrive
        per_pane = p.evaluate(counts)
        assert per_pane and all(n <= 1 for n in per_pane), (i, per_pane)


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


def test_assistant_opens_over_the_tool_area_and_gives_the_tool_back(e2e_browser, over_tools_server):
    from .conftest import Page, _context

    ctx = _context(e2e_browser, over_tools_server, viewport={"width": 1400, "height": 900})
    p = Page(ctx.new_page(), over_tools_server)
    try:
        name = "e2e" + uuid.uuid4().hex[:8]
        r = p.request.post("/api/auth/register", data={"username": name, "password": "secret1", "confirm": "secret1",
                                                       "consent": True})
        assert r.ok, r.text()
        p.goto("/app?view=simple")
        tools = p.locator("[data-region=tools]")
        expect(tools).to_have_count(1)
        tablist = tools.get_by_role("tablist")
        expect(tablist).to_be_visible()
        open_tab = tablist.get_by_role("tab", selected=True).first
        tab_name = open_tab.inner_text()
        p.get_by_role("banner").get_by_role("button", name="Assistant", exact=True).click()
        # the Assistant sits in the tool area, in the open tool's place, and nowhere else
        assistant = p.locator("aside[aria-label=Assistant]")
        expect(assistant).to_have_count(1)
        expect(tools.locator("aside[aria-label=Assistant]")).to_be_visible()
        expect(tablist).to_be_hidden()
        expect(tools).to_have_count(1)
        # closing it brings the same tool back
        p.get_by_role("button", name="Close assistant").click()
        expect(assistant).to_have_count(0)
        expect(tablist).to_be_visible()
        expect(tablist.get_by_role("tab", selected=True).first).to_have_text(tab_name)
        # the character opens it in the same place
        p.locator("[data-persona]").click()
        expect(assistant).to_have_count(1)
        expect(tools.locator("aside[aria-label=Assistant]")).to_be_visible()
        p.get_by_role("button", name="Close assistant").click()
        expect(p.locator("[data-persona]")).to_be_visible()
        # the full view: it fills the tools column
        p.get_by_role("button", name="Layout").click()
        p.get_by_role("menuitem", name=re.compile("^Full")).or_(p.get_by_role("button", name=re.compile("^Full"))).first.click()
        p.get_by_role("banner").get_by_role("button", name="Assistant", exact=True).click()
        expect(assistant).to_have_count(1)
        expect(tools.first.locator("aside[aria-label=Assistant]")).to_be_visible()
        # starting a negotiation reveals the participant's preferences, so the Assistant makes way
        start(p)
        expect(assistant).to_have_count(0)
        # a tool in a popup is the tool in front: the Assistant takes its window and gives it back
        p.get_by_role("button", name="Layout").click()
        p.get_by_role("menuitem", name=re.compile("^Focus")).or_(p.get_by_role("button", name=re.compile("^Focus"))).first.click()
        expect(tools).to_have_count(0)
        p.get_by_test_id("launch-generator").click()
        popup = p.get_by_test_id("tool-popup")
        bar = popup.get_by_test_id("range-bar-area")
        expect(bar).to_be_visible()
        p.get_by_role("banner").get_by_role("button", name="Assistant", exact=True).click()
        expect(assistant).to_have_count(1)
        expect(popup.locator("aside[aria-label=Assistant]")).to_be_visible()
        expect(bar).to_be_hidden()
        p.get_by_role("button", name="Close assistant").click()
        expect(assistant).to_have_count(0)
        expect(bar).to_be_visible()
        popup.press("Escape")
        expect(popup).to_have_count(0)
        # in the bare view there is no tool area: it opens beside the page as before
        p.get_by_role("button", name="Layout").click()
        p.get_by_role("menuitem", name=re.compile("^Bare")).or_(p.get_by_role("button", name=re.compile("^Bare"))).first.click()
        expect(tools).to_have_count(0)
        p.get_by_role("banner").get_by_role("button", name="Assistant", exact=True).click()
        expect(assistant).to_be_visible()
        assert not p.errors, p.errors
    finally:
        ctx.close()


def test_bare_view_shows_no_tools_on_desktop_and_phone(new_page):
    p = new_page(viewport={"width": 1400, "height": 900})
    p.goto("/play?view=bare")
    start(p)
    expect(p.locator("[data-region=tools]")).to_have_count(0)
    expect(p.get_by_role("tablist")).to_have_count(0)
    expect(p.locator("[data-anchor=history]")).to_be_visible()
    expect(p.get_by_role("button", name=ACCEPT).first).to_be_visible()
    # the layout menu offers the way back
    p.get_by_role("button", name="Layout").click()
    p.get_by_role("menuitem", name=re.compile("^Full")).or_(p.get_by_role("button", name=re.compile("^Full"))).first.click()
    expect(p.locator("[data-region=tools]").first).to_be_visible()

    phone = new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    phone.goto("/play?view=bare")
    phone.get_by_role("button", name="Start negotiation").click()
    expect(phone.get_by_role("button", name="Counter-offer").or_(phone.locator("[data-anchor=send]").get_by_role("button", name="Send offer")).first).to_be_visible()
    expect(phone.get_by_role("navigation", name="Sections")).to_have_count(0)  # no Tools tab, no Assistant
    expect(phone.locator("[data-region=tools]")).to_have_count(0)


def test_a_style_sheet_that_hides_accept_is_dropped(e2e_browser, css_server):
    from .conftest import Page, _context

    ctx = _context(e2e_browser, css_server, viewport={"width": 1400, "height": 900})
    p = Page(ctx.new_page(), css_server)
    try:
        name = "e2e" + uuid.uuid4().hex[:8]
        r = p.request.post("/api/auth/register", data={"username": name, "password": "secret1", "confirm": "secret1",
                                                       "consent": True})
        assert r.ok, r.text()
        p.goto("/app")
        start(p)
        wait_for_my_turn_with_an_offer(p)
        paper = "() => getComputedStyle(document.documentElement).getPropertyValue('--paper').trim()"
        assert p.evaluate(paper) != "10 200 30"
        header_button = p.get_by_role("banner").get_by_role("button", name="Assistant", exact=True)
        box = p.get_by_placeholder("Message the assistant")
        if not box.count():
            header_button.click()
        expect(box).to_be_visible()
        box.fill("calm")
        box.press("Enter")
        p.wait_for_function(f"() => ({paper})() === '10 200 30'")  # a harmless sheet applies
        box.fill("hide")
        box.press("Enter")
        p.wait_for_function("() => !document.getElementById('hani2-custom-css')")  # the page dropped it
        expect(p.get_by_role("button", name=ACCEPT).first).to_be_visible()
        assert not p.errors, p.errors
    finally:
        ctx.close()


def _drag_across(p, locator, a: float, b: float):
    """Drag across ``locator`` from fraction ``a`` to fraction ``b`` of its width."""
    box = locator.bounding_box()
    y = box["y"] + box["height"] / 2
    p.mouse.move(box["x"] + box["width"] * a, y)
    p.mouse.down()
    p.mouse.move(box["x"] + box["width"] * (a + b) / 2, y, steps=4)
    p.mouse.move(box["x"] + box["width"] * b, y, steps=4)
    p.mouse.up()


@pytest.mark.parametrize("view", ["simple", "focus"])
def test_the_action_panel_opens_the_utility_bar_in_a_popup(new_page, view):
    """Outside the full view the action panel opens offer generators (the Utility Bar first) and any
    other tool in a popup; a drag on the bar lists offers and a picked one fills the counter-offer."""
    p = new_page(viewport={"width": 1400, "height": 900})
    p.goto(f"/play?view={view}")
    start(p)
    if view == "focus":  # the start reveals the participant's preferences in the popup, and focus stays
        expect(p.get_by_test_id("tool-popup")).to_have_attribute("aria-label", "Preferences (popup)")
        expect(p.locator("[data-region=tools]")).to_have_count(0)
    gen = p.get_by_test_id("launch-generator")
    expect(gen).to_have_text(re.compile("Utility Bar"))
    gen.click()
    popup = p.get_by_test_id("tool-popup")
    expect(popup).to_be_visible()
    expect(gen).to_have_attribute("aria-pressed", "true")
    bar = popup.get_by_test_id("range-bar-area")
    expect(bar).to_be_visible()
    popup.get_by_role("combobox").first.select_option(label="All offers")
    _drag_across(p, bar, 0.05, 0.95)
    expect(bar).to_have_attribute("aria-valuetext", re.compile(r"^\d+% – \d+%$"))
    rows = popup.locator("tbody tr")
    expect(rows.first).to_be_visible()
    rows.first.click()
    # the counter-offer editor opens with the deal; the popup does not cover the offer area
    expect(p.locator("[data-anchor=send]").get_by_role("button", name="Send offer")).to_be_visible()
    # a click on the bar picks the nearest deal
    box = bar.bounding_box()
    p.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] / 2)
    expect(bar).to_have_attribute("aria-valuetext", re.compile("^nearest to"))
    expect(popup.locator("tbody tr").first).to_be_visible()
    # Esc closes it; the Tools menu opens any other tool in its place
    popup.press("Escape")
    expect(popup).to_have_count(0)
    p.get_by_test_id("launch-tools").click()
    menu = p.get_by_role("menu", name="Open a tool")
    expect(menu.get_by_text("Offer generators")).to_be_visible()
    menu.get_by_role("menuitem", name=re.compile("^Preferences")).click()
    expect(p.get_by_test_id("tool-popup")).to_have_attribute("aria-label", "Preferences (popup)")


def test_full_view_opens_a_pane_tool_in_a_popup_and_back(new_page):
    p = new_page(viewport={"width": 1400, "height": 900})
    p.goto("/play")
    start(p)
    expect(p.get_by_test_id("launch-generator")).to_have_count(0)  # the generators sit next to the offer
    p.get_by_role("button", name="Open Utility Bar in a popup").click()
    popup = p.get_by_test_id("tool-popup")
    expect(popup.get_by_test_id("range-bar-area")).to_be_visible()
    expect(p.get_by_text("Utility Bar is open in a popup.")).to_be_visible()
    p.get_by_role("button", name="Bring it back here").click()
    expect(popup).to_have_count(0)
    expect(p.get_by_test_id("range-bar-area")).to_be_visible()


def test_send_offer_in_the_selector_sends_the_picked_deal(new_page):
    """Picking a deal in the Utility-based Selector only fills the counter-offer; its Send offer button
    then sends the deal at once, with the message typed in the message box, and it lands in the history."""
    p = new_page(viewport={"width": 1400, "height": 900})
    p.goto("/play")
    start(p)
    side = p.locator('[data-anchor="pane:side"]')
    side.get_by_role("tab", name="Utility-based Selector").click()
    panel = side.get_by_role("tabpanel")
    tool_send = panel.get_by_role("button", name="Send offer")
    expect(tool_send).to_be_disabled()  # nothing picked yet
    expect(tool_send).to_have_attribute("title", "Pick a deal first.")
    # wait for our turn and open the composer (the opponent may move first)
    counter = p.get_by_role("button", name="Counter-offer")
    box = p.get_by_placeholder(re.compile("Explain your offer"))
    for _ in range(300):
        if counter.count() and counter.first.is_enabled() and not box.count():
            counter.first.click()
        if box.count() and box.first.is_enabled():
            break
        p.wait_for_timeout(100)
    expect(box).to_be_enabled()
    n_rows = panel.locator("tbody tr")
    expect(n_rows.first).to_be_visible()
    n_rows.first.click()
    expect(tool_send).to_be_enabled()
    # typed just before the click: the message must still go with the offer
    box.fill("Sent straight from the Selector.")
    tool_send.click()
    expect(p.locator('[data-anchor="history"]').get_by_text("Sent straight from the Selector.")).to_be_visible()
    expect(tool_send).to_be_disabled()  # the deal is sent; pick again for the next offer
    # the message was used up: on our next turn the message box is empty
    expect(p.get_by_role("button", name=ACCEPT).first).to_be_enabled(timeout=30000)
    if not box.count():
        counter.first.click()
    expect(box).to_be_enabled()
    expect(box).to_have_value("")


def test_random_generates_a_deal_and_send_offer_sends_it(new_page):
    """The Random generator (admins): Generate fills the counter-offer, its Send offer sends that deal."""
    p = new_page(viewport={"width": 1400, "height": 900})
    fresh_admin(p)
    p.goto("/app")
    start(p)
    side = p.locator('[data-anchor="pane:side"]')
    side.get_by_role("tab", name="Random").click()
    panel = side.get_by_role("tabpanel")
    tool_send = panel.get_by_role("button", name="Send offer")
    expect(tool_send).to_have_attribute("title", "Generate a deal first.")
    expect(panel.get_by_role("button", name="Set Offer")).to_have_count(0)
    accept = p.get_by_role("button", name=ACCEPT).first
    dock_send = p.locator("[data-anchor=send]").get_by_role("button", name="Send offer")
    for _ in range(300):  # our turn: the opponent may move first
        if (accept.count() and accept.is_enabled()) or (dock_send.count() and dock_send.is_enabled()):
            break
        p.wait_for_timeout(100)
    expect(p.locator('[data-anchor="history"]').get_by_text("You", exact=True)).to_have_count(0)
    panel.get_by_role("button", name="Generate").click()
    expect(panel.get_by_text("Generated deal")).to_be_visible()
    expect(tool_send).to_be_enabled()
    tool_send.click()
    expect(tool_send).to_be_disabled()
    expect(panel.get_by_text("Generated deal")).to_have_count(0)
    expect(p.locator('[data-anchor="history"]').get_by_text("You", exact=True).first).to_be_visible()


def test_the_llm_tool_recommends_an_offer_when_nothing_is_typed(new_page):
    """With an empty instruction the LLM tool's button reads Recommend an offer; typing makes it Generate."""
    p = new_page(viewport={"width": 1400, "height": 900})
    fresh_admin(p)
    p.goto("/app")
    start(p)
    side = p.locator('[data-anchor="pane:side"]')
    side.get_by_role("tab", name="LLM").click()
    panel = side.get_by_role("tabpanel")
    expect(panel.get_by_role("button", name="Recommend an offer")).to_be_visible()
    panel.locator("textarea").fill("hold firm on the price")
    expect(panel.get_by_role("button", name="Generate")).to_be_visible()
    panel.locator("textarea").fill("")
    expect(panel.get_by_role("button", name="Recommend an offer")).to_be_visible()
    panel.get_by_text("Text only").click()
    expect(panel.get_by_role("button", name="Write a message")).to_be_visible()


def fresh_admin(p) -> str:
    """Log ``p`` in as a new admin account: sessions resume per user, so tests that share the built-in
    admin would find each other's negotiation running."""
    name = "adm" + uuid.uuid4().hex[:8]
    assert p.request.post("/api/auth/login", data={"username": "admin", "password": "adminpass"}).ok
    r = p.request.post("/api/admin/users", data={"username": name, "password": "secret1", "is_admin": True})
    assert r.ok, r.text()
    assert p.request.post("/api/auth/logout").ok
    assert p.request.post("/api/auth/login", data={"username": name, "password": "secret1"}).ok
    return name
