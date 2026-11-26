"""Hand-off sign-in from a trusted website (hani2.sso), e.g. scmlweb accounts for ANAC participants."""

import time
import uuid

import pytest
from conftest import write_settings
from fastapi.testclient import TestClient

from hani2 import auth, sso

SECRET = "test-secret-0123456789abcdef"


@pytest.fixture
def client(hani2_home, monkeypatch):
    monkeypatch.setenv("HANI2_OPPONENTS", "BoulwareTBNegotiator")
    write_settings(hani2_home, "env.json", {
        "auth": {"sso": {"scmlweb": {"secret": SECRET, "login_url": "https://anac.example.org/hani2/sso",
                                     "label": "ANAC account"}}},
        "admin": {"emails": ["chair@anac.org"]}})
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        yield c


def claims(**kw):
    now = int(time.time())
    return {"iss": "scmlweb", "aud": "hani2", "sub": "789", "iat": now, "exp": now + 60,
            "jti": uuid.uuid4().hex, "email": "p@uni.edu", "name": "Pat", "leagues": ["han", "hi"], **kw}


def go(client, token, next="/app?group=test_hi_789_tok"):
    return client.get("/api/sso/scmlweb", params={"token": token, "next": next}, follow_redirects=False)


def _independent_hs256(claims: dict, secret: str) -> str:
    """A plain HS256 JWT built without hani2 (what any JWT library or a few lines of PHP produce)."""
    import base64
    import hashlib
    import hmac
    import json

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    head = b64(b'{"alg":"HS256","typ":"JWT"}')
    body = b64(json.dumps(claims, separators=(",", ":")).encode())
    return f"{head}.{body}." + b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())


def test_known_answer_token():
    """The website's minting must agree with this (also checked against openssl when written)."""
    c = {"iss": "scmlweb", "aud": "hani2/hiplay2", "sub": "789", "iat": 1767225600, "exp": 1767225660,
         "jti": "0123456789abcdef", "email": "p@uni.edu", "name": "Pat", "leagues": ["hi"]}
    assert sso.sign(c, SECRET) == _independent_hs256(c, SECRET)


def test_a_token_from_another_implementation_is_accepted(client):
    assert go(client, _independent_hs256(claims(), SECRET)).headers["location"].startswith("/app")


def test_a_valid_token_signs_the_participant_in(client):
    r = go(client, sso.sign(claims(), SECRET))
    assert r.status_code == 303 and r.headers["location"] == "/app?group=test_hi_789_tok"
    assert r.headers["referrer-policy"] == "no-referrer"
    me = client.get("/api/auth/me").json()
    assert me["user"] == "anac_789" and not me["is_admin"]
    meta = auth.get_meta("anac_789")
    assert meta["email"] == "p@uni.edu" and meta["sso"] == "scmlweb" and meta["leagues"] == ["han", "hi"]
    assert client.post("/api/session", json={"mode": "main"}).status_code == 200


def test_second_visit_updates_the_same_account(client):
    go(client, sso.sign(claims(), SECRET))
    go(client, sso.sign(claims(name="Pat Lee", leagues=["han"]), SECRET))
    assert auth.get_meta("anac_789")["full_name"] == "Pat Lee" and auth.get_meta("anac_789")["leagues"] == ["han"]


@pytest.mark.parametrize("bad, code", [
    (lambda: sso.sign(claims(), "another-secret-0123456789"), "signature"),
    (lambda: sso.sign(claims(iss="evil"), SECRET), "issuer"),
    (lambda: sso.sign(claims(aud="hani2/other"), SECRET), "audience"),
    (lambda: sso.sign(claims(iat=int(time.time()) - 600, exp=int(time.time()) - 540), SECRET), "expired"),
    (lambda: sso.sign(claims(exp=int(time.time()) + 3600), SECRET), "lifetime"),
    (lambda: sso.sign(claims(sub="../admin"), SECRET), "subject"),
    (lambda: sso.sign(claims(jti=""), SECRET), "token"),
    (lambda: "eyJhbGciOiJub25lIn0." + sso.sign(claims(), SECRET).split(".")[1] + ".", "token"),
    (lambda: "garbage", "token"),
])
def test_bad_tokens_are_refused(client, bad, code):
    r = go(client, bad())
    assert r.status_code == 303 and r.headers["location"] == f"/login?error=sso_{code}"
    assert client.get("/api/auth/me").json()["user"] is None


def test_a_token_works_once(client):
    t = sso.sign(claims(), SECRET)
    assert go(client, t).headers["location"].startswith("/app")
    client.post("/api/auth/logout")
    assert go(client, t).headers["location"] == "/login?error=sso_replayed"


