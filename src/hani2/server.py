"""The HANI2 web server (FastAPI).

* ``/`` … the single-page web app (shipped pre-built inside the package)
* ``/api/...`` the REST API (auth, admin, configuration)
* ``/api/ws/{sid}`` the live negotiation channel (WebSocket)
* ``/s/<project>/<study>/...`` any of the above for one study (``?study=project/study``
  also works); without it, the process default study is used.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer

from hani2 import __version__, agents, auth, projects, sso
from hani2 import events as ev
from hani2.config import get_env, load_env, read_settings_text, save_json_settings, settings_dir
from hani2.hub import Hub
from hani2.session import NegotiationSession
from hani2.tools.ui import jsonable

WEB_DIR = Path(__file__).parent / "web"
AUTH_COOKIE = "hani2_auth"
GUEST_COOKIE = "hani2_guest"
SID_COOKIE = "hani2_sid"
MAX_AGE = 30 * 24 * 3600

hub = Hub()


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(str(get_env("auth.cookie_secret")), salt="hani2-auth")


def auth_mode() -> str:
    mode = str(get_env("auth.mode", "password") or "password").lower()
    providers = oauth_providers()
    if mode == "auto":
        return "dual" if providers else "password"
    if mode in ("oauth", "dual") and not providers:
        return "password"
    return mode if mode in ("password", "oauth", "dual", "none") else "password"


def oauth_providers() -> dict[str, dict]:
    cfg = get_env("oauth.providers", {}) or {}
    out = {}
    for name, p in cfg.items():
        if isinstance(p, dict) and p.get("key") and p.get("secret") and p.get("enabled", True):
            out[name] = p
    return out


def current_user(request: Request) -> str | None:
    tok = request.cookies.get(AUTH_COOKIE)
    if not tok:
        return None
    try:
        return _serializer().loads(tok, max_age=MAX_AGE)
    except BadSignature:
        return None


def _set_auth(response: Response, user: str) -> None:
    response.set_cookie(AUTH_COOKIE, _serializer().dumps(user), max_age=MAX_AGE, httponly=True, samesite="lax")


def require_user(request: Request) -> str:
    u = current_user(request)
    if not u:
        raise HTTPException(401, "Not logged in")
    return u


def require_admin(request: Request) -> str:
    u = require_user(request)
    if not auth.is_admin_user(u):
        raise HTTPException(403, "Admins only")
    return u


@asynccontextmanager
async def lifespan(app: FastAPI):
    from hani2 import conflicts

    problems = conflicts.startup_problems()
    if problems:  # refuse to start: say which setting to use
        for p in problems:
            print(f"[hani2] ERROR: {p}")
        raise conflicts.ConflictError("confusing settings: " + "; ".join(problems))
    hub.attach_loop(asyncio.get_running_loop())
    auth.ensure_default_users()
    for u in auth.default_password_users():
        print(f"[hani2] WARNING: the account {u!r} still has its default password; "
              f"set one with `hani2 users passwd {u}`"
              + (" (admin logins with it are refused on this server)"
                 if auth.is_admin_user(u) and auth.refuses_default_admin_password() else ""))
    try:
        from hani2.agents import _prime_group_syspaths

        _prime_group_syspaths()
    except Exception:
        pass
    # the old local-ollama fallback is an entry of the model chain now (hani2.model_chain)

    async def _gc():
        while True:
            await asyncio.sleep(600)
            hub.gc()

    task = asyncio.create_task(_gc())
    yield
    task.cancel()
    # finish open recordings (compressed, with their summary); the sessions stay usable
    for sess in list(hub.sessions.values()):
        r = getattr(sess, "recorder", None)
        if r is not None:
            try:
                r.finalize()
            except Exception:
                traceback.print_exc()


app = FastAPI(title="HANI2", version=__version__, lifespan=lifespan)
app.include_router(__import__("hani2.api_library", fromlist=["router"]).router)  # /api/admin/library (hani2.library)


# --------------------------------------------------------------------------- #
# Public configuration                                                         #
# --------------------------------------------------------------------------- #
@app.get("/api/config")
def api_config(request: Request):
    from hani2.templates import render, study_variables

    env = load_env()
    ref = projects.current_study()
    st = projects.get_study(ref)
    vals = study_variables(ref)
    return {
        "title": render(str(env.get("title", "HANI2")), vals),
        "subtitle": render(str(env.get("subtitle", "")), vals),
        "version": __version__,
        "auth_mode": auth_mode(),
        "oauth_providers": list(oauth_providers()),
        "sso_providers": sso.public(),
        "allow_registration": bool(env["auth"].get("allow_registration", True)) and auth_mode() != "none",
        "enforce_consent": bool(env["auth"].get("enforce_consent", False)),
        "playground": bool((env.get("playground") or {}).get("enabled", True)),
        "experiment": os.environ.get("HANI2_EXPERIMENT") or None,
        "project": ref.project if ref else projects.DEFAULT_PROJECT,
        "study": None if ref is None else {"project": ref.project, "name": ref.study, "type": st.type if st else None,
                                           "title": vals.get("study_title"), "path": projects.study_url_prefix(ref)},
        "docs_url": env.get("docs_url") or "https://autoneg.github.io/hani2/",  # empty: the documentation
    }


@app.get("/api/announcements")
def api_announcements(mode: str = "main"):
    from hani2.templates import render

    return {"markdown": render(read_settings_text("announcements.md", ""))}


def _consent_text() -> str:
    """The current study's consent text, placeholders filled."""
    from hani2.templates import render

    return render(read_settings_text("consent.md", ""))


def _has_consent(user: str) -> bool:
    return auth.has_study_consent(user, projects.current_study(), _consent_text())


# --------------------------------------------------------------------------- #
# Authentication                                                               #
# --------------------------------------------------------------------------- #
@app.get("/api/auth/me")
def api_me(request: Request):
    u = current_user(request)
    if not u:
        return {"user": None}
    meta = auth.get_meta(u)
    return {
        "user": u,
        "display_name": meta.get("full_name") or u,
        "email": meta.get("email"),
        "is_admin": auth.is_admin_user(u),
        "consented": _has_consent(u),
        "needs_consent": bool(get_env("auth.enforce_consent", False)) and not _has_consent(u)
        and not auth.is_admin_user(u),
    }


@app.post("/api/auth/login")
def api_login(response: Response, body: dict = Body(...)):
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if auth_mode() == "oauth":
        raise HTTPException(400, "Password login is disabled on this server.")
    if not auth.verify_user_password(username, password):
        ev.log_event(None, ev.EventType.LOGIN_FAILED, user=username)
        raise HTTPException(401, "Invalid username or password")
    if auth.is_refused_default_login(username, password):
        ev.log_event(None, ev.EventType.LOGIN_FAILED, user=username)
        raise HTTPException(403, f"The {username!r} account still has its default password, which is refused "
                            f"on a server reachable from other machines. Set a new one on the server with "
                            f"`hani2 users passwd {username}` and log in again.")
    _set_auth(response, username)
    ev.log_event(None, ev.EventType.LOGIN, user=username)
    return {"ok": True, "user": username}


@app.post("/api/auth/logout")
def api_logout(request: Request, response: Response):
    u = current_user(request)
    response.delete_cookie(AUTH_COOKIE)
    response.delete_cookie(SID_COOKIE)
    if u:
        ev.log_event(None, ev.EventType.LOGOUT, user=u)
    return {"ok": True}


@app.post("/api/auth/register")
def api_register(response: Response, body: dict = Body(...)):
    if not get_env("auth.allow_registration", True) or auth_mode() in ("oauth", "none"):
        raise HTTPException(403, "Registration is disabled")
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    err = auth.validate_new_user(username, password, body.get("confirm"))
    email = str(body.get("email", "")).strip()
    if not err and body.get("confirm_email") is not None and body.get("confirm_email") != email:
        err = "Emails do not match."
    if err:
        raise HTTPException(400, err)
    meta = {"email": email, "full_name": str(body.get("full_name", "")).strip(), "self_registered": True}
    ref = projects.current_study()
    if body.get("consent") and (ref is None or ref == projects.default_study()):
        meta.update(consented=True, consent_date=time.strftime("%Y-%m-%dT%H:%M:%S"))
    auth.create_user(username, password, **meta)
    if body.get("consent"):
        auth.set_study_consent(username, ref, _consent_text(), full_name=meta["full_name"])
    _set_auth(response, username)
    return {"ok": True, "user": username}


@app.post("/api/auth/password")
def api_change_password(user: str = Depends(require_user), body: dict = Body(...)):
    if not auth.verify_user_password(user, str(body.get("old", ""))):
        raise HTTPException(400, "The current password is wrong")
    new = str(body.get("new", ""))
    if len(new) < 4:
        raise HTTPException(400, "Password must have at least 4 characters")
    auth.set_password(user, new)
    return {"ok": True}


@app.get("/api/consent")
def api_consent_text():
    """The current study's consent text (rendered) and its hash."""
    text = _consent_text()
    ref = projects.current_study()
    return {"markdown": text, "hash": auth.consent_hash(text), "study": str(ref) if ref else None}


@app.post("/api/consent")
def api_consent(user: str = Depends(require_user), body: dict = Body(...)):
    """Record consent to the current study (with the date and a hash of the text accepted)."""
    if not body.get("agree") or not str(body.get("full_name", "")).strip():
        raise HTTPException(400, "Please agree and sign with your full name")
    text = _consent_text()
    if body.get("hash") and body["hash"] != auth.consent_hash(text):
        raise HTTPException(409, "The consent text has changed; please read it again")
    auth.set_study_consent(user, projects.current_study(), text, full_name=str(body["full_name"]).strip())
    return {"ok": True}


# -- OAuth (GitHub / Google, authorization-code flow) ------------------------
OAUTH_ENDPOINTS = {
    "github": dict(
        authorize="https://github.com/login/oauth/authorize",
        token="https://github.com/login/oauth/access_token",
        user="https://api.github.com/user",
        emails="https://api.github.com/user/emails",
        scope="read:user user:email",
    ),
    "google": dict(
        authorize="https://accounts.google.com/o/oauth2/v2/auth",
        token="https://oauth2.googleapis.com/token",
        user="https://openidconnect.googleapis.com/v1/userinfo",
        scope="openid email profile",
    ),
}


def _redirect_uri(request: Request, provider: str) -> str:
    base = str(get_env("oauth.redirect_uri", "") or "").rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/api/oauth/{provider}/callback"


