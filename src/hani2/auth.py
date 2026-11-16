"""User store, password hashing, consent and roles.

Users live in ``settings/users.json`` (``{"username": "<hash or legacy plain>"}``)
and metadata (consent, email, full name, created) in ``settings/users_meta.json``
— two small JSON files that are easy to inspect and back up.
Passwords are stored as PBKDF2-SHA256 hashes; legacy plain-text entries still
verify and are upgraded to a hash on the next successful login.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from datetime import datetime
from typing import Any

from hani2.config import get_env, settings_dir

_LOCK = threading.RLock()
_PREFIX = "pbkdf2_sha256"
_ITER = 200_000
RESERVED_NAMES = {"ai", "agent", "guest", "admin2"}


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITER)
    return f"{_PREFIX}${_ITER}${salt}${dk.hex()}"


def _check(stored: str, password: str) -> bool:
    if stored.startswith(_PREFIX + "$"):
        try:
            _, it, salt, digest = stored.split("$", 3)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(it))
            return hmac.compare_digest(dk.hex(), digest)
        except ValueError:
            return False
    return hmac.compare_digest(stored, password)  # legacy plain-text entry


def _users_file():
    return settings_dir() / "users.json"


def _meta_file():
    return settings_dir() / "users_meta.json"


def _read(path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def _write(path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def load_users() -> dict:
    with _LOCK:
        return _read(_users_file())


def load_users_meta() -> dict:
    with _LOCK:
        return _read(_meta_file())


def user_exists(username: str) -> bool:
    return username in load_users()


def create_user(username: str, password: str | None = None, **meta: Any) -> bool:
    with _LOCK:
        users = _read(_users_file())
        if username in users:
            return False
        users[username] = hash_password(password or secrets.token_urlsafe(16))
        _write(_users_file(), users)
        allmeta = _read(_meta_file())
        allmeta[username] = {"created": datetime.now().isoformat(), **meta}
        _write(_meta_file(), allmeta)
        return True


def verify_user_password(username: str, password: str) -> bool:
    with _LOCK:
        users = _read(_users_file())
        stored = users.get(username)
        if stored is None or not _check(str(stored), password):
            return False
        if not str(stored).startswith(_PREFIX + "$"):
            users[username] = hash_password(password)
            _write(_users_file(), users)
        return True


def set_password(username: str, password: str) -> bool:
    with _LOCK:
        users = _read(_users_file())
        if username not in users:
            return False
        users[username] = hash_password(password)
        _write(_users_file(), users)
        return True


def delete_user(username: str) -> bool:
    with _LOCK:
        users = _read(_users_file())
        if username not in users:
            return False
        users.pop(username)
        _write(_users_file(), users)
        meta = _read(_meta_file())
        meta.pop(username, None)
        _write(_meta_file(), meta)
        return True


def update_meta(username: str, **fields: Any) -> None:
    with _LOCK:
        meta = _read(_meta_file())
        meta.setdefault(username, {}).update(fields)
        _write(_meta_file(), meta)


def get_meta(username: str) -> dict:
    return load_users_meta().get(username, {})


def get_user_consent(username: str) -> bool:
    return bool(get_meta(username).get("consented", False))


def set_user_consent(username: str, consented: bool = True, **extra: Any) -> None:
    update_meta(
        username, consented=consented, consent_date=datetime.now().isoformat(), **extra
    )


def is_admin_user(username: str | None) -> bool:
    if not username:
        return False
    if username == "admin":
        return True
    meta = get_meta(username)
    if meta.get("role") == "admin":
        return True
    email = str(meta.get("email", "")).strip().lower()
    emails = [str(e).strip().lower() for e in (get_env("admin.emails", []) or [])]
    return bool(email) and email in emails


def ensure_default_users(admin_password: str | None = None) -> list[str]:
    """Create the default ``admin`` and ``user`` accounts if missing."""
    created = []
    if not user_exists("admin"):
        create_user(
            "admin",
            admin_password or str(get_env("admin.password", "adminpass") or "adminpass"),
            consented=True,
            consent_date="default",
            role="admin",
        )
        created.append("admin")
    if not user_exists("user"):
        create_user("user", "userpass", consented=True, consent_date="default")
        created.append("user")
    return created


def validate_new_user(username: str, password: str, confirm: str | None = None) -> str | None:
    """Return an error message, or None if the registration data is valid."""
    username = (username or "").strip()
    if not username:
        return "Username is required."
    if len(username) > 64 or any(c in username for c in "/\\:*?\"<>| "):
        return "Username may not contain spaces or path characters."
    if username.lower() in RESERVED_NAMES or username.lower().startswith("prolific_"):
        return "This username is reserved."
    if not password or len(password) < 4:
        return "Password must have at least 4 characters."
    if confirm is not None and confirm != password:
        return "Passwords do not match."
    if user_exists(username):
        return "This username is already taken."
    return None
