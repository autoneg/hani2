"""``{{variable}}`` placeholders in participant-facing texts.

Consent, announcements, the page title and subtitle, the end page and
questionnaire texts may use placeholders that are filled per session from the
session's project and study (see :func:`study_variables`). An unknown
placeholder is left as written, so a typo stays visible; :func:`render_report`
also returns the unknown names (for an editor preview).
"""

from __future__ import annotations

import os
import re
from typing import Any

from hani2 import projects

VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")

#: the built-in variables with what they hold (custom keys of project.yaml and
#: study.yaml are added as ``project_<key>`` / ``study_<key>``)
VARIABLES: dict[str, str] = {
    "project_name": "The project's short name (its folder name)",
    "project_full_name": "The project's full name (full_name in project.yaml; else its name)",
    "project_short_description": "short_description in project.yaml",
    "project_link": "link in project.yaml",
    "project_year": "year in project.yaml",
    "study_name": "The study's short name (its folder name)",
    "study_title": "title in study.yaml (else the study's name)",
    "study_type": "prolific, online or lab",
    "study_link": "link in study.yaml",
    "study_year": "year in study.yaml, else the year of its start date, else the project's year",
    "organizer": "organizer in study.yaml, else in project.yaml",
    "contact": "contact in study.yaml, else in project.yaml",
    "n_required": "Counted negotiations per participant (PROLIFIC_N_REQUIRED, else n_required of the study / project, else 5)",
    "minutes": "Expected maximum minutes (PROLIFIC_MAX_MINUTES, else minutes of the study / project, else 45)",
    "completion_code": "The completion code (PROLIFIC_COMPLETION_CODE, else completion_code in study.yaml)",
}


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def study_variables(ref: "projects.StudyRef | None" = projects.UNSET) -> dict[str, str]:
    """The placeholder values for study ``ref`` (default: the current study)."""
    r = projects.current_study() if ref is projects.UNSET else ref
    pr = projects.get_project(r)
    st = projects.get_study(r)
    year = ""
    if st is not None:
        year = _s(st.year) or (st.start[:4] if st.start[:4].isdigit() else "")
    out = {
        "project_name": pr.name,
        "project_full_name": _s(pr.full_name) or pr.name,
        "project_short_description": _s(pr.short_description),
        "project_link": _s(pr.link),
        "project_year": _s(pr.year),
        "study_name": st.name if st else "",
        "study_title": (_s(st.title) or st.name) if st else "",
        "study_type": st.type if st else "",
        "study_link": _s(st.link) if st else "",
        "study_year": year or _s(pr.year),
        "organizer": _s(st.organizer if st and st.organizer else pr.organizer),
        "contact": _s(st.contact if st and st.contact else pr.contact),
        "n_required": _s(projects.setting("n_required", 5, env="PROLIFIC_N_REQUIRED", cast=int, ref=r)),
        "minutes": _s(projects.setting("minutes", 45, env="PROLIFIC_MAX_MINUTES", cast=int, ref=r)),
        "completion_code": (os.environ.get("PROLIFIC_COMPLETION_CODE") or "").strip() or (_s(st.completion_code) if st else ""),
    }
    for k, v in pr.extra.items():
        if isinstance(v, (str, int, float, bool)) and re.fullmatch(r"[A-Za-z0-9_]+", str(k)):
            out.setdefault(f"project_{k}", _s(v))
    for k, v in (pr.defaults or {}).items():
        if isinstance(v, (str, int, float, bool)):
            out.setdefault(f"project_{k}", _s(v))
    if st is not None:
        for src in (st.extra, st.overrides):
            for k, v in src.items():
                if isinstance(v, (str, int, float, bool)) and re.fullmatch(r"[A-Za-z0-9_]+", str(k)):
                    out.setdefault(f"study_{k}", _s(v))
        for k in ("start", "end", "prolific_study_id", "completion_url"):
            out.setdefault(f"study_{k}", _s(getattr(st, k)))
    return out


def render_report(text: str, variables: dict[str, Any] | None = None) -> tuple[str, list[str]]:
    """``(rendered text, unknown variable names)``; unknown placeholders stay as written."""
    vals = study_variables() if variables is None else variables
    unknown: list[str] = []

    def _sub(m: re.Match) -> str:
        name = m.group(1)
        if name in vals:
            return _s(vals[name])
        if name not in unknown:
            unknown.append(name)
        return m.group(0)

    return VAR.sub(_sub, text or ""), unknown


def render(text: str, variables: dict[str, Any] | None = None) -> str:
    return render_report(text, variables)[0]


def render_data(obj: Any, variables: dict[str, Any] | None = None) -> Any:
    """Render every string in a nested structure (e.g. a questionnaire)."""
    vals = study_variables() if variables is None else variables
    if isinstance(obj, str):
        return render(obj, vals) if "{{" in obj else obj
    if isinstance(obj, list):
        return [render_data(x, vals) for x in obj]
    if isinstance(obj, dict):
        return {k: render_data(v, vals) for k, v in obj.items()}
    return obj
