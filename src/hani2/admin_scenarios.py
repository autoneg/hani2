"""Admin API: the details of a scenario type (roles, issues, sample utilities, an example).

Listing, uploading, linking and removing scenario types and editing scenario sets are the
library's (``/api/admin/library/scenarios``, :mod:`hani2.library`); this adds what it has
not: ``GET /api/admin/scenarios/{name}`` describes one type as participants would see it.
"""

from __future__ import annotations

import math
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from hani2 import scenario_links
from hani2 import scenario_store as store
from hani2.admin_common import admin_dep, need_layer
from hani2.config import DEFAULT_SCENARIOS
from hani2.layers import Layer, binding
from hani2.scenarios import registry

router = APIRouter(dependencies=[Depends(admin_dep)])

_GEN_INFO: dict[str, dict] = {}
_GEN_LOCK = threading.Lock()


def _display_py(folder: Path | None) -> bool:
    if folder is None or not folder.is_dir():
        return False
    return (folder / "display.py").exists() or any((p / "display.py").exists() for p in store.pool_of(folder))


def _generated_info(name: str) -> dict:
    """The title and descriptions of a generator's scenarios (from its story, else its first scenario)."""
    t = registry.get(name)
    if t is not None and t.story is not None:
        st = t.story
        return {"title": st.title, "short_description": st.short_description, "source": st.source}
    with _GEN_LOCK:
        if name in _GEN_INFO:
            return _GEN_INFO[name]
    info: dict = {}
    try:
        s = registry.MAKERS[name](0)
        info = dict(s.info or {})
    except Exception:  # noqa: BLE001 - a broken generator must not break the list
        pass
    with _GEN_LOCK:
        _GEN_INFO[name] = info
    return info


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def describe_scenario(name: str, layer: Layer, scenario: str | None, generate: int | None) -> dict:
    from negmas import Scenario

    warnings: list[str] = []
    with binding(layer):
        registry.load_plugins()
        reg = registry.get(name)
        folder = store.category_dir(name)
        linked = folder is not None and scenario_links.find(name) == folder
        pool: list[str] = []
        path: Path | None = None
        generated = False
        if generate is not None:
            if reg is None:
                raise HTTPException(400, f"{name} has no generator")
            s = registry.MAKERS[name](generate)
            generated = True
        elif folder is not None and store.pool_of(folder):
            folders = store.pool_of(folder)
            pool = [p.name for p in folders]
            if scenario:
                match = [p for p in folders if p.name == scenario]
                if not match:
                    raise HTTPException(404, f"{name} has no scenario {scenario!r}")
                path = match[0]
            else:
                path = folders[0]
            try:
                s = Scenario.load(path)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(400, f"cannot load {path}: {e}") from None
            s.info = store._read_info(path) or (s.info or {})
        elif reg is not None:
            s = registry.MAKERS[name](0)
            generated = True
        elif (DEFAULT_SCENARIOS / name).is_dir():
            path = DEFAULT_SCENARIOS / name
            s = Scenario.load(path)
            s.info = store._read_info(path) or (s.info or {})
        else:
            raise HTTPException(404, "Unknown scenario type")
    if s is None:
        raise HTTPException(400, "the scenario could not be loaded")
    info = dict(s.info or {})
    gi = _generated_info(name) if reg is not None else {}
    roles = []
    human_idx = store.assign_human(s, "auto", 1)
    rdesc = info.get("role_descriptions") or {}
    for i, u in enumerate(s.ufuns):
        rn = str(getattr(u, "name", "") or "")
        roles.append({"name": rn, "description": str(rdesc.get(rn, "") or ""),
                      "reserved_value": _num(getattr(u, "reserved_value", None)), "human": i == human_idx})
    idesc = info.get("issue_description") or {}
    issues = []
    for iss in s.outcome_space.issues:
        try:
            vals = [str(v) for v in list(iss.all)[:60]]
        except Exception:  # noqa: BLE001 - continuous issues have no value list
            vals = []
        card = _num(getattr(iss, "cardinality", None))
        issues.append({"name": str(iss.name), "type": type(iss).__name__,
                       "n_values": int(card) if card is not None else None, "values": vals,
                       "description": str(idesc.get(iss.name, "") or "")})
    card = _num(getattr(s.outcome_space, "cardinality", None))
    sample = _sample(s)
    if len(s.ufuns) < 2:
        warnings.append(f"needs a utility function per role, found {len(s.ufuns)}")
    for k in store.REQUIRED_INFO:
        if not str(info.get(k) or gi.get(k) or "").strip():
            warnings.append(f"no {k}")
    found = folder is not None and bool(store.pool_of(folder))
    folder_for_display = (folder if found else path) if not generated else None
    return {
        "name": name, "title": str(info.get("title") or gi.get("title") or name),
        "short_description": str(info.get("short_description") or gi.get("short_description") or ""),
        "long_description": str(info.get("long_description") or ""),
        "source": str(info.get("source") or gi.get("source") or ""),
        "kind": ("story" if reg and reg.story else "generator") if reg and generated
        else ("link" if found and linked else "folder" if found else "sample"),
        "roles": roles, "issues": issues, "n_outcomes": int(card) if card is not None else None, "pool": pool,
        "loaded_from": str(path) if path else None, "generated": generated, "sample": sample,
        "has_display_py": _display_py(folder_for_display), "warnings": warnings,
    }


def _sample(s) -> list[dict]:
    try:
        outs = list(s.outcome_space.enumerate_or_sample(max_cardinality=5000))
    except Exception:  # noqa: BLE001
        return []
    if not outs:
        return []
    names = [str(i.name) for i in s.outcome_space.issues]
    ufs = list(s.ufuns)
    vals = [[float(u(o)) for u in ufs] for o in outs]
    chosen: list[int] = []
    for j in range(len(ufs)):
        b = max(range(len(outs)), key=lambda k: vals[k][j])
        if b not in chosen:
            chosen.append(b)
    step = max(1, len(outs) // 8)
    for k in range(0, len(outs), step):
        if len(chosen) >= 8:
            break
        if k not in chosen:
            chosen.append(k)
    out = []
    for k in chosen[:8]:
        out.append({"outcome": {n: str(v) for n, v in zip(names, outs[k])},
                    "utilities": {str(getattr(u, "name", j)): vals[k][j] for j, u in enumerate(ufs)}})
    return out


@router.get("/api/admin/scenarios/{name}")
def admin_scenario(name: str, layer: str | None = None, study: str | None = None, project: str | None = None,
                   scenario: str | None = None, generate: int | None = None):
    return describe_scenario(name, need_layer(layer, study, project), scenario, generate)