@pytest.mark.parametrize("nxt", ["https://evil.org/", "//evil.org/x", "/\\evil.org", "app"])
def test_next_never_leaves_this_server(client, nxt):
    assert go(client, sso.sign(claims(), SECRET), next=nxt).headers["location"] == "/app"


def test_a_listed_admin_email_does_not_make_a_handoff_account_admin(client):
    go(client, sso.sign(claims(email="chair@anac.org"), SECRET))
    assert not client.get("/api/auth/me").json()["is_admin"]



def test_an_admin_role_given_in_hani2_survives_the_next_handoff(client):
    """An organiser's hand-off account can be made admin on the Users page; signing in again keeps it."""
    go(client, sso.sign(claims(), SECRET))
    auth.update_meta("anac_789", role="admin")
    go(client, sso.sign(claims(name="Pat Lee"), SECRET))
    assert client.get("/api/auth/me").json()["is_admin"]

def test_handoff_names_cannot_be_registered_by_hand(client):
    r = client.post("/api/auth/register", json={"username": "anac_789", "password": "secret", "confirm": "secret"})
    assert r.status_code == 400


def test_config_lists_the_button_but_never_the_secret(client):
    cfg = client.get("/api/config")
    assert cfg.json()["sso_providers"] == [{"name": "scmlweb", "label": "ANAC account"}]
    assert SECRET not in cfg.text


def test_login_goes_to_the_website_with_a_site_key_not_a_url(client):
    r = client.get("/api/sso/scmlweb/login", params={"next": "/app?group=g1"}, follow_redirects=False)
    loc = r.headers["location"]
    assert loc.startswith("https://anac.example.org/hani2/sso?") and "site=%2F" in loc and "next=%2Fapp%3Fgroup%3Dg1" in loc
    assert "http%3A" not in loc and "127.0.0.1" not in loc


def test_without_a_secret_there_is_no_handoff(hani2_home):
    write_settings(hani2_home, "env.json", {"auth": {"sso": {"scmlweb": {"secret": "", "login_url": "x"}}}})
    assert sso.providers() == {}
    with pytest.raises(sso.SSOError):
        sso.verify("scmlweb", sso.sign(claims(), ""))


def test_audience_follows_the_root_path():
    assert sso.audience("") == "hani2" and sso.audience("/hiplay2") == "hani2/hiplay2"


def test_behind_a_root_path_like_the_hi_instance(client, monkeypatch):
    monkeypatch.setenv("HANI2_ROOT_PATH", "/hiplay2")
    assert go(client, sso.sign(claims(), SECRET)).headers["location"] == "/hiplay2/login?error=sso_audience"
    r = go(client, sso.sign(claims(aud="hani2/hiplay2"), SECRET), next="/app?group=g")
    assert r.headers["location"] == "/hiplay2/app?group=g"
    loc = client.get("/hiplay2/api/sso/scmlweb/login", params={"next": "/app"}, follow_redirects=False).headers["location"]
    assert "site=%2Fhiplay2" in loc


def test_consent_is_still_asked_when_the_study_enforces_it(client, hani2_home):
    import json

    env = json.loads((hani2_home / "settings" / "env.json").read_text(encoding="utf-8"))
    env["auth"]["enforce_consent"] = True
    write_settings(hani2_home, "env.json", env)
    go(client, sso.sign(claims(sub="c1"), SECRET))
    assert client.get("/api/auth/me").json()["user"] == "anac_c1"
    r = client.post("/api/session", json={"mode": "main"})
    assert r.status_code == 403 and r.json()["detail"] == "consent_required"