@app.get("/api/oauth/{provider}/login")
def oauth_login(provider: str, request: Request):
    p = oauth_providers().get(provider)
    ep = OAUTH_ENDPOINTS.get(provider)
    if not p or not ep:
        raise HTTPException(404, "Unknown OAuth provider")
    state = secrets.token_urlsafe(16)
    params = dict(client_id=p["key"], redirect_uri=_redirect_uri(request, provider), scope=ep["scope"], state=state)
    if provider == "google":
        params["response_type"] = "code"
    r = RedirectResponse(f"{ep['authorize']}?{urlencode(params)}")
    r.set_cookie("hani2_oauth_state", state, max_age=600, httponly=True, samesite="lax")
    return r


# -- hand-off sign-in from a trusted website (hani2.sso; e.g. scmlweb) --------------
@app.get("/api/sso/{name}/login")
def sso_login(name: str, next: str = "/app"):
    """Send the browser to the website's token page with this server's site key and the page to return to.
    The website picks this server's base URL from its own settings: it never trusts a URL from here."""
    cfg = sso.providers().get(name)
    if not cfg or not cfg.get("login_url"):
        raise HTTPException(404, "Unknown sign-in provider")
    params = urlencode({"site": root_path() or "/", "next": sso.safe_next(next)})
    sep = "&" if "?" in str(cfg["login_url"]) else "?"
    return RedirectResponse(f"{cfg['login_url']}{sep}{params}", status_code=303)


@app.get("/api/sso/{name}")
def sso_callback(name: str, token: str = "", next: str = "/app"):
    try:
        claims = sso.verify(name, token, root_path=root_path())
        user = sso.sign_in(name, claims, next, root_path=root_path())
    except sso.SSOError as e:
        print(f"[sso] {name}: refused ({e.code}): {e}")
        r = RedirectResponse(root_path() + f"/login?error=sso_{e.code}", status_code=303)
    else:
        r = RedirectResponse(root_path() + sso.safe_next(next), status_code=303)
        _set_auth(r, user)
    r.headers["Referrer-Policy"] = "no-referrer"  # the token is in this URL
    r.headers["Cache-Control"] = "no-store"
    return r


@app.get("/api/oauth/{provider}/callback")
def oauth_callback(provider: str, request: Request, code: str = "", state: str = ""):
    import httpx

    p = oauth_providers().get(provider)
    ep = OAUTH_ENDPOINTS.get(provider)
    if not p or not ep:
        raise HTTPException(404, "Unknown OAuth provider")
    if not code or state != request.cookies.get("hani2_oauth_state"):
        return RedirectResponse(root_path() + "/login?error=oauth_state")
    try:
        data = dict(client_id=p["key"], client_secret=p["secret"], code=code,
                    redirect_uri=_redirect_uri(request, provider))
        if provider == "google":
            data["grant_type"] = "authorization_code"
        tok = httpx.post(ep["token"], data=data, headers={"Accept": "application/json"}, timeout=15).json()
        access = tok.get("access_token")
        if not access:
            return RedirectResponse(root_path() + "/login?error=oauth_token")
        hdr = {"Authorization": f"Bearer {access}", "Accept": "application/json"}
        info = httpx.get(ep["user"], headers=hdr, timeout=15).json()
        if not (info.get("login") if provider == "github" else (info.get("sub") or info.get("email"))):
            return RedirectResponse(root_path() + "/login?error=oauth_failed")  # an error body, not a user
        if provider == "github":
            username = f"gh_{info.get('login')}"
            email = info.get("email")
            if not email:
                try:
                    emails = httpx.get(ep["emails"], headers=hdr, timeout=15).json()
                    email = next((e["email"] for e in emails if e.get("primary")), None)
                except Exception:
                    email = None
            name = info.get("name") or info.get("login")
        else:
            email = info.get("email")
            username = f"g_{info.get('sub') or (email or 'user').replace('@', '_at_')}"
            name = info.get("name") or username
    except Exception:
        traceback.print_exc()
        return RedirectResponse(root_path() + "/login?error=oauth_failed")
    if not auth.user_exists(username):
        auth.create_user(username, None, email=email or "", full_name=name or "", oauth=provider)
    else:
        auth.update_meta(username, email=email or "", oauth=provider)
    r = RedirectResponse(root_path() + "/app")
    _set_auth(r, username)
    ev.log_event(None, ev.EventType.LOGIN, user=username, value={"oauth": provider})
    return r


# --------------------------------------------------------------------------- #
# Sessions                                                                     #
# --------------------------------------------------------------------------- #
_GID = __import__("re").compile(r"^[0-9a-f]{12}$")


def _guest_id(request: Request, response: Response) -> str:
    """The per-browser id from the guest cookie; anything that is not exactly 12
    hex characters is replaced (it becomes part of a folder name)."""
    gid = request.cookies.get(GUEST_COOKIE) or ""
    if not _GID.match(gid):
        gid = uuid.uuid4().hex[:12]
    response.set_cookie(GUEST_COOKIE, gid, max_age=MAX_AGE, samesite="lax")
    return gid


