"""Library → Hosted agents in a real browser: register a team's address, see its token once, check the
host, switch it off and make the project's Assistants self-hosted."""

from __future__ import annotations

import uuid

from playwright.sync_api import expect


def test_register_check_and_self_host(new_page):
    p = new_page(viewport={"width": 1400, "height": 1200})
    assert p.request.post("/api/auth/login", data={"username": "admin", "password": "adminpass"}).ok
    name = "E2E" + uuid.uuid4().hex[:6]
    assert p.request.put(f"/api/admin/projects/{name}", data={"data": {"kind": "assistant", "year": 2027}}).ok
    p.goto("/admin#hosted")
    p.get_by_role("combobox", name="Project").select_option(name)
    expect(p.get_by_text("None yet")).to_be_visible()
    p.get_by_role("textbox", name="Name").fill("teamA")
    p.get_by_role("textbox", name="Address").fill("http://127.0.0.1:9")
    p.get_by_role("button", name="Register").click()
    expect(p.get_by_text("Token for remote:teamA")).to_be_visible()
    expect(p.locator("code", has_text="h2t_")).to_be_visible()  # shown once
    expect(p.get_by_text("remote:teamA", exact=True)).to_be_visible()
    p.get_by_role("button", name="Check").click()
    expect(p.locator("[data-check=fail]")).to_contain_text("cannot be reached")
    p.get_by_role("switch", name="Use remote:teamA").click()
    p.get_by_role("switch", name="Assistants are self-hosted").click()
    expect(p.get_by_text("Saved").first).to_be_visible()
    data = p.request.get(f"/api/admin/projects/{name}/hosted").json()
    assert data["mode"]["assistants"] is True and data["agents"][0]["enabled"] is False
    assert "token" not in data["agents"][0]
