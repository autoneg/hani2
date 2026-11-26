"""Signed hand-off sign-in from a trusted website (for example scmlweb, the ANAC competition site).

The website already knows its user. It signs a short-lived HS256 JWT with a secret shared with
HANI2 and sends the browser to ``/api/sso/<name>?token=…&next=/app?group=…``. HANI2 checks the
token, creates or updates the account ``<prefix><sub>`` (``anac_<id>`` by default) and logs the
browser in. Nobody types a HANI2 password, and accounts appear on the first click-through.

``env.json``::

    {"auth": {"sso": {"scmlweb": {
        "secret": "<random, 32+ bytes>",               # or HANI2_SSO_SCMLWEB_SECRET
        "login_url": "https://anac.cs.brown.edu/hani2/sso",   # the site's page that mints a token
        "label": "ANAC account",                        # the login page's button
        "prefix": "anac_",                              # HANI2 user names: <prefix><sub>
        "issuer": "scmlweb"}}}}                         # the token's iss (default: the name)

Token claims: ``iss`` (the issuer), ``aud`` (``hani2`` plus this server's root path, e.g.
``hani2/hiplay2``; just ``hani2`` without one), ``sub`` (the site's user id: letters, digits,
``_`` and ``-``), ``iat`` and ``exp`` (at most :data:`MAX_LIFETIME` seconds apart), ``jti``
(single use), and optionally ``email``, ``name`` and ``leagues`` (a list such as ``["han", "hi"]``).

Emails from the website are not verified by HANI2, so these accounts never become admins
through ``admin.emails``.

Admins from the website: with ``"trust_admin_claim": true`` in the provider's settings (off by default), a
verified, non-guest token with the claim ``admin`` set to the JSON boolean ``true`` (nothing else counts:
not ``"true"``, not ``1``) makes the account an admin of this instance. The grant is stored apart from
``role`` (``sso_admin``: ``{<this server's aud>: <provider>}``) and is decided again on every hand-off: a
token without the claim removes it, never a ``role`` given in HANI2. :func:`hani2.auth.is_admin_user`
honours it only while the provider is configured with ``trust_admin_claim`` on.

Guests: a token with ``guest: true`` (optionally ``invited_by`` and ``name``) signs in a person who has no
account on the website (for example someone a participant invited). The account ``<prefix><sub>`` is
flagged as a guest and bound to the one study ``next`` names, which must be listed in the provider's
``guest_studies``; it can open nothing else (no other study, no admin page). A guest account never
becomes a normal one, nor the other way round.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
import time
from typing import Any

MAX_LIFETIME = 120  # seconds between iat and exp: the token travels in a URL
LEEWAY = 30  # clock skew allowed on iat / exp
_SUB = re.compile(r"^[A-Za-z0-9_-]{1,48}$")
_used_lock = threading.Lock()


class SSOError(Exception):
    """A refused token; ``code`` goes to the login page as ``?error=sso_<code>``."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _env_secret(name: str) -> str:
    return (os.environ.get(f"HANI2_SSO_{re.sub(r'[^A-Za-z0-9]', '_', name).upper()}_SECRET") or "").strip()


def providers() -> dict[str, dict[str, Any]]:
    """The configured hand-off providers (only those with a secret: no secret, no sign-in)."""
    from hani2.config import get_env

    out: dict[str, dict[str, Any]] = {}
    for name, cfg in (get_env("auth.sso", {}) or {}).items():
        if not isinstance(cfg, dict) or cfg.get("enabled", True) is False:
            continue
        secret = _env_secret(name) or str(cfg.get("secret") or "").strip()
        if len(secret) < 16:
            continue  # an empty or toy secret would let anyone mint tokens
        out[str(name)] = {**cfg, "secret": secret, "prefix": str(cfg.get("prefix") or "anac_"),
                          "issuer": str(cfg.get("issuer") or name), "label": str(cfg.get("label") or name)}
    return out


def public() -> list[dict[str, str]]:
    """What the login page may know: names and labels, never secrets."""
    return [{"name": n, "label": c["label"]} for n, c in providers().items() if c.get("login_url")]


def secrets_in_use() -> list[str]:
    return [c["secret"] for c in providers().values()]


def reserved_prefixes() -> list[str]:
    """User-name prefixes only a hand-off may create (``anac_`` always, plus configured ones)."""
    from hani2.config import get_env

    cfgs = get_env("auth.sso", {}) or {}
    return sorted({"anac_", *(str(c.get("prefix")) for c in cfgs.values() if isinstance(c, dict) and c.get("prefix"))})


def trusts_admin_claim(cfg: dict[str, Any] | None) -> bool:
    """Whether a provider's ``admin`` claim may make admins (only ``"trust_admin_claim": true``)."""
    return isinstance(cfg, dict) and cfg.get("trust_admin_claim") is True


