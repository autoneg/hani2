"""Admin API of the library (see docs/reference/library-api.md and :mod:`hani2.library`).

Every route is admin-only and lives under ``/api/admin/library``. ``?layer=``
chooses where to read from and write to: ``settings`` (default),
``project:<P>`` or ``study:<P>/<S>``.
"""

from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile

from hani2 import library

#: largest upload accepted (bytes)
MAX_UPLOAD = 100 * 1024 * 1024


def _admin(request: Request) -> str:
    from hani2.server import require_admin

    return require_admin(request)


router = APIRouter(prefix="/api/admin/library", dependencies=[Depends(_admin)], tags=["library"])


def _call(fn: Callable[..., Any], *a: Any, **kw: Any) -> Any:
    try:
        return fn(*a, **kw)
    except library.LibraryError as e:
        raise HTTPException(e.status, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


def _kind(kind: str) -> str:
    return _call(library.check_kind, kind)


@router.get("")
def kinds() -> dict[str, Any]:
    """The kinds and the layer syntax."""
    return {"kinds": list(library.KINDS), "layers": ["settings", "project:<P>", "study:<P>/<S>"],
            "notice": library.CODE_WARNING}


@router.get("/{kind}")
def items(kind: str, layer: str = "settings") -> dict[str, Any]:
    k = _kind(kind)
    la = _call(library.parse_layer, layer)
    return {"kind": k, "layer": la.name, "items": _call(library.list_items, k, la)}


@router.post("/{kind}/upload")
async def upload(kind: str, request: Request, file: UploadFile = File(...), layer: str | None = Form(None),
                 name: str | None = Form(None), group: str | None = Form(None), classes: str | None = Form(None),
                 allow_code: str | None = Form(None), replace: str | None = Form(None)) -> dict[str, Any]:
    """Multipart upload of a ``.zip`` (any kind) or ``.py`` (code kinds). Each
    form field may also be given as a query parameter (the form field wins)."""
    k = _kind(kind)
    q = request.query_params

    def val(v: str | None, key: str) -> str | None:
        return v if v not in (None, "") else q.get(key)

    def flag(v: str | None, key: str) -> bool:
        return str(val(v, key) or "").strip().lower() in ("1", "true", "yes", "on")

    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, f"uploads are limited to {MAX_UPLOAD // (1024 * 1024)} MB")
    cls = [c.strip() for c in (val(classes, "classes") or "").split(",") if c.strip()] or None
    return _call(library.add_upload, k, file.filename or "upload", data, val(layer, "layer") or "settings",
                 name=val(name, "name"), group=val(group, "group"), classes=cls,
                 allow_code=flag(allow_code, "allow_code"), replace=flag(replace, "replace"))


@router.post("/{kind}/link")
def link(kind: str, body: dict = Body(...), layer: str = "settings") -> dict[str, Any]:
    """``{"target": "/abs/path" | "pkg.module:Class", "name"?, "group"?, "classes"?,
    "syspath"?, "allow_code"?, "replace"?}``."""
    k = _kind(kind)
    return _call(library.add_link, k, str(body.get("target") or body.get("path") or body.get("spec") or ""),
                 body.get("layer") or layer, name=body.get("name") or None, group=body.get("group") or None,
                 classes=body.get("classes") or None, syspath=body.get("syspath") or None,
                 allow_code=bool(body.get("allow_code")), replace=bool(body.get("replace")))


@router.delete("/{kind}/items/{name}")
def remove(kind: str, name: str, layer: str = "settings") -> dict[str, Any]:
    return _call(library.remove_item, _kind(kind), name, layer)


@router.get("/{kind}/groups")
def groups(kind: str, layer: str = "settings") -> dict[str, Any]:
    k = _kind(kind)
    la = _call(library.parse_layer, layer)
    return {"kind": k, "layer": la.name, "groups": _call(library.list_groups, k, la)}


@router.put("/{kind}/groups/{name}")
def put_group(kind: str, name: str, body: Any = Body(...), layer: str = "settings") -> dict[str, Any]:
    """Body: a list of raw entries, or ``{"entries": [...], "description"?,
    "rename_from"?, "syspath"?, "assistant"?}``."""
    k = _kind(kind)
    if isinstance(body, list):
        body = {"entries": body}
    if not isinstance(body, dict):
        raise HTTPException(400, "send a list of entries or an object with entries")
    extra = {x: body[x] for x in ("syspath", "assistant") if x in body}
    return _call(library.put_group, k, name, body.get("entries"), layer, description=body.get("description"),
                 rename_from=body.get("rename_from") or None, extra=extra)


@router.delete("/{kind}/groups/{name}")
def delete_group(kind: str, name: str, layer: str = "settings") -> dict[str, Any]:
    return _call(library.delete_group, _kind(kind), name, layer)


@router.get("/tools/placement")
def get_placement(layer: str = "settings") -> dict[str, Any]:
    return _call(library.get_placement, layer)


@router.put("/tools/placement")
def put_placement(body: dict = Body(...), layer: str = "settings", replace: bool = False) -> dict[str, Any]:
    """Body: ``{tool: placement | null}`` (``{"tools": {...}}`` works too)."""
    pl = body.get("tools") if isinstance(body.get("tools"), dict) else body
    return _call(library.put_placement, pl, layer, replace)


@router.get("/tools/offer")
def get_offer(layer: str = "settings") -> dict[str, Any]:
    return _call(library.get_offer, layer)


@router.put("/tools/offer")
def put_offer(body: Any = Body(...), layer: str = "settings") -> dict[str, Any]:
    """Body: a list of tools and groups (``["@information", "Trace"]``), ``null``
    (every tool), or ``{"offer": ...}``."""
    entries = body.get("offer") if isinstance(body, dict) else body
    return _call(library.put_offer, entries, layer)
