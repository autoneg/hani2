"""Helpers shared by the admin API modules."""

from __future__ import annotations

from fastapi import HTTPException, Request

from hani2.layers import SETTINGS, Layer, LayerError, parse_layer


def admin_dep(request: Request) -> str:
    """``require_admin`` of the server (imported late: the server includes the routers)."""
    from hani2.server import require_admin

    return require_admin(request)


def get_layer(layer: str | None = None, study: str | None = None, project: str | None = None,
              default: Layer | None = SETTINGS) -> Layer | None:
    try:
        return parse_layer(layer, study, project, default)
    except LayerError as e:
        raise HTTPException(e.status, str(e)) from None


def need_layer(layer: str | None, study: str | None = None, project: str | None = None) -> Layer:
    return get_layer(layer, study, project)  # type: ignore[return-value]


def guard(fn, *a, **kw):
    """Run ``fn`` turning :class:`LayerError` into HTTP errors."""
    try:
        return fn(*a, **kw)
    except LayerError as e:
        raise HTTPException(e.status, str(e)) from None