def _truthy(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _clean_id(v: Any) -> str:
    return "".join(c for c in str(v) if c.isalnum() or c in "-_")[:64]


def _session_sid(base: str, ref: "projects.StudyRef | None") -> str:
    """Session ids carry the study, except for the process default study (whose ids stay as they were)."""
    if ref == projects.default_study():
        return base
    return f"{base}::{ref.project}:{ref.study}" if ref is not None else f"{base}::"


def _request_study(query: dict) -> "projects.StudyRef | None":
    """The study of a request: the URL (``/s/P/S/...`` or ``?study=`` on the API call), else
    ``study`` in the page's query, else the process default."""
    if projects.is_bound():
        return projects.current_study()
    if query.get("study"):
        try:
            ref = projects.parse_ref(str(query["study"]))
        except ValueError:
            raise HTTPException(404, "Unknown study") from None
        if not _study_allowed(ref):
            raise HTTPException(404, "Unknown study")
        return ref
    return projects.current_study()


@app.post("/api/session")
def api_session(request: Request, response: Response, body: dict = Body(default={})):
    query = {str(k): v for k, v in (body.get("query") or {}).items()}
    ref = _request_study(query)
    with projects.use_study(ref):
        return _api_session(request, response, body, query, ref)


def _api_session(request: Request, response: Response, body: dict, query: dict, ref) -> dict:
    mode = "guest" if body.get("mode") == "guest" else "main"
    signed_in = current_user(request)
    gstudy = sso.guest_study(signed_in)
    if gstudy is not None:
        # an invited guest (hani2.sso): only the one study their invitation names, as a participant
        if ref is None or f"{ref.project}/{ref.study}" != gstudy:
            raise HTTPException(403, "guest_study")
        return _guest_session(request, response, body, query, ref, signed_in)
    pid = query.get("PROLIFIC_PID") or query.get("prolific_pid")
    st = projects.get_study(ref)
    participant = None
    if not pid and st is not None and st.type in ("online", "lab"):
        participant = next((query[k] for k in ("pid", "participant", "code") if query.get(k)), None)
        participant = _clean_id(participant) if participant else None
    ua = request.headers.get("user-agent", "")
    user = current_user(request)
    is_admin = auth.is_admin_user(user)
    if mode == "main":
        if auth_mode() == "none":
            user = user or f"user_{_guest_id(request, response)}"
        if not user:
            raise HTTPException(401, "Not logged in")
        if get_env("auth.enforce_consent", False) and not _has_consent(user) and not is_admin:
            raise HTTPException(403, "consent_required")
        sid = f"main:{user}"
        display = auth.get_meta(user).get("full_name") or user
    else:
        if not (get_env("playground.enabled", True) or pid or participant):
            raise HTTPException(403, "The playground is disabled")
        if pid:
            pid = _clean_id(pid)
            user, display = f"prolific_{pid}", "Participant"
            sid = f"prolific:{pid}"
        elif participant:
            user, display = f"participant_{participant}", "Participant"
            sid = f"participant:{participant}"
            pid = participant
        elif user:
            # a signed-in browser plays under its own account (its results show in its Results tab);
            # a separate session from its /app one. Without a login: the anonymous guest playground.
            display = auth.get_meta(user).get("full_name") or user
            sid = f"play:{user}"
        else:
            gid = _guest_id(request, response)
            # each browser gets its own results folder (no concurrent writes to one file)
            user, display = f"guest_{gid}", "Guest"
            sid = f"guest:{gid}"
        is_admin = False if pid else is_admin
    admin_mode = is_admin  # ?admin=1 no longer turns on the admin view for non-admins
    # An admin can negotiate exactly as a participant would (?as_participant=1): no admin controls, no
    # opponent type, no scenario/opponent pickers. It is a separate session and results folder, and it
    # is never counted as a study participant.
    viewer = None
    if is_admin and _truthy(query.get("as_participant", "")):
        viewer, is_admin, admin_mode = user, False, False
        user, sid = f"{user}~participant", f"{sid}~participant"
    sid = _session_sid(sid, ref)
    # A session keeps the admin flag it was made with (tools, settings and the view are built from it), so
    # an account that became or stopped being an admin since (a hand-off's admin claim, the Users page)
    # gets a new session instead of the old one.
    old = hub.get(sid)
    stale = old is not None and (bool(old.is_admin) != bool(is_admin)
                                 or (getattr(old, "admin_viewer", None) or None) != (viewer or None))
    # atomic per sid: a double page load, two tabs or a retry must not each make (and replace) a session
    s, created = hub.get_or_create(
        sid,
        lambda: NegotiationSession(sid, user, mode=mode, is_admin=is_admin, admin_mode=admin_mode, query=query,
                                   hub=hub, user_agent=ua, display_name=display, study=ref, admin_viewer=viewer),
        fresh=bool(body.get("fresh")) or stale,
        init=lambda s: s.load(),
    )
    if not created:
        s.query.update(query)
        if mode == "main" and user and user.startswith(tuple(sso.reserved_prefixes())):
            _new_round_after_handoff(s, auth.get_meta(user))
        s.refresh_assistant(getattr(s, "round_plan", None))  # a new ?group= may name another Assistant
    elif mode == "main" and user:
        s._handoff_seen = float(auth.get_meta(user).get("last_handoff") or 0)
    s.last_seen = time.time()
    return {"sid": sid}


def _guest_session(request: Request, response: Response, body: dict, query: dict, ref, account: str) -> dict:
    """The session of an invited guest: one per browser (several people may share one invitation, hence
    one account), results in ``<account>~<browser>``, never admin, no URL overrides for admins."""
    meta = auth.get_meta(account)
    if get_env("auth.enforce_consent", False) and not _has_consent(account):
        raise HTTPException(403, "consent_required")
    gid = _guest_id(request, response)
    user, sid = f"{account}~{gid}", _session_sid(f"main:{account}~{gid}", ref)
    display = meta.get("full_name") or "Guest"
    ua = request.headers.get("user-agent", "")

    def make():
        s = NegotiationSession(sid, user, mode="main", is_admin=False, admin_mode=False, query=query, hub=hub,
                               user_agent=ua, display_name=display, study=ref)
        return s

    def init(s):
        _bind_account(s, account, meta)
        s.load()

    s, created = hub.get_or_create(sid, make, fresh=bool(body.get("fresh")), init=init)
    if not created:
        s.query.update(query)
        _bind_account(s, account, meta)
        _new_round_after_handoff(s, meta)
        s.refresh_assistant(getattr(s, "round_plan", None))
    s.last_seen = time.time()
    return {"sid": sid}


def _bind_account(s: NegotiationSession, account: str, meta: dict) -> None:
    s.account = account  # the login the WebSocket checks
    s.ss["invited_by"] = str(meta.get("invited_by") or "")
    s.ss["guest"] = bool(meta.get("guest"))


def _new_round_after_handoff(s: NegotiationSession, meta: dict) -> None:
    """A fresh hand-off from the website (a new "play" click) after a finished negotiation opens a new
    one, instead of the old result; a reload of the page does not."""
    t = float(meta.get("last_handoff") or 0)
    if t and t > float(getattr(s, "_handoff_seen", 0) or 0):
        s._handoff_seen = t
        if s.phase == "ended":
            s.submit(s.load)


def _dispatch(s: NegotiationSession, msg: dict[str, Any]) -> Any:
    from hani2.recording.recorder import acting

    with acting("human"):
        return _dispatch_msg(s, msg)


def _dispatch_msg(s: NegotiationSession, msg: dict[str, Any]) -> Any:
    t = msg.get("type")
    if t == "load":
        return s.load(msg.get("scenario_type"), msg.get("name"))
    if t == "start":
        return s.start()
    if t == "opponent_choice":  # play a person, or an AI opponent now (also while waiting)
        r = s.choose_opponent_kind(str(msg.get("kind", "")))
        if not r.get("ok"):
            s.toast(r.get("error", "Could not choose"), "warning")
        return r
    if t == "draft":
        return s.set_draft(msg.get("values") or {})
    if t == "draft_input":
        return s.draft_input(str(msg.get("name", "")), msg.get("value"))
    if t == "draft_action":
        return s.draft_action(str(msg.get("action", "")), msg.get("payload") or {})
    if t == "draft_text":
        return s.set_draft_text(str(msg.get("text", "")))
    if t == "send":
        r = s.send_counter(text=msg.get("text"), offer=msg.get("values") or None, text_only=msg.get("text_only"))
        if not r.get("ok"):
            s.toast(r.get("error", "Could not send"), "warning")
        return r
    if t == "accept":
        return s.accept()
    if t == "end":
        return s.end()
    if t == "tool_input":
        return s.tool_input(msg["id"], str(msg["name"]), msg.get("value"))
    if t == "tool_action":
        return s.tool_action(msg["id"], str(msg["action"]), msg.get("payload") or {})
    if t == "tool_layout":
        if not s.admin_prefs.get("allow_moving_tools", True) and msg.get("op") in ("move",):
            return None
        c = s.tool_controller
        op, name = msg.get("op"), msg.get("name")
        if op in ("show", "hide", "enable", "focus"):
            opened = op in ("show", "focus") or (op == "enable" and bool(msg.get("enabled", True)))
            ev.log_event(s.sid, ev.EventType.TOOL_OPENED if opened else ev.EventType.TOOL_CLOSED, user=s.user,
                         component=str(name), action=op)
        if op == "move":
            return c.move_tool(name, position=msg.get("position"), pane=msg.get("pane"))
        if op == "hide":
            return c.set_tool_visible(name, False)
        if op == "show":
            return c.set_tool_visible(name, True)
        if op == "enable":
            return c.set_tool_enabled(name, bool(msg.get("enabled", True)))
        if op == "focus":
            return c.focus_tool(name)
        if op == "restore":
            return c.restore_all()
        return None
    if t == "active_tab":
        s.active_tabs[str(msg.get("pane"))] = msg.get("name")
        tool = s.tool_controller.find(msg.get("name") or "")
        if tool is not None:
            s.retry_tool(tool)  # opening the tab retries a tool given up for being too slow
            tool.refresh()
        s.push_state()
        ev.log_event(s.sid, ev.EventType.TAB_CHANGED, user=s.user, component=str(msg.get("name")))
        return None
    if t == "device":
        s.ss["device"] = str(msg.get("device") or "")[:16]
        s.ss["orientation"] = "landscape" if msg.get("landscape") else "portrait"
        return None
    if t == "pref":
        return s.set_pref(str(msg.get("key")), msg.get("value"))
    if t == "layout":
        changes = {k: msg[k] for k in ("view", "sizes", "collapsed") if k in msg}
        if "view" in changes and not s.may_adjust("layout_view"):
            changes.pop("view")
        return s.set_layout(**changes)
    if t == "unpin":
        return s.unpin(str(msg.get("id") or "") or None, by="human")
    if t == "clear_notifications":
        return s.clear_notifications()
    if t == "chat":
        return s.user_chat(str(msg.get("text", "")))
    if t == "answer":
        sa = s.support_agent
        if sa is not None:
            sa._answer_question(str(msg.get("text", "")), echo=True)
        return None
    if t == "support":
        sa = s.support_agent
        if sa is None:
            return None
        op = msg.get("op")
        gate = {"enable": "assistant_switch", "capability": "assistant_abilities", "autonomy": "assistant_autonomy",
                "delivery": "assistant_delivery"}.get(str(op))
        if gate and not s.may_adjust(gate):
            return None
        if op == "enable":
            sa.set_user_enabled(bool(msg.get("value")))
        elif op == "capability":
            sa.capabilities.set_user_capability(str(msg.get("key")), bool(msg.get("value")))
        elif op == "autonomy":
            sa.capabilities.set_user_autonomy(str(msg.get("value")))
        elif op == "delivery":
            sa.set_proactive_delivery(str(msg.get("value")))
        elif op == "reset":
            sa.clear_conversation()
            with s.lock:
                s.chat = []
        s.push_state()
        return None
    if t == "panel_action":
        return s.panel_event(str(msg.get("panel_id")), str(msg.get("action")), msg.get("payload") or {})
    if t == "close_panel":
        return s.close_panel(msg.get("panel_id"))
    if t == "clear_highlight":
        return s.clear_highlights(msg.get("target"))
    if t == "autopilot":
        r = s.set_autopilot(bool(msg.get("active")), msg.get("driver"))
        if not r.get("ok"):
            s.toast(r.get("error", "Autopilot unavailable"), "warning")
        return r
    if t == "questionnaire":
        r = s.study.submit_questionnaire(msg.get("answers") or {})
        if not r.get("ok"):
            s.toast(r.get("error", "Please complete the questionnaire"), "warning")
        return r
    if t == "choose":
        r = s.choose(str(msg.get("kind") or ""), msg.get("value"))
        if not r.get("ok"):
            s.toast(r.get("error", "Not allowed"), "warning")
        return r
    if t == "opponent" and s.admin_mode:
        spec = str(msg.get("spec") or "")
        if not s.is_admin and not agents.client_spec_allowed(spec):
            return {"ok": False, "error": "file: opponents need an admin account"}
        s.next_opponent = spec
        s.push_state()
        return None
    if t == "extract" and s.is_admin:
        r = s.extract_offer_from_text()
        if not r.get("ok"):
            s.toast(r.get("error", "Extraction failed"), "warning")
        return r
    if t == "generate" and s.is_admin:
        r = s.generate_text()
        if not r.get("ok"):
            s.toast(r.get("error", "Generation failed"), "warning")
        return r
    if t == "event":
        ev.log_event(s.sid, str(msg.get("name") or "button_clicked"), user=s.user, component=msg.get("component"),
                     action=msg.get("action"), value=msg.get("value"))
        return None
    return None


@app.websocket("/api/ws/{sid}")
async def ws_endpoint(websocket: WebSocket, sid: str):
    s = hub.get(sid)
    if s is None:
        await websocket.close(code=4404)
        return
    # The main-app and signed-in playground sessions belong to a logged-in user: check the cookie.
    if sid.startswith(("main:", "play:")):
        user = None
        tok = websocket.cookies.get(AUTH_COOKIE)
        if tok:
            try:
                user = _serializer().loads(tok, max_age=MAX_AGE)
            except BadSignature:
                user = None
        if auth_mode() != "none" and user != (getattr(s, "account", None) or getattr(s, "admin_viewer", None) or s.user):
            await websocket.close(code=4401)
            return
        if getattr(s, "account", None) and websocket.cookies.get(GUEST_COOKIE) != s.user.rsplit("~", 1)[-1]:
            await websocket.close(code=4401)  # a guest's session belongs to one browser
            return
    elif sid.startswith("guest:"):
        if websocket.cookies.get(GUEST_COOKIE) != sid.split("::", 1)[0].split(":", 1)[1]:
            await websocket.close(code=4401)
            return
    if _admin_lapsed(s):
        _drop_lapsed(sid, s)
        await websocket.close(code=4404)  # the page asks for a new (non-admin) session
        return
    await websocket.accept()
    hub.connect(sid, websocket)
    loop = asyncio.get_running_loop()
    try:
        snap = await loop.run_in_executor(None, s.snapshot)
        from hani2.hub import _dumps

        await websocket.send_text(_dumps(hub._stamp(sid, {"type": "state", "state": snap})))
        for t in list(s.tools):
            hub.tool_changed(sid, s.tool_state(t)["id"])
        while True:
            raw = await websocket.receive_text()
            s.last_seen = time.time()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(msg, dict):
                continue  # [] or 1 would end this connection at msg.get
            if _admin_lapsed(s):  # demoted while connected (checked on pings too): no admin action on the old session
                _drop_lapsed(sid, s)
                await websocket.close(code=4404)
                return
            if msg.get("type") == "ping":
                await websocket.send_text('{"type":"pong"}')
                continue
            r = getattr(s, "recorder", None)
            if r is not None:
                r.inbound(msg)  # before the executors, which may reorder messages
            if msg.get("type") == "telemetry":
                continue
            if msg.get("type") in ("chat", "answer", "panel_action", "extract", "generate"):
                s.submit(_dispatch, s, msg)  # may block on an LLM / the human: keep the UI queue free
            else:
                s.submit_ui(_dispatch, s, msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        hub.disconnect(sid, websocket)


def _admin_lapsed(s: NegotiationSession) -> bool:
    """Whether an admin session (or an admin's ``?as_participant=1`` one) belongs to an account that is no
    longer an admin (checked again on every WebSocket message: the role is read fresh, never cached)."""
    owner = getattr(s, "admin_viewer", None) or (s.user if s.is_admin else None)
    return bool(owner) and not auth.is_admin_user(owner)


def _drop_lapsed(sid: str, s: NegotiationSession) -> None:
    if hub.get(sid) is s:  # not a new session another page load made meanwhile
        hub.remove(sid)


# --------------------------------------------------------------------------- #
# Admin API                                                                    #
# --------------------------------------------------------------------------- #
from hani2.layers import SETTINGS_KINDS, TEXT_FILES  # noqa: E402


def _layer_dir(study: str | None, project: str | None) -> Path | None:
    """The folder of the settings layer an admin call names (``None``: the settings folder)."""
    try:
        if study:
            ref = projects.parse_ref(study)
            if ref is None or not projects.study_exists(ref):
                raise HTTPException(404, "Unknown study")
            return projects.study_dir(ref)
        if project:
            projects.check_name(project, "project")
            if project == projects.DEFAULT_PROJECT:
                return None
            if not projects.project_exists(project):
                raise HTTPException(404, "Unknown project")
            return projects.project_dir(project)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return None


@app.get("/api/admin/settings/{kind}")
def admin_get_settings(kind: str, layer: str | None = None, study: str | None = None, project: str | None = None,
                       _: str = Depends(require_admin)):
    """A settings file. Without ``layer``/``study``/``project``: the effective settings (all layers).
    With ``?study=P/S`` or ``?project=P``: that layer's own file (raw: ``{}`` / empty when it has none).
    With ``?layer=settings|project:P|study:P/S``: the layer's own file, what is in effect there and what it inherits."""
    from hani2 import admin_api

    if kind not in SETTINGS_KINDS and kind not in TEXT_FILES:
        raise HTTPException(404)
    if layer:
        return admin_api.settings_get(kind, admin_api.need_layer(layer))
    if not study and not project:
        if kind in SETTINGS_KINDS:
            return SETTINGS_KINDS[kind][1]()
        return {"text": read_settings_text(TEXT_FILES[kind], "")}
    folder = _layer_dir(study, project) or settings_dir()
    if kind in SETTINGS_KINDS:
        f = folder / SETTINGS_KINDS[kind][0]
        try:
            return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        except json.JSONDecodeError:
            raise HTTPException(409, f"{f.name} in this layer is not valid JSON") from None
    f = folder / TEXT_FILES[kind]
    return {"text": f.read_text(encoding="utf-8") if f.exists() else "", "exists": f.exists(),
            "effective": read_settings_text(TEXT_FILES[kind], "")}


@app.put("/api/admin/settings/{kind}")
def admin_put_settings(kind: str, request: Request, body: dict = Body(...), layer: str | None = None,
                       study: str | None = None, project: str | None = None, _: str = Depends(require_admin)):
    """Replace a layer's own settings file (``?layer=``, ``?study=P/S``, ``?project=P``). Without any of
    them the settings folder is written, except in a console opened under ``/s/P/S/`` (409)."""
    from hani2 import admin_api

    if kind not in SETTINGS_KINDS and kind not in TEXT_FILES:
        raise HTTPException(404)
    return admin_api.settings_put(kind, admin_api.write_target(request, layer, study, project), body)


@app.patch("/api/admin/settings/{kind}")
def admin_patch_settings(kind: str, request: Request, body: dict = Body(...), layer: str | None = None,
                         study: str | None = None, project: str | None = None, _: str = Depends(require_admin)):
    """Deep-merge a partial dict into a layer's own JSON settings file."""
    from hani2 import admin_api

    return admin_api.settings_patch(kind, admin_api.write_target(request, layer, study, project), body)


@app.delete("/api/admin/settings/{kind}")
def admin_delete_settings(kind: str, request: Request, layer: str | None = None, study: str | None = None,
                          project: str | None = None, key: str | None = None, _: str = Depends(require_admin)):
    """Remove one dotted ``key`` from a layer's own JSON file, or the whole file (back to inherited)."""
    from hani2 import admin_api

    return admin_api.settings_delete(kind, admin_api.write_target(request, layer, study, project), key)


# -- projects and studies ------------------------------------------------------
def _count_rows(files: list[Path]) -> int:
    import csv

    n = 0
    for f in files:
        try:
            with open(f, newline="", encoding="utf-8", errors="replace") as fh:
                n += max(0, sum(1 for _ in csv.reader(fh)) - 1)
        except OSError:
            pass
    return n


def _editor_info(project: str, ref: "projects.StudyRef | None" = None) -> dict:
    """What the project and study editor needs besides the file: the project's kind and year (the
    "this year" / "last year" labels of the HAN picker), the years each HAN source covers (read in
    the file's own layer, as the save checks do), what a study inherits from its project, and
    ``effective``: the Assistant and opponent pools a session would play (with their sources), K,
    the mode in use and the derived one (:meth:`hani2.study_modes.Pools.to_dict`)."""
    from hani2 import han_submissions, study_modes

    pr = projects.load_project(project)
    with study_modes._layer(ref, None if ref is not None else project):
        current = han_submissions.current_year()
        years = han_submissions.package_years()
    inherited: dict[str, Any] = {"n_required": 5, "study_mode": None, "opponents": None, "assistants": None,
                                 "pairing": {}, "scheduling": {}, "questionnaire_agent": None}
    if ref is not None:
        d = pr.defaults
        inherited = {"n_required": d.get("n_required") if d.get("n_required") is not None else 5,
                     "study_mode": d.get("study_mode"), "opponents": d.get("opponents"),
                     "assistants": d.get("assistants"),
                     "pairing": dict(d["pairing"]) if isinstance(d.get("pairing"), dict) else {},
                     "scheduling": dict(d["scheduling"]) if isinstance(d.get("scheduling"), dict) else {},
                     "questionnaire_agent": d.get("questionnaire_agent") or None}
    try:  # the pools a session would play, K and the mode, for the editor's live checks
        st = projects.get_study(ref) if ref is not None else None
        p = study_modes.effective_pools(pr, st.overrides if st is not None else ({} if ref else None), ref)
        effective, pools = p.to_dict(), p.editor_pools(p.env_opponents)
    except Exception as e:  # noqa: BLE001 — a broken file is reported by the page's errors
        effective, pools = {"error": str(e)}, None
    return {"kind": pr.kind, "project_year": pr.year, "han": {"package_years": years, "current_year": current},
            "inherited": inherited, "pools": pools, "leaderboard": _board_editor_info(project, ref),
            "effective": effective}


def _board_editor_info(project: str, ref: "projects.StudyRef | None") -> dict | None:
    """The ``leaderboard`` block a layer inherits (a project: the defaults; a study: its project's board)
    and the one in effect as saved, for the editor's "inherit (…)" labels."""
    from hani2.evaluation import boards

    try:
        if ref is None:
            return {"inherited": boards.settings(project, project_block=None).to_dict(),
                    "effective": boards.settings(project).to_dict()}
        return {"inherited": boards.settings(project).to_dict(),
                "effective": boards.settings(project, ref.study).to_dict()}
    except Exception:  # noqa: BLE001 — a broken file is reported by the page's errors
        return None


def _study_info(ref: "projects.StudyRef") -> dict:
    from hani2 import scheduling, study_modes

    st = projects.load_study(ref)
    results = projects.study_dir(ref) / "results"
    files = list(results.glob("*/results.csv")) if results.is_dir() else []
    effective, _, sched_errors = scheduling.resolve(ref)
    mode = study_modes.resolve(ref)
    return {**st.to_dict(), "path": str(st.path), "legacy": st.legacy, "participants": len(files),
            "results_rows": _count_rows(files),
            "default": ref == projects.default_study(),
            # the study's own choice (as in study.yaml), and what it uses (study, then project, then defaults)
            "scheduling": dict(st.overrides.get("scheduling") or {}) if isinstance(st.overrides.get("scheduling"), dict) else {},
            "scheduling_effective": effective,
            # the mode in use (declared, else derived from opponents) and the merged pairing keys
            "study_mode_effective": mode.to_dict(),
            "editor": _editor_info(ref.project, ref),
            "errors": list(dict.fromkeys([*st.errors, *sched_errors, *mode.errors])),
            "links": projects.participant_links(ref, projects.public_base_url())}


@app.get("/api/admin/help")
def admin_help(_: str = Depends(require_admin)):
    """The texts of the editor's ``?`` buttons, keyed by setting id (title, one-line summary, Markdown
    details), and the ids every editor choice that is not self-explanatory must have."""
    from hani2 import help_texts

    return help_texts.api_payload()


@app.get("/api/admin/scheduling-methods")
def admin_scheduling_methods(_: str = Depends(require_admin)):
    """The scheduling methods of each dimension (key, title, summary, Markdown details) and the defaults."""
    from hani2 import scheduling

    return scheduling.api_payload()


@app.get("/api/admin/criteria")
def admin_criteria(project: str | None = None, study: str | None = None, coverage: bool = False,
                   _: str = Depends(require_admin)):
    """The evaluation criteria a score can use (metric columns, the questionnaire answers of the forms of
    ``project`` or of ``study`` = ``project/study``, scores), each with its source, level, direction, default
    normaliser and cost, and the project's reference. ``coverage=true`` evaluates the games (no judge) and
    adds each criterion's coverage."""
    from hani2.evaluation import criteria

    try:
        ref = projects.parse_ref(study) if study else None
        if project:
            projects.check_name(project, "project")
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if ref is not None and project and ref.project != project:
        raise HTTPException(400, f"study {ref} is not in project {project!r}")
    project = ref.project if ref is not None else project
    if coverage and not project:
        raise HTTPException(400, "coverage needs a project or a study")
    if project and not projects.project_exists(project):
        raise HTTPException(404, f"no project {project!r}")
    if ref is not None and not projects.study_exists(ref):
        raise HTTPException(404, f"no study {ref}")
    name = ref.study if ref is not None else None
    rows = criteria.reference_rows(project, [name] if name else None, include_simulated=True)[0] \
        if coverage and project else None
    return jsonable(criteria.api_payload(project, name, rows))


# --------------------------------------------------------------------------- #
# Scores (defined in project.yaml and study.yaml)                              #
# --------------------------------------------------------------------------- #
def _score_target(project: str, study: str | None = None) -> tuple[str, str | None]:
    try:
        projects.check_name(project, "project")
        if study is not None:
            projects.check_name(study, "study")
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if not projects.project_exists(project):
        raise HTTPException(404, f"no project {project!r}")
    if study is not None and not projects.study_exists(projects.StudyRef(project, study)):
        raise HTTPException(404, f"no study {project}/{study}")
    return project, study


@app.get("/api/admin/scores")
def admin_scores(project: str | None = None, study: str | None = None, _: str = Depends(require_admin)):
    """The scores of ``project`` (or of ``study`` = ``project/study``): the built-ins (read-only), the
    project's and the study's definitions with their weights in effect (summing to 1) and flattened down
    to criteria, ``scores_enabled``, and the problems and warnings of the files."""
    from hani2.evaluation import scores as S

    try:
        ref = projects.parse_ref(study) if study else None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if ref is not None and project and ref.project != project:
        raise HTTPException(400, f"study {ref} is not in project {project!r}")
    if ref is None and not project:
        raise HTTPException(400, "give a project or a study (project/study)")
    project, name = _score_target(ref.project if ref is not None else str(project), ref.study if ref else None)
    from hani2.evaluation.catalog import VALIDATED_TOOLTIP, validation_of

    ss = S.resolve(project, name)
    out = ss.to_dict()
    for d in out["scores"]:  # a built-in score checked against a hand-worked example carries the ✓
        s = ss.scores.get(d["key"])
        d["validated"] = bool(s is not None and s.builtin and validation_of(d["key"]))
    out["validated_tooltip"] = VALIDATED_TOOLTIP
    return jsonable(out)


@app.post("/api/admin/scores/preview")
def admin_score_preview(project: str | None = None, study: str | None = None, body: Any = Body(...),
                        _: str = Depends(require_admin)):
    """A score that is not saved (``{"key": …, "score": {definition}}``, or the definition itself) on the
    current data of the board of ``project`` (or of ``study`` = ``project/study``): the weights in effect
    after coverage, the dropped parts, the distribution of the score over the counted games and the top
    entrants. Nothing is written; a definition that cannot be computed gives its ``problems``."""
    from hani2.evaluation import boards

    try:
        ref = projects.parse_ref(study) if study else None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if ref is not None and project and ref.project != project:
        raise HTTPException(400, f"study {ref} is not in project {project!r}")
    if ref is None and not project:
        raise HTTPException(400, "give a project or a study (project/study)")
    project, name = _score_target(ref.project if ref is not None else str(project), ref.study if ref else None)
    if not isinstance(body, dict):
        raise HTTPException(400, "send the score's definition as a JSON object")
    key = body.get("key") if isinstance(body.get("key"), str) else None
    definition = body.get("score") if isinstance(body.get("score"), dict) else \
        {k: v for k, v in body.items() if k not in ("key", "origin", "enabled", "flattened")}
    try:
        return jsonable(boards.preview(project, name, definition, key))
    except boards.BoardNotFound as e:
        raise HTTPException(404, str(e)) from None


def _save_score(project: str, study: str | None, key: str, body: Any) -> dict:
    from hani2.evaluation import scores as S

    if not isinstance(body, dict):
        raise HTTPException(400, "send the score's definition as a JSON object")
    body = {k: v for k, v in body.items() if k not in ("key", "origin", "enabled", "flattened")}
    try:
        S.save_score(project, study, key, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"ok": True, **jsonable(S.resolve(project, study).to_dict())}


def _delete_score(project: str, study: str | None, key: str) -> dict:
    from hani2.evaluation import scores as S

    try:
        S.delete_score(project, study, key)
    except KeyError:
        raise HTTPException(404, f"no score {key!r} defined here") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None
    return {"ok": True}


def _save_enabled(project: str, study: str | None, body: Any) -> dict:
    from hani2.evaluation import scores as S

    enabled = body.get("enabled") if isinstance(body, dict) else body
    if enabled is not None and not isinstance(enabled, list):
        raise HTTPException(400, 'send {"enabled": [score, ...]} or {"enabled": null} for the default')
    try:
        return {"ok": True, "enabled": S.save_enabled(project, study, enabled)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


def _duplicate_score(project: str, study: str | None, key: str, body: Any) -> dict:
    from hani2.evaluation import scores as S

    source = body.get("from") if isinstance(body, dict) else None
    if not isinstance(source, str) or not source:
        raise HTTPException(400, 'send {"from": "<score to copy>"}')
    try:
        S.duplicate(project, study, source, key)
    except KeyError:
        raise HTTPException(404, f"no score {source!r}") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"ok": True, **jsonable(S.resolve(project, study).to_dict())}


@app.put("/api/admin/projects/{project}/scores/{key}")
def admin_put_project_score(project: str, key: str, body: Any = Body(...), _: str = Depends(require_admin)):
    """Add or replace a score in ``project.yaml``. 400 unless the weights are ≥ 0 and sum to 1 and every
    check passes (known criteria, directions, normalisers, no cycles, no key clashes)."""
    return _save_score(*_score_target(project), key, body)


@app.delete("/api/admin/projects/{project}/scores/{key}")
def admin_delete_project_score(project: str, key: str, _: str = Depends(require_admin)):
    """Remove a score from ``project.yaml`` (409 while another score contains it or ``scores_enabled``
    names it)."""
    return _delete_score(*_score_target(project), key)


@app.post("/api/admin/projects/{project}/scores/{key}/duplicate")
def admin_duplicate_project_score(project: str, key: str, body: Any = Body(...), _: str = Depends(require_admin)):
    """Copy a score (``{"from": "hi_team"}``, for example a read-only built-in) into ``project.yaml`` as ``key``."""
    return _duplicate_score(*_score_target(project), key, body)


@app.put("/api/admin/projects/{project}/scores_enabled")
def admin_put_project_enabled(project: str, body: Any = Body(...), _: str = Depends(require_admin)):
    """Set the project's ``scores_enabled`` (``{"enabled": [...]}``; ``null``: every score)."""
    return _save_enabled(*_score_target(project), body)


@app.put("/api/admin/projects/{project}/studies/{study}/scores/{key}")
def admin_put_study_score(project: str, study: str, key: str, body: Any = Body(...), _: str = Depends(require_admin)):
    """Add a score to ``study.yaml``, or redefine one of the project's by key."""
    return _save_score(*_score_target(project, study), key, body)


@app.delete("/api/admin/projects/{project}/studies/{study}/scores/{key}")
def admin_delete_study_score(project: str, study: str, key: str, _: str = Depends(require_admin)):
    return _delete_score(*_score_target(project, study), key)


@app.post("/api/admin/projects/{project}/studies/{study}/scores/{key}/duplicate")
def admin_duplicate_study_score(project: str, study: str, key: str, body: Any = Body(...),
                                _: str = Depends(require_admin)):
    return _duplicate_score(*_score_target(project, study), key, body)


@app.put("/api/admin/projects/{project}/studies/{study}/scores_enabled")
def admin_put_study_enabled(project: str, study: str, body: Any = Body(...), _: str = Depends(require_admin)):
    """Set the study's ``scores_enabled`` (``{"enabled": [...]}``; ``null``: the project's choice)."""
    return _save_enabled(*_score_target(project, study), body)


def _ref_or_404(project: str, study: str) -> "projects.StudyRef":
    try:
        ref = projects.StudyRef(projects.check_name(project, "project"), projects.check_name(study, "study"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return ref


@app.get("/api/admin/projects")
def admin_projects(_: str = Depends(require_admin)):
    out = []
    for name in projects.list_projects():
        pr = projects.load_project(name)
        out.append({**pr.to_dict(), "path": str(pr.path) if pr.path else None, "studies": projects.list_studies(name)})
    d = projects.default_study()
    return {"projects": out, "default_study": str(d) if d else None}


@app.get("/api/admin/projects/{project}")
def admin_project(project: str, _: str = Depends(require_admin)):
    try:
        if not projects.project_exists(project):
            raise HTTPException(404, "Unknown project")
        pr = projects.load_project(project)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    f = projects.project_dir(project) / projects.PROJECT_FILE
    sched = pr.defaults.get("scheduling")
    from hani2 import study_modes

    mode = study_modes.resolve_project(project)
    return {**pr.to_dict(), "path": str(pr.path) if pr.path else None, "yaml": f.read_text(encoding="utf-8") if f.exists() else "",
            "scheduling": dict(sched) if isinstance(sched, dict) else {},
            "study_mode_effective": mode.to_dict(), "editor": _editor_info(project),
            "errors": list(dict.fromkeys([*pr.errors, *mode.errors])),
            "studies": [_study_info(projects.StudyRef(project, s)) for s in projects.list_studies(project)]}


def _yaml_body(body: dict) -> dict:
    if "yaml" in body:
        import yaml

        try:
            data = yaml.safe_load(str(body["yaml"])) or {}
        except yaml.YAMLError as e:
            raise HTTPException(400, f"invalid YAML: {e}") from None
        if not isinstance(data, dict):
            raise HTTPException(400, "the YAML must be a mapping")
        return data
    return dict(body.get("data") or {})


#: keys the GET endpoints add that are not part of project.yaml / study.yaml (dropped on PUT, so a
#: client may send back what it read)
_READ_ONLY_KEYS = ("path", "legacy", "participants", "results_rows", "default", "links", "yaml", "studies",
                   "scheduling_effective", "study_mode_effective", "editor", "errors")


def _writable(data: dict, nested: str) -> dict:
    """``data`` as sent back by a client: without the read-only keys, and with a top-level
    ``scheduling`` winning over the copy the GET endpoints show under ``overrides`` / ``defaults``
    (an empty one removes the choice: every dimension is inherited)."""
    out = {k: v for k, v in data.items() if k not in _READ_ONLY_KEYS}
    inner = out.get(nested)
    if "scheduling" in out and isinstance(inner, dict) and "scheduling" in inner:
        out[nested] = {k: v for k, v in inner.items() if k != "scheduling"}
        if not out[nested]:
            out.pop(nested)
    if "scheduling" in out and not out["scheduling"]:
        out.pop("scheduling")  # ``scheduling: {}`` (or null): inherit every dimension
    return out


def _check_scores_change(project: str, study: str | None, data: dict, nested: str) -> None:
    """A ValueError when the ``scores`` / ``scores_enabled`` of a whole project.yaml
    (``nested="defaults"``) or study.yaml (``"overrides"``; ``study`` is ``None`` for a new one) being
    saved would add a problem (an unknown criterion, a missing direction, …)."""
    from hani2.evaluation import scores as S

    inner = data.get(nested) if isinstance(data.get(nested), dict) else {}
    layer = {**inner, **{k: data[k] for k in ("scores", "scores_enabled") if k in data}}
    p = S.change_problems(project, study, scores=layer.get("scores") or {}, enabled=layer.get("scores_enabled"),
                          side="project" if nested == "defaults" else "study")
    if p:
        raise ValueError("; ".join(p))


@app.put("/api/admin/projects/{project}")
def admin_put_project(project: str, body: dict = Body(...), _: str = Depends(require_admin)):
    """Create or replace ``project.yaml``: ``{"data": {...}}`` or ``{"yaml": "..."}``."""
    data = _yaml_body(body) if "yaml" in body else _writable(_yaml_body(body), "defaults")
    try:
        projects.check_name(project, "project")
        if data.get("kind", "none") not in projects.KINDS:
            raise HTTPException(400, f"kind must be one of {', '.join(projects.KINDS)}")
        projects.check_file_data(data, "defaults", project=project)
        _check_scores_change(project, None, data, "defaults")
        projects.write_yaml(projects.project_dir(project) / projects.PROJECT_FILE, data)
        (projects.project_dir(project) / "studies").mkdir(exist_ok=True)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"ok": True}


@app.get("/api/admin/projects/{project}/studies/{study}")
def admin_study(project: str, study: str, _: str = Depends(require_admin)):
    ref = _ref_or_404(project, study)
    if not projects.study_exists(ref):
        raise HTTPException(404, "Unknown study")
    f = projects.study_dir(ref) / projects.STUDY_FILE
    return {**_study_info(ref), "yaml": f.read_text(encoding="utf-8") if f.exists() else ""}


@app.put("/api/admin/projects/{project}/studies/{study}")
def admin_put_study(project: str, study: str, body: dict = Body(...), _: str = Depends(require_admin)):
    """Create or replace ``study.yaml`` (the project is created when missing)."""
    ref = _ref_or_404(project, study)
    data = _yaml_body(body) if "yaml" in body else _writable(_yaml_body(body), "overrides")
    if data.get("type", "prolific") not in projects.STUDY_TYPES:
        raise HTTPException(400, f"type must be one of {', '.join(projects.STUDY_TYPES)}")
    try:
        projects.check_file_data(data, "overrides", ref=ref)
        _check_scores_change(ref.project, ref.study if projects.study_exists(ref) else None, data, "overrides")
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if ref.project != projects.DEFAULT_PROJECT and not projects.project_dir(ref.project).is_dir():
        projects.create_project(ref.project)
    folder = projects.study_dir(ref)
    projects.write_yaml(folder / projects.STUDY_FILE, data)
    (folder / "results").mkdir(parents=True, exist_ok=True)
    return {"ok": True, "links": projects.participant_links(ref, projects.public_base_url())}


# --------------------------------------------------------------------------- #
# Groups (opponent and Assistant pools)                                        #
# --------------------------------------------------------------------------- #
def _group_kind(kind: str) -> str:
    from hani2 import groups

    try:
        return groups.check_kind(kind)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.get("/api/admin/groups")
def admin_groups(project: str | None = None, study: str | None = None, _: str = Depends(require_admin)):
    """Opponent and Assistant groups with members, source file and description:
    of a project (``?project=P``: its folder, its studies and the settings folder),
    else as a study resolves them (``?study=P/S``, default: the default study)."""
    from hani2 import groups

    try:
        if project is not None:
            if not projects.project_exists(project):
                raise HTTPException(404, "Unknown project")
            kw: dict[str, Any] = {"project": project}
        else:
            kw = {"ref": projects.parse_ref(study) if study else None}
        return {"project": project, "study": study,
                "opponent": groups.list_groups(groups.OPPONENT, **kw),
                "assistant": groups.list_groups(groups.ASSISTANT, **kw)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.get("/api/admin/projects/{project}/groups/{kind}/{key}")
def admin_get_group(project: str, kind: str, key: str, _: str = Depends(require_admin)):
    """A project's group file (``kind``: ``opponent(s)`` or ``assistant(s)``)."""
    from hani2 import groups

    k = _group_kind(kind)
    try:
        groups.check_key(key)
        f = groups.project_group_dir(project, k) / f"{key}.json"
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    g = groups.load_file(f, k, key, "project")
    if g is None:
        raise HTTPException(404, "Unknown group")
    return {**g.to_dict(), "data": json.loads(f.read_text(encoding="utf-8"))}


@app.put("/api/admin/projects/{project}/groups/{kind}/{key}")
def admin_put_group(project: str, kind: str, key: str, body: Any = Body(...), _: str = Depends(require_admin)):
    """Create or replace a project's group file: a list of specs, or
    ``{"description", "syspath", "agents"|"assistants", "assistant"}``."""
    from hani2 import groups

    k = _group_kind(kind)
    try:
        if not projects.project_exists(project):
            raise HTTPException(404, "Unknown project")
        f = groups.write_group(project, k, key, body.get("data", body) if isinstance(body, dict) and "data" in body else body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"ok": True, "path": str(f)}


@app.delete("/api/admin/projects/{project}/groups/{kind}/{key}")
def admin_delete_group(project: str, kind: str, key: str, _: str = Depends(require_admin)):
    from hani2 import groups

    k = _group_kind(kind)
    try:
        projects.check_name(project, "project")
        if not groups.delete_group(project, k, key):
            raise HTTPException(404, "Unknown group")
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"ok": True}


@app.get("/api/admin/projects/{project}/studies/{study}/assignments")
def admin_study_assignments(project: str, study: str, _: str = Depends(require_admin)):
    """The study's ``assignments.json`` (participant index and Assistant of each human)."""
    from hani2 import assignment

    ref = _ref_or_404(project, study)
    if not projects.study_exists(ref):
        raise HTTPException(404, "Unknown study")
    return assignment.read_assignments(ref)


@app.post("/api/admin/templates/preview")
def admin_template_preview(body: dict = Body(...), _: str = Depends(require_admin)):
    """Render a text for a layer: ``{"text": "...", "study": "P/S"}`` or ``{"kind": "consent", "study": "P/S"}``
    (``kind`` reads the effective file). ``"layer"`` (``settings`` | ``project:P`` | ``study:P/S``) previews
    as that layer: a study with its variables, a project with the project's only, settings with none.
    Returns the rendered text, the unknown placeholders and every variable with its value."""
    from hani2.admin_api import get_layer
    from hani2.layers import binding
    from hani2.templates import VARIABLES, project_variables, render_report, study_variables

    lay = get_layer(body.get("layer"), default=None) if body.get("layer") else None
    try:
        ref = projects.parse_ref(body["study"]) if body.get("study") else projects.current_study()
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if lay is None and ref is not None and not _study_allowed(ref):
        raise HTTPException(404, "Unknown study")
    if lay is not None:
        ref = lay.ref
    ctx = binding(lay) if lay is not None else projects.use_study(ref)
    with ctx:
        if "text" in body:
            text = str(body["text"])
        elif body.get("kind") in TEXT_FILES:
            text = read_settings_text(TEXT_FILES[body["kind"]], "")
        else:
            raise HTTPException(400, "give text or kind")
        if lay is not None and lay.kind == "project":
            vals = project_variables(lay.project)
        elif lay is not None and lay.kind == "settings":
            vals = study_variables(None)
        else:
            vals = study_variables(ref)
        rendered, unknown = render_report(text, vals)
    return {"rendered": rendered, "unknown": unknown, "variables": vals,
            "descriptions": VARIABLES, "study": str(ref) if ref else None, "layer": lay.id if lay else None}


@app.get("/api/admin/meta")
def admin_meta(_: str = Depends(require_admin)):
    from hani2 import scenario_store as store
    from hani2.agents import SELECTABLE_GROUPS
    from hani2.support_agent.autopilot import driver_options
    from hani2.support_agent.capabilities import CAPABILITY_INFO
    from hani2.tools.registry import tool_specs

    return {
        "opponent_groups": {k: list(v) for k, v in SELECTABLE_GROUPS.items()},
        "agent_groups": {k: list(v) for k, v in SELECTABLE_GROUPS.items()},  # old name
        "scenario_types": store.available_types(),
        "scenario_sets": __import__("hani2.scenario_sets", fromlist=["x"]).load_sets()[0],
        "scenario_set": __import__("hani2.scenario_sets", fromlist=["x"]).active_set(),
        "role_rules": store.ROLE_RULES,
        "scenarios": {t: store.list_scenarios(t) for t in store.available_types()},
        "tools": [dict(name=s.name, pane=s.pane, timing=s.timing, enabled=s.enabled, admin_only=s.admin_only,
                       guest=s.guest, at_front=s.at_front, description=s.cls.description) for s in tool_specs()],
        # the names project.yaml / study.yaml give a meaning (a "custom variable" must not take one)
        "setting_keys": {"project": sorted({*projects.DEFAULT_KEYS, *projects.PROJECT_FIELDS, "defaults", "scheduling"}),
                         "study": sorted({*projects.DEFAULT_KEYS, *projects.STUDY_FIELDS, "project", "overrides",
                                          "scheduling"})},
        "capabilities": {k: {"label": v[0], "description": v[1]} for k, v in CAPABILITY_INFO.items()},
        "autopilot_drivers": driver_options({"allowed_drivers": None}),
        "participant_settings": {k: {"label": v[0], "description": v[1]}
                                 for k, v in __import__("hani2.session", fromlist=["x"]).PARTICIPANT_SETTINGS.items()},
    }


def _df_records(df) -> list[dict]:
    from hani2.tools.ui import jsonable

    return [jsonable(r) for r in df.to_dict(orient="records")] if len(df) else []


@app.get("/api/admin/results")
def admin_results(_: str = Depends(require_admin)):
    from hani2.results import (DEFAULT_COLUMNS, leaderboard, leaderboard_by_type, read_all_results,
                               simulated_leaderboard)

    df = read_all_results()
    # simulated participants (mode: simulated) are never ranked with humans
    return {"columns": [str(c) for c in df.columns], "default_columns": DEFAULT_COLUMNS + ["user"],
            "rows": _df_records(df), "leaderboard": leaderboard(df),
            "leaderboard_by_type": leaderboard_by_type(df), "simulated": simulated_leaderboard(df)}


@app.get("/api/admin/results.csv")
def admin_results_csv(_: str = Depends(require_admin)):
    from hani2.results import read_all_results

    buf = io.StringIO()
    read_all_results().to_csv(buf, index=False)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=hani2_results.csv"})


@app.get("/api/admin/events")
def admin_events(user: str | None = None, session_id: str | None = None, types: str | None = None,
                 since: str | None = None, until: str | None = None, limit: int = 500, offset: int = 0,
                 _: str = Depends(require_admin)):
    return ev.query_events(user=user, session_id=session_id, event_types=[t for t in (types or "").split(",") if t],
                           since=since, until=until, limit=limit, offset=offset)


@app.get("/api/admin/events/summary")
def admin_event_summary(_: str = Depends(require_admin)):
    return ev.event_summary() | {"sessions": ev.query_sessions(200)}


@app.get("/api/admin/events.csv")
def admin_events_csv(_: str = Depends(require_admin)):
    import csv

    rows = ev.query_events(limit=1_000_000)
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=hani2_events.csv"})


# --------------------------------------------------------------------------- #
# Recordings: replay and evaluation (admin only — a recording holds every     #
# party's preferences)                                                         #
# --------------------------------------------------------------------------- #
def _rec_or_404(key: str):
    from hani2.recording import store as rstore

    try:
        return rstore.load(key)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None


@app.get("/api/replay/recordings")
def replay_list(all: bool = False, _: str = Depends(require_admin)):
    from hani2.recording import store as rstore

    return {"recordings": jsonable(rstore.list_recordings(include_empty=all)),
            "roots": [str(r) for r in rstore.roots()]}


@app.get("/api/replay/recording")
def replay_get(key: str, _: str = Depends(require_admin)):
    rec = _rec_or_404(key)
    return Response(json.dumps({"key": key, "header": rec.header, "events": rec.events}, allow_nan=False, default=str),
                    media_type="application/json")


@app.get("/api/replay/download")
def replay_download(key: str, _: str = Depends(require_admin)):
    from hani2.recording import store as rstore

    try:
        p = rstore.resolve(key)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return FileResponse(p, filename=p.name, media_type="application/octet-stream")


@app.post("/api/replay/upload")
async def replay_upload(request: Request, name: str = "upload.hrec", _: str = Depends(require_admin)):
    from hani2.recording import store as rstore

    data = await request.body()
    if len(data) > 200 * 1024 * 1024:
        raise HTTPException(413, "file too large")
    try:
        return {"key": rstore.save_upload(name, data)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@app.get("/api/replay/metrics")
def replay_metrics(_: str = Depends(require_admin)):
    from hani2.evaluation import available_metrics, llm_judge_status

    return {"metrics": available_metrics(), "llm": llm_judge_status()}


@app.get("/api/replay/metric-reference")
def replay_metric_reference(_: str = Depends(require_admin)):
    """What every metric and column measures and how it is calculated: notation,
    metrics (with formulas, details and dynamic columns), compare statistics,
    identifier columns and the figures (SVG)."""
    from hani2.evaluation import metric_reference

    return metric_reference()


@app.post("/api/replay/evaluate")
def replay_evaluate(body: dict = Body(...), _: str = Depends(require_admin)):
    """Evaluate recordings: ``{"keys": [...], "metrics": [names] | null, "llm": bool, "refresh": bool}``."""
    from hani2.evaluation import evaluate_keys

    keys = [str(k) for k in body.get("keys") or []]
    if not keys:
        raise HTTPException(400, "no recordings selected")
    return jsonable(evaluate_keys(keys, metrics=body.get("metrics"), use_llm=bool(body.get("llm")),
                                  refresh=bool(body.get("refresh")), options=body.get("options") or {}))


@app.post("/api/replay/compare")
def replay_compare(body: dict = Body(...), _: str = Depends(require_admin)):
    """Aggregate evaluated recordings by a field: ``{"keys", "metrics", "by", "llm"}``."""
    from hani2.evaluation import compare_keys

    keys = [str(k) for k in body.get("keys") or []]
    if not keys:
        raise HTTPException(400, "no recordings selected")
    return jsonable(compare_keys(keys, by=str(body.get("by") or "opponent"), metrics=body.get("metrics"),
                                 use_llm=bool(body.get("llm")), options=body.get("options") or {}))


def _reliability_body(rep):
    """A judge reliability report from a request (the report itself, never a server path)."""
    if rep in (None, "", {}):
        return None
    if not isinstance(rep, dict):
        raise HTTPException(400, "reliability is a judge reliability report (the JSON object), not a path")
    return rep


@app.post("/api/replay/leaderboard")
def replay_leaderboard(body: dict = Body(...), _: str = Depends(require_admin)):
    """Leaderboards of a competition track: ``{"keys", "track": "han"|"hi", "board": "outcome"|"interaction"|null,
    "metrics", "llm", "options", "success", "success_threshold", "relative", "min_coverage", "practice",
    "reliability" (a judge reliability report), "official", "judge" (provider:model), "stratum" (hi: combined, solo,
    paired; han: alone, vs_team, both), "ci_unit" (participant or match), "head_to_head" (hi: the Bradley–Terry view)}``;
    without ``board`` both boards (``{"boards": {"outcome": ..., "interaction": ...}}``)."""
    from hani2.evaluation import TRACKS, evaluate_keys, leaderboard

    keys = [str(k) for k in body.get("keys") or []]
    if not keys:
        raise HTTPException(400, "no recordings selected")
    track = str(body.get("track") or "hi")
    if track not in TRACKS:
        raise HTTPException(400, f"unknown track {track!r}")
    boards = [str(body["board"])] if body.get("board") else ["outcome", "interaction"]
    if any(b not in ("outcome", "interaction") for b in boards):
        raise HTTPException(400, "board is outcome or interaction")
    opts = body.get("options") or {}
    judge = str(body["judge"]) if body.get("judge") else None
    try:
        ev = evaluate_keys(keys, metrics=body.get("metrics"), use_llm=bool(body.get("llm")) or judge is not None,
                           options=opts, judge=judge)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    kw = dict(options=opts, success=body.get("success") or None, success_threshold=body.get("success_threshold"),
              relative=bool(body.get("relative")),
              min_coverage=0.5 if body.get("min_coverage") is None else float(body["min_coverage"]),
              include_practice=bool(body.get("practice")), reliability=_reliability_body(body.get("reliability")),
              official=bool(body.get("official")), stratum=str(body["stratum"]) if body.get("stratum") else None,
              ci_unit=str(body.get("ci_unit") or "participant"), head_to_head=bool(body.get("head_to_head")))
    try:
        out = {b: leaderboard(ev["rows"], track, b, **kw) for b in boards}
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e)) from None
    return jsonable({"track": track, "boards": out, "errors": ev["errors"]})


# -- leaderboards of projects and studies (hani2.evaluation.boards): the pages, the admin and a website --------
def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization") or ""
    return h[7:].strip() if h[:7].lower() == "bearer " else None


def _board_viewer(request: Request, project: str, study: str | None) -> bool:
    """Who reads a board: ``True`` for an admin (every enabled score and switch value), ``False`` for an
    end user or a website with an API token; 401/403/404 when the board's ``visibility`` refuses."""
    from hani2.evaluation import boards

    try:
        vis = boards.visibility(project, study)
    except boards.BoardNotFound as e:
        raise HTTPException(404, str(e)) from None
    user = current_user(request)
    if user and auth.is_admin_user(user):
        return True
    tok = _bearer(request)
    if tok is not None:
        # an ``admins`` board needs the scope leaderboard:admin; the others leaderboard:read (or admin)
        scope = sso.SCOPE_LEADERBOARD_ADMIN if vis == "admins" else sso.SCOPE_LEADERBOARD
        try:
            sso.verify_api_token(tok, scope, root_path=root_path())
        except sso.APITokenError as e:
            raise HTTPException(e.status, f"API token refused ({e.code}): {e}"
                                + (" (this board has visibility: admins)" if e.code == "scope" and vis == "admins" else ""),
                                headers={"WWW-Authenticate": "Bearer"} if e.status == 401 else None) from None
        return False
    if vis == "public":
        return False
    if not user:
        raise HTTPException(401, "Sign in, or send an API token (Authorization: Bearer …)",
                            headers={"WWW-Authenticate": "Bearer"})
    if vis == "admins":
        raise HTTPException(403, "This board is for admins only")
    gstudy = sso.guest_study(user)
    if gstudy is not None and gstudy != f"{project}/{study}":
        raise HTTPException(403, "A guest may see only the board of the study they were invited to")
    return False


def _board_response(request: Request, project: str, study: str | None) -> Response:
    from hani2.evaluation import boards

    admin = _board_viewer(request, project, study)
    q = dict(request.query_params)
    # ``view=user``: the board exactly as end users get it (the end-user pages send it, so an admin who
    # opens them sees what everyone else sees); it only ever takes options away
    view = q.pop("view", None)
    if view not in (None, "", "user"):
        raise HTTPException(400, f"view {view!r} is not known; use view=user or leave it out")
    if view == "user":
        admin = False
    try:
        out = boards.board(project, study, q, admin=admin)
    except boards.BoardError as e:
        raise HTTPException(400, str(e)) from None
    except boards.BoardNotFound as e:
        raise HTTPException(404, str(e)) from None
    etag = f'"{out["data_version"]}|{boards.query_key(out["query"], admin)}"'
    headers = {"Cache-Control": "no-cache", "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(jsonable(out), headers=headers)


@app.get("/api/v1/projects/{project}/leaderboard")
def api_project_leaderboard(project: str, request: Request):
    """The project board (schema ``hani2.leaderboard/2``): ``?sort=&games=&stratum=&window=``, within the
    options the project allows (else 400). Public boards need nothing; others a signed-in user or an
    API token (``Authorization: Bearer <JWT>``, see :func:`hani2.sso.verify_api_token`)."""
    return _board_response(request, project, None)


@app.get("/api/v1/projects/{project}/studies/{study}/leaderboard")
def api_study_leaderboard(project: str, study: str, request: Request):
    """One study's board (the study's ``leaderboard`` overrides the project's, key by key)."""
    return _board_response(request, project, study)


@app.get("/api/v1/leaderboards")
def api_leaderboards(request: Request):
    """Every project that has a board, with its track, year and visibility. Without a signed-in user or
    an API token, only the public boards are listed; ``admins`` boards only to an admin or to an API
    token with the scope ``leaderboard:admin``."""
    from hani2.evaluation import boards

    user = current_user(request)
    full = bool(user) and sso.guest_study(user) is None  # a guest sees the public boards only
    admins = bool(user) and auth.is_admin_user(user)
    tok = _bearer(request)
    if tok is not None:
        try:
            claims = sso.verify_api_token(tok, root_path=root_path())
        except sso.APITokenError as e:
            raise HTTPException(e.status, f"API token refused ({e.code}): {e}") from None
        full = True
        admins = admins or sso.token_has_scope(claims, sso.SCOPE_LEADERBOARD_ADMIN)
    items = boards.list_boards()
    if not (full and admins):
        def shown(v: str) -> bool:
            return v == "public" if not full else v != "admins"

        items = [dict(b, studies=[x for x in b["studies"] if shown(x["visibility"])])
                 for b in items if shown(b["visibility"]) or any(shown(x["visibility"]) for x in b["studies"])]
    return {"schema": "hani2.leaderboards/1", "boards": items}


@app.get("/api/admin/users")
def admin_users(_: str = Depends(require_admin)):
    meta = auth.load_users_meta()
    return [dict(username=u, is_admin=auth.is_admin_user(u), **{k: v for k, v in meta.get(u, {}).items()
                                                                if k in ("email", "full_name", "consented", "created", "oauth", "role", "sso", "sso_admin")})
            for u in sorted(auth.load_users())]


@app.post("/api/admin/users")
def admin_create_user(body: dict = Body(...), _: str = Depends(require_admin)):
    err = auth.validate_new_user(str(body.get("username", "")), str(body.get("password", "")))
    if err:
        raise HTTPException(400, err)
    meta = {k: body[k] for k in ("email", "full_name") if body.get(k)}
    if body.get("is_admin"):
        meta["role"] = "admin"
    auth.create_user(str(body["username"]).strip(), str(body["password"]), consented=True, **meta)
    return {"ok": True}


@app.patch("/api/admin/users/{username}")
def admin_update_user(username: str, body: dict = Body(...), me: str = Depends(require_admin)):
    if not auth.user_exists(username):
        raise HTTPException(404)
    if body.get("password"):
        auth.set_password(username, str(body["password"]))
    if "is_admin" in body and username != "admin":
        auth.update_meta(username, role="admin" if body["is_admin"] else "user")
        if not body["is_admin"]:
            sso.drop_admin_grant(username, by=me)  # "Remove admin" also ends a website's admin-claim grant
    return {"ok": True}


@app.delete("/api/admin/users/{username}")
def admin_delete_user(username: str, me: str = Depends(require_admin)):
    if username in (me, "admin"):
        raise HTTPException(400, "You cannot delete this user")
    return {"ok": auth.delete_user(username)}


@app.get("/api/admin/sessions")
def admin_sessions(_: str = Depends(require_admin)):
    out = []
    for sid, s in list(hub.sessions.items()):
        out.append(dict(sid=sid, user=s.user, mode=s.mode, phase=s.phase, round=s.round_number,
                        study=str(s.study_ref) if getattr(s, "study_ref", None) else None,
                        connections=hub.n_connections(sid), idle=round(time.time() - s.last_seen),
                        opponent=s.ss.get("last_partner_type"), opponent_group=s.ss.get("opponent_group", ""),
                        support_agent=type(s.support_agent).__name__ if s.support_agent is not None else "none",
                        **s.assistant_attribution(), scenario=s._scenario_name()))
    return out


@app.get("/api/admin/llm/status")
def admin_llm_status(_: str = Depends(require_admin)):
    from hani2.llm_service import get_llm_status

    return get_llm_status()


# --------------------------------------------------------------------------- #
# The web app                                                                  #
# --------------------------------------------------------------------------- #
_COMPRESSIBLE = (".js", ".mjs", ".css", ".svg", ".json", ".map", ".txt", ".html")


class _Assets(StaticFiles):
    """The built app's files: gzip-compressed (once, then kept in memory) and cached for a year.

    Their names carry a content hash, so a browser never has to ask for them again,
    and compression shrinks the charting library from ~4.8 MB to ~1.5 MB.
    """

    def __init__(self, *args: Any, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self._gz: dict[str, tuple[float, bytes]] = {}

    def _gzipped(self, path: str, mtime: float) -> bytes:
        hit = self._gz.get(path)
        if hit is None or hit[0] != mtime:
            import gzip

            hit = (mtime, gzip.compress(Path(path).read_bytes(), compresslevel=9, mtime=0))
            self._gz[path] = hit
        return hit[1]

    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        if not isinstance(response, FileResponse) or response.status_code != 200:
            return response
        file = str(response.path)
        if not file.endswith(_COMPRESSIBLE):
            return response
        response.headers["Vary"] = "Accept-Encoding"
        accept = dict(scope.get("headers") or []).get(b"accept-encoding", b"")
        if b"gzip" not in accept:
            return response
        st = os.stat(file)
        body = await asyncio.to_thread(self._gzipped, file, st.st_mtime)
        headers = {k: v for k, v in response.headers.items() if k.lower() not in ("content-length", "accept-ranges")}
        headers["Content-Encoding"] = "gzip"
        return Response(body, headers=headers, media_type=response.media_type)


if (WEB_DIR / "assets").is_dir():
    app.mount("/assets", _Assets(directory=WEB_DIR / "assets"), name="assets")


def _study_allowed(ref: "projects.StudyRef | None") -> bool:
    """A study named in a URL must exist (the process default study may be created on first use)."""
    return ref is None or ref == projects.default_study() or projects.study_exists(ref)


_STUDY_PATH = __import__("re").compile(r"^/s/([^/]+)/([^/]+)(/.*)?$")
#: ``/s/<project>/leaderboard``: the project board's page (not a study named "leaderboard")
_PROJECT_BOARD_PAGE = __import__("re").compile(r"^/s/[^/]+/leaderboard/?$")


class _StripPrefix:
    """Accept requests with or without the mount prefix (HTTP and WebSocket), and bind
    the study named by ``/s/<project>/<study>/...`` or ``?study=project/study``."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            await self.inner(scope, receive, send)
            return
        base = root_path()
        path = scope.get("path", "")
        if base and (path == base or path.startswith(base + "/")):
            scope = dict(scope, path=path[len(base):] or "/")
            if "raw_path" in scope and scope["raw_path"]:
                scope["raw_path"] = scope["raw_path"][len(base):] or b"/"
        ref, named = None, False
        if _PROJECT_BOARD_PAGE.match(scope.get("path", "")):
            # the project board's page /s/<project>/leaderboard: the app at the root base (no study)
            await self.inner(scope, receive, send)
            return
        m = _STUDY_PATH.match(scope.get("path", ""))
        try:
            if m:
                named = True
                ref = projects.StudyRef(projects.check_name(m.group(1), "project"), projects.check_name(m.group(2), "study"))
                rest = m.group(3) or "/"
                scope = dict(scope, path=rest, raw_path=rest.encode())
                scope["state"] = {**(scope.get("state") or {}), "hani2_study_path": True}
            else:
                from urllib.parse import parse_qs

                q = parse_qs((scope.get("query_string") or b"").decode(errors="replace"))
                if q.get("study") and q["study"][0].strip():
                    named = True
                    ref = projects.parse_ref(q["study"][0])
        except ValueError:
            ref = None
        if named and (ref is None or not _study_allowed(ref)):
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 4404})
                return
            await JSONResponse({"detail": "Unknown study"}, status_code=404)(scope, receive, send)
            return
        if not named:
            await self.inner(scope, receive, send)
            return
        scope["state"] = {**(scope.get("state") or {}), "hani2_study": str(ref)}
        with projects.use_study(ref):
            await self.inner(scope, receive, send)


def root_path() -> str:
    """Sub-path this server is mounted under behind a reverse proxy ('' at a root)."""
    v = os.environ.get("HANI2_ROOT_PATH", "").strip().strip("/")
    return f"/{v}" if v else ""


def _index_html(text: str, study_prefix: str = "") -> str:
    """The app's page: assets under the mount path, and the app's own base (mount path plus
    the study's ``/s/<project>/<study>``, so every page and API call stays in the study)."""
    base = root_path()
    app_base = base + study_prefix
    if not app_base:
        return text
    text = text.replace('"/assets/', f'"{base}/assets/').replace('"/favicon.svg"', f'"{base}/favicon.svg"')
    return text.replace("<head>", f'<head>\n    <meta name="hani2-base" content="{app_base}" />', 1)


from hani2.admin_api import router as _admin_router  # noqa: E402

app.include_router(_admin_router)  # before the catch-all page route below
app.include_router(__import__("hani2.admin_hosted", fromlist=["router"]).router)  # self-hosted agents


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str, request: Request):
    if path.startswith("api/"):
        raise HTTPException(404)
    in_path = bool(getattr(request.state, "hani2_study_path", False))
    study_prefix = projects.study_url_prefix(projects.current_study()) if in_path else ""
    if not in_path and request.query_params.get("study"):
        # a page asked for with ?study=P/S moves to /s/P/S/... so the whole app stays in that study
        ref = projects.current_study()
        rest = [(k, v) for k, v in request.query_params.multi_items() if k != "study"]
        url = f"{root_path()}{projects.study_url_prefix(ref)}/{path}" + (f"?{urlencode(rest)}" if rest else "")
        return RedirectResponse(url, status_code=307)
    f = (WEB_DIR / path).resolve()
    if path and f.is_file() and WEB_DIR.resolve() in f.parents:
        return FileResponse(f)
    index = WEB_DIR / "index.html"
    if index.exists():
        return HTMLResponse(_index_html(index.read_text(encoding="utf-8"), study_prefix), headers={"Cache-Control": "no-cache"})
    return HTMLResponse(
        "<h1>HANI2</h1><p>The web interface has not been built. Run <code>npm run build</code> in "
        "<code>frontend/</code>.</p>",
        status_code=503,
    )


app.add_middleware(_StripPrefix)
