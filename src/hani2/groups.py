"""Groups: named pools of opponents and of Assistants.

A group is a JSON file. Opponent groups live in ``groups/<key>.json``, Assistant
groups in ``assistant_groups/<key>.json``; both have the same shape::

    ["spec", ...]                                     # a plain list
    {"description": "...",                            # or an object
     "syspath": ["/dir/with/packages", ...],          # added to sys.path (relative: to the file)
     "agents": ["spec", ...],                         # opponent groups (Assistant groups: "assistants")
     "assistant": "pkg.module:Class",                 # opponent groups only: the Assistant for
                                                      # participants arriving with ?group=<key>
                                                      # ("support_agent" is the old name)
     "ai_fallback": false}                            # opponent groups only (default true): a
                                                      # ?group=<key> session never gets an AI
                                                      # opponent (no wait-time fallback, no "play
                                                      # an AI" button); its AI entries are dropped

A group token ``:key`` (or ``?group=key``) is looked up, first hit wins, in

1. the current study's results folder (``<results>/groups/``) — where an outside
   system drops its files, so its groups always win;
2. the study folder (``<study>/groups/``);
3. the project folder (``projects/<P>/groups/``; for the default project: the
   settings folder, ``settings/groups/``);
4. the settings folder (``settings/groups/``), for every project;
5. the built-in groups (opponents: ``:llm``, ``:template``, …; Assistants:
   ``:default`` and ``:tutorial``).

The server only reads these files (and writes project group files when an admin
asks); it never calls another service.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

OPPONENT = "opponent"
ASSISTANT = "assistant"
KINDS = (OPPONENT, ASSISTANT)
SUBDIR = {OPPONENT: "groups", ASSISTANT: "assistant_groups"}
#: the key holding a group's members (Assistant groups also accept "agents")
MEMBERS_KEY = {OPPONENT: "agents", ASSISTANT: "assistants"}
#: keys of an opponent group file naming the Assistant for its participants (new name first)
ASSISTANT_KEYS = ("assistant", "support_agent")
#: key of an opponent group file: ``false`` keeps its sessions to people only (no AI opponent ever)
AI_FALLBACK_KEY = "ai_fallback"
# group keys: letters, digits, '.', '_' and '-' (long enough for hmac-carrying keys)
_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


def valid_key(key: Any) -> bool:
    return isinstance(key, str) and bool(_KEY.match(key)) and ".." not in key


def check_key(key: Any) -> str:
    if not valid_key(key):
        raise ValueError(f"invalid group name {key!r}: use letters, digits, '.', '_' and '-'")
    return key


def check_kind(kind: str) -> str:
    k = {"opponents": OPPONENT, "assistants": ASSISTANT}.get(kind, kind)
    if k not in KINDS:
        raise ValueError(f"group kind must be one of {', '.join(KINDS)}")
    return k


@dataclass
class Group:
    key: str
    kind: str
    members: list[str] = field(default_factory=list)
    syspath: list[str] = field(default_factory=list)
    #: opponent groups: the Assistant(s) named by the file (``assistant`` / ``support_agent``)
    assistant: Any = None
    description: str = ""
    #: results | study | project | settings | builtin
    source: str = "builtin"
    path: Path | None = None
    #: opponent groups: ``False`` when the file says ``"ai_fallback": false`` (people only, no AI opponent)
    ai_fallback: bool = True
    #: why the file cannot be used as written (conflicting keys); its members / Assistant are then empty
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        out = dict(key=self.key, kind=self.kind, members=list(self.members), syspath=list(self.syspath),
                   description=self.description, source=self.source, path=str(self.path) if self.path else None)
        if self.kind == OPPONENT:
            out["assistant"] = self.assistant
            out["ai_fallback"] = self.ai_fallback
        if self.error:
            out["error"] = self.error
        return out


# --------------------------------------------------------------------------- #
# Where group files live                                                       #
# --------------------------------------------------------------------------- #
def project_group_dir(project: str, kind: str) -> Path:
    """The folder of a project's group files (the default project: the settings folder)."""
    from hani2 import projects
    from hani2.config import settings_dir

    sub = SUBDIR[check_kind(kind)]
    if not project or project == projects.DEFAULT_PROJECT:
        return settings_dir() / sub
    return projects.project_dir(project) / sub