def this_audience() -> str:
    """The ``aud`` of this process (its ``HANI2_ROOT_PATH``): the key of the admin grants it honours."""
    return audience(os.environ.get("HANI2_ROOT_PATH", ""))


def claim_admin_provider(meta: dict[str, Any]) -> str | None:
    """The provider whose ``admin`` claim makes this account an admin of this instance now, else ``None``:
    the grant must be for this instance, from the provider that made the account, not a guest, and that
    provider must still be configured with ``trust_admin_claim`` on."""
    grants = meta.get("sso_admin")
    if not isinstance(grants, dict) or meta.get("guest"):
        return None
    name = grants.get(this_audience())
    if not name or name != meta.get("sso"):
        return None
    return str(name) if trusts_admin_claim(providers().get(str(name))) else None


def audience(root_path: str = "") -> str:
    """This server's ``aud``: ``hani2`` plus its root path (``hani2/hiplay2``), so a token minted for one
    instance does not open another."""
    root = (root_path or "").strip("/")
    return f"hani2/{root}" if root else "hani2"


def _b64d(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign(claims: dict[str, Any], secret: str) -> str:
    """An HS256 JWT (what the website does; here for tests and the known-answer example)."""
    head = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64e(json.dumps(claims, separators=(",", ":")).encode())
    mac = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64e(mac)}"


def verify(name: str, token: str, *, root_path: str = "", now: float | None = None) -> dict[str, Any]:
    """The checked claims of ``token`` for provider ``name``, or :class:`SSOError`."""
    cfg = providers().get(name)
    if cfg is None:
        raise SSOError("unknown", f"no hand-off sign-in named {name!r} is configured")
    parts = (token or "").split(".")
    if len(parts) != 3:
        raise SSOError("token", "not a JWT")
    try:
        head = json.loads(_b64d(parts[0]))
        claims = json.loads(_b64d(parts[1]))
        mac = _b64d(parts[2])
    except (ValueError, json.JSONDecodeError) as e:
        raise SSOError("token", f"unreadable token: {e}") from None
    if not isinstance(head, dict) or head.get("alg") != "HS256":
        raise SSOError("token", "only HS256 tokens are accepted")
    want = hmac.new(cfg["secret"].encode(), f"{parts[0]}.{parts[1]}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(mac, want):
        raise SSOError("signature", "bad signature")
    if not isinstance(claims, dict):
        raise SSOError("token", "claims must be an object")
    if claims.get("iss") != cfg["issuer"]:
        raise SSOError("issuer", f"iss must be {cfg['issuer']!r}")
    aud = claims.get("aud")
    if (aud if isinstance(aud, list) else [aud]).count(audience(root_path)) == 0:
        raise SSOError("audience", f"aud must be {audience(root_path)!r}")
    t = time.time() if now is None else now
    try:
        iat, exp = float(claims["iat"]), float(claims["exp"])
    except (KeyError, TypeError, ValueError):
        raise SSOError("token", "iat and exp are required") from None
    if exp - iat > MAX_LIFETIME or exp < iat:
        raise SSOError("lifetime", f"exp - iat must be between 0 and {MAX_LIFETIME} seconds")
    if t > exp + LEEWAY or t < iat - LEEWAY:
        raise SSOError("expired", "the token is expired (or not valid yet): try again")
    sub = str(claims.get("sub") or "")
    if not _SUB.match(sub):
        raise SSOError("subject", "sub must be 1-48 letters, digits, '_' or '-'")
    jti = str(claims.get("jti") or "")
    if not 8 <= len(jti) <= 128:
        raise SSOError("token", "jti (8-128 characters) is required")
    _use_once(name, jti, exp + LEEWAY, t)
    return claims


def _use_once(name: str, jti: str, until: float, now: float) -> None:
    """Refuse a token seen before (it may have leaked through a log or a shared link)."""
    from hani2.config import settings_dir

    path = settings_dir() / ".sso_used.json"
    with _used_lock:
        try:
            used = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, json.JSONDecodeError):
            used = {}
        used = {k: v for k, v in used.items() if isinstance(v, (int, float)) and v >= now}
        key = f"{name}:{jti}"
        if key in used:
            raise SSOError("replayed", "this sign-in link was already used: start again from the website")
        used[key] = until
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")  # two servers share a home
        tmp.write_text(json.dumps(used), encoding="utf-8")
        tmp.replace(path)


def _truthy(v: Any) -> bool:
    return v is True or (isinstance(v, (int, float)) and v == 1) or \
        (isinstance(v, str) and v.strip().lower() in ("1", "true", "yes"))


