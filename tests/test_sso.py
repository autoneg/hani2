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

    env = json.loads((hani2_home / "settings" / "env.json").read_text())
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
    (g / f"{key}.json").write_text(json.dumps(data))


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
