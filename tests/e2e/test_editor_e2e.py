"""The project editor in the admin console: a `?` opens its help, the score builder saves a score only
at 100 % (Normalise gets it there), a page Save afterwards keeps that score, and a mode that
contradicts the pool is refused with a 400."""

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
        builder.get_by_role("option").filter(has_text=crit).first.click()
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