def study_of_next(next_path: str | None) -> str | None:
    """The study (``project/study``) a ``next`` path names: ``?study=P/S`` or a ``/s/P/S/`` prefix."""
    from urllib.parse import parse_qs, urlsplit

    from hani2 import projects

    v = safe_next(next_path)
    parts = urlsplit(v)
    raw = (parse_qs(parts.query).get("study") or [None])[0]
    if not raw:
        segs = [x for x in parts.path.split("/") if x]
        if len(segs) >= 3 and segs[0] == "s":
            raw = f"{segs[1]}/{segs[2]}"
    if not raw:
        return None
    try:
        ref = projects.parse_ref(raw)
    except ValueError:
        return None
    return f"{ref.project}/{ref.study}" if ref is not None else None


def guest_studies(cfg: dict[str, Any]) -> list[str]:
    raw = cfg.get("guest_studies") or []
    if isinstance(raw, str):
        raw = [x for x in raw.replace(",", " ").split() if x]
    return [str(x).strip().strip("/") for x in raw if str(x).strip()]


def sign_in(name: str, claims: dict[str, Any], next_path: str | None = None, *, root_path: str | None = None) -> str:
    """Create or update the account for verified ``claims``; returns its user name. A guest token
    (``guest: true``) needs ``next_path`` to name a study in the provider's ``guest_studies``. The
    ``admin`` claim is decided again here (see :func:`_admin_grants`)."""
    from hani2 import auth

    cfg = providers()[name]
    user = f"{cfg['prefix']}{claims['sub']}"
    leagues = [str(x) for x in claims.get("leagues") or [] if isinstance(x, (str, int))][:16]
    fields: dict[str, Any] = dict(email=str(claims.get("email") or "")[:200],
                                  full_name=str(claims.get("name") or "")[:200],
                                  sso=name, sso_sub=str(claims["sub"]), leagues=leagues)
    guest = _truthy(claims.get("guest"))
    if guest:
        study = study_of_next(next_path)
        allowed = guest_studies(cfg)
        if not study or study not in allowed:
            raise SSOError("guest", f"guest sign-in is not open for {study or 'this page'} "
                                    f"(the provider's guest_studies: {', '.join(allowed) or 'none'})")
        inviter = claims.get("invited_by")
        fields.update(guest=True, guest_study=study, email="",
                      invited_by=str(inviter)[:64] if isinstance(inviter, (str, int)) and str(inviter) else "")
    aud = audience(root_path) if root_path is not None else this_audience()
    granted = not guest and trusts_admin_claim(cfg) and claims.get("admin") is True
    if not auth.user_exists(user):
        before: dict[str, Any] = {}
        grants = _admin_grants(before, aud, name, granted)
        auth.create_user(user, None, **fields, **({"sso_admin": grants} if grants else {}))
    else:
        before = auth.get_meta(user)
        if before.get("sso") != name:
            raise SSOError("conflict", f"the account {user} was not made by {name}")
        if bool(before.get("guest")) != guest:
            raise SSOError("conflict", f"the account {user} is {'a guest' if before.get('guest') else 'not a guest'} "
                                       f"account; a {'guest' if guest else 'normal'} token cannot sign it in")
        grants = _admin_grants(before, aud, name, granted)
        auth.update_meta(user, **fields, sso_admin=grants)
    auth.update_meta(user, last_handoff=time.time())
    had = isinstance(before.get("sso_admin"), dict) and before["sso_admin"].get(aud) == name
    if granted != had:
        _log_admin_change(user, name, aud, granted)
    return user


def _admin_grants(meta: dict[str, Any], aud: str, name: str, granted: bool) -> dict[str, str]:
    """The account's ``sso_admin`` after a hand-off to the instance ``aud``: this instance's entry is set
    (claim honoured) or dropped (anything else); other instances' entries stay as they are."""
    old = meta.get("sso_admin")
    grants = {str(k): str(v) for k, v in old.items()} if isinstance(old, dict) else {}
    if granted:
        grants[aud] = name
    else:
        grants.pop(aud, None)
    return grants


def _log_admin_change(user: str, provider: str, aud: str, granted: bool) -> None:
    """A security event and a log line for every admin grant or removal by a hand-off."""
    from hani2 import events as ev

    what = "granted" if granted else "removed"
    print(f"[sso] {provider}: admin {what} for {user} on {aud} (the token's admin claim)")
    ev.log_event(None, ev.EventType.ADMIN_GRANTED if granted else ev.EventType.ADMIN_REVOKED, user=user,
                 component="sso", value={"provider": provider, "audience": aud, "source": "admin_claim"})


def guest_study(user: str | None) -> str | None:
    """The one study a guest account may open (``None``: not a guest)."""
    from hani2 import auth

    if not user:
        return None
    meta = auth.get_meta(user)
    if not meta.get("guest"):
        return None
    return str(meta.get("guest_study") or "") or "-"  # a guest without a study opens nothing


def safe_next(value: str | None) -> str:
    """A path on this server only (``/app?group=…``): never another site."""
    v = (value or "").strip()
    if not v.startswith("/") or v.startswith("//") or v.startswith("/\\") or any(c in v for c in "\r\n"):
        return "/app"
    return v
