"""The questionnaire library as the admin console edits it: every predefined set with where it
comes from (bundled, your own, or your own overriding a bundled set), the file that defines it,
whether it may be edited in the app, and saving, adding and copying sets.

The sets themselves are read by :func:`hani2.questionnaires.library` (one scanner for the
sessions, the CLI and the console). This module adds the rules of the editor:

* **Sourced sets are read-only in the app.** A set is *sourced* when it reproduces a published
  instrument: the metric catalogue (:data:`hani2.evaluation.catalog.QUESTIONNAIRES`) cites one
  for its id (SVI, SUS, UEQ-S, UEQ, TAM, trust in automation, NASA-TLX), or its file has a
  ``url`` linking to one. (``reference`` alone does not count: HANI2's own sets name themselves
  there.) Such a set can only be copied ("Copy as new"): the copy gets a new id, no
  ``reference`` or ``url``, and ``based_on`` / ``copied_from`` keep its origin. Edit the file by
  hand to change a sourced set.
* **The app never writes into the package.** Editing a bundled set writes an override,
  ``<settings>/questionnaire_library/<id>.yaml``; editing your own set rewrites the file that
  defines it. Files are written atomically.
* **No deletion in the app.** Each own set carries the command that removes its file; removing
  an override restores the bundled set.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Any

import yaml

from hani2 import questionnaires

#: the ids the app accepts (letters, digits, ``_`` and ``-``; no dots or slashes, so no path traversal)
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")

#: what a new blank set starts with
BLANK = """id: my_set
title: "My questions"
description: "What these questions measure."
forms: [per_negotiation]
questions:
  - {id: my_question, text: "How satisfied are you with this negotiation?", type: likert7, required: true, labels: {1: "Not at all", 7: "Very"}}
"""


class LibraryError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def own_dir() -> Path:
    """Where the app writes sets: ``questionnaire_library/`` in the settings folder."""
    return questionnaires.library_dirs()[-1]


def check_id(sid: str) -> str:
    if not isinstance(sid, str) or not ID_RE.match(sid):
        raise LibraryError(400, f"invalid set id {sid!r}: use letters, digits, _ and - (at most 80)")
    return sid


def _read(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _bundled() -> dict[str, dict]:
    """The bundled sets by id, with their path (whether or not an own file overrides them)."""
    d = questionnaires.library_dirs()[0]
    out: dict[str, dict] = {}
    for p in sorted(d.glob("*.y*ml")) if d.is_dir() else []:
        data = _read(p)
        if isinstance(data.get("questions"), list):
            out[str(data.get("id") or p.stem)] = {**data, "path": str(p)}
    return out


def _citation(sid: str) -> str:
    from hani2.evaluation import catalog

    info = catalog.QUESTIONNAIRES.get(sid)
    return info.citation if info else ""


def _warning(*ids: str) -> str:
    from hani2.evaluation import catalog

    for i in ids:
        if i and catalog.QUESTIONNAIRE_WARNINGS.get(i):
            return catalog.QUESTIONNAIRE_WARNINGS[i]
    return ""


def source_of(sid: str, data: dict) -> str:
    """The published instrument a set reproduces (empty: none, so the app may edit it): the
    catalogue's citation for its id, or the ``reference`` (else the ``url``) of a file with a ``url``."""
    cited = _citation(sid)
    if cited:
        return cited
    if str(data.get("url") or "").strip():
        return str(data.get("reference") or data["url"]).strip()
    return ""


def _delete_hint(path: str, override: bool) -> dict[str, str]:
    return {"command": f"rm {shlex.quote(path)}", "file": path,
            "effect": "The bundled version comes back." if override else "The set disappears from the library."}


