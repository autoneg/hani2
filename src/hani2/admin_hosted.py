"""The admin console API of self-hosted agents (:mod:`hani2.hosting`): a project's registered endpoints
and its ``hosted:`` mode. Tokens are shown once, when HANI2 makes one; never listed."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException

from hani2 import projects
from hani2.admin_common import admin_dep

router = APIRouter(dependencies=[Depends(admin_dep)])


def _project(project: str) -> str:
    if not projects.valid_name(project) or not projects.project_exists(project):
        raise HTTPException(404, f"no project {project!r}")
    return project


def _mode(project: str) -> dict[str, Any]:
    from hani2.hosting.registry import HOSTED_DEFAULTS

    pr = projects.load_project(project)
    given = pr.defaults.get("hosted") if isinstance(pr.defaults.get("hosted"), dict) else {}
    return {**HOSTED_DEFAULTS, **{k: v for k, v in (given or {}).items() if v is not None}}


@router.get("/api/admin/projects/{project}/hosted")
def hosted_list(project: str):
    from hani2.hosting import registry

    _project(project)
    return {"agents": [registry.public(e) for e in registry.entries(project)], "mode": _mode(project)}


@router.post("/api/admin/projects/{project}/hosted")
def hosted_add(project: str, body: dict = Body(...)):
    from hani2.hosting import registry

    _project(project)
    try:
        e, tok = registry.add(project, str(body.get("name") or "").strip(), str(body.get("kind") or "assistant"),
                              str(body.get("url") or ""), token=(body.get("token") or None), team=str(body.get("team") or ""),
                              timeout=body.get("timeout") or None, replace=bool(body.get("replace")))
    except ValueError as ex:
        raise HTTPException(400, str(ex)) from None
    out: dict[str, Any] = {"agent": registry.public(e)}
    if not body.get("token") and not body.get("replace"):
        out["token"] = tok  # shown once: the team starts its host with it
    return out


@router.delete("/api/admin/projects/{project}/hosted/{name}")
def hosted_remove(project: str, name: str):
    from hani2.hosting import registry

    _project(project)
    if not registry.remove(project, name):
        raise HTTPException(404, f"no hosted agent {name!r}")
    return {"ok": True}


@router.put("/api/admin/projects/{project}/hosted/{name}/enabled")
def hosted_enable(project: str, name: str, body: dict = Body(...)):
    from hani2.hosting import registry

    _project(project)
    if not registry.set_enabled(project, name, bool(body.get("enabled"))):
        raise HTTPException(404, f"no hosted agent {name!r}")
    return {"ok": True}


@router.post("/api/admin/projects/{project}/hosted/{name}/token")
def hosted_new_token(project: str, name: str):
    """A new token for the team (the old one stops working at once)."""
    from hani2.hosting import registry

    _project(project)
    e = registry.get(project, name)
    if e is None:
        raise HTTPException(404, f"no hosted agent {name!r}")
    tok = registry.new_token()
    registry.add(project, name, e["kind"], e["url"], token=tok, team=e.get("team") or "", timeout=e.get("timeout"),
                 replace=True, enabled=e.get("enabled", True))
    return {"token": tok}


@router.post("/api/admin/projects/{project}/hosted/{name}/check")
def hosted_check(project: str, name: str):
    from hani2.hosting import client, registry

    _project(project)
    e = registry.get(project, name)
    if e is None:
        raise HTTPException(404, f"no hosted agent {name!r}")
    return client.check(registry.endpoint_of(e))


@router.put("/api/admin/projects/{project}/hosted-mode")
def hosted_mode(project: str, body: dict = Body(...)):
    """Set the project's ``hosted:`` block (its studies may override it in study.yaml)."""
    from hani2.hosting.registry import HOSTED_KEYS, check_hosted_block

    _project(project)
    block = {k: body[k] for k in HOSTED_KEYS if k in body and body[k] is not None}
    problems = check_hosted_block(block)
    if problems:
        raise HTTPException(400, "; ".join(problems))
    f = projects.project_dir(project) / projects.PROJECT_FILE
    data = projects.read_yaml(f)
    target = data["defaults"] if isinstance(data.get("defaults"), dict) and "hosted" in data["defaults"] else data
    target["hosted"] = block
    projects.write_yaml(f, data)
    return {"mode": _mode(project)}
