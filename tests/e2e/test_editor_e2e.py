"""The project editor in the admin console: a `?` opens its help, the score builder saves a score only
at 100 % (Normalise gets it there), a page Save afterwards keeps that score, a mode that
contradicts the pool is refused with a 400, the criteria picker shows the catalogue's groups with
validated criteria marked, and so do the predefined questionnaires of the Study forms page (TAM sets
with their source warning, for admins only)."""

from __future__ import annotations

import uuid

from playwright.sync_api import expect


def _admin(p):
    assert p.request.post("/api/auth/login", data={"username": "admin", "password": "adminpass"}).ok


def _open_project(p, name):
    p.goto("/admin#projects")
    p.get_by_text(name, exact=True).first.click()
    expect(p.get_by_text("Defaults for its studies")).to_be_visible()


def _project(p) -> str:
    name = "E2E" + uuid.uuid4().hex[:6]
    r = p.request.put(f"/api/admin/projects/{name}", data={"data": {"kind": "assistant", "year": 2027}})
    assert r.ok, r.text()
    return name


def test_a_question_mark_opens_the_settings_help(new_page):
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    name = _project(p)
    _open_project(p, name)
    p.get_by_role("button", name="About Mode").click()
    dialog = p.get_by_role("dialog")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("derived from the opponents")
    expect(dialog.locator("table").first).to_be_visible()
    p.keyboard.press("Escape")
    expect(dialog).to_have_count(0)
    # a scheduling row lists the methods of its dimension from the scheduling registry
    p.get_by_role("button", name="About Assistant assignment").click()
    expect(p.get_by_role("dialog")).to_contain_text("latin_square")
    p.keyboard.press("Escape")
    # the Pairing group appears only for Paired and Mixed
    expect(p.get_by_text("Where people meet", exact=True)).to_have_count(0)
    p.get_by_role("combobox", name="Mode").select_option("paired")
    expect(p.get_by_text("Where people meet", exact=True)).to_be_visible()


def test_build_a_score_then_save_a_contradiction(new_page):
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    name = _project(p)
    _open_project(p, name)

    p.get_by_role("button", name="New score").click()
    builder = p.locator("[data-score-builder]")
    builder.get_by_label("Score key").fill("e2e_score")
    for crit in ("human_advantage", "agreement"):
        builder.get_by_label("Search criteria").fill(crit)
        builder.get_by_role("listbox", name="Criteria").get_by_role("option").filter(has_text=crit).first.click()
    for crit in ("human_advantage", "agreement"):
        w = builder.get_by_label(f"Weight of {crit} (%)")
        w.fill("30")
        w.blur()
    expect(builder.locator("[data-weight-sum]")).to_have_text("Sum 60 %")
    save = builder.get_by_role("button", name="Save score")
    expect(save).to_be_disabled()
    builder.get_by_role("button", name="Normalise", exact=True).click()
    expect(builder.locator("[data-weight-sum]")).to_have_text("Sum 100 %")
    expect(save).to_be_enabled()
    save.click()
    expect(p.get_by_text("Saved score e2e_score")).to_be_visible()
    scores = p.request.get(f"/api/admin/scores?project={name}").json()
    mine = next(s for s in scores["scores"] if s["key"] == "e2e_score")
    assert [round(c["weight"], 6) for c in mine["components"]] == [0.5, 0.5]

    # Mixed without a pool contradicts the opponents: the editor says so, and saving gets a 400
    p.get_by_role("combobox", name="Mode").select_option("mixed")
    expect(p.locator("[data-mode-problem]")).to_be_visible()
    with p.expect_response(lambda r: r.url.endswith(f"/api/admin/projects/{name}") and r.request.method == "PUT") as resp:
        p.get_by_role("button", name="Save", exact=True).click()
    assert resp.value.status == 400
    assert "mixed" in resp.value.text()

    # Solo saves, and the page's Save keeps the score the builder wrote
    p.get_by_role("combobox", name="Mode").select_option("solo")
    with p.expect_response(lambda r: r.url.endswith(f"/api/admin/projects/{name}") and r.request.method == "PUT") as resp:
        p.get_by_role("button", name="Save", exact=True).click()
    assert resp.value.status == 200, resp.value.text()
    scores = p.request.get(f"/api/admin/scores?project={name}").json()
    assert "e2e_score" in [s["key"] for s in scores["scores"]]


