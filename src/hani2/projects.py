"""Projects and studies.

* A **project** is a long-lived research or competition programme. It lives in
  ``$HANI2_HOME/projects/<project>/`` with a ``project.yaml`` (identity and
  defaults) and any settings file (``consent.md``, ``env.json``, …) that its
  studies share.
* A **study** is one data collection inside a project, with its own results:
  ``projects/<project>/studies/<study>/`` with a ``study.yaml``, optional
  overrides of any settings file and ``results/``.

The built-in project ``default`` has no folder layer of its own (its layer is
the settings folder). Its studies are the old experiment folders
``$HANI2_EXPERIMENTS/<name>/`` (default ``$HANI2_HOME/experiments``), read where
they are; ``projects/default/studies/<name>/`` also works.

The *current study* is per session: a context variable bound by the server
for each request (from the URL) and by every session for its own threads.
Without a binding, the process default study is used: ``HANI2_STUDY``
(``project/study``), else the old ``HANI2_EXPERIMENT`` (a study of the default
project), else none (results in ``$HANI2_HOME/db``, as always).
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

DEFAULT_PROJECT = "default"
PROJECT_FILE = "project.yaml"
STUDY_FILE = "study.yaml"
KINDS = ("opponent", "assistant", "none")
STUDY_TYPES = ("prolific", "online", "lab")
#: settings a project gives its studies (a study may override each one)
DEFAULT_KEYS = (
    "scenario_set", "n_required", "practice", "practice_time_limit", "counted_time_limit", "time_limit",
    "n_steps", "minutes", "role_rule", "human_roles", "opponents", "assistants", "scheduling",
    "strict_scenarios", "information", "assistant_starts_on", "questionnaires",
)
PROJECT_FIELDS = ("name", "full_name", "short_description", "link", "year", "kind", "organizer", "contact")
STUDY_FIELDS = ("name", "project", "type", "title", "link", "year", "start", "end", "prolific_study_id",
                "completion_code", "completion_url", "end_text", "organizer", "contact")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def valid_name(name: Any) -> bool:
    """A project or study name: letters, digits, ``.``, ``_`` and ``-`` (no path tricks)."""
    return isinstance(name, str) and bool(_NAME.match(name)) and ".." not in name


def check_name(name: Any, what: str = "name") -> str:
    if not valid_name(name):
        raise ValueError(f"invalid {what} {name!r}: use letters, digits, '.', '_' and '-'")
    return name


@dataclass(frozen=True)
class StudyRef:
    project: str
    study: str

    def __str__(self) -> str:
        return f"{self.project}/{self.study}"

    @property
    def key(self) -> str:
        return str(self)


def parse_ref(text: "str | StudyRef | None") -> StudyRef | None:
    """``"P/S"`` → ``StudyRef("P", "S")``; a bare ``"S"`` is a study of the default project."""
    if text is None or isinstance(text, StudyRef):
        return text
    t = str(text).strip().strip("/")
    if not t:
        return None
    project, _, study = t.rpartition("/") if "/" in t else (DEFAULT_PROJECT, "", t)
    return StudyRef(check_name(project, "project"), check_name(study, "study"))


# --------------------------------------------------------------------------- #
# Folders                                                                      #
# --------------------------------------------------------------------------- #
def projects_root() -> Path:
    from hani2.config import home

    return Path(os.environ.get("HANI2_PROJECTS") or home() / "projects").expanduser()


def project_dir(name: str) -> Path:
    return projects_root() / check_name(name, "project")


def study_dir(ref: StudyRef) -> Path:
    """The study's folder. Studies of the default project are the old experiment
    folders (``$HANI2_EXPERIMENTS/<name>``) unless ``projects/default/studies/<name>`` exists."""
    from hani2.config import experiments_root

    check_name(ref.study, "study")
    new = project_dir(ref.project) / "studies" / ref.study
    if ref.project == DEFAULT_PROJECT and not new.is_dir():
        return experiments_root() / ref.study
    return new


def project_layer_dir(name: str | None) -> Path | None:
    """The settings layer of a project (``None`` for the default project: its layer is the settings folder)."""
    if not name or name == DEFAULT_PROJECT:
        return None
    return project_dir(name)


def project_exists(name: str) -> bool:
    return name == DEFAULT_PROJECT or (valid_name(name) and project_dir(name).is_dir())


def study_exists(ref: StudyRef | None) -> bool:
    if ref is None:
        return True
    try:
        return study_dir(ref).is_dir()
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# project.yaml / study.yaml                                                    #
# --------------------------------------------------------------------------- #
_YAML_CACHE: dict[str, tuple[tuple[int, int], dict]] = {}
_YAML_LOCK = threading.Lock()


def read_yaml(path: Path) -> dict:
    """A YAML mapping (cached by modification time); ``{}`` when missing or broken."""
    import yaml

    try:
        st = path.stat()
        mtime = (st.st_mtime_ns, st.st_size)
    except OSError:
        return {}
    with _YAML_LOCK:
        hit = _YAML_CACHE.get(str(path))
        if hit and hit[0] == mtime:
            return dict(hit[1])
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:  # noqa: BLE001 - a broken edit must not break the server
        print(f"[hani2] ignoring {path}: {e}")
        data = {}
    if not isinstance(data, dict):
        data = {}
    with _YAML_LOCK:
        _YAML_CACHE[str(path)] = (mtime, data)
    return dict(data)


def write_yaml(path: Path, data: dict) -> Path:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    tmp.replace(path)
    return path


@dataclass
class Project:
    name: str
    full_name: str = ""
    short_description: str = ""
    link: str = ""
    year: Any = None
    kind: str = "none"  # opponent | assistant | none
    organizer: str = ""
    contact: str = ""
    #: defaults for the project's studies (scenario_set, n_required, practice, time limits, …)
    defaults: dict[str, Any] = field(default_factory=dict)
    #: any other key of project.yaml (available to texts as ``project_<key>``)
    extra: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None
    #: problems found when reading project.yaml (conflicting keys, unknown scheduling methods)
    errors: list[str] = field(default_factory=list)

    @property
    def file(self) -> Path:
        return project_dir(self.name) / PROJECT_FILE

    def to_dict(self) -> dict[str, Any]:
        out = {k: getattr(self, k) for k in PROJECT_FIELDS}
        out["defaults"] = dict(self.defaults)
        out.update(self.extra)
        return out


@dataclass
class Study:
    name: str
    project: str = DEFAULT_PROJECT
    type: str = "prolific"  # prolific | online | lab
    title: str = ""
    link: str = ""
    year: Any = None
    start: str = ""
    end: str = ""
    prolific_study_id: str = ""
    completion_code: str = ""
    completion_url: str = ""
    end_text: str = ""
    organizer: str = ""
    contact: str = ""
    #: overrides of the project's defaults
    overrides: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None
    #: an old experiment folder (no study.yaml)
    legacy: bool = False
    #: problems found when reading study.yaml (conflicting keys, unknown scheduling methods)
    errors: list[str] = field(default_factory=list)

    @property
    def ref(self) -> StudyRef:
        return StudyRef(self.project, self.name)

    def to_dict(self) -> dict[str, Any]:
        out = {k: getattr(self, k) for k in STUDY_FIELDS}
        out["overrides"] = dict(self.overrides)
        out.update(self.extra)
        return out


def _split(data: dict, fields: tuple[str, ...], nested: str) -> tuple[dict, dict, dict]:
    known = {k: data[k] for k in fields if k in data}
    settings = dict(data.get(nested) or {}) if isinstance(data.get(nested), dict) else {}
    extra: dict[str, Any] = {}
    for k, v in data.items():
        if k in fields or k == nested:
            continue
        if k in DEFAULT_KEYS:
            settings.setdefault(k, v)
        else:
            extra[k] = v
    return known, settings, extra


def file_problems(data: dict, nested: str) -> list[str]:
    """What is wrong with a project.yaml (``nested="defaults"``) or study.yaml
    (``nested="overrides"``) mapping: a setting given both at the top level and under
    ``nested`` with different values (they mean the same thing), and unknown
    scheduling methods."""
    from hani2 import scheduling

    out: list[str] = []
    inner = data.get(nested)
    if inner is not None and not isinstance(inner, dict):
        out.append(f"'{nested}' must be a mapping")
        inner = {}
    inner = inner or {}
    for k in DEFAULT_KEYS:
        if k in data and k in inner and data[k] != inner[k]:
            out.append(f"'{k}' is given twice with different values (top level: {data[k]!r}, "
                       f"under '{nested}': {inner[k]!r}); keep one")
    for where, d in (("scheduling", data.get("scheduling")), (f"{nested}.scheduling", inner.get("scheduling"))):
        try:
            scheduling.check_scheduling(d, where)
        except ValueError as e:
            out.append(str(e))
    return out


def check_file_data(data: dict, nested: str) -> dict:
    """``data`` when :func:`file_problems` finds nothing, else a ValueError naming every problem."""
    problems = file_problems(data, nested)
    if problems:
        raise ValueError("; ".join(problems))
    return data


def _report(problems: list[str], where: Path) -> list[str]:
    for p in problems:
        key = f"{where}: {p}"
        if key not in _REPORTED:
            _REPORTED.add(key)
            print(f"[hani2] ERROR: {key}")
    return problems


_REPORTED: set[str] = set()


def _no_none(known: dict[str, Any]) -> dict[str, Any]:
    """Text fields given as ``null`` in the YAML read as ``""`` (``year`` may stay ``None``)."""
    return {k: ("" if v is None and k != "year" else v) for k, v in known.items()}


def _ref(ref: "StudyRef | str") -> StudyRef:
    r = parse_ref(ref)
    if r is None:
        raise ValueError("a study is needed (project/study)")
    return r


def load_project(name: str) -> Project:
    check_name(name, "project")
    path = project_dir(name)
    data = read_yaml(path / PROJECT_FILE)
    known, defaults, extra = _split(data, PROJECT_FIELDS, "defaults")
    known.pop("name", None)
    known = _no_none(known)
    kind = str(known.pop("kind", "none") or "none").lower()
    return Project(name=name, kind=kind if kind in KINDS else "none", defaults=defaults, extra=extra,
                   path=path if path.is_dir() else None,
                   errors=_report(file_problems(data, "defaults"), path / PROJECT_FILE),
                   **{k: v for k, v in known.items()})


def load_study(ref: "StudyRef | str") -> Study:
    ref = _ref(ref)
    folder = study_dir(ref)
    f = folder / STUDY_FILE
    data = read_yaml(f)
    known, overrides, extra = _split(data, STUDY_FIELDS, "overrides")
    known.pop("name", None)
    known.pop("project", None)
    known = _no_none(known)
    stype = str(known.pop("type", "prolific") or "prolific").lower()
    for k in ("start", "end", "completion_code", "prolific_study_id"):
        if k in known and not isinstance(known[k], str):
            known[k] = str(known[k])
    return Study(name=ref.study, project=ref.project, type=stype if stype in STUDY_TYPES else "prolific",
                 overrides=overrides, extra=extra, path=folder, legacy=not f.exists(),
                 errors=_report(file_problems(data, "overrides"), f), **known)


def list_projects() -> list[str]:
    root = projects_root()
    names = {DEFAULT_PROJECT}
    if root.is_dir():
        names |= {p.name for p in root.iterdir() if p.is_dir() and valid_name(p.name)}
    return sorted(names, key=lambda n: (n != DEFAULT_PROJECT, n.lower()))


def list_studies(project: str) -> list[str]:
    from hani2.config import experiments_root

    names: set[str] = set()
    dirs = [project_dir(project) / "studies"]
    if project == DEFAULT_PROJECT:
        dirs.append(experiments_root())
    for d in dirs:
        if d.is_dir():
            names |= {p.name for p in d.iterdir() if p.is_dir() and valid_name(p.name)}
    return sorted(names, key=str.lower)


def _merge_fields(data: dict, fields: dict) -> None:
    """``data.update(fields)`` without ``None`` values; ``scheduling`` merges per dimension."""
    for k, v in fields.items():
        if v is None:
            continue
        if k == "scheduling" and isinstance(v, dict) and isinstance(data.get(k), dict):
            data[k] = {**data[k], **v}
        else:
            data[k] = v


def create_project(name: str, **fields: Any) -> Project:
    """Create (or update) ``projects/<name>/project.yaml``."""
    check_name(name, "project")
    f = project_dir(name) / PROJECT_FILE
    data = read_yaml(f)
    _merge_fields(data, fields)
    if not data.get("kind"):
        data["kind"] = "none"
    if data["kind"] not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    check_file_data(data, "defaults")
    write_yaml(f, data)
    (f.parent / "studies").mkdir(exist_ok=True)
    return load_project(name)


def create_study(ref: "StudyRef | str", **fields: Any) -> Study:
    """Create (or update) a study folder with its ``study.yaml`` and ``results/``.
    The project is created when it does not exist yet."""
    ref = _ref(ref)
    if ref.project != DEFAULT_PROJECT and not project_dir(ref.project).is_dir():
        create_project(ref.project)
    folder = study_dir(ref)
    data = read_yaml(folder / STUDY_FILE)
    _merge_fields(data, fields)
    if not data.get("type"):
        data["type"] = "prolific"
    if data["type"] not in STUDY_TYPES:
        raise ValueError(f"type must be one of {', '.join(STUDY_TYPES)}")
    check_file_data(data, "overrides")
    write_yaml(folder / STUDY_FILE, data)
    (folder / "results").mkdir(parents=True, exist_ok=True)
    return load_study(ref)


# --------------------------------------------------------------------------- #
# The current study                                                            #
# --------------------------------------------------------------------------- #
_UNSET: Any = object()
UNSET = _UNSET
_CURRENT: contextvars.ContextVar[Any] = contextvars.ContextVar("hani2_study", default=_UNSET)
#: the study each live session belongs to (so code running for a session id finds it)
_SID_STUDY: dict[str, "StudyRef | None"] = {}


def default_study() -> StudyRef | None:
    """The process default study: ``HANI2_STUDY`` (``project/study``), else ``HANI2_EXPERIMENT``, else none."""
    for var in ("HANI2_STUDY", "HANI2_EXPERIMENT"):
        v = (os.environ.get(var) or "").strip()
        if v:
            try:
                return parse_ref(v) if var == "HANI2_STUDY" else StudyRef(DEFAULT_PROJECT, v)
            except ValueError:
                return StudyRef(DEFAULT_PROJECT, v) if var == "HANI2_EXPERIMENT" else None
    return None


def current_study() -> StudyRef | None:
    """The study the current code runs for: the bound one, else the study of the
    session this thread works for, else the process default."""
    v = _CURRENT.get()
    if v is not _UNSET:
        return v
    try:
        from hani2.recording.recorder import CURRENT_SID

        sid = CURRENT_SID.get()
    except Exception:  # pragma: no cover
        sid = None
    if sid and sid in _SID_STUDY:
        return _SID_STUDY[sid]
    return default_study()


def is_bound() -> bool:
    return _CURRENT.get() is not _UNSET


@contextlib.contextmanager
def use_study(ref: "StudyRef | str | None") -> Iterator[StudyRef | None]:
    """Run a block for study ``ref`` (``None``: no study)."""
    r = parse_ref(ref) if isinstance(ref, str) else ref
    tok = _CURRENT.set(r)
    try:
        yield r
    finally:
        _CURRENT.reset(tok)


def bind(fn: Callable, ref: "StudyRef | None" = _UNSET) -> Callable:
    """``fn`` wrapped to run for study ``ref`` (default: the current one) — for
    handing work to another thread, which does not inherit the binding."""
    r = current_study() if ref is _UNSET else ref

    @functools.wraps(fn)
    def _run(*a: Any, **kw: Any) -> Any:
        with use_study(r):
            return fn(*a, **kw)

    return _run


def register_session(sid: str, ref: StudyRef | None) -> None:
    _SID_STUDY[sid] = ref


def forget_session(sid: str) -> None:
    _SID_STUDY.pop(sid, None)


def study_of_session(sid: str | None) -> StudyRef | None:
    if sid and sid in _SID_STUDY:
        return _SID_STUDY[sid]
    return current_study()


def stamp(ref: "StudyRef | None" = _UNSET) -> dict[str, str]:
    """``{"project": ..., "study": ...}`` for results rows, events and recordings."""
    r = current_study() if ref is _UNSET else ref
    return {"project": r.project if r else DEFAULT_PROJECT, "study": r.study if r else ""}


# --------------------------------------------------------------------------- #
# Settings of the current study                                                #
# --------------------------------------------------------------------------- #
def current_project_name() -> str:
    r = current_study()
    return r.project if r else DEFAULT_PROJECT


def get_study(ref: "StudyRef | None" = _UNSET) -> Study | None:
    r = current_study() if ref is _UNSET else ref
    if r is None:
        return None
    try:
        return load_study(r)
    except ValueError:
        return None


def get_project(ref: "StudyRef | None" = _UNSET) -> Project:
    r = current_study() if ref is _UNSET else ref
    try:
        return load_project(r.project if r else DEFAULT_PROJECT)
    except ValueError:
        return Project(name=DEFAULT_PROJECT)


def setting(key: str, default: Any = None, env: str | None = None, cast: Callable | None = None,
            ref: "StudyRef | None" = _UNSET) -> Any:
    """A study setting: the environment variable ``env`` when set (an outside
    system's explicit input wins), else the study's override, else the
    project's default, else ``default``."""
    raw: Any = None
    if env and (os.environ.get(env) or "").strip():
        raw = os.environ[env]
    else:
        st = get_study(ref)
        if st is not None and st.overrides.get(key) is not None:  # a blank `key:` in study.yaml inherits
            raw = st.overrides[key]
        else:
            pr = get_project(ref)
            if key in pr.defaults:
                raw = pr.defaults[key]
    if raw is None:
        return default
    if cast is None:
        return raw
    try:
        if cast is bool and isinstance(raw, str):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        return cast(raw)
    except (TypeError, ValueError):
        return default


def study_url_prefix(ref: StudyRef | None) -> str:
    """The in-app path prefix of a study's pages (``/s/<project>/<study>``)."""
    return f"/s/{ref.project}/{ref.study}" if ref is not None else ""


def participant_links(ref: StudyRef, base_url: str) -> dict[str, str]:
    """The URLs to give participants of a study."""
    base = base_url.rstrip("/") + study_url_prefix(ref)
    st = load_study(ref)
    links = {"app": f"{base}/app", "play": f"{base}/play"}
    if st.type == "prolific":
        links["prolific"] = (f"{base}/play?PROLIFIC_PID={{{{%PROLIFIC_PID%}}}}&STUDY_ID={{{{%STUDY_ID%}}}}"
                             f"&SESSION_ID={{{{%SESSION_ID%}}}}")
    elif st.type == "online":
        links["participant"] = f"{base}/play?pid=<PARTICIPANT_ID>"
    else:
        links["session_code"] = f"{base}/play?code=<SESSION_CODE>"
    return links


def public_base_url() -> str:
    """Where participants reach this server (``HANI2_PUBLIC_URL``, else ``public_url`` in env.json)."""
    v = (os.environ.get("HANI2_PUBLIC_URL") or "").strip()
    if not v:
        from hani2.config import get_env

        v = str(get_env("public_url", "") or "")
    if not v:
        from hani2.config import DEFAULT_PORT

        root = (os.environ.get("HANI2_ROOT_PATH") or "").strip().strip("/")
        v = f"http://localhost:{DEFAULT_PORT}" + (f"/{root}" if root else "")
    return v.rstrip("/")