def search_dirs(kind: str, ref: Any = None) -> list[tuple[Path, str]]:
    """The folders searched for a group of ``kind``, most specific first, for study
    ``ref`` (default: the current study)."""
    from hani2 import projects
    from hani2.config import home, settings_dir

    kind = check_kind(kind)
    sub = SUBDIR[kind]
    r = projects.current_study() if ref is None else ref
    out: list[tuple[Path, str]] = []
    if r is not None:
        try:
            sdir = projects.study_dir(r)
            out.append((sdir / "results" / sub, "results"))
            out.append((sdir / sub, "study"))
        except ValueError:
            pass
    else:
        out.append((home() / "db" / sub, "results"))
    from hani2.config import view_project

    # an admin view of a project's layer (no study): that project's group files
    proj = r.project if r is not None else (view_project() or projects.DEFAULT_PROJECT)
    try:
        out.append((project_group_dir(proj, kind), "project"))
    except ValueError:
        pass
    s = settings_dir() / sub
    if all(p != s for p, _ in out):
        out.append((s, "settings"))
    return out


def _add_syspath(dirs: list[str]) -> None:
    for d in dirs:
        if d and d not in sys.path:
            sys.path.append(d)


def parse_flag(v: Any, default: bool = True) -> bool:
    """A boolean written in a group file: JSON booleans, ``0``/``1`` and the usual words
    (``"false"``, ``"no"``, ``"off"`` …); anything else is ``default``."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
    return default


def group_problems(data: Any, kind: str) -> list[str]:
    """Keys of a group file that mean the same thing but disagree (``[]``: none)."""
    kind = check_kind(kind)
    if not isinstance(data, dict):
        return []
    out = []
    names = [k for k in (MEMBERS_KEY[kind], "agents", "members") if k in data]
    names = list(dict.fromkeys(names))
    vals = {k: data[k] for k in names}
    if len({repr(v) for v in vals.values()}) > 1:
        out.append(f"the members are given under {', '.join(repr(k) for k in names)} with different values; "
                   f"keep only '{MEMBERS_KEY[kind]}'")
    if kind == OPPONENT:
        given = {k: data[k] for k in ASSISTANT_KEYS if data.get(k)}
        if len({repr(v) for v in given.values()}) > 1:
            out.append(f"'assistant' ({data['assistant']!r}) and its old name 'support_agent' "
                       f"({data['support_agent']!r}) disagree; keep only 'assistant'")
    return out


def load_file(path: Path, kind: str, key: str | None = None, source: str = "") -> Group | None:
    """Read one group file (``None`` when missing or broken); its ``syspath`` is added to ``sys.path``."""
    kind = check_kind(kind)
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - a broken file must not break the server
        print(f"⚠️ Could not read group file {path}: {e}")
        return None
    g = Group(key=key or path.stem, kind=kind, source=source, path=path)
    problems = group_problems(data, kind)
    if problems:
        g.error = f"group file {path}: " + "; ".join(problems)
        print(f"[hani2] ERROR: {g.error}")
    members: Any = data
    if isinstance(data, dict):
        for d in data.get("syspath", []) or []:
            p = Path(str(d)).expanduser()
            if str(d).strip():
                g.syspath.append(str(p if p.is_absolute() else (path.parent / p).resolve()))
        members = data.get(MEMBERS_KEY[kind])
        if members is None:
            members = data.get("agents", [])
        g.description = str(data.get("description") or "")
        if kind == OPPONENT:  # read even from a file with an error: a broken strict file stays strict
            g.ai_fallback = parse_flag(data.get(AI_FALLBACK_KEY), True)
        if kind == OPPONENT and not g.error:
            g.assistant = next((data[k] for k in ASSISTANT_KEYS if data.get(k)), None)
        if g.error and kind == ASSISTANT:
            members = []
    if not isinstance(members, list):
        print(f"⚠️ Group file {path} has no member list")
        members = []
    g.members = [str(x).strip() for x in members if str(x).strip()]
    _add_syspath(g.syspath)
    return g


def find_file(kind: str, key: str, ref: Any = None) -> Group | None:
    """The first group file named ``key`` along :func:`search_dirs` (``None``: no file)."""
    k = key.strip().lstrip(":@")
    if not valid_key(k):
        return None
    for d, source in search_dirs(kind, ref):
        g = load_file(d / f"{k}.json", kind, k, source)
        if g is None and d.is_dir():  # names are case-insensitive: the exact file first, then any case
            f = next((x for x in sorted(d.glob("*.json")) if x.stem.lower() == k.lower() and valid_key(x.stem)), None)
            g = load_file(f, kind, f.stem, source) if f is not None else None
        if g is not None:
            return g
    return None


# --------------------------------------------------------------------------- #
# Built-in groups                                                              #
# --------------------------------------------------------------------------- #
def _tutorial_dir() -> Path | None:
    import hani2

    for cand in (Path(hani2.__file__).resolve().parents[2] / "examples" / "support_agent_tutorial",
                 Path.cwd() / "examples" / "support_agent_tutorial"):
        if cand.is_dir():
            return cand
    return None


#: the tutorial Assistants (module:Class), in level order
TUTORIAL_ASSISTANTS = [
    "level1_hello:HelloAgent", "level2_rules:RulesAgent", "level3_llm_coach:CoachAgent",
    "level4_tools:ToolCoachAgent", "level5_deal_coach:DealCoach", "level6_guided:GuidedAgent",
    "level7_asking:AskingCoach", "level8_spotlight:SpotlightAgent", "level9_panels:PanelAgent",
    "level10_toolsmith:ToolsmithAgent",
]

DEFAULT_ASSISTANT_SPEC = "hani2.assistant:Assistant"


def default_assistant_spec(settings: dict | None = None) -> str:
    """The configured Assistant class (``agent_class`` in assistant_settings.json), else the built-in one."""
    if settings is None:
        from hani2.support_agent import runtime

        settings = runtime.load_support_agent_settings()
    return str((settings or {}).get("agent_class") or "").strip() or DEFAULT_ASSISTANT_SPEC


def tutorial_assistants() -> list[str]:
    """The example tutorial Assistants, when the examples folder is present (else ``[]``)."""
    import importlib.util

    d = _tutorial_dir()
    if d is not None:
        _add_syspath([str(d)])
    out = []
    for spec in TUTORIAL_ASSISTANTS:
        mod = spec.split(":")[0]
        try:
            if importlib.util.find_spec(mod) is not None:
                out.append(spec)
        except (ImportError, ValueError):
            pass
    return out


BUILTIN_DESCRIPTIONS = {
    (ASSISTANT, "default"): "The configured Assistant (agent_class in assistant_settings.json, else the built-in one)",
    (ASSISTANT, "tutorial"): "The tutorial Assistants (examples/support_agent_tutorial), when present",
    (OPPONENT, "llm"): "Negotiators driven by a language model",
    (OPPONENT, "template"): "Strategy negotiators that talk with text templates (no language model)",
    (OPPONENT, "notext"): "Strategy negotiators without text",
    (OPPONENT, "negmas"): "Every negotiator NegMAS ships",
    (OPPONENT, "classic"): "Classic competition agents",
    (OPPONENT, "hani"): "Old name of :classic",
    (OPPONENT, "genius"): "Genius agents (needs the Genius bridge)",
    (OPPONENT, "pan"): "The personality-adjusted pool (pan.py), when present",
    (OPPONENT, "custom"): "The negotiators in HANI2_CUSTOM_AGENTS",
}


def builtin_description(kind: str, key: str) -> str:
    """The description of a built-in group (``""``: none)."""
    k = key.strip().lstrip(":").lower()
    d = BUILTIN_DESCRIPTIONS.get((check_kind(kind), k))
    if d is None and check_kind(kind) == OPPONENT:
        from hani2.agents import HAN_GROUP_DESCRIPTIONS

        d = HAN_GROUP_DESCRIPTIONS.get(k)
    return d or ""


def builtin_keys(kind: str) -> list[str]:
    kind = check_kind(kind)
    if kind == ASSISTANT:
        return ["default", "tutorial"]
    from hani2.agents import AGENT_GROUPS

    return [k.lstrip(":") for k in AGENT_GROUPS] + ["notext", "pan", "custom"]


def builtin_members(kind: str, key: str) -> list[str] | None:
    """The members of a built-in group (``None``: no such built-in)."""
    kind = check_kind(kind)
    k = key.strip().lstrip(":").lower()
    if kind == ASSISTANT:
        if k == "default":
            return [default_assistant_spec()]
        if k == "tutorial":
            return tutorial_assistants()
        return None
    if k not in builtin_keys(OPPONENT):
        return None
    from hani2.agents import _resolve_builtin

    return [str(x) for x in _resolve_builtin(":" + k)]


# --------------------------------------------------------------------------- #
# Resolution                                                                   #
# --------------------------------------------------------------------------- #
def resolve(kind: str, key: str, ref: Any = None) -> Group | None:
    """A group by key: a file along :func:`search_dirs`, else a built-in group."""
    g = find_file(kind, key, ref)
    if g is not None:
        return g
    members = builtin_members(kind, key)
    if members is None:
        return None
    k = key.strip().lstrip(":").lower()
    return Group(key=k, kind=check_kind(kind), members=members, description=builtin_description(kind, k))


def assistant_lookup(ref: Any = None, errors: list[str] | None = None):
    """The :mod:`hani2.composition` lookup of Assistant groups: ``@key`` / ``:key``
    is a group file, else a built-in group (``:default``, ``:tutorial``); a bare
    word without ``.``/``:`` is a group file only. Problems of the group files
    used are appended to ``errors``."""

    def lookup(name: str, explicit: bool):
        if not explicit and ("." in name or ":" in name):
            return None
        g = find_file(ASSISTANT, name, ref)
        if g is not None:
            if g.error and errors is not None:
                errors.append(g.error)
            return g.key, list(g.members)
        if explicit:
            members = builtin_members(ASSISTANT, name)
            if members is not None:
                return name.strip().lower(), members, True
            print(f"⚠️ Unknown Assistant group ':{name}'")
        return None

    return lookup


def expand_assistants(items: Any, ref: Any = None, errors: list[str] | None = None) -> list[str]:
    """Expand Assistant specs and group tokens into a flat, de-duplicated list of
    class specs: ``@key`` / ``:key`` is an Assistant group; a bare word without
    ``.``/``:`` that names an Assistant group file is that group; anything else is
    a class spec. Groups may hold other groups (see :mod:`hani2.composition`).
    Problems of the group files used are appended to ``errors``."""
    from hani2.composition import expand_entries

    if isinstance(items, str):
        items = [s for s in items.split(",") if s.strip()]
    return [str(x) for x in expand_entries(list(items or []), assistant_lookup(ref, errors), label="Assistant group")]


def expand_members(kind: str, key: str, ref: Any = None) -> list[Any] | None:
    """The expanded members of group ``key`` of ``kind`` (``None``: no such group)."""
    from hani2.composition import expand_entries

    kind = check_kind(kind)
    if kind == ASSISTANT:
        lk = assistant_lookup(ref)
    else:
        from hani2.agents import opponent_lookup

        lk = opponent_lookup
    hit = lk(key.strip().lstrip(":@"), True)
    if hit is None:
        return None
    if len(hit) > 2 and hit[2]:
        return list(hit[1])
    return expand_entries(hit[1], lk, name=hit[0], label=f"{kind} group")


def list_groups(kind: str, *, project: str | None = None, ref: Any = None,
                include_builtin: bool = True) -> list[dict[str, Any]]:
    """Every group of ``kind`` with its members, source file and description.

    With ``project``: the project's folder, the settings folder and each of its
    studies (study folder and results). Otherwise the folders searched for study
    ``ref`` (default: the current study). ``active`` marks the file a token resolves to."""
    from hani2 import projects

    kind = check_kind(kind)
    dirs: list[tuple[Path, str]]
    if project is not None:
        projects.check_name(project, "project")
        dirs = [(project_group_dir(project, kind), "project")]
        for st in projects.list_studies(project):
            sdir = projects.study_dir(projects.StudyRef(project, st))
            dirs += [(sdir / "results" / SUBDIR[kind], f"results:{st}"), (sdir / SUBDIR[kind], f"study:{st}")]
        from hani2.config import settings_dir

        s = settings_dir() / SUBDIR[kind]
        if all(p != s for p, _ in dirs):
            dirs.append((s, "settings"))
    else:
        dirs = search_dirs(kind, ref)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for d, source in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            if not valid_key(f.stem):
                continue
            g = load_file(f, kind, f.stem, source)
            if g is None:
                continue
            item = g.to_dict()
            item["active"] = f.stem not in seen if project is None else None
            seen.add(f.stem)
            out.append(item)
    if include_builtin:
        for k in builtin_keys(kind):
            members = builtin_members(kind, k) or []
            out.append(dict(key=k, kind=kind, members=members, syspath=[], source="builtin", path=None,
                            description=builtin_description(kind, k),
                            active=(k not in seen) if project is None else None))
    return out


def prime_syspaths(ref: Any = None) -> None:
    """Add the ``syspath`` of every group file reachable from the current study to
    ``sys.path``, so a dotted spec imports however the session reached it (and
    those of the library's uploaded and linked packages, see :mod:`hani2.library`)."""
    try:
        from hani2 import library

        library.prime_syspaths(ref)
    except Exception as e:  # noqa: BLE001 - a broken library must not break sessions
        print(f"[hani2] library syspaths: {e}")
    for kind in KINDS:
        try:
            dirs = search_dirs(kind, ref)
        except Exception:  # noqa: BLE001
            continue
        for d, _ in dirs:
            if not d.is_dir():
                continue
            for f in sorted(d.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except Exception:  # noqa: BLE001
                    continue
                if isinstance(data, dict):
                    load_file(f, kind, f.stem)


# --------------------------------------------------------------------------- #
# Writing project groups (admin)                                               #
# --------------------------------------------------------------------------- #
def validate_data(kind: str, data: Any) -> dict[str, Any]:
    """Normalise a group's content (a list, or an object with members, syspath, description)."""
    kind = check_kind(kind)
    if isinstance(data, list):
        data = {MEMBERS_KEY[kind]: data}
    if not isinstance(data, dict):
        raise ValueError("a group is a list of specs or an object")
    problems = group_problems(data, kind)
    if problems:
        raise ValueError("; ".join(problems))
    members = data.get(MEMBERS_KEY[kind], data.get("agents", data.get("members")))
    if not isinstance(members, list) or not all(isinstance(x, str) and x.strip() for x in members):
        raise ValueError(f"'{MEMBERS_KEY[kind]}' must be a list of non-empty strings")
    out: dict[str, Any] = {}
    if data.get("description"):
        out["description"] = str(data["description"])
    sp = data.get("syspath") or []
    if not isinstance(sp, list) or not all(isinstance(x, str) for x in sp):
        raise ValueError("'syspath' must be a list of folders")
    if sp:
        out["syspath"] = sp
    out[MEMBERS_KEY[kind]] = [x.strip() for x in members]
    if kind == OPPONENT:
        a = next((data[k] for k in ASSISTANT_KEYS if data.get(k)), None)
        if a is not None:
            if not (isinstance(a, str) or (isinstance(a, list) and all(isinstance(x, str) for x in a))):
                raise ValueError("'assistant' must be a class spec or a list of them")
            out["assistant"] = a
        if AI_FALLBACK_KEY in data:
            f = data[AI_FALLBACK_KEY]
            if not isinstance(f, bool):
                raise ValueError(f"'{AI_FALLBACK_KEY}' must be true or false")
            out[AI_FALLBACK_KEY] = f
    return out


def write_group(project: str, kind: str, key: str, data: Any) -> Path:
    check_key(key)
    clean = validate_data(kind, data)
    f = project_group_dir(project, kind) / f"{key}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    tmp.replace(f)
    return f


def delete_group(project: str, kind: str, key: str) -> bool:
    check_key(key)
    f = project_group_dir(project, kind) / f"{key}.json"
    if f.is_file():
        f.unlink()
        return True
    return False
