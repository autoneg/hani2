"""The admin console API: layers, settings files, pools, balance and scenario details.

Items, uploads, links and groups of scenarios, opponents, Assistants and tools are the
library's (:mod:`hani2.api_library`, ``/api/admin/library``); this module has what the
library does not: settings per layer, the pools participants face, the Assistant balance of a
study and the details of a scenario type (:mod:`hani2.admin_scenarios`). Every endpoint is
admin only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from hani2 import groups, projects
from hani2.admin_common import admin_dep, get_layer, guard, need_layer
from hani2.config import _deep_merge, get_settings_file
from hani2.layers import (SETTINGS, SETTINGS_KINDS, TEXT_FILES, Layer, LayerError, binding, layer_of_path,
                          list_layers, read_json_own, remove_dotted, write_json_own)


router = APIRouter(dependencies=[Depends(admin_dep)])


# --------------------------------------------------------------------------- #
# Layers                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/api/admin/layers")
def admin_layers(request: Request):
    out = []
    for lay in list_layers():
        d: dict[str, Any] = {"id": lay.id, "kind": lay.kind, "label": lay.label, "path": str(lay.dir)}
        if lay.project and lay.kind != "settings":
            d["project"] = lay.project
        if lay.study:
            d["study"] = lay.study
        out.append(d)
    bound = getattr(request.state, "hani2_study", None)
    default = projects.default_study()
    from hani2.config import overrides, overrides_path

    ov = overrides_path()
    return {"layers": out, "bound": f"study:{bound}" if bound else None,
            "default_study": str(default) if default else None,
            # the start-time settings file (hani2 --settings): it wins over the settings folder
            "overrides": {"path": str(ov), "files": sorted(overrides())} if ov else None}


# --------------------------------------------------------------------------- #
# Settings files                                                               #
# --------------------------------------------------------------------------- #
def _check_kind(kind: str) -> None:
    if kind not in SETTINGS_KINDS and kind not in TEXT_FILES:
        raise HTTPException(404)


def settings_get(kind: str, layer: Layer) -> dict:
    _check_kind(kind)
    if kind in SETTINGS_KINDS:
        fname, loader = SETTINGS_KINDS[kind]
        own = _read_own(kind, layer.dir / fname)
        with binding(layer):
            eff = loader()
        with binding(layer, skip_own=True):
            inh = loader()
        return {"layer": layer.id, "own": own, "effective": eff, "inherited": inh}
    fname = TEXT_FILES[kind]
    f = layer.dir / fname
    with binding(layer):
        src = get_settings_file(fname)
    return {"layer": layer.id, "text": f.read_text(encoding="utf-8") if f.exists() else "", "exists": f.exists(),
            "effective": src.read_text(encoding="utf-8") if src.exists() else "",
            "source": layer_of_path(src) if src.exists() else "bundled", "source_path": str(src)}


def _read_own(kind: str, path: Path) -> dict:
    if kind == "models":  # a bare list is the default chain
        from hani2.model_chain import read_layer_file

        return read_layer_file(path)
    return guard(read_json_own, path)


def _check_models(kind: str, data: dict) -> None:
    if kind == "models":
        from hani2.admin_models import check_body

        check_body(data)


def settings_put(kind: str, layer: Layer, body: dict) -> dict:
    _check_kind(kind)
    _check_models(kind, body)
    if kind in SETTINGS_KINDS:
        write_json_own(layer.dir / SETTINGS_KINDS[kind][0], body)
        return {"ok": True}
    p = layer.dir / TEXT_FILES[kind]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(str(body.get("text", "")), encoding="utf-8")
    return {"ok": True}


def settings_patch(kind: str, layer: Layer, body: dict) -> dict:
    _check_kind(kind)
    if kind not in SETTINGS_KINDS:
        raise HTTPException(400, "PATCH is for JSON settings; use PUT for texts")
    f = layer.dir / SETTINGS_KINDS[kind][0]
    own = _deep_merge(_read_own(kind, f), body)
    _check_models(kind, own)
    write_json_own(f, own)
    return {"ok": True, "own": own}


def settings_delete(kind: str, layer: Layer, key: str | None) -> dict:
    _check_kind(kind)
    if kind in SETTINGS_KINDS:
        f = layer.dir / SETTINGS_KINDS[kind][0]
    else:
        f = layer.dir / TEXT_FILES[kind]
    if key:
        if kind not in SETTINGS_KINDS:
            raise HTTPException(400, "a key can only be removed from JSON settings")
        own = guard(read_json_own, f)
        if not remove_dotted(own, key):
            raise HTTPException(404, f"{key!r} is not set in this layer")
        write_json_own(f, own)
    elif f.exists():
        f.unlink()
    return {"ok": True}


def write_target(request: Request, layer: str | None, study: str | None, project: str | None) -> Layer:
    """The layer a settings write goes to; 409 when none is named in a study-bound console."""
    lay = get_layer(layer, study, project, default=None)
    if lay is None:
        if getattr(request.state, "hani2_study_path", False):
            s = getattr(request.state, "hani2_study", "")
            p = s.split("/")[0] if s else "P"
            raise HTTPException(409, f"This console is open in study {s}; say which layer to save to "
                                     f"(?layer=settings, ?layer=project:{p} or ?layer=study:{s})")
        return SETTINGS
    return lay


# --------------------------------------------------------------------------- #
# Pools (opponents / assistants per layer)                                     #
# --------------------------------------------------------------------------- #
def _pool_kind(kind: str) -> str:
    try:
        return groups.check_kind(kind)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


def _read_yaml_strict(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise LayerError(409, f"{path.name} is not valid YAML: {e}") from None
    if not isinstance(data, dict):
        raise LayerError(409, f"{path.name} is not a mapping")
    return data


def _items(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [s.strip() for s in raw.split(",") if s.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(s).strip() for s in raw if str(s).strip()]
    return [str(raw).strip()]


def _pool_loc(kind: str, layer: Layer) -> tuple[Path, str, list[str]]:
    """``(file, dotted key, path of the key inside the file)`` for a layer's pool."""
    k = f"{kind}s"
    if layer.kind == "settings":
        return layer.dir / "env.json", k, [k]
    if layer.kind == "project":
        return layer.dir / projects.PROJECT_FILE, f"defaults.{k}", ["defaults", k]
    return layer.dir / projects.STUDY_FILE, f"overrides.{k}", ["overrides", k]