def test_k_of_n_and_repeats(new_page):
    """K counted negotiations over N Assistants: the row shows both, warns at K > N, the server
    refuses that file, and Repeats on lets it save."""
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    name = "E2E" + uuid.uuid4().hex[:6]
    r = p.request.put(f"/api/admin/projects/{name}", data={"data": {
        "kind": "assistant", "defaults": {"n_required": 2, "assistants": ["x.AssistantA", "x.AssistantB"]},
        "scheduling": {"assistants": "latin_square"}}})
    assert r.ok, r.text()
    _open_project(p, name)
    row = p.locator("[data-k-of-n]")
    expect(row).to_contain_text("K = 2 counted negotiations, N = 2 Assistants")
    expect(row).to_have_attribute("data-k-of-n", "ok")
    p.get_by_role("button", name="Increase n_required").click()
    expect(row).to_have_attribute("data-k-of-n", "warn")
    save = p.get_by_role("button", name="Save", exact=True)
    with p.expect_response(lambda r: r.url.endswith(f"/api/admin/projects/{name}") and r.request.method == "PUT") as resp:
        save.click()
    assert resp.value.status == 400 and "assistant_repeats" in resp.value.text()
    p.get_by_role("combobox", name="Repeats").select_option("yes")
    expect(row).to_have_attribute("data-k-of-n", "ok")
    with p.expect_response(lambda r: r.url.endswith(f"/api/admin/projects/{name}") and r.request.method == "PUT") as resp:
        save.click()
    assert resp.value.status == 200, resp.value.text()


def test_a_paired_studys_pool_editor_offers_only_the_human_entry(new_page):
    """Opponents → the pool picker of a study declared Paired in an HI project offers human+assistant
    only (no human, no AI agent or group); a Solo study offers no human entry."""
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    name = _project(p)
    for study, mode in (("pair", "paired"), ("alone", "solo")):
        r = p.request.put(f"/api/admin/projects/{name}/studies/{study}", data={"data": {"type": "online", "overrides": {"study_mode": mode}}})
        assert r.ok, r.text()
    p.goto("/admin#opponents")
    p.get_by_role("combobox", name="Layer to edit").first.select_option(f"study:{name}/pair")
    picker = p.locator("#setting-opponent-pool")
    expect(picker.locator("[data-pool-mode=paired]")).to_be_visible()
    choices = picker.get_by_role("listbox", name="Pool choices").locator("label")
    expect(choices).to_have_count(1)
    expect(choices.first).to_contain_text("human+assistant")
    p.get_by_role("combobox", name="Layer to edit").first.select_option(f"study:{name}/alone")
    picker = p.locator("#setting-opponent-pool")
    expect(picker.locator("[data-pool-mode=solo]")).to_be_visible()
    box = picker.get_by_role("listbox", name="Pool choices")
    expect(box.locator("label").first).to_be_visible()
    expect(box.locator("label").filter(has_text="human")).to_have_count(0)


def test_editing_a_score_keeps_zero_if_and_needs_assistant(new_page):
    """A copy of a built-in keeps its rules (zero_if, needs_assistant); Edit, then Save score, keeps them."""
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    name = _project(p)
    for key, src in (("my_han", "han_outcome"), ("my_team", "hi_team")):
        r = p.request.post(f"/api/admin/projects/{name}/scores/{key}/duplicate", data={"from": src})
        assert r.ok, r.text()
    before = {s["key"]: s for s in p.request.get(f"/api/admin/scores?project={name}").json()["scores"]}
    assert before["my_han"]["zero_if"] == ["opponent_failed"] and before["my_team"]["needs_assistant"] is True
    _open_project(p, name)
    for key in ("my_han", "my_team"):
        p.locator("#setting-scores > div > div").filter(has_text=key).get_by_role("button", name="Edit").click()
        builder = p.locator("[data-score-builder]")
        expect(builder.get_by_role("button", name="About Zero if")).to_be_visible()
        expect(builder.get_by_role("button", name="About Needs an Assistant")).to_be_visible()
        builder.get_by_role("button", name="Save score").click()
        expect(p.get_by_text(f"Saved score {key}")).to_be_visible()
    after = {s["key"]: s for s in p.request.get(f"/api/admin/scores?project={name}").json()["scores"]}
    assert after["my_han"]["zero_if"] == ["opponent_failed"]
    assert after["my_team"]["needs_assistant"] is True


def test_the_criteria_picker_is_grouped_and_marks_validated_criteria(new_page):
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    name = _project(p)
    _open_project(p, name)
    p.get_by_role("button", name="New score").click()
    builder = p.locator("[data-score-builder]")
    picker = builder.get_by_role("listbox", name="Criteria")
    groups = picker.locator("[data-group]")
    expect(groups.first).to_have_attribute("data-group", "outcome")
    titles = [g.get_attribute("aria-label") for g in groups.all()]
    assert titles[:3] == ["Outcome and utility", "Efficiency and welfare", "Fairness"], titles
    fairness = picker.get_by_role("group", name="Fairness")
    expect(fairness.get_by_role("option").filter(has_text="fairness_gap")).to_have_count(1)
    expect(fairness.get_by_role("option").filter(has_text="fairness_gap").locator("[data-validated]")).to_have_count(1)
    judged = picker.get_by_role("group", name="Language-model judgements").get_by_role("option").filter(has_text="ja_overall")
    expect(judged).to_have_count(1)
    expect(judged.locator("[data-validated]")).to_have_count(0)  # a judgement is not validated
    # searching keeps the groups: a group's title finds its criteria
    builder.get_by_label("Search criteria").fill("fairness")
    expect(picker.get_by_role("group", name="Fairness")).to_be_visible()


