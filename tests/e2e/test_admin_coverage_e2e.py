"""The admin console sets what the settings files can hold: the new rows of a project, the whole-file
editors of a project and a settings page, and the new groups of General, Negotiation, Participant
interface, Tool settings and Study forms, in a real browser."""

from __future__ import annotations

import uuid

import yaml
from playwright.sync_api import expect


def _admin(p):
    assert p.request.post("/api/auth/login", data={"username": "admin", "password": "adminpass"}).ok


def _project(p) -> str:
    name = "COV" + uuid.uuid4().hex[:6]
    assert p.request.put(f"/api/admin/projects/{name}", data={"data": {"kind": "assistant", "year": 2027}}).ok
    assert p.request.put(f"/api/admin/projects/{name}/studies/s1", data={"data": {"type": "prolific"}}).ok
    return name


def _yaml(p, url: str) -> dict:
    return yaml.safe_load(p.request.get(url).json()["yaml"]) or {}


def test_project_rows_and_the_whole_file_editor(new_page):
    p = new_page(viewport={"width": 1400, "height": 1100})
    _admin(p)
    name = _project(p)
    p.goto("/admin#projects")
    p.get_by_text(name, exact=True).first.click()
    expect(p.get_by_text("Defaults for its studies")).to_be_visible()
    p.get_by_role("combobox", name="assistant_starts_on", exact=True).select_option("yes")
    p.get_by_role("combobox", name="questionnaires", exact=True).select_option("no")
    p.get_by_role("button", name="Add a briefing").click()
    p.get_by_label("Briefing 1").fill("Your manager will not approve more than 3200.")
    p.get_by_role("combobox", name="For").first.select_option("assistant")
    p.locator("[data-information-more]").click()
    p.get_by_role("combobox", name="Market research describes").select_option("both")
    # a custom variable cannot take the name of a setting
    p.get_by_label("New variable name").fill("scheduling")
    expect(p.locator("[data-reserved-name]")).to_be_visible()
    p.get_by_label("New variable name").fill("")
    # the file editor is locked while the rows have unsaved changes
    raw = p.locator("#raw-project-yaml")
    expect(raw.get_by_role("button", name="Edit the file")).to_be_disabled()
    p.get_by_role("button", name="Save", exact=True).click()
    url = f"/api/admin/projects/{name}"
    expect(raw.get_by_role("button", name="Edit the file")).to_be_enabled()
    d = _yaml(p, url)
    defaults = d.get("defaults", d)
    assert defaults["assistant_starts_on"] is True and defaults["questionnaires"] is False
    info = defaults["information"]
    assert info["briefing"] == [{"text": "Your manager will not approve more than 3200.", "to": "assistant"}]
    assert info["market_research"] == {"sides": "both"}
    # the whole file: a key without a row, then a refusal with the reason
    raw.get_by_role("button", name="Edit the file").click()
    box = raw.get_by_role("textbox")
    expect(box).to_contain_text("assistant_starts_on")
    box.fill(box.input_value() + "sponsor: ACME\n")
    raw.get_by_role("button", name="Save the file").click()
    expect(raw.get_by_role("button", name="Edit the file")).to_be_visible()
    assert _yaml(p, url)["sponsor"] == "ACME"
    raw.get_by_role("button", name="Edit the file").click()
    raw.get_by_role("textbox").fill("defaults:\n  questionnaire_agent: partner\n")
    raw.get_by_role("button", name="Save the file").click()
    expect(p.get_by_text("questionnaire_agent must be assistant or opponent").first).to_be_visible()
    assert _yaml(p, url)["sponsor"] == "ACME"  # refused: the file is unchanged
    # the reference games of the project's scores
    expect(p.locator("text=Reference games").first).to_be_visible()
    # the file editor reads the file when it opens: a change saved elsewhere since the page loaded is kept
    raw.get_by_role("button", name="Close without saving").click()
    text = p.request.get(url).json()["yaml"] + "saved_elsewhere: yes\n"
    assert p.request.put(url, data={"yaml": text}).ok
    raw.get_by_role("button", name="Edit the file").click()
    expect(raw.get_by_role("textbox")).to_contain_text("saved_elsewhere")


def test_a_study_has_its_own_self_hosted_mode(new_page):
    p = new_page(viewport={"width": 1400, "height": 1100})
    _admin(p)
    name = _project(p)
    p.goto("/admin#projects")
    p.get_by_text(name, exact=True).first.click()
    p.get_by_role("button").filter(has_text="participants").filter(has_text="s1").first.click()
    group = p.locator("#setting-study-hosted")
    group.get_by_role("combobox", name="Own self-hosted mode").select_option("own")
    group.get_by_role("combobox", name="Opponents are self-hosted").select_option("yes")
    p.get_by_role("button", name="Save", exact=True).click()
    expect(p.get_by_text("Saved study.yaml").first).to_be_visible()
    d = _yaml(p, f"/api/admin/projects/{name}/studies/s1")
    assert d.get("overrides", d)["hosted"] == {"assistants": False, "opponents": True}


def test_settings_pages_show_the_new_groups(new_page):
    p = new_page(viewport={"width": 1400, "height": 1100})
    _admin(p)
    p.goto("/admin#general")
    expect(p.get_by_role("switch", name="Sign in with GitHub").or_(p.get_by_label("Sign in with GitHub"))).to_be_visible()
    p.get_by_label("New provider name").fill("partner_site")
    p.get_by_role("button", name="Add a provider").click()
    expect(p.locator("[data-sso-providers]")).to_contain_text("partner_site")
    expect(p.get_by_label("partner_site Shared secret")).to_be_visible()
    expect(p.locator("#raw-env").get_by_role("button", name="Edit the file")).to_be_disabled()  # unsaved row edits
    p.goto("/admin#negotiation")
    expect(p.get_by_text("HAN league agents")).to_be_visible()
    expect(p.get_by_text("Who knows what (every project)")).to_be_visible()
    p.goto("/admin#interface")
    expect(p.get_by_text("Browser AI agents (WebMCP)")).to_be_visible()
    # unset in the files, WebMCP is on (its default), and the switch says so
    expect(p.get_by_role("switch", name="Offer tools to browser AI agents")).to_have_attribute("aria-checked", "true")
    expect(p.get_by_role("switch", name="Also for Prolific participants")).to_have_attribute("aria-checked", "false")
    expect(p.get_by_role("combobox", name="Relabel the sides")).to_be_visible()
    p.goto("/admin#tools")
    expect(p.get_by_label("Scenario Info appears", exact=True)).to_be_visible()
    p.goto("/admin#assistant")
    raw = p.locator("#raw-assistant")
    raw.get_by_role("button", name="Edit the file").click()
    raw.get_by_role("textbox").fill("[1, 2]")
    expect(raw.locator("[data-raw-problem]")).to_contain_text("JSON object")
    expect(raw.get_by_role("button", name="Save the file")).to_be_disabled()


def test_study_forms_name_a_form_and_map_participant_types(new_page):
    p = new_page(viewport={"width": 1400, "height": 1100})
    _admin(p)
    p.goto("/admin#forms")
    expect(p.locator("#setting-all-questionnaires").get_by_role("switch").or_(p.locator("#setting-all-questionnaires").get_by_label("Ask the questionnaires"))).to_be_visible()
    expect(p.locator("#setting-form-named").get_by_role("combobox", name="Use the named form")).to_be_visible()
    p.get_by_role("tab", name="Pre-questionnaire").click()
    expect(p.locator("[data-participant-type]")).to_be_visible()