def entries() -> list[dict[str, Any]]:
    """Every set for the admin console, with ``origin`` (``bundled``, ``own`` or ``override``),
    ``path``, ``bundled_path`` (an override), ``read_only`` and why, ``scales``, the validation mark,
    the source warning and how to delete its file (own sets only)."""
    from hani2.evaluation import catalog

    bundled = _bundled()
    out = []
    for sid, s in questionnaires.library().items():
        data = _read(Path(s["path"]))
        origin = "bundled" if s["source"] == "bundled" else ("override" if sid in bundled else "own")
        source = source_of(sid, data)
        copied = str(data.get("copied_from") or "")
        payload = catalog.questionnaire_payload(sid) if origin == "bundled" else {"validated": False}
        scales = list(dict.fromkeys(str(q["scale"]) for q in s["questions"] if isinstance(q, dict) and q.get("scale")))
        e = {**s, **payload, "origin": origin, "n_questions": len(s["questions"]), "scales": scales,
             "based_on": str(data.get("based_on") or ""), "copied_from": copied,
             "read_only": bool(source), "source_citation": source,
             "warning": _warning(sid, copied), "url": payload.get("url") or str(data.get("url") or "")}
        if origin == "override":
            e["bundled_path"] = bundled[sid]["path"]
        if origin != "bundled":
            e["delete"] = _delete_hint(s["path"], origin == "override")
        out.append(e)
    return out


def broken_files() -> list[dict[str, str]]:
    """Files in the settings folder's library that are not sets (bad YAML, no questions): to fix or delete."""
    d = own_dir()
    out = []
    for p in sorted(d.glob("*.y*ml")) if d.is_dir() else []:
        try:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception as e:
            out.append({"path": str(p), "problem": f"not valid YAML: {e}", "command": f"rm {shlex.quote(str(p))}"})
            continue
        if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
            out.append({"path": str(p), "problem": "not a question set (no questions list)",
                        "command": f"rm {shlex.quote(str(p))}"})
    return out


def get(sid: str) -> dict[str, Any]:
    """One set with the text of the file that defines it."""
    check_id(sid)
    e = next((x for x in entries() if x["id"] == sid), None)
    if e is None:
        raise LibraryError(404, f"no question set {sid!r}")
    return {**e, "text": Path(e["path"]).read_text(encoding="utf-8")}


def check(text: str, original: str | None = None, *, in_app: bool = True) -> list[str]:
    """Problems in a set's text (empty: it may be saved). ``original``: the id of the set being
    edited (``None``: a new set). The question rules are those of the Study forms editor and
    ``hani2 questionnaire check`` (:func:`hani2.questionnaires.validate`). ``in_app=False``
    (``hani2 questionnaire check --set``) checks a file as written: no id uniqueness, and a ``url`` is fine."""
    if not text.strip():
        return ["the set is empty"]
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"not valid YAML: {e}"]
    if not isinstance(data, dict):
        return ["the set must be a mapping (id, title, description, forms, questions)"]
    errors: list[str] = []
    sid = data.get("id")
    lib = questionnaires.library()
    if not isinstance(sid, str) or not sid:
        errors.append("the set has no id")
    elif not ID_RE.match(sid):
        errors.append(f"invalid id {sid!r}: use letters, digits, _ and - (at most 80)")
    elif not in_app:
        pass
    elif original is None and sid in lib:
        errors.append(f"the id {sid!r} is already used by another set")
    elif original is not None and sid != original:
        errors.append(f"the id must stay {original!r} (use Copy as new for another id)")
    if not str(data.get("title") or "").strip():
        errors.append("the set has no title")
    forms = data.get("forms")
    if forms is not None:
        if not isinstance(forms, list) or not forms:
            errors.append(f"forms must be a non-empty list of {', '.join(questionnaires.FORMS)}")
        else:
            bad = [str(f) for f in forms if f not in questionnaires.FORMS]
            if bad:
                errors.append(f"unknown form(s) {', '.join(bad)} (use {', '.join(questionnaires.FORMS)})")
    if in_app and str(data.get("url") or "").strip():
        errors.append("a set saved in the app cannot have a url (a link to a published source makes it read-only); "
                      "put the source in based_on instead")
    if "enabled" in data:
        errors.append("enabled belongs to form files, not to sets")
    if not isinstance(data.get("questions"), list) or not data["questions"]:
        errors.append("the set has no questions")
    else:
        errors.extend(questionnaires.validate(yaml.safe_dump({"questions": data["questions"]}, allow_unicode=True)))
    return errors


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _inside(path: Path, folder: Path) -> Path:
    if path.resolve().parent != folder.resolve():
        raise LibraryError(400, "refusing to write outside the settings folder's questionnaire_library/")
    return path