def _group(hani2_home, key, data):
    import json

    from hani2 import projects

    ref = projects.current_study()
    base = projects.study_dir(ref) / "results" if ref else hani2_home / "db"
    g = base / "groups"
    g.mkdir(parents=True, exist_ok=True)
    (g / f"{key}.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("finish_first", [False, True])
def test_test_my_agent_link_on_an_existing_session_uses_the_new_group(client, hani2_home, finish_first):
    """A participant who already has a session (ready, or after a round) then clicks 'Test my agent'."""
    from hani2.server import hub
    from hani2.testing import TestSession

    go(client, sso.sign(claims(sub="t1"), SECRET))
    sid = client.post("/api/session", json={"mode": "main", "query": {}}).json()["sid"]
    s = hub.get(sid)
    s.__class__ = TestSession  # only adds the waiting helpers
    if finish_first:
        s.start()
        s.wait_for_turn()
        s.end()
        assert s.wait(lambda: s.phase != "running", 10)
    _group(hani2_home, "test_han_t1_tok", {"syspath": [], "agents": ["ConcederTBNegotiator"]})
    client.post("/api/session", json={"mode": "main", "query": {"group": "test_han_t1_tok"}})
    if s.phase in ("ended", "finished"):
        s.load()
    s.start()
    s.wait_for_turn()
    assert "Conceder" in str(s.ss.get("last_partner_type")), s.ss.get("last_partner_type")


# --------------------------------------------------------------------------- #
# The website's "admin" claim (trust_admin_claim)                              #
# --------------------------------------------------------------------------- #
def _trusting(hani2_home, on=True, **extra):
    write_settings(hani2_home, "env.json", {
        "auth": {"sso": {"scmlweb": {"secret": SECRET, "login_url": "https://anac.example.org/hani2/sso",
                                     "guest_studies": ["arena/play"], **({"trust_admin_claim": on} if on is not None else {}),
                                     **extra}}},
        "admin": {"emails": ["chair@anac.org"]}})


def _events(kind):
    from hani2 import events as ev

    return [e for e in ev.query_events(limit=1000) if e["event_type"] == kind]


@pytest.mark.parametrize("setting", [None, False, "true", 1])
def test_the_admin_claim_is_ignored_unless_the_setting_is_exactly_true(client, hani2_home, setting):
    _trusting(hani2_home, setting)
    go(client, sso.sign(claims(admin=True), SECRET))
    assert client.get("/api/auth/me").json()["user"] == "anac_789"
    assert not client.get("/api/auth/me").json()["is_admin"] and not auth.is_admin_user("anac_789")
    assert not auth.get_meta("anac_789").get("sso_admin")
    assert client.get("/api/admin/users").status_code == 403


def test_with_the_setting_on_the_claim_makes_an_admin_and_is_logged(client, hani2_home, capsys):
    _trusting(hani2_home)
    go(client, sso.sign(claims(admin=True), SECRET))
    assert client.get("/api/auth/me").json()["is_admin"]
    assert client.get("/api/admin/users").status_code == 200
    meta = auth.get_meta("anac_789")
    assert meta["sso_admin"] == {"hani2": "scmlweb"} and "role" not in meta  # kept apart from role
    assert "[sso] scmlweb: admin granted for anac_789" in capsys.readouterr().out
    (e,) = _events("admin_granted")
    assert e["user"] == "anac_789" and '"provider": "scmlweb"' in e["value"]
    go(client, sso.sign(claims(admin=True), SECRET))  # still admin: no second grant event
    assert len(_events("admin_granted")) == 1


@pytest.mark.parametrize("value", [None, False, "true", "True", 1, "yes", [True], {"v": True}])
def test_only_a_boolean_true_claim_counts(client, hani2_home, value):
    _trusting(hani2_home)
    go(client, sso.sign(claims(**({} if value is None else {"admin": value})), SECRET))
    assert not client.get("/api/auth/me").json()["is_admin"]


def test_a_later_handoff_without_the_claim_removes_the_admin(client, hani2_home, capsys):
    _trusting(hani2_home)
    go(client, sso.sign(claims(admin=True), SECRET))
    assert auth.is_admin_user("anac_789")
    go(client, sso.sign(claims(), SECRET))
    assert not client.get("/api/auth/me").json()["is_admin"] and not auth.is_admin_user("anac_789")
    assert "[sso] scmlweb: admin removed for anac_789" in capsys.readouterr().out
    (e,) = _events("admin_revoked")
    assert e["user"] == "anac_789"
    go(client, sso.sign(claims(admin=False), SECRET))  # already not an admin: nothing more to log
    assert len(_events("admin_revoked")) == 1
    go(client, sso.sign(claims(admin=True), SECRET))  # granted again
    assert auth.is_admin_user("anac_789")


def test_turning_the_setting_off_ends_the_claims_admins_at_once(client, hani2_home):
    _trusting(hani2_home)
    go(client, sso.sign(claims(admin=True), SECRET))
    assert auth.is_admin_user("anac_789")
    _trusting(hani2_home, False)
    assert not auth.is_admin_user("anac_789") and not client.get("/api/auth/me").json()["is_admin"]


def test_guest_tokens_never_become_admins(client, hani2_home):
    _trusting(hani2_home)
    user = sso.sign_in("scmlweb", claims(sub="invite-1", guest=True, admin=True), "/app?study=arena/play")
    assert user == "anac_invite-1" and auth.get_meta(user)["guest"]
    assert not auth.is_admin_user(user) and not auth.get_meta(user).get("sso_admin")
    # even a grant planted in the store does not count for a guest account
    auth.update_meta(user, sso_admin={"hani2": "scmlweb"})
    assert not auth.is_admin_user(user)


def test_the_grant_is_per_instance(client, hani2_home, monkeypatch):
    """Two instances (HAN at /, HI at /hiplay2) share one home: each honours only its own grant."""
    _trusting(hani2_home)
    monkeypatch.setenv("HANI2_ROOT_PATH", "/hiplay2")
    go(client, sso.sign(claims(aud="hani2/hiplay2", admin=True), SECRET))
    assert auth.is_admin_user("anac_789")
    monkeypatch.setenv("HANI2_ROOT_PATH", "")
    assert not auth.is_admin_user("anac_789")
    go(client, sso.sign(claims(), SECRET))  # a hand-off to the root instance without the claim
    monkeypatch.setenv("HANI2_ROOT_PATH", "/hiplay2")
    assert auth.is_admin_user("anac_789")  # leaves the other instance's grant alone


def test_removing_the_claim_never_demotes_other_admins(client, hani2_home):
    """A role given in HANI2 (Users page / users add --admin) survives a hand-off without the claim; the
    built-in admin and an admin.emails admin are not touched by grants and removals."""
    _trusting(hani2_home)
    auth.create_user("chair", "pw-0123456789", email="chair@anac.org")
    assert auth.is_admin_user("chair") and auth.is_admin_user("admin")
    go(client, sso.sign(claims(admin=True), SECRET))
    auth.update_meta("anac_789", role="admin")
    go(client, sso.sign(claims(), SECRET))
    assert auth.is_admin_user("anac_789") and auth.get_meta("anac_789")["role"] == "admin"
    assert not auth.get_meta("anac_789")["sso_admin"]
    assert auth.is_admin_user("chair") and auth.is_admin_user("admin")
    # an admin.emails address in the token still does not make a hand-off account admin
    go(client, sso.sign(claims(sub="790", email="chair@anac.org"), SECRET))
    assert not auth.is_admin_user("anac_790")


@pytest.mark.parametrize("bad", [
    lambda c: sso.sign(c, "another-secret-0123456789"),
    lambda c: "eyJhbGciOiJub25lIn0." + sso.sign(c, SECRET).split(".")[1] + ".",
    lambda c: sso.sign({**c, "iat": c["iat"] - 600, "exp": c["exp"] - 600}, SECRET),
])
def test_a_bad_token_neither_grants_nor_removes(client, hani2_home, bad):
    _trusting(hani2_home)
    r = go(client, bad(claims(admin=True)))
    assert r.headers["location"].startswith("/login?error=sso_")
    assert not auth.user_exists("anac_789")
    go(client, sso.sign(claims(admin=True), SECRET))
    before = auth.get_meta("anac_789")
    client.post("/api/auth/logout")
    go(client, bad(claims()))  # a bad token without the claim must not remove it either
    assert auth.get_meta("anac_789")["sso_admin"] == before["sso_admin"] and auth.is_admin_user("anac_789")


def test_a_demoted_account_loses_admin_on_its_next_request_and_page_load(client, hani2_home):
    from starlette.websockets import WebSocketDisconnect

    from hani2.server import hub

    _trusting(hani2_home)
    go(client, sso.sign(claims(admin=True), SECRET))
    sid = client.post("/api/session", json={"mode": "main"}).json()["sid"]
    old = hub.get(sid)
    assert old.is_admin
    with client.websocket_connect(f"/api/ws/{sid}") as ws:
        assert ws.receive_json()["type"] == "state"
        go(client, sso.sign(claims(), SECRET))  # demoted by the next hand-off
        assert client.get("/api/admin/users").status_code == 403  # the next REST request
        ws.send_json({"type": "noop"})  # the next message on the open socket closes it
        with pytest.raises(WebSocketDisconnect) as e:
            while True:
                ws.receive_json()
        assert e.value.code == 4404
    assert hub.get(sid) is not old
    sid2 = client.post("/api/session", json={"mode": "main"}).json()["sid"]  # the page load after
    assert sid2 == sid and not hub.get(sid).is_admin and hub.get(sid) is not old
    # and back: a new grant gives the next page load an admin session
    go(client, sso.sign(claims(admin=True), SECRET))
    client.post("/api/session", json={"mode": "main"})
    assert hub.get(sid).is_admin


def test_a_page_load_after_demotion_gets_a_new_non_admin_session(client, hani2_home):
    from starlette.websockets import WebSocketDisconnect

    from hani2.server import hub

    _trusting(hani2_home)
    go(client, sso.sign(claims(admin=True), SECRET))
    sid = client.post("/api/session", json={"mode": "main"}).json()["sid"]
    psid = client.post("/api/session", json={"mode": "main", "query": {"as_participant": "1"}}).json()["sid"]
    assert hub.get(sid).is_admin and hub.get(psid).admin_viewer == "anac_789"
    go(client, sso.sign(claims(), SECRET))
    assert client.post("/api/session", json={"mode": "main"}).json()["sid"] == sid
    assert not hub.get(sid).is_admin and not hub.get(sid).admin_mode
    with pytest.raises(WebSocketDisconnect) as e:  # the admin's participant view is gone too
        with client.websocket_connect(f"/api/ws/{psid}") as ws:
            ws.receive_json()
    assert e.value.code == 4404 and hub.get(psid) is None
