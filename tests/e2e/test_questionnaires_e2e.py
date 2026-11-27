"""The questionnaire explorer and the Study forms item editor in a real browser: add a set and
find it in "Add predefined questionnaires", sourced sets offer only "Copy as new", and the items
of a project's form are reordered, removed, edited and added, then saved to that layer's file."""

from __future__ import annotations

import re
import uuid

import yaml
from playwright.sync_api import expect


def _admin(p):
    assert p.request.post("/api/auth/login", data={"username": "admin", "password": "adminpass"}).ok


def test_add_a_set_and_see_it_in_add_predefined_questionnaires(new_page):
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    sid = "E2E-" + uuid.uuid4().hex[:6]
    title = f"Questions {sid}"
    p.goto("/admin#questionnaires")
    # a sourced set is read-only: no Edit, only Copy as new; its warning is shown here
    tam = p.locator('[data-set="tam_ease"]')
    tam.get_by_role("button").first.click()
    details = tam.locator("[data-set-details]")
    expect(details.get_by_role("button", name="Copy as new")).to_be_visible()
    expect(details.get_by_role("button", name="Edit")).to_have_count(0)
    expect(details).to_contain_text("Davis, 1989")
    expect(details).to_contain_text("default_settings/questionnaire_library/tam_ease.yaml")
    # a new set
    p.get_by_role("button", name="New set").click()
    editor = p.get_by_label("Set (YAML)")
    editor.fill(f"id: {sid}\ntitle: {title}\nforms: [post_session]\nquestions:\n  - {{id: e2e_q, text: Bad, type: nope}}\n")
    expect(p.locator("[data-problems]")).to_contain_text("unknown type")
    expect(p.get_by_role("button", name="Save set")).to_be_disabled()
    editor.fill(f"id: {sid}\ntitle: {title}\nforms: [post_session]\nquestions:\n  - {{id: e2e_q_{sid[-6:]}, text: Fine, type: yes_no}}\n")
    expect(p.get_by_role("button", name="Save set")).to_be_enabled()
    p.get_by_role("button", name="Save set").click()
    row = p.locator(f'[data-set="{sid}"]')
    expect(row).to_contain_text("Your own")
    expect(row.locator("[data-delete-hint]")).to_contain_text("rm ")
    expect(row.locator("[data-delete-hint]")).to_contain_text(f"questionnaire_library/{sid}.yaml")
    # it is offered by the Study forms page
    p.goto("/admin#forms")
    p.get_by_role("button", name="Add predefined questionnaires").click()
    p.locator("#setting-form-library").get_by_label("Show sets meant for other forms").check()
    expect(p.locator("#setting-form-library label").filter(has_text=title)).to_have_count(1)


def test_reorder_remove_edit_and_add_form_items(new_page):
    p = new_page(viewport={"width": 1400, "height": 1100})
    _admin(p)
    name = "E2EF" + uuid.uuid4().hex[:6]
    assert p.request.put(f"/api/admin/projects/{name}", data={"data": {"kind": "assistant", "year": 2027}}).ok
    sus = next(s for s in p.request.get("/api/admin/questionnaire-library").json()["sets"] if s["id"] == "sus")
    form = {"title": "After", "questions": [{"id": "a", "text": "Alpha?", "type": "likert5", "required": True},
                                            {"id": "b", "text": "Beta?", "type": "text"},
                                            *sus["questions"]]}
    layer = f"project:{name}"
    r = p.request.put(f"/api/admin/settings/per_negotiation?layer={layer}", data={"text": yaml.safe_dump(form, sort_keys=False)})
    assert r.ok, r.text()
    p.goto("/admin#forms")
    p.get_by_label("Layer to edit").select_option(layer)
    items = p.locator("#setting-form-items")
    expect(items.locator("[data-item]")).to_have_count(12)
    expect(items.locator("[data-scale-notice]")).to_have_count(0)  # all ten SUS items, as published
    # reorder: b up; remove sus_2 (a scored item of a published instrument: a notice, not a block)
    items.get_by_role("button", name="Move b up").click()
    expect(items.locator("[data-item]").first).to_have_attribute("data-item", "b")
    items.get_by_role("button", name="Remove sus_2").click()
    expect(items.locator("[data-item]")).to_have_count(11)
    expect(items.locator('[data-scale-notice="sus"]')).to_contain_text("may no longer match")
    expect(items.locator("[data-scale-notice]")).to_have_count(1)
    # edit an item's text, type and required flag; the title
    items.locator('[data-item="a"]').get_by_role("button", name="Alpha?").click()
    items.get_by_label("Text of a").fill("Alpha, edited?")
    items.get_by_label("Type of a").select_option("likert7")
    items.get_by_label("Label 7 of a").fill("Very")
    items.get_by_label("Required: a").uncheck()
    items.get_by_label("Form title").fill("After, edited")
    # add a new blank item and an item from a set
    items.get_by_role("button", name="New item").click()
    items.get_by_label("Set to add an item from").select_option("attention_check")
    items.get_by_label("Item to add").select_option(index=1)
    items.get_by_role("button", name="Add item").click()
    expect(items.locator("[data-item]")).to_have_count(13)
    # a complete published set added through the picker raises no notice for the sets it overlaps with
    p.get_by_role("button", name="Add predefined questionnaires").click()
    p.locator("#setting-form-library label").filter(has_text="TAM perceived usefulness, 2 items").locator("input").check()
    p.locator("#setting-form-library").get_by_role("button", name="Add 1 set to the form").click()
    expect(items.locator("[data-item]")).to_have_count(15)
    expect(items.locator("[data-scale-notice]")).to_have_count(1)  # only SUS (sus_2 removed)
    expect(items.locator('[data-scale-notice="sus"]')).to_have_count(1)
    # the YAML view shows the same form
    p.get_by_role("tab", name="YAML").click()
    expect(p.get_by_role("textbox", name="Form", exact=True)).to_have_value(re.compile("Alpha, edited"))
    p.get_by_role("tab", name="Items").click()
    p.get_by_role("button", name="Save", exact=True).click()
    expect(p.get_by_text(f"Saved to Project {name}")).to_be_visible()
    saved = yaml.safe_load(p.request.get(f"/api/admin/settings/per_negotiation?layer={layer}").json()["text"])
    ids = [q["id"] for q in saved["questions"]]
    assert ids[:3] == ["b", "a", "sus_1"] and "sus_2" not in ids and len(ids) == 15, ids
    a = saved["questions"][1]
    assert a["text"] == "Alpha, edited?" and a["type"] == "likert7" and a["required"] is False and a["labels"] == {7: "Very"}
    assert saved["title"] == "After, edited"
    assert sorted(ids[-2:]) == ["tam_effectiveness", "tam_useful"] and ids[-4] == "q12" and ids[-3] in {q["id"] for q in next(
        s for s in p.request.get("/api/admin/questionnaire-library").json()["sets"] if s["id"] == "attention_check")["questions"]}