def save(sid: str, text: str) -> dict[str, Any]:
    """Save an edit of set ``sid``: a bundled set gets an override file, your own set's file is
    rewritten. Sourced sets are refused (copy them instead)."""
    check_id(sid)
    e = next((x for x in entries() if x["id"] == sid), None)
    if e is None:
        raise LibraryError(404, f"no question set {sid!r}")
    if e["read_only"]:
        raise LibraryError(403, f"{sid} cites a published source ({e['source_citation']}) and is read-only in the "
                                "app: use Copy as new, or edit its file by hand")
    problems = check(text, original=sid)
    if problems:
        raise LibraryError(422, "; ".join(problems))
    folder = own_dir()
    if e["origin"] == "bundled":
        target = folder / f"{sid}.yaml"
        if target.exists() and str(_read(target).get("id") or target.stem) != sid:
            raise LibraryError(409, f"{target} already defines another set")
    else:
        target = Path(e["path"])
    _write(_inside(target, folder), text)
    return {"ok": True, "id": sid, "path": str(target), "origin": "own" if e["origin"] == "own" else "override"}


def create(text: str) -> dict[str, Any]:
    """Add a new set (its id must be new: creating never overrides a set)."""
    problems = check(text)
    if problems:
        raise LibraryError(422, "; ".join(problems))
    sid = yaml.safe_load(text)["id"]
    target = own_dir() / f"{sid}.yaml"
    if target.exists():
        raise LibraryError(409, f"{target} already exists")
    _write(_inside(target, own_dir()), text)
    return {"ok": True, "id": sid, "path": str(target), "origin": "own"}


def dump_set(data: dict) -> str:
    """A set as YAML in the library's style: header keys, then one flow line per question."""
    head = {k: v for k, v in data.items() if k != "questions"}
    out = yaml.safe_dump(head, sort_keys=False, allow_unicode=True, width=1000) if head else ""
    lines = [f"  - {yaml.safe_dump(q, default_flow_style=True, sort_keys=False, allow_unicode=True, width=100000).strip()}"
             for q in data.get("questions") or []]
    return out + ("questions:\n" + "\n".join(lines) + "\n" if lines else "questions: []\n")


def copy_text(sid: str, new_id: str = "") -> str:
    """The text of a new set copied from ``sid`` (nothing is saved): a new id, no ``reference``,
    and ``based_on`` (the source, or the set's title) and ``copied_from`` (its id)."""
    check_id(sid)
    lib = questionnaires.library()
    if sid not in lib:
        raise LibraryError(404, f"no question set {sid!r}")
    data = _read(Path(lib[sid]["path"]))
    source = source_of(sid, data)
    if not new_id:
        new_id = f"{sid}_copy"
        n = 2
        while new_id in lib:
            new_id, n = f"{sid}_copy{n}", n + 1
    check_id(new_id)
    out: dict[str, Any] = {"id": new_id, "title": f"{lib[sid]['title']} (copy)"}
    for k, v in data.items():
        if k not in ("id", "title", "reference", "url", "based_on", "copied_from", "questions"):
            out[k] = v
    out["based_on"] = source or str(data.get("based_on") or "") or f"{lib[sid]['title']} ({sid}; {lib[sid]['reference']})".replace("; )", ")")
    out["copied_from"] = str(data.get("copied_from") or "") or sid  # the first set of the chain (its warnings)
    out["questions"] = [dict(q) for q in lib[sid]["questions"]]
    return dump_set(out)


# --------------------------------------------------------------------------- #
# Form files as data, for the structured item editor of the Study forms page   #
# --------------------------------------------------------------------------- #
def _int_keys(v: Any) -> Any:
    """JSON turns ``labels: {1: ...}`` keys into strings; give digit keys back their numbers."""
    if isinstance(v, dict):
        return {(int(k) if isinstance(k, str) and re.fullmatch(r"-?\d+", k) else k): _int_keys(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_int_keys(x) for x in v]
    return v


def parse_form(text: str) -> dict:
    """A form file's text as data (``{}`` for an empty text); raises ``ValueError`` when it is not a mapping."""
    data = yaml.safe_load(text) if text.strip() else {}
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("the form file must be a mapping")
    return data


def dump_form(data: dict) -> str:
    """A form as YAML: its keys in order, ``questions`` last with one flow line per question."""
    return dump_set(_int_keys(data)) if data.get("questions") is not None else yaml.safe_dump(
        _int_keys(data), sort_keys=False, allow_unicode=True, width=1000)
