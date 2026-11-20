"""Default accounts with their well-known passwords: a startup warning, and admin
logins with the default refused on a server reachable from other machines."""

import pytest
from fastapi.testclient import TestClient

from hani2 import auth
from conftest import write_settings


def _login(client, user, pw):
    return client.post("/api/auth/login", json={"username": user, "password": pw})


@pytest.fixture
def client(hani2_home):
    from hani2.server import app

    with TestClient(app) as c:
        yield c


@pytest.mark.parametrize("host,loopback", [
    (None, True), ("", True), ("127.0.0.1", True), ("127.0.1.1", True), ("localhost", True), ("::1", True),
    ("[::1]", True), ("0.0.0.0", False), ("::", False), ("192.168.1.5", False), ("example.org", False),
])
def test_loopback_hosts(host, loopback):
    assert auth.is_loopback_host(host) is loopback


def test_default_password_users(hani2_home):
    auth.ensure_default_users()
    assert auth.default_password_users() == ["admin", "user"]
    auth.set_password("user", "something-else")
    assert auth.default_password_users() == ["admin"]
    auth.set_password("admin", "another")
    assert auth.default_password_users() == []


def test_legacy_plaintext_default_is_found_and_not_rewritten(hani2_home):
    write_settings(hani2_home, "users.json", {"admin": "adminpass"})
    assert auth.default_password_users() == ["admin"]
    assert auth.load_users()["admin"] == "adminpass"  # the check does not upgrade the entry


def test_startup_warns_about_default_passwords(hani2_home, capsys):
    from hani2.server import app

    with TestClient(app):
        pass
    out = capsys.readouterr().out
    assert "'admin' still has its default password" in out and "'user' still has its default password" in out
    assert "hani2 users passwd admin" in out
    auth.set_password("admin", "new-admin")
    auth.set_password("user", "new-user")
    with TestClient(app):
        pass
    assert "default password" not in capsys.readouterr().out


@pytest.mark.parametrize("host", [None, "127.0.0.1", "localhost"])
def test_loopback_bind_allows_the_default_admin_password(client, monkeypatch, host):
    if host:
        monkeypatch.setenv(auth.BIND_HOST_ENV_VAR, host)
    assert _login(client, "admin", "adminpass").status_code == 200


def test_public_bind_refuses_the_default_admin_password(client, monkeypatch):
    monkeypatch.setenv(auth.BIND_HOST_ENV_VAR, "0.0.0.0")
    r = _login(client, "admin", "adminpass")
    assert r.status_code == 403 and "hani2 users passwd admin" in r.json()["detail"]
    assert "hani2_auth" not in r.cookies
    assert _login(client, "admin", "wrong").status_code == 401  # a wrong password stays a 401
    assert _login(client, "user", "userpass").status_code == 200  # only admins are refused
    auth.set_password("admin", "a-real-password")
    assert _login(client, "admin", "a-real-password").status_code == 200


def test_another_admin_with_a_changed_default_account_is_not_refused(client, monkeypatch):
    monkeypatch.setenv(auth.BIND_HOST_ENV_VAR, "0.0.0.0")
    auth.create_user("boss", "adminpass", role="admin")  # not a default account
    assert _login(client, "boss", "adminpass").status_code == 200


@pytest.mark.parametrize("mode,host,status", [
    ("allow", "0.0.0.0", 200), ("refuse", "127.0.0.1", 403), ("refuse", None, 403), ("auto", "0.0.0.0", 403),
])
def test_default_password_login_setting(hani2_home, monkeypatch, mode, host, status):
    write_settings(hani2_home, "env.json", {"auth": {"default_password_login": mode}})
    if host:
        monkeypatch.setenv(auth.BIND_HOST_ENV_VAR, host)
    from hani2.server import app

    with TestClient(app) as c:
        assert _login(c, "admin", "adminpass").status_code == status


def test_serve_exports_the_bind_host(hani2_home, monkeypatch):
    import sys
    import types

    from hani2 import cli

    seen = {}
    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(
        run=lambda *a, **k: seen.update(host=k["host"], env=__import__("os").environ.get(auth.BIND_HOST_ENV_VAR))))
    monkeypatch.setenv(auth.BIND_HOST_ENV_VAR, "unset-by-test")  # restored by monkeypatch afterwards
    cli._serve("0.0.0.0", 5999, None)
    assert seen == {"host": "0.0.0.0", "env": "0.0.0.0"}
