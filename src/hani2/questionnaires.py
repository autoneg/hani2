"""Where the study forms come from: the pre-questionnaire, the per-negotiation
questionnaire and the post-session questionnaire.

One resolver serves the running sessions and the admin console, so the console
always names the file a participant actually gets. For each form the first match wins:

1. the environment variables of the form (a path, or a bundled / settings name);
2. the name in ``env.json`` (``pre_questionnaire``, ``questionnaire``, ``post_questionnaire``);
3. ``questionnaires/<file>`` in the study folder, then in its project folder;
4. ``questionnaires/<file>`` in the settings folder.

A file with ``enabled: false`` switches the form off and ends the lookup (so a study can
switch off a form its project defines). A file without questions is skipped.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Form:
    key: str  #: the admin kind, also the ``stage`` of the form in a session
    file: str  #: the file name inside ``questionnaires/``
    env_vars: tuple[str, ...]  #: environment variables naming the form (first set wins)
    env_key: str  #: the ``env.json`` key naming the form
    title: str


FORMS: dict[str, Form] = {
    "pre_questionnaire": Form("pre_questionnaire", "pre_questionnaire.yaml", ("HANI2_PRE_YAML",), "pre_questionnaire",
                              "Pre-questionnaire"),
    "per_negotiation": Form("per_negotiation", "per_negotiation.yaml", ("HANI2_PER_NEG_YAML", "PROLIFIC_PER_NEG_YAML"),
                            "questionnaire", "Per-negotiation questionnaire"),
    "post_session": Form("post_session", "post_session.yaml", ("HANI2_POST_YAML",), "post_questionnaire",
                         "Post-session questionnaire"),
}

#: question types the participant's form can show
QUESTION_TYPES = ("likert5", "likert7", "yes_no", "select", "text")


@dataclass
class Resolved:
    spec: dict | None  #: the form as written (not rendered); ``None``: no form
    path: Path | None = None  #: the file it comes from
    source: str = ""  #: ``env:<VAR>``, ``env.json``, a layer id (``study:P/S``, ``project:P``, ``settings``) or ``bundled``
    disabled: bool = False  #: switched off by ``enabled: false`` in ``path``


def _named(v: str) -> list[Path]:
    """A path, or a bare name (``evaluation``) looked up in the layers, the settings folder and the bundle."""
    from hani2.config import DEFAULT_SETTINGS_DIR, settings_dir, settings_layers

    if "/" in v or v.endswith((".yaml", ".yml")):
        return [Path(v).expanduser()]
    return [*(d / "questionnaires" / f"{v}.yaml" for d in settings_layers()),
            settings_dir() / "questionnaires" / f"{v}.yaml", DEFAULT_SETTINGS_DIR / "questionnaires" / f"{v}.yaml"]


def layer_of(path: Path) -> str:
    """The layer id of a questionnaire file (``<layer>/questionnaires/<file>``)."""
    from hani2.config import DEFAULT_SETTINGS_DIR
    from hani2.layers import list_layers

    try:
        folder = path.resolve().parent.parent
    except OSError:
        return "settings"
    if folder == DEFAULT_SETTINGS_DIR.resolve():
        return "bundled"
    for lay in list_layers():
        try:
            if lay.dir.resolve() == folder:
                return lay.id
        except (OSError, ValueError):
            continue
    return "settings"


def candidates(form: Form | str) -> list[tuple[str, Path]]:
    """Every file the lookup tries, in order, with where it came from."""
    from hani2.config import get_env, settings_dir, settings_layers

    form = FORMS[form] if isinstance(form, str) else form
    out: list[tuple[str, Path]] = []
    for var in form.env_vars:
        if os.environ.get(var):
            out.extend((f"env:{var}", p) for p in _named(os.environ[var]))
    named = get_env(form.env_key, None)
    if named:
        out.extend(("env.json", p) for p in _named(str(named)))
    for layer in settings_layers():  # the study, then its project
        out.append(("", layer / "questionnaires" / form.file))
    out.append(("", settings_dir() / "questionnaires" / form.file))
    return out


def resolve(form: Form | str) -> Resolved:
    """The form in effect for the current study (unrendered), and where it comes from."""
    import yaml

    for origin, p in candidates(form):
        if not p.is_file():
            continue
        try:
            spec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception as e:  # pragma: no cover - reported by the admin console's check
            print(f"[hani2] questionnaire {p} failed to parse: {e}")
            continue
        if not isinstance(spec, dict):
            continue
        source = origin or layer_of(p)
        if spec.get("enabled") is False:
            return Resolved(None, p, source, disabled=True)
        if spec.get("questions"):
            return Resolved(spec, p, source)
    return Resolved(None)


def spec(form: Form | str) -> dict | None:
    """The form in effect, with its ``{{variables}}`` filled in (``None``: no form)."""
    r = resolve(form)
    if r.spec is None:
        return None
    from hani2.templates import render_data

    return render_data(r.spec)


def validate(text: str) -> list[str]:
    """Problems in a questionnaire file (empty: fine). An empty text or ``enabled: false`` is valid."""
    import yaml

    if not text.strip():
        return []
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        return [f"not valid YAML: {e}"]
    if data is None:
        return []
    if not isinstance(data, dict):
        return ["the file must be a mapping (title, intro, questions, ...)"]
    if "enabled" in data and not isinstance(data["enabled"], bool):
        errors = ["enabled must be true or false"]
    else:
        errors = []
    qs = data.get("questions")
    if qs is None:
        if data.get("enabled") is not False:
            errors.append("no questions (add questions, or set enabled: false to switch the form off)")
        return errors
    if not isinstance(qs, list):
        return errors + ["questions must be a list"]
    seen: set[str] = set()
    for i, q in enumerate(qs, 1):
        if not isinstance(q, dict):
            errors.append(f"question {i} is not a mapping")
            continue
        qid = q.get("id")
        if not qid or not isinstance(qid, str):
            errors.append(f"question {i} has no id")
        elif qid in seen:
            errors.append(f"question id {qid!r} is used twice")
        else:
            seen.add(qid)
        if not q.get("text"):
            errors.append(f"question {qid or i} has no text")
        t = q.get("type")
        if t not in QUESTION_TYPES:
            errors.append(f"question {qid or i}: unknown type {t!r} (use {', '.join(QUESTION_TYPES)})")
        if t == "select" and not (isinstance(q.get("options"), list) and q["options"]):
            errors.append(f"question {qid or i}: a select question needs options")
    return errors


def describe(form: Form | str) -> dict[str, Any]:
    """For the admin console: where the form in effect comes from."""
    r = resolve(form)
    return {"source": r.source or "none", "source_path": str(r.path) if r.path else "",
            "disabled": r.disabled, "active": r.spec is not None,
            "n_questions": len((r.spec or {}).get("questions") or [])}


# --------------------------------------------------------------------------- #
# The library of predefined question sets                                     #
# --------------------------------------------------------------------------- #
LIBRARY_DIR = "questionnaire_library"
#: what a new form file starts with
FORM_HEADERS: dict[str, dict[str, str]] = {
    "pre_questionnaire": {"title": "Before you start", "intro": "A few questions before the first negotiation."},
    "per_negotiation": {"title": "After this negotiation", "intro": "A few quick questions about this negotiation. There are no right or wrong answers."},
    "post_session": {"title": "Before you finish", "intro": "A few last questions about the whole session."},
}


def library_dirs() -> list[Path]:
    """Where predefined sets are read from: the bundled library, then the settings folder's
    ``questionnaire_library/`` (a set there replaces a bundled set with the same id)."""
    from hani2.config import DEFAULT_SETTINGS_DIR, settings_dir

    return [DEFAULT_SETTINGS_DIR / LIBRARY_DIR, settings_dir() / LIBRARY_DIR]


def library() -> dict[str, dict]:
    """Every predefined question set by id: ``title``, ``description``, ``reference``,
    ``forms`` (the forms it suits), ``questions`` and ``source`` (``bundled`` or ``settings``)."""
    import yaml

    out: dict[str, dict] = {}
    for i, d in enumerate(library_dirs()):
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.y*ml")):
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception as e:  # pragma: no cover
                print(f"[hani2] questionnaire library file {p} failed to parse: {e}")
                continue
            if not isinstance(data, dict) or not isinstance(data.get("questions"), list):
                continue
            sid = str(data.get("id") or p.stem)
            out[sid] = {"id": sid, "title": str(data.get("title") or sid), "description": str(data.get("description") or ""),
                        "reference": str(data.get("reference") or ""), "forms": list(data.get("forms") or list(FORMS)),
                        "questions": data["questions"], "source": "bundled" if i == 0 else "settings"}
    return out


def _question_yaml(q: dict) -> str:
    import yaml

    text = yaml.safe_dump([q], sort_keys=False, allow_unicode=True, default_flow_style=False, width=1000)
    return "".join("  " + line if line.strip() else line for line in text.splitlines(keepends=True))


def compose(text: str, set_ids: list[str], form: str = "per_negotiation") -> tuple[str, list[str], list[str]]:
    """Add the questions of predefined sets to a form file's text.

    Returns ``(new text, ids added, ids skipped because the form already has them)``. A new or
    empty file gets the form's title and intro. When ``questions:`` is the file's last top-level
    key the questions are appended as text (comments kept); otherwise the file is rewritten."""
    import re

    import yaml

    lib = library()
    unknown = [s for s in set_ids if s not in lib]
    if unknown:
        raise KeyError(f"unknown question set(s): {', '.join(unknown)} (known: {', '.join(sorted(lib))})")
    data = yaml.safe_load(text) if text.strip() else None
    if data is not None and not isinstance(data, dict):
        raise ValueError("the form file must be a mapping")
    data = data or {}
    have = {str(q.get("id")) for q in (data.get("questions") or []) if isinstance(q, dict)}
    added: list[str] = []
    skipped: list[str] = []
    blocks: list[str] = []
    new_qs: list[dict] = []
    for sid in set_ids:
        s = lib[sid]
        qs = []
        for q in s["questions"]:
            qid = str(q.get("id"))
            if qid in have:
                skipped.append(qid)
                continue
            have.add(qid)
            added.append(qid)
            qs.append(dict(q))
        if qs:
            new_qs.extend(qs)
            ref = f" ({s['reference']})" if s["reference"] else ""
            blocks.append(f"  # --- {s['title']}{ref}\n" + "".join(_question_yaml(q) for q in qs))
    if not new_qs:
        return text, added, skipped
    if not text.strip() or not data:
        head = {"version": "1", **FORM_HEADERS.get(form, {})}
        out = yaml.safe_dump(head, sort_keys=False, allow_unicode=True, width=1000) + "questions:\n" + "".join(blocks)
        return out, added, skipped
    lines = text.rstrip("\n").splitlines()
    top = [i for i, line in enumerate(lines) if re.match(r"^[A-Za-z_][\w-]*\s*:", line)]
    last_is_questions = bool(top) and re.match(r"^questions\s*:\s*(#.*)?$", lines[top[-1]]) is not None
    if last_is_questions and data.get("enabled") is not False:
        out = text.rstrip("\n") + "\n" + "".join(blocks)
        try:
            check = yaml.safe_load(out)
            if [str(q.get("id")) for q in check.get("questions", [])][-len(new_qs):] == added:
                return out, added, skipped
        except Exception:
            pass
    data["questions"] = list(data.get("questions") or []) + new_qs
    if data.get("enabled") is False:  # adding questions switches the form back on
        data.pop("enabled")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=1000), added, skipped
