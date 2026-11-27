"""Admin API of the questionnaire explorer (:mod:`hani2.questionnaire_library`) and the
structured item editor of the Study forms page. Every endpoint is admin only (the router is
included by :mod:`hani2.admin_api`)."""

from __future__ import annotations

import yaml
from fastapi import APIRouter, Body, HTTPException

from hani2 import questionnaire_library as ql
from hani2 import questionnaires

router = APIRouter()


def _call(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ql.LibraryError as e:
        raise HTTPException(e.status, str(e)) from None


@router.get("/api/admin/questionnaire-library")
def library_list():
    """Every set with its origin, file, read-only flag, validation mark and warnings; the folder
    the app writes to; files there that are not sets; a blank set to start from."""
    from hani2.evaluation import catalog

    return {"sets": ql.entries(), "own_dir": str(ql.own_dir()), "broken": ql.broken_files(), "blank": ql.BLANK,
            "validated_tooltip": catalog.VALIDATED_SOURCE_TOOLTIP,
            "forms": [{"key": f.key, "title": f.title} for f in questionnaires.FORMS.values()],
            "types": list(questionnaires.QUESTION_TYPES)}


@router.post("/api/admin/questionnaire-library")
def library_create(body: dict = Body(...)):
    """Add a new set: ``{"text"}`` (its id must be new)."""
    return _call(ql.create, str(body.get("text") or ""))


@router.post("/api/admin/questionnaire-library/check")
def library_check(body: dict = Body(...)):
    """Check a set's text: ``{"text", "original"}`` (``original``: the id being edited, none for a new set)."""
    original = body.get("original") or None
    if original is not None:
        _call(ql.check_id, str(original))
    return {"problems": ql.check(str(body.get("text") or ""), original)}


@router.get("/api/admin/questionnaire-library/{sid}")
def library_get(sid: str):
    return _call(ql.get, sid)


@router.put("/api/admin/questionnaire-library/{sid}")
def library_save(sid: str, body: dict = Body(...)):
    """Save an edit: ``{"text"}``. A bundled set gets an override file; sourced sets are refused (403)."""
    return _call(ql.save, sid, str(body.get("text") or ""))


@router.get("/api/admin/questionnaire-library/{sid}/copy")
def library_copy(sid: str, new_id: str = ""):
    """The text of a new set copied from ``sid`` (not saved)."""
    return {"text": _call(ql.copy_text, sid, new_id)}


# --------------------------------------------------------------------------- #
# Study forms as data (the structured item editor)                             #
# --------------------------------------------------------------------------- #
@router.post("/api/admin/questionnaires/parse")
def form_parse(body: dict = Body(...)):
    """A form's text as data: ``{"text"}`` → ``{"data"}`` (422 when it does not parse)."""
    try:
        return {"data": ql.parse_form(str(body.get("text") or ""))}
    except (ValueError, yaml.YAMLError) as e:
        raise HTTPException(422, f"the form is not valid YAML: {e}") from None


@router.post("/api/admin/questionnaires/dump")
def form_dump(body: dict = Body(...)):
    """Data back to a form's text: ``{"data"}`` → ``{"text", "problems"}`` (nothing is saved)."""
    data = body.get("data")
    if not isinstance(data, dict):
        raise HTTPException(400, "data must be a mapping")
    text = ql.dump_form(data)
    return {"text": text, "problems": questionnaires.validate(text)}