def _get_path(data: dict, path: list[str]) -> Any:
    cur: Any = data
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return None
        cur = cur[p]
    return cur


def _own_items(kind: str, layer: Layer) -> list[str]:
    if kind == groups.ASSISTANT and layer.kind == "settings":
        from hani2.support_agent.settings import load_assistant_settings

        with binding(layer):
            return [groups.default_assistant_spec(load_assistant_settings())]
    f, _, path = _pool_loc(kind, layer)
    data = guard(read_json_own, f) if f.suffix == ".json" else guard(_read_yaml_strict, f)
    raw = _get_path(data, path)
    if raw is None and layer.kind != "settings":  # old top-level key
        raw = data.get(path[-1])
    return _items(raw)


def _expand(kind: str, items: list[str], layer: Layer) -> list[str]:
    with binding(layer):
        if kind == groups.OPPONENT:
            from hani2.agents import expand_agents

            return [str(x) for x in expand_agents(items)]
        return groups.expand_assistants(items, projects.current_study())


def pool_payload(kind: str, layer: Layer) -> dict:
    f, key, _ = _pool_loc(kind, layer)
    note = ""
    editable = True
    items = _own_items(kind, layer)
    par = layer.parent
    inherited: list[str] = []
    while par is not None:
        inherited = _own_items(kind, par) if not (kind == groups.ASSISTANT and par.kind == "settings") else []
        if inherited:
            break
        par = par.parent
    if kind == groups.ASSISTANT and layer.kind == "settings":
        editable = False
        note = "At the settings level the Assistant is the Assistant class (assistant_settings.json agent_class)"
        f, key = layer.dir / "assistant_settings.json", "agent_class"
    if kind == groups.ASSISTANT and layer.kind != "settings" and not inherited:
        with binding(layer, skip_own=True):
            from hani2.support_agent.settings import load_assistant_settings

            inherited = [groups.default_assistant_spec(load_assistant_settings())]
    effective_items = items or inherited
    return {"layer": layer.id, "items": items, "file": str(f), "key": key, "inherited": inherited,
            "effective": _expand(kind, effective_items, layer), "editable": editable, "note": note}


