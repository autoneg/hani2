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

from hani2 import __version__, agents, auth, projects
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
        "allow_registration": bool(env["auth"].get("allow_registration", True)) and auth_mode() != "none",
        "enforce_consent": bool(env["auth"].get("enforce_consent", False)),
        "playground": bool((env.get("playground") or {}).get("enabled", True)),
        "experiment": os.environ.get("HANI2_EXPERIMENT") or None,
        "project": ref.project if ref else projects.DEFAULT_PROJECT,
        "study": None if ref is None else {"project": ref.project, "name": ref.study, "type": st.type if st else None,
                                           "title": vals.get("study_title"), "path": projects.study_url_prefix(ref)},
        "docs_url": env.get("docs_url", "https://autoneg.github.io/hani2/"),
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
        else:
            gid = _guest_id(request, response)
            # each browser gets its own results folder (no concurrent writes to one file)
            user, display = f"guest_{gid}", "Guest"
            sid = f"guest:{gid}"
            if current_user(request) and is_admin:
                display = current_user(request)  # type: ignore
        is_admin = False if pid else is_admin
    admin_mode = is_admin or (_truthy(query.get("admin", "")) and not pid)
    # An admin can negotiate exactly as a participant would (?as_participant=1): no admin controls, no
    # opponent type, no scenario/opponent pickers. It is a separate session and results folder, and it
    # is never counted as a study participant.
    viewer = None
    if is_admin and _truthy(query.get("as_participant", "")):
        viewer, is_admin, admin_mode = user, False, False
        user, sid = f"{user}~participant", f"{sid}~participant"
    sid = _session_sid(sid, ref)
    s = hub.get(sid)
    if s is not None and body.get("fresh"):
        hub.remove(sid)
        s = None
    if s is None:
        s = NegotiationSession(sid, user, mode=mode, is_admin=is_admin, admin_mode=admin_mode, query=query,
                               hub=hub, user_agent=ua, display_name=display, study=ref, admin_viewer=viewer)
        hub.add(s)
        s.load()
    else:
        s.query.update(query)
        s.refresh_assistant(getattr(s, "round_plan", None))  # a new ?group= may name another Assistant
    s.last_seen = time.time()
    return {"sid": sid}


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
            sa.messages = sa.messages[:1]
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
    # The main-app session belongs to a logged-in user: check the cookie.
    if sid.startswith("main:"):
        user = None
        tok = websocket.cookies.get(AUTH_COOKIE)
        if tok:
            try:
                user = _serializer().loads(tok, max_age=MAX_AGE)
            except BadSignature:
                user = None
        if auth_mode() != "none" and user != (getattr(s, "admin_viewer", None) or s.user):
            await websocket.close(code=4401)
            return
    elif sid.startswith("guest:"):
        if websocket.cookies.get(GUEST_COOKIE) != sid.split("::", 1)[0].split(":", 1)[1]:
            await websocket.close(code=4401)
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
            return json.loads(f.read_text()) if f.exists() else {}
        except json.JSONDecodeError:
            raise HTTPException(409, f"{f.name} in this layer is not valid JSON") from None
    f = folder / TEXT_FILES[kind]
    return {"text": f.read_text() if f.exists() else "", "exists": f.exists(),
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


def _study_info(ref: "projects.StudyRef") -> dict:
    from hani2 import scheduling

    st = projects.load_study(ref)
    results = projects.study_dir(ref) / "results"
    files = list(results.glob("*/results.csv")) if results.is_dir() else []
    effective, _, sched_errors = scheduling.resolve(ref)
    return {**st.to_dict(), "path": str(st.path), "legacy": st.legacy, "participants": len(files),
            "results_rows": _count_rows(files),
            "default": ref == projects.default_study(),
            # the study's own choice (as in study.yaml), and what it uses (study, then project, then defaults)
            "scheduling": dict(st.overrides.get("scheduling") or {}) if isinstance(st.overrides.get("scheduling"), dict) else {},
            "scheduling_effective": effective,
            "errors": list(dict.fromkeys([*st.errors, *sched_errors])),
            "links": projects.participant_links(ref, projects.public_base_url())}


@app.get("/api/admin/scheduling-methods")
def admin_scheduling_methods(_: str = Depends(require_admin)):
    """The scheduling methods of each dimension (key, title, summary, Markdown details) and the defaults."""
    from hani2 import scheduling

    return scheduling.api_payload()


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
    return {**pr.to_dict(), "path": str(pr.path) if pr.path else None, "yaml": f.read_text() if f.exists() else "",
            "scheduling": dict(sched) if isinstance(sched, dict) else {}, "errors": list(pr.errors),
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
                   "scheduling_effective", "errors")


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


@app.put("/api/admin/projects/{project}")
def admin_put_project(project: str, body: dict = Body(...), _: str = Depends(require_admin)):
    """Create or replace ``project.yaml``: ``{"data": {...}}`` or ``{"yaml": "..."}``."""
    data = _yaml_body(body) if "yaml" in body else _writable(_yaml_body(body), "defaults")
    try:
        projects.check_name(project, "project")
        if data.get("kind", "none") not in projects.KINDS:
            raise HTTPException(400, f"kind must be one of {', '.join(projects.KINDS)}")
        projects.check_file_data(data, "defaults")
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
    return {**_study_info(ref), "yaml": f.read_text() if f.exists() else ""}


@app.put("/api/admin/projects/{project}/studies/{study}")
def admin_put_study(project: str, study: str, body: dict = Body(...), _: str = Depends(require_admin)):
    """Create or replace ``study.yaml`` (the project is created when missing)."""
    ref = _ref_or_404(project, study)
    data = _yaml_body(body) if "yaml" in body else _writable(_yaml_body(body), "overrides")
    if data.get("type", "prolific") not in projects.STUDY_TYPES:
        raise HTTPException(400, f"type must be one of {', '.join(projects.STUDY_TYPES)}")
    try:
        projects.check_file_data(data, "overrides")
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
    return {**g.to_dict(), "data": json.loads(f.read_text())}


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
                       guest=s.guest, description=s.cls.description) for s in tool_specs()],
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
    "reliability" (a judge reliability report), "official", "judge" (provider:model)}``;
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
              official=bool(body.get("official")))
    try:
        out = {b: leaderboard(ev["rows"], track, b, **kw) for b in boards}
    except (ValueError, OSError) as e:
        raise HTTPException(400, str(e)) from None
    return jsonable({"track": track, "boards": out, "errors": ev["errors"]})


@app.get("/api/admin/users")
def admin_users(_: str = Depends(require_admin)):
    meta = auth.load_users_meta()
    return [dict(username=u, is_admin=auth.is_admin_user(u), **{k: v for k, v in meta.get(u, {}).items()
                                                                if k in ("email", "full_name", "consented", "created", "oauth", "role")})
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
def admin_update_user(username: str, body: dict = Body(...), _: str = Depends(require_admin)):
    if not auth.user_exists(username):
        raise HTTPException(404)
    if body.get("password"):
        auth.set_password(username, str(body["password"]))
    if "is_admin" in body and username != "admin":
        auth.update_meta(username, role="admin" if body["is_admin"] else "user")
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
        return HTMLResponse(_index_html(index.read_text(), study_prefix), headers={"Cache-Control": "no-cache"})
    return HTMLResponse(
        "<h1>HANI2</h1><p>The web interface has not been built. Run <code>npm run build</code> in "
        "<code>frontend/</code>.</p>",
        status_code=503,
    )


app.add_middleware(_StripPrefix)
