"""Admin API: the details of a scenario type (roles, issues, sample utilities, an example).

Listing, uploading, linking and removing scenario types and editing scenario sets are the
library's (``/api/admin/library/scenarios``, :mod:`hani2.library`); this adds what it has
not: ``GET /api/admin/scenarios/{name}`` describes one type as participants would see it.
"""

from __future__ import annotations

import math
import secrets
import threading
from collections import OrderedDict
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
            s = store.make_scenario(name, generate, store.simple_scenarios())  # as this layer would serve it
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
            s = store.make_scenario(name, 0, store.simple_scenarios())
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
    plot_token = _remember(s, human_idx)
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
        "plot_token": plot_token,
    }


_SHOWN: OrderedDict[str, tuple[Any, int | None]] = OrderedDict()
"""The scenarios last described, by plot token, so their plot (fetched after the details, to not
delay them) shows the very scenario on screen: generators do not repeat a draw."""
_SHOWN_MAX = 64
_SHOWN_LOCK = threading.Lock()


def _remember(s, human_idx: int | None) -> str:
    token = secrets.token_urlsafe(12)
    with _SHOWN_LOCK:
        _SHOWN[token] = (s, human_idx)
        while len(_SHOWN) > _SHOWN_MAX:
            _SHOWN.popitem(last=False)
    return token


def scenario_plots(token: str) -> dict:
    """The plots of a scenario described before (``plot_token`` of its details)."""
    with _SHOWN_LOCK:
        hit = _SHOWN.get(token)
        if hit is not None:
            _SHOWN.move_to_end(token)
    if hit is None:
        raise HTTPException(404, "This example is no longer available; reload the details to plot it.")
    plots, note = _plots(*hit)
    return {"plots": plots, "plot_note": note}


PLOT_MAX_OUTCOMES = 5_000
"""Outcome spaces larger than this (or continuous ones) are plotted from a random sample."""


def _role_names(s) -> list[str]:
    names: list[str] = []
    for i, u in enumerate(s.ufuns):
        n = str(getattr(u, "name", "") or "") or f"role {i + 1}"
        while n in names:
            n = f"{n} ({i + 1})"
        names.append(n)
    return names


def _plots(s, human_idx: int | None) -> tuple[list[dict], str]:
    """The outcome space in utility space (negmas ``plot_2dutils``), one Plotly figure per pair of
    roles: the participant's role against each other role. Returns ``(figures, note)``; a failure
    gives no figures and the reason in the note, never an error for the whole page."""
    import json

    from negmas.plots.util import plot_2dutils

    ufuns = list(s.ufuns)
    if len(ufuns) < 2:
        return [], "Needs two roles to plot."
    try:
        card = _num(s.outcome_space.cardinality)
        sampled = card is None or card > PLOT_MAX_OUTCOMES
        outcomes = (list(s.outcome_space.sample(PLOT_MAX_OUTCOMES, with_replacement=False, fail_if_not_enough=False))
                    if sampled else list(s.outcome_space.enumerate()))
        names = _role_names(s)
        h = human_idx if human_idx is not None and 0 <= human_idx < len(ufuns) else 0
        pairs = [(h, j) for j in range(len(ufuns)) if j != h] if len(ufuns) > 2 else [(h, 1 - h)]
        figs = []
        for i, j in pairs:
            pn = [names[i], names[j]]
            fig = plot_2dutils(
                [], [ufuns[i], ufuns[j]], pn, offering_negotiators=pn,
                outcome_space=s.outcome_space, outcomes=outcomes,
                show_annotations=False, show_total_time=False, show_relative_time=False,
                show_n_steps=False,
            )
            figs.append({"title": f"{names[i]} vs {names[j]}", "figure": _tidy(json.loads(fig.to_json()), pn)})
    except Exception as e:  # noqa: BLE001 - the plot is a nicety; the details must still load
        return [], f"Could not plot this scenario: {e}"
    note = (f"Plotted from a random sample of {len(outcomes)} outcomes; the frontier and the "
            "bargaining solutions are those of the sample.") if sampled else ""
    return figs, note


# mid-tone colours that read on light and dark backgrounds
_POINT_COLORS = {"Max Welfare Points": "#3b82f6", "Kalai Point": "#22c55e", "KS Point": "#06b6d4", "Nash Point": "#ef4444"}


def _tidy(fig: dict, roles: list[str]) -> dict:
    """Drop the empty offer traces (no negotiation ran), make the frontier visible on any
    background, and label the axes and the shaded no-deal regions plainly."""
    data = []
    for t in fig.get("data", []):
        if t.get("name") in roles and not t.get("x"):
            continue
        if t.get("name") == "Pareto":
            t["marker"] = {**t.get("marker", {}), "color": "#d97706", "opacity": 0.9, "size": 9}
            t["name"] = "Pareto frontier"
        if t.get("name") in _POINT_COLORS:
            t["marker"] = {**t.get("marker", {}), "color": _POINT_COLORS[t["name"]], "opacity": 0.95}
        if t.get("name") == "Outcomes":
            t["marker"] = {**t.get("marker", {}), "color": "rgba(128,128,128,0.55)", "size": 5}
        data.append(t)
    fig["data"] = data
    lay = fig.setdefault("layout", {})
    for ax, r in (("xaxis", roles[0]), ("yaxis", roles[1])):
        a = lay.setdefault(ax, {})
        a["title"] = {**(a.get("title") or {}), "text": f"{r} utility"}
    # square, without widening the range: the plot area shrinks rather than the axis growing
    lay["xaxis"]["constrain"] = "domain"
    lay["legend"] = {"orientation": "h", "yanchor": "top", "y": -0.15, "xanchor": "left", "x": 0}
    lay["margin"] = {"l": 50, "r": 10, "t": 10, "b": 40}
    return fig


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


@router.get("/api/admin/scenarios/plot/{token}")
def admin_scenario_plot(token: str):
    """The outcome-space plots of the example a details call just showed (by its ``plot_token``)."""
    return scenario_plots(token)


@router.get("/api/admin/scenarios/{name}")
def admin_scenario(name: str, layer: str | None = None, study: str | None = None, project: str | None = None,
                   scenario: str | None = None, generate: int | None = None):
    return describe_scenario(name, need_layer(layer, study, project), scenario, generate)