def test_predefined_questionnaires_mark_the_validated_ones(new_page):
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    p.goto("/admin#forms")
    p.get_by_role("button", name="Add predefined questionnaires").click()
    svi = p.locator("#setting-form-library label").filter(has_text="Subjective Value Inventory")
    expect(svi.locator("[data-validated]")).to_have_count(1)
    expect(svi.get_by_role("link", name="source")).to_have_attribute("href", "https://www.subjectivevalue.com/")
    tam = p.locator("#setting-form-library label").filter(has_text="TAM perceived ease of use")
    expect(tam).to_have_count(1)
    expect(tam.locator("[data-validated]")).to_have_count(0)


def test_study_forms_warn_admins_about_the_tam_items(new_page):
    """Each TAM set in the picker carries the registry's source warning (not the validated ones); a form
    using TAM items gets the warning above its preview, outside the form the participant would see."""
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    p.goto("/admin#forms")
    p.get_by_role("button", name="Add predefined questionnaires").click()
    lib = p.locator("#setting-form-library")
    for title in ("TAM perceived ease of use", "TAM perceived usefulness, 2 items"):
        warn = lib.locator("label").filter(has_text=title).get_by_test_id("set-source-warning")
        expect(warn).to_contain_text("not been checked against the published instrument (Davis, 1989)")
    svi = lib.locator("label").filter(has_text="Subjective Value Inventory")
    expect(svi.get_by_test_id("set-source-warning")).to_have_count(0)
    lib.locator("label").filter(has_text="TAM perceived ease of use").locator("input[type=checkbox]").check()
    lib.get_by_role("button", name="Add 1 set to the form").click()
    preview = p.locator("#setting-form-preview")
    expect(preview.get_by_test_id("form-source-warning")).to_contain_text("TAM perceived ease of use")
    expect(preview.get_by_test_id("form-source-warning")).to_contain_text("participants never see it")
    form = preview.locator("form")
    expect(form).to_be_visible()
    expect(form).not_to_contain_text("Davis")
    expect(form).not_to_contain_text("not been checked")


def test_zero_if_offers_grouped_criteria(new_page):
    """The score builder's Zero if menu lists the criteria in the catalogue's groups, validated ones marked."""
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    name = _project(p)
    _open_project(p, name)
    p.get_by_role("button", name="New score").click()
    builder = p.locator("[data-score-builder]")
    menu = builder.get_by_role("combobox", name="Add to Zero if")
    expect(menu.locator("optgroup").first).to_be_attached()  # the catalogue has loaded
    labels = [g.get_attribute("label") for g in menu.locator("optgroup").all()]
    assert labels[:2] == ["Outcome and utility", "Efficiency and welfare"] and "Task success and rules" in labels, labels
    assert "Combined scores" not in labels  # a rule names criteria, not scores
    failed = menu.locator("optgroup[label='Task success and rules'] option[value='opponent_failed']")
    expect(failed).to_have_attribute("data-validated", "")
    menu.select_option("opponent_failed")
    chips = builder.locator("[data-key-list='Zero if'] .chip")
    expect(chips).to_have_count(1)
    expect(chips.first.locator("[data-validated]")).to_have_count(1)


def test_study_forms_warn_when_the_form_in_effect_uses_tam(new_page):
    """A saved post-session form with TAM items: 'In effect here' carries the source warning."""
    p = new_page(viewport={"width": 1400, "height": 1000})
    _admin(p)
    url = "/api/admin/settings/post_session?layer=settings"
    before = p.request.get(url).json()
    text = p.request.post("/api/admin/questionnaires/compose", data={"sets": ["tam_ease"], "form": "post_session"}).json()["text"]
    assert p.request.put(url, data={"text": text}).ok
    try:
        p.goto("/admin#forms")
        p.get_by_role("tab", name="Post-session").click()
        warn = p.locator("#setting-form-effective-warning")
        expect(warn).to_contain_text("TAM perceived ease of use")
        expect(warn).to_contain_text("Davis, 1989")
    finally:
        if before.get("exists"):
            p.request.put(url, data={"text": before["text"]})
        else:
            p.request.delete(url)