def pool_put(kind: str, layer: Layer, items: list[str]) -> dict:
    if kind == groups.ASSISTANT and layer.kind == "settings":
        raise HTTPException(400, "the Assistant at the settings level is agent_class in assistant_settings.json")
    items = [str(i).strip() for i in items if str(i).strip()]
    # a library item's name is written as its spec (as in group files), so the pool works on its own
    from hani2 import library

    items = library._normalise_entries(f"{kind}s", library.parse_layer(layer.id), items)
    f, _, path = _pool_loc(kind, layer)
    if f.suffix == ".json":
        data = guard(read_json_own, f)
    else:
        data = guard(_read_yaml_strict, f)
    cur = data
    for p in path[:-1]:
        if not isinstance(cur.get(p), dict):
            if items:
                cur[p] = {}
            else:
                cur = None  # type: ignore[assignment]
                break
        cur = cur[p]
    if cur is not None:
        if items:
            cur[path[-1]] = items
        else:
            cur.pop(path[-1], None)
            if len(path) > 1 and not cur:
                data.pop(path[0], None)
    if f.suffix == ".json":
        write_json_own(f, data)
    else:
        projects.write_yaml(f, data)
    return pool_payload(kind, layer)


@router.get("/api/admin/pools/{kind}")
def admin_get_pool(kind: str, layer: str | None = None, study: str | None = None, project: str | None = None):
    return guard(pool_payload, _pool_kind(kind), need_layer(layer, study, project))


@router.put("/api/admin/pools/{kind}")
def admin_put_pool(kind: str, body: dict = Body(...), layer: str | None = None, study: str | None = None,
                   project: str | None = None):
    items = body.get("items")
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        raise HTTPException(400, "items must be a list of strings")
    return guard(pool_put, _pool_kind(kind), need_layer(layer, study, project), items)


# --------------------------------------------------------------------------- #
# Balance                                                                      #
# --------------------------------------------------------------------------- #
@router.get("/api/admin/projects/{project}/studies/{study}/balance")
def admin_balance(project: str, study: str):
    from hani2 import assignment

    try:
        ref = projects.StudyRef(projects.check_name(project, "project"), projects.check_name(study, "study"))
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    if not projects.study_exists(ref):
        raise HTTPException(404, "Unknown study")
    st = projects.load_study(ref)
    pr = projects.load_project(ref.project)
    if "assistants" in st.overrides:
        source = "study"
    elif "assistants" in pr.defaults:
        source = "project"
    else:
        source = "settings"
    raw = projects.setting("assistants", None, ref=ref)
    items = _items(raw)
    with projects.use_study(ref):
        if items:
            pool = groups.expand_assistants(items, ref)
        else:
            pool = [groups.default_assistant_spec()]
    group = assignment._group_of(items)
    data = assignment.read_assignments(ref)
    humans = data.get("humans", {})
    rows = [{"user": u, "index": h.get("index"), "assistant": h.get("assistant", ""),
             "assistant_group": h.get("assistant_group", ""), "assigned_at": h.get("assigned_at", ""),
             "first_seen": h.get("first_seen", "")} for u, h in humans.items()]
    return {"pool": pool, "source": source, "group": group,
            "counts": assignment.assistant_counts(data, pool), "humans": len(humans), "assignments": rows}


from hani2 import admin_scenarios  # noqa: E402

router.include_router(admin_scenarios.router)

from hani2 import admin_models  # noqa: E402

router.include_router(admin_models.router)
