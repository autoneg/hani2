import json
import time

import pytest
from conftest import write_settings
from fastapi.testclient import TestClient


@pytest.fixture
def client(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c


def login(c, u="admin", p="adminpass"):
    r = c.post("/api/auth/login", json={"username": u, "password": p})
    assert r.status_code == 200, r.text


def recv_until(ws, pred, n=400):
    for _ in range(n):
        m = json.loads(ws.receive_text())
        if pred(m):
            return m
    raise AssertionError("message never arrived")


def test_config_and_spa(client):
    cfg = client.get("/api/config").json()
    assert cfg["auth_mode"] == "password" and cfg["title"] == "HANI2"
    r = client.get("/app")
    assert r.status_code in (200, 503)


def test_login_rules(client):
    assert client.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401
    assert client.get("/api/auth/me").json()["user"] is None
    assert client.post("/api/session", json={"mode": "main"}).status_code == 401
    login(client)
    me = client.get("/api/auth/me").json()
    assert me["user"] == "admin" and me["is_admin"]


def test_register_validation(client):
    bad = client.post("/api/auth/register", json={"username": "ai", "password": "secret", "confirm": "secret"})
    assert bad.status_code == 400
    mismatch = client.post("/api/auth/register", json={"username": "bob", "password": "secret", "confirm": "other"})
    assert mismatch.status_code == 400
    ok = client.post("/api/auth/register", json={"username": "bob", "password": "secret", "confirm": "secret", "consent": True})
    assert ok.status_code == 200 and client.get("/api/auth/me").json()["user"] == "bob"
    assert client.get("/api/admin/users").status_code == 403


def test_registering_with_an_admin_email_does_not_grant_admin(client, hani2_home):
    write_settings(hani2_home, "env.json", {"admin": {"emails": ["pi@lab.org"]}})
    r = client.post("/api/auth/register", json={"username": "mallory", "password": "secret", "confirm": "secret",
                                                "email": "PI@lab.org", "consent": True})
    assert r.status_code == 200
    assert not client.get("/api/auth/me").json()["is_admin"]
    assert client.get("/api/admin/users").status_code == 403
    from hani2 import auth

    auth.create_user("pi", "secret", email="pi@lab.org")  # an account the admin made: the email is trusted
    assert auth.is_admin_user("pi")


def test_usernames_cannot_name_other_folders_or_oauth_accounts():
    from hani2.auth import validate_new_user

    for name in ("..", ".", "_uploads", ".hidden", "gh_someone", "g_12345"):
        assert validate_new_user(name, "secret"), name
    assert validate_new_user("bob.smith", "secret") is None


def test_session_refuses_a_user_folder_outside_the_results():
    from hani2.testing import make_session

    with pytest.raises(ValueError):
        make_session(user="..")


def test_consent_enforced(client, hani2_home):
    write_settings(hani2_home, "env.json", {"auth": {"enforce_consent": True}})
    client.post("/api/auth/register", json={"username": "carol", "password": "secret", "confirm": "secret"})
    r = client.post("/api/session", json={"mode": "main"})
    assert r.status_code == 403 and r.json()["detail"] == "consent_required"
    assert client.post("/api/consent", json={"agree": True, "full_name": "Carol C"}).status_code == 200
    assert client.post("/api/session", json={"mode": "main"}).status_code == 200


def test_full_round_over_websocket(client):
    login(client)
    sid = client.post("/api/session", json={"mode": "main", "query": {}}).json()["sid"]
    with client.websocket_connect(f"/api/ws/{sid}") as ws:
        st = recv_until(ws, lambda m: m["type"] == "state")["state"]
        assert st["phase"] == "ready"
        ws.send_text(json.dumps({"type": "pref", "key": "n_steps", "value": 4}))
        ws.send_text(json.dumps({"type": "start"}))
        recv_until(ws, lambda m: m["type"] == "state" and m["state"]["negotiation"]["is_my_turn"] and not m["state"]["negotiation"]["thinking"])
        issue = st["scenario"]["issues"][0]
        value = issue["values"][0] if issue.get("values") else issue["min"]
        ws.send_text(json.dumps({"type": "draft", "values": {issue["name"]: value}}))
        d = recv_until(ws, lambda m: m["type"] == "draft")
        assert d["draft"][issue["name"]] == value
        ws.send_text(json.dumps({"type": "send", "text": "hello", "values": d["draft"]}))
        h = recv_until(ws, lambda m: m["type"] == "history" and any(x.get("by") == "human" for x in m["items"]))
        assert any(x.get("text") == "hello" for x in h["items"])
        ws.send_text(json.dumps({"type": "end"}))
        end = recv_until(ws, lambda m: m["type"] == "state" and m["state"]["phase"] == "ended")
        assert end["state"]["result"]["ended_by"] == "human"
    res = client.get("/api/admin/results").json()
    assert len(res["rows"]) == 1
    assert client.get("/api/admin/results.csv").text.startswith(("index", "scenario", "load"))
    ev = client.get("/api/admin/events/summary").json()
    assert ev["n_events"] > 0


def test_guest_playground_and_cookie_binding(client):
    r = client.post("/api/session", json={"mode": "guest", "query": {}})
    sid = r.json()["sid"]
    assert sid.startswith("guest:")
    with client.websocket_connect(f"/api/ws/{sid}") as ws:
        st = recv_until(ws, lambda m: m["type"] == "state")["state"]
        assert st["mode"] == "guest" and "My Results" not in [t["name"] for t in st["tools"]]
    from fastapi.testclient import TestClient

    from hani2.server import app

    other = TestClient(app)
    with pytest.raises(Exception):
        with other.websocket_connect(f"/api/ws/{sid}") as ws:
            ws.receive_text()


def test_prolific_session_id(client):
    sid = client.post("/api/session", json={"mode": "guest", "query": {"PROLIFIC_PID": "abc123", "noautostart": "1"}}).json()["sid"]
    assert sid == "prolific:abc123"
    with client.websocket_connect(f"/api/ws/{sid}") as ws:
        st = recv_until(ws, lambda m: m["type"] == "state")["state"]
        assert st["round"]["practice"] and st["study"]["kind"] == "prolific"


def test_admin_settings_roundtrip(client):
    login(client)
    s = client.get("/api/admin/settings/support_agent").json()
    s["autonomy"] = "semi"
    assert client.put("/api/admin/settings/support_agent", json=s).status_code == 200
    assert client.get("/api/admin/settings/support_agent").json()["autonomy"] == "semi"
    assert client.put("/api/admin/settings/consent", json={"text": "# Hi"}).status_code == 200
    assert client.get("/api/consent").json()["markdown"] == "# Hi"
    meta = client.get("/api/admin/meta").json()
    assert "template" in meta["agent_groups"] and "highlight" in meta["capabilities"]
    assert client.post("/api/admin/users", json={"username": "dave", "password": "pw12"}).status_code == 200
    assert any(u["username"] == "dave" for u in client.get("/api/admin/users").json())
    assert client.delete("/api/admin/users/dave").json()["ok"]


def test_active_tab_switch_pushes_state(client):
    login(client)
    sid = client.post("/api/session", json={"mode": "main", "query": {}}).json()["sid"]
    with client.websocket_connect(f"/api/ws/{sid}") as ws:
        recv_until(ws, lambda m: m["type"] == "state")
        ws.send_text(json.dumps({"type": "active_tab", "pane": "upper", "name": "Preferences"}))
        st = recv_until(ws, lambda m: m["type"] == "state" and m["state"]["active_tabs"]["upper"] == "Preferences")
        assert st


def test_guest_cookie_cannot_escape_the_results_folder(client, hani2_home):
    client.cookies.set("hani2_guest", "x/../admin")
    r = client.post("/api/session", json={"mode": "guest", "query": {}})
    sid = r.json()["sid"]
    gid = sid.split(":", 1)[1]
    assert len(gid) == 12 and all(c in "0123456789abcdef" for c in gid)
    from hani2.server import hub

    assert hub.get(sid).ss["user_path"].parent == hani2_home / "db"


def test_admin_participant_view(client):
    """An admin can negotiate exactly as a participant: no admin controls, no opponent type, not counted."""
    from hani2.assignment import counts_as_human
    from hani2.server import hub

    login(client)
    sid = client.post("/api/session", json={"mode": "main", "query": {"as_participant": "1", "noautostart": "1"}}).json()["sid"]
    assert sid.startswith("main:admin~participant")
    s = hub.get(sid)
    assert not s.is_admin and not s.admin_mode and s.admin_viewer == "admin"
    assert not counts_as_human(s) and not s.can_choose_scenario()
    with client.websocket_connect(f"/api/ws/{sid}") as ws:
        st = recv_until(ws, lambda m: m["type"] == "state")["state"]
        assert st["participant_view"] and not st["is_admin"] and not st["admin_mode"]
        assert st["next_opponent"] is None
    # the admin's own session is untouched
    admin_sid = client.post("/api/session", json={"mode": "main", "query": {"noautostart": "1"}}).json()["sid"]
    assert admin_sid != sid and hub.get(admin_sid).is_admin


def test_participant_view_needs_an_admin(client):
    client.post("/api/auth/register", json={"username": "bob", "password": "pw12"})
    login(client, "bob", "pw12")
    r = client.post("/api/session", json={"mode": "main", "query": {"as_participant": "1"}})
    if r.status_code == 200:
        assert "~participant" not in r.json()["sid"]


@pytest.fixture
def oauth(client, hani2_home, monkeypatch):
    """GitHub and Google configured; ``replies[provider]`` is what the provider's user API answers."""
    import httpx

    write_settings(hani2_home, "env.json", {"auth": {"mode": "dual"}, "oauth": {"providers": {
        "github": {"enabled": True, "key": "k", "secret": "s"}, "google": {"enabled": True, "key": "k", "secret": "s"}}}})
    replies: dict = {}

    class R:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: R({"access_token": "tok"}))
    monkeypatch.setattr(httpx, "get", lambda url, **kw: R(replies["emails"] if url.endswith("/emails") else replies["user"]))

    def login_with(provider: str, user: dict, emails: list | None = None):
        replies.update(user=user, emails=emails or [])
        r = client.get(f"/api/oauth/{provider}/login", follow_redirects=False)
        assert r.status_code in (302, 307)
        state = client.cookies.get("hani2_oauth_state")
        return client.get(f"/api/oauth/{provider}/callback", params={"code": "c", "state": state}, follow_redirects=False)

    return login_with


def test_github_and_google_sign_in(oauth, client):
    from hani2 import auth

    r = oauth("github", {"login": "octo", "name": "Octo Cat"}, [{"email": "o@x.org", "primary": True}])
    assert r.headers["location"].endswith("/app")
    assert client.get("/api/auth/me").json()["user"] == "gh_octo"
    assert auth.get_meta("gh_octo")["email"] == "o@x.org"
    client.post("/api/auth/logout")
    oauth("google", {"sub": "123", "email": "g@x.org", "name": "Gee"})
    assert client.get("/api/auth/me").json()["user"] == "g_123"


def test_oauth_error_reply_creates_no_shared_account(oauth, client):
    from hani2 import auth

    r = oauth("github", {"message": "Bad credentials"})
    assert "error=oauth_failed" in r.headers["location"]
    assert not auth.user_exists("gh_None")
    assert client.get("/api/auth/me").json()["user"] is None


def test_oauth_rejects_a_wrong_state(oauth, client):
    r = client.get("/api/oauth/github/callback", params={"code": "c", "state": "forged"}, follow_redirects=False)
    assert "error=oauth_state" in r.headers["location"]
