"""The HANI2 web server (FastAPI).

* ``/`` … the single-page web app (shipped pre-built inside the package)
* ``/api/...`` the REST API (auth, admin, configuration)
* ``/api/ws/{sid}`` the live negotiation channel (WebSocket)
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

from hani2 import __version__, auth
from hani2 import events as ev
from hani2.config import get_env, load_env, read_settings_text, save_json_settings, settings_dir
from hani2.hub import Hub
from hani2.session import NegotiationSession

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
    hub.attach_loop(asyncio.get_running_loop())
    auth.ensure_default_users()
    try:
        from hani2.agents import _prime_group_syspaths

        _prime_group_syspaths()
    except Exception:
        pass
    try:
        from hani2.ollama_fallback import install_ollama_local_fallback

        install_ollama_local_fallback()
    except Exception:
        pass

    async def _gc():
        while True:
            await asyncio.sleep(600)
            hub.gc()

    task = asyncio.create_task(_gc())
    yield
    task.cancel()


app = FastAPI(title="HANI2", version=__version__, lifespan=lifespan)


# --------------------------------------------------------------------------- #
# Public configuration                                                         #
# --------------------------------------------------------------------------- #
@app.get("/api/config")
def api_config(request: Request):
    env = load_env()
    return {
        "title": env.get("title", "HANI2"),
        "subtitle": env.get("subtitle", ""),
        "version": __version__,
        "auth_mode": auth_mode(),
        "oauth_providers": list(oauth_providers()),
        "allow_registration": bool(env["auth"].get("allow_registration", True)) and auth_mode() != "none",
        "enforce_consent": bool(env["auth"].get("enforce_consent", False)),
        "playground": bool((env.get("playground") or {}).get("enabled", True)),
        "experiment": os.environ.get("HANI2_EXPERIMENT") or None,
        "docs_url": env.get("docs_url", "https://autoneg.github.io/hani2/"),
    }


@app.get("/api/announcements")
def api_announcements(mode: str = "main"):
    return {"markdown": read_settings_text("announcements.md", "")}


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
        "consented": auth.get_user_consent(u),
        "needs_consent": bool(get_env("auth.enforce_consent", False)) and not auth.get_user_consent(u)
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
    meta = {"email": email, "full_name": str(body.get("full_name", "")).strip()}
    if body.get("consent"):
        meta.update(consented=True, consent_date=time.strftime("%Y-%m-%dT%H:%M:%S"))
    auth.create_user(username, password, **meta)
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
    return {"markdown": read_settings_text("consent.md", "")}


@app.post("/api/consent")
def api_consent(user: str = Depends(require_user), body: dict = Body(...)):
    if not body.get("agree") or not str(body.get("full_name", "")).strip():
        raise HTTPException(400, "Please agree and sign with your full name")
    auth.set_user_consent(user, True, full_name=str(body["full_name"]).strip())
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
        return RedirectResponse("/login?error=oauth_state")
    try:
        data = dict(client_id=p["key"], client_secret=p["secret"], code=code,
                    redirect_uri=_redirect_uri(request, provider))
        if provider == "google":
            data["grant_type"] = "authorization_code"
        tok = httpx.post(ep["token"], data=data, headers={"Accept": "application/json"}, timeout=15).json()
        access = tok.get("access_token")
        if not access:
            return RedirectResponse("/login?error=oauth_token")
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
            username = f"g_{(email or info.get('sub', 'user')).split('@')[0]}"
            name = info.get("name") or username
    except Exception:
        traceback.print_exc()
        return RedirectResponse("/login?error=oauth_failed")
    if not auth.user_exists(username):
        auth.create_user(username, None, email=email or "", full_name=name or "", oauth=provider)
    else:
        auth.update_meta(username, email=email or "", oauth=provider)
    r = RedirectResponse("/app")
    _set_auth(r, username)
    ev.log_event(None, ev.EventType.LOGIN, user=username, value={"oauth": provider})
    return r


# --------------------------------------------------------------------------- #
# Sessions                                                                     #
# --------------------------------------------------------------------------- #
def _truthy(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@app.post("/api/session")
def api_session(request: Request, response: Response, body: dict = Body(default={})):
    mode = "guest" if body.get("mode") == "guest" else "main"
    query = {str(k): v for k, v in (body.get("query") or {}).items()}
    pid = query.get("PROLIFIC_PID") or query.get("prolific_pid")
    ua = request.headers.get("user-agent", "")
    user = current_user(request)
    is_admin = auth.is_admin_user(user)
    if mode == "main":
        if auth_mode() == "none":
            gid = request.cookies.get(GUEST_COOKIE) or uuid.uuid4().hex[:12]
            response.set_cookie(GUEST_COOKIE, gid, max_age=MAX_AGE, samesite="lax")
            user = user or f"user_{gid}"
        if not user:
            raise HTTPException(401, "Not logged in")
        if get_env("auth.enforce_consent", False) and not auth.get_user_consent(user) and not is_admin:
            raise HTTPException(403, "consent_required")
        sid = f"main:{user}"
        display = auth.get_meta(user).get("full_name") or user
    else:
        if not (get_env("playground.enabled", True) or pid):
            raise HTTPException(403, "The playground is disabled")
        if pid:
            pid = "".join(c for c in str(pid) if c.isalnum() or c in "-_")[:64]
            user, display = f"prolific_{pid}", "Participant"
            sid = f"prolific:{pid}"
        else:
            gid = request.cookies.get(GUEST_COOKIE) or uuid.uuid4().hex[:12]
            response.set_cookie(GUEST_COOKIE, gid, max_age=MAX_AGE, samesite="lax")
            # each browser gets its own results folder (no concurrent writes to one file)
            user, display = f"guest_{gid}", "Guest"
            sid = f"guest:{gid}"
            if current_user(request) and is_admin:
                display = current_user(request)  # type: ignore
        is_admin = False if pid else is_admin
    admin_mode = is_admin or (_truthy(query.get("admin", "")) and not pid)
    s = hub.get(sid)
    if s is not None and body.get("fresh"):
        hub.remove(sid)
        s = None
    if s is None:
        s = NegotiationSession(sid, user, mode=mode, is_admin=is_admin, admin_mode=admin_mode, query=query,
                               hub=hub, user_agent=ua, display_name=display)
        hub.add(s)
        s.load()
    else:
        s.query.update(query)
    s.last_seen = time.time()
    return {"sid": sid}


def _dispatch(s: NegotiationSession, msg: dict[str, Any]) -> Any:
    t = msg.get("type")
    if t == "load":
        return s.load(msg.get("scenario_type"), msg.get("name"))
    if t == "start":
        return s.start()
    if t == "draft":
        return s.set_draft(msg.get("values") or {})
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
    if t == "pref":
        return s.set_pref(str(msg.get("key")), msg.get("value"))
    if t == "layout":
        return s.set_layout(**{k: msg[k] for k in ("view", "sizes", "collapsed") if k in msg})
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
        s.next_opponent = str(msg.get("spec") or "")
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
        if auth_mode() != "none" and user != s.user:
            await websocket.close(code=4401)
            return
    elif sid.startswith("guest:"):
        if websocket.cookies.get(GUEST_COOKIE) != sid.split(":", 1)[1]:
            await websocket.close(code=4401)
            return
    await websocket.accept()
    hub.connect(sid, websocket)
    loop = asyncio.get_running_loop()
    try:
        snap = await loop.run_in_executor(None, s.snapshot)
        from hani2.hub import _dumps

        await websocket.send_text(_dumps({"type": "state", "state": snap}))
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
SETTINGS_KINDS = {
    "env": ("env.json", lambda: load_env()),
    "llm": ("llm_settings.json", lambda: __import__("hani2.config", fromlist=["x"]).load_llm_settings()),
    "support_agent": ("support_agent_settings.json",
                      lambda: __import__("hani2.support_agent.settings", fromlist=["x"]).load_support_agent_settings()),
    "autopilot": ("autopilot_settings.json",
                  lambda: __import__("hani2.support_agent.autopilot", fromlist=["x"]).load_autopilot_settings()),
}
TEXT_FILES = {"consent": "consent.md", "announcements": "announcements.md", "scenario_order": "scenario_order.txt"}


@app.get("/api/admin/settings/{kind}")
def admin_get_settings(kind: str, _: str = Depends(require_admin)):
    if kind in SETTINGS_KINDS:
        return SETTINGS_KINDS[kind][1]()
    if kind in TEXT_FILES:
        return {"text": read_settings_text(TEXT_FILES[kind], "")}
    raise HTTPException(404)


@app.put("/api/admin/settings/{kind}")
def admin_put_settings(kind: str, body: dict = Body(...), _: str = Depends(require_admin)):
    if kind in SETTINGS_KINDS:
        save_json_settings(SETTINGS_KINDS[kind][0], body)
        return {"ok": True}
    if kind in TEXT_FILES:
        p = settings_dir() / TEXT_FILES[kind]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(body.get("text", "")))
        return {"ok": True}
    raise HTTPException(404)


@app.get("/api/admin/meta")
def admin_meta(_: str = Depends(require_admin)):
    from hani2 import scenario_store as store
    from hani2.agents import SELECTABLE_GROUPS
    from hani2.support_agent.autopilot import driver_options
    from hani2.support_agent.capabilities import CAPABILITY_INFO
    from hani2.tools.registry import tool_specs

    return {
        "agent_groups": {k: list(v) for k, v in SELECTABLE_GROUPS.items()},
        "scenario_types": store.available_types(),
        "scenarios": {t: store.list_scenarios(t) for t in store.available_types()},
        "tools": [dict(name=s.name, pane=s.pane, timing=s.timing, enabled=s.enabled, admin_only=s.admin_only,
                       guest=s.guest, description=s.cls.description) for s in tool_specs()],
        "capabilities": {k: {"label": v[0], "description": v[1]} for k, v in CAPABILITY_INFO.items()},
        "autopilot_drivers": driver_options({"allowed_drivers": None}),
    }


def _df_records(df) -> list[dict]:
    from hani2.tools.ui import jsonable

    return [jsonable(r) for r in df.to_dict(orient="records")] if len(df) else []


@app.get("/api/admin/results")
def admin_results(_: str = Depends(require_admin)):
    from hani2.results import DEFAULT_COLUMNS, leaderboard, read_all_results

    df = read_all_results()
    return {"columns": [str(c) for c in df.columns], "default_columns": DEFAULT_COLUMNS + ["user"],
            "rows": _df_records(df), "leaderboard": leaderboard(df)}


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
                        connections=hub.n_connections(sid), idle=round(time.time() - s.last_seen),
                        partner=s.ss.get("last_partner_type"), scenario=s._scenario_name()))
    return out


@app.get("/api/admin/llm/status")
def admin_llm_status(_: str = Depends(require_admin)):
    from hani2.llm_service import get_llm_status

    return get_llm_status()


# --------------------------------------------------------------------------- #
# The web app                                                                  #
# --------------------------------------------------------------------------- #
if (WEB_DIR / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=WEB_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    f = (WEB_DIR / path).resolve()
    if path and f.is_file() and WEB_DIR.resolve() in f.parents:
        return FileResponse(f)
    index = WEB_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text(), headers={"Cache-Control": "no-cache"})
    return HTMLResponse(
        "<h1>HANI2</h1><p>The web interface has not been built. Run <code>npm run build</code> in "
        "<code>frontend/</code>.</p>",
        status_code=503,
    )
