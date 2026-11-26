"""HAN agents of the current year, from the submitted zips.

Where the agents of a ``:han<year>-<set>`` group come from:

* the **current year** (``han.current_year`` in env.json, set explicitly, never the clock)
  comes from that year's **submissions index**;
* **every other year** comes from the installed ``han-agents`` package
  (:func:`hani2.agents.han_groups`);
* a year that neither covers has no agents (refused when a project or study is saved,
  reported when a hand-edited file is read).

The submissions of a year are a folder named in env.json::

    "han": {"current_year": 2027,
            "submissions": {"2027": {"dir": "~/anac/_agents_han/2027"}}}

The folder holds the zips and an ``index.json`` with one entry per submission::

    [{"entrant": "sub_0981", "team": "t17", "zip": "t17.zip",
      "class": "t17_agent.agent:MyNegotiator",
      "qualified": true, "finalist": false, "winner": false}]

The index is read tolerantly (see :func:`read_index`): a list or a mapping holding the list,
other spellings of the keys, flags as booleans or words, ``winner`` implying ``finalist``
implying ``qualified``, and unknown keys ignored.

``hani2 han import --year <y>`` unpacks each zip, without running anything, into a new folder
``<HANI2_HOME>/han_submissions/<y>/<entrant>/<sha256 of the zip>/`` and then checks, in a
separate process, that the class imports. A new upload (a new hash) is a new folder, so an
agent can be updated without changing what past games mean: every game records the version it
played (``opponent_han_version``). ``hani2 han check --year <y>`` lists the entries, their sets
and whether each imports.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SETS = ("all", "qualified", "finalists", "winners")
SOURCE_SUBMISSIONS = "submissions"
SOURCE_PACKAGE = "han-agents"
#: a group file that names the agents by class path and gives their year (``han_year``)
SOURCE_GROUP_FILE = "group-file"
INDEX_FILE = "index.json"
CURRENT_FILE = "current.json"
#: seconds the class-import check of one submission may take
IMPORT_TIMEOUT = 120
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_KEY_ALIASES = {
    "entrant": ("entrant", "entrant_id", "id", "submission", "submission_id", "entry", "entry_id"),
    "team": ("team", "team_id", "team_name"),
    "zip": ("zip", "zip_file", "file", "filename", "archive", "path"),
    "class": ("class", "class_name", "agent_class", "agent_class_name", "negotiator", "spec"),
    "name": ("name", "label", "agent_name", "title"),
    "sha256": ("sha256", "hash", "zip_sha256"),
    "qualified": ("qualified", "is_qualified"),
    "finalist": ("finalist", "finalists", "is_finalist"),
    "winner": ("winner", "winners", "is_winner"),
}


# --------------------------------------------------------------------------- #
# Settings                                                                     #
# --------------------------------------------------------------------------- #
def _int(v: Any) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def current_year() -> int | None:
    """``han.current_year`` from env.json (``None``: not set, every year comes from ``han-agents``)."""
    from hani2.config import get_env

    return _int(get_env("han.current_year", None))


def submissions_dir(year: int) -> Path | None:
    """The folder of a year's submissions (``han.submissions.<year>``: ``{"dir": ...}`` or a path)."""
    from hani2.config import get_env

    conf = get_env("han.submissions", {}) or {}
    if not isinstance(conf, dict):
        return None
    v = conf.get(str(year), conf.get(year)) if isinstance(conf, dict) else None
    if isinstance(v, dict):
        v = v.get("dir") or v.get("path")
    if not v:
        return None
    return Path(os.path.expandvars(str(v))).expanduser()


def import_root() -> Path:
    """Where imported submissions are unpacked (``han.import_dir``, else ``<HANI2_HOME>/han_submissions``)."""
    from hani2.config import get_env, home

    v = get_env("han.import_dir", None)
    return Path(os.path.expandvars(str(v))).expanduser() if v else home() / "han_submissions"


def package_years() -> list[int]:
    from hani2.agents import han_years

    return han_years()


def year_covered(year: int) -> bool:
    """Whether a source has the agents of ``year``: the submissions (the current year) or ``han-agents``."""
    return year == current_year() or year in package_years()


def source_of(year: int) -> str | None:
    """``submissions``, ``han-agents`` or ``None`` (no source covers ``year``)."""
    if year == current_year():
        return SOURCE_SUBMISSIONS
    return SOURCE_PACKAGE if year in package_years() else None


def coverage_text() -> str:
    """What the sources cover, for error messages."""
    years = package_years()
    cy = current_year()
    parts = [f"han-agents covers {', '.join(map(str, years))}" if years else "han-agents is not installed"]
    parts.append(f"the submissions cover {cy} (han.current_year)" if cy else "han.current_year is not set")
    return "; ".join(parts)


def source_text(year: int) -> str:
    """Where the agents of ``year`` come from, for ``hani2 study show``."""
    src = source_of(year)
    if src == SOURCE_SUBMISSIONS:
        d = submissions_dir(year)
        return f"the submissions of {year} ({d if d else 'han.submissions is not set for this year'})"
    if src == SOURCE_PACKAGE:
        return f"the han-agents package ({package_version() or 'version unknown'})"
    return f"no agents for {year} ({coverage_text()})"


def package_version() -> str:
    """The installed ``han-agents`` version (``""``: unknown)."""
    try:
        from importlib.metadata import version

        return version("han-agents")
    except Exception:  # noqa: BLE001
        try:
            import han_agents  # type: ignore

            return str(getattr(han_agents, "__version__", "") or "")
        except Exception:  # noqa: BLE001
            return ""


# --------------------------------------------------------------------------- #
# The index                                                                    #
# --------------------------------------------------------------------------- #
def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on", "x")


def safe_name(text: Any) -> str:
    """A folder name made from untrusted text (letters, digits, ``.``, ``_``, ``-``; no ``..``)."""
    s = _SAFE.sub("_", str(text or "").strip()).strip("._-")
    return s.replace("..", "_")[:64]


def dotted(cls: str) -> str:
    """``pkg.module:Class`` → ``pkg.module.Class`` (a dotted path is kept)."""
    return str(cls or "").strip().replace(":", ".")


@dataclass
class Entry:
    """One submission of the index."""

    entrant: str
    team: str = ""
    zip: str = ""
    cls: str = ""
    name: str = ""
    sha256: str = ""
    qualified: bool = False
    finalist: bool = False
    winner: bool = False
    problems: list[str] = field(default_factory=list)

    @property
    def spec(self) -> str:
        return dotted(self.cls)

    @property
    def sets(self) -> list[str]:
        """The sets this entry is in (``winner`` ⇒ ``finalists`` ⇒ ``qualified``)."""
        out = ["all"]
        if self.qualified or self.finalist or self.winner:
            out.append("qualified")
        if self.finalist or self.winner:
            out.append("finalists")
        if self.winner:
            out.append("winners")
        return out


def _get(raw: dict, key: str) -> Any:
    for k in _KEY_ALIASES[key]:
        if k in raw and raw[k] not in (None, ""):
            return raw[k]
    return None


def _entry(raw: Any, fallback_id: str = "") -> Entry | None:
    if not isinstance(raw, dict):
        return None
    zipname = str(_get(raw, "zip") or "").strip()
    rid = _get(raw, "entrant") or fallback_id or (Path(zipname).stem if zipname else "") or _get(raw, "team")
    entrant = safe_name(rid)
    if not entrant:
        return None
    e = Entry(entrant=entrant, team=str(_get(raw, "team") or ""), zip=zipname, cls=str(_get(raw, "class") or ""),
              name=str(_get(raw, "name") or ""), sha256=str(_get(raw, "sha256") or "").lower(),
              qualified=_truthy(_get(raw, "qualified")), finalist=_truthy(_get(raw, "finalist")),
              winner=_truthy(_get(raw, "winner")))
    if entrant != str(rid).strip():
        e.problems.append(f"entrant {rid!r} is used as {entrant!r}")
    if not e.zip:
        e.problems.append("no zip")
    if not e.cls:
        e.problems.append("no class")
    return e


def read_index(year: int) -> tuple[list[Entry], list[str]]:
    """``(entries, problems)`` of a year's ``index.json``. Accepted shapes: a list of entries; a
    mapping with the list under ``entries``, ``submissions`` or ``agents``; a mapping of entrant id
    to entry. Entries without an id are skipped; a repeated id keeps the last entry."""
    d = submissions_dir(year)
    if d is None:
        return [], [f"han.submissions has no folder for {year}"]
    f = d / INDEX_FILE
    if not f.is_file():
        return [], [f"no {INDEX_FILE} in {d}"]
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        return [], [f"{f} cannot be read: {e}"]
    raw: list[tuple[str, Any]] = []
    if isinstance(data, list):
        raw = [("", x) for x in data]
    elif isinstance(data, dict):
        lst = next((data[k] for k in ("entries", "submissions", "agents") if isinstance(data.get(k), list)), None)
        if lst is not None:
            raw = [("", x) for x in lst]
        else:
            raw = [(str(k), v) for k, v in data.items() if isinstance(v, dict)]
    else:
        return [], [f"{f}: expected a list of entries"]
    out: dict[str, Entry] = {}
    problems: list[str] = []
    for i, (k, x) in enumerate(raw):
        e = _entry(x, k)
        if e is None:
            problems.append(f"{f}: entry {i + 1} has no entrant id and is skipped")
            continue
        if e.entrant in out:
            problems.append(f"{f}: entrant {e.entrant!r} is listed twice; the last entry is used")
        out[e.entrant] = e
    return list(out.values()), problems


def zip_path(year: int, e: Entry) -> Path | None:
    """The entry's zip inside the year's folder (``None``: missing, or a name pointing outside it)."""
    d = submissions_dir(year)
    if d is None or not e.zip:
        return None
    root = d.resolve()
    p = (root / e.zip).resolve()
    if root not in p.parents or not p.is_file():
        return None
    return p


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


# --------------------------------------------------------------------------- #
# Imported versions                                                            #
# --------------------------------------------------------------------------- #
def entrant_dir(year: int, entrant: str) -> Path:
    return import_root() / str(int(year)) / safe_name(entrant)


def version_dir(year: int, entrant: str, sha: str) -> Path:
    return entrant_dir(year, entrant) / safe_name(sha)


def current(year: int, entrant: str) -> dict | None:
    """The manifest of the entrant's current imported version (``None``: never imported)."""
    f = entrant_dir(year, entrant) / CURRENT_FILE
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return data if isinstance(data, dict) and data.get("sha256") else None


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _find_syspath(folder: Path, spec: str) -> Path | None:
    """The folder (within ``folder``, at most three levels down) holding the class's top module."""
    top = spec.split(".", 1)[0]
    if not top:
        return None
    candidates = [folder]
    for depth in range(3):
        nxt: list[Path] = []
        for c in candidates:
            if (c / top).is_dir() or (c / f"{top}.py").is_file():
                return c
            if depth < 2:
                nxt += sorted(p for p in c.iterdir() if p.is_dir() and not p.name.startswith((".", "__")))
        candidates = nxt
    return None


def check_import(syspath: Path, spec: str, timeout: float = IMPORT_TIMEOUT) -> str:
    """Import ``spec`` (``pkg.module.Class``) in a separate, isolated Python process with
    ``syspath`` first on its path; ``""`` when it imports, else the error."""
    module, _, cls = spec.rpartition(".")
    if not module or not cls:
        return f"{spec!r} is not a dotted class path (package.module.Class)"
    code = ("import sys, importlib; sys.path.insert(0, sys.argv[1]); "
            "m = importlib.import_module(sys.argv[2]); c = getattr(m, sys.argv[3]); "
            "assert isinstance(c, type), 'not a class'")
    with tempfile.TemporaryDirectory() as cwd:
        try:
            r = subprocess.run([sys.executable, "-I", "-c", code, str(syspath), module, cls], cwd=cwd,
                               capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return f"importing {spec} took more than {timeout:.0f} s"
    if r.returncode == 0:
        return ""
    lines = [x for x in (r.stderr or "").strip().splitlines() if x.strip()]
    return lines[-1] if lines else f"importing {spec} failed (exit code {r.returncode})"


@dataclass
class ImportResult:
    entrant: str
    status: str  # imported | unchanged | error
    sha256: str = ""
    message: str = ""


def import_entry(year: int, e: Entry, *, check: bool = True) -> ImportResult:
    """Unpack one entry's zip into its own new folder (nothing in it is run) and make it the
    entrant's current version; then check, in another process, that the class imports."""
    from hani2.library import LibraryError, safe_extract

    zp = zip_path(year, e)
    if zp is None:
        return ImportResult(e.entrant, "error", message=f"zip {e.zip!r} not found in {submissions_dir(year)}")
    if not e.spec:
        return ImportResult(e.entrant, "error", message="the index names no class")
    sha = sha256_of(zp)
    if e.sha256 and e.sha256 != sha:
        return ImportResult(e.entrant, "error", sha,
                            f"the zip's sha256 is {sha[:12]}… but the index says {e.sha256[:12]}…")
    dest = version_dir(year, e.entrant, sha)
    status = "unchanged"
    if not dest.is_dir():
        dest.parent.mkdir(parents=True, exist_ok=True)
        staging = dest.parent / f".tmp-{uuid.uuid4().hex}"
        try:
            safe_extract(zp, staging, enter=False)
            staging.replace(dest)
        except (LibraryError, OSError) as ex:
            shutil.rmtree(staging, ignore_errors=True)
            return ImportResult(e.entrant, "error", sha, f"cannot unpack {zp.name}: {ex}")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        status = "imported"
    syspath = _find_syspath(dest, e.spec)
    error = "" if syspath is not None else f"no module {e.spec.split('.', 1)[0]!r} in the zip"
    if syspath is not None and check:
        error = check_import(syspath, e.spec)
    manifest = {"entrant": e.entrant, "team": e.team, "year": int(year), "sha256": sha, "zip": e.zip,
                "class": e.cls, "spec": e.spec,
                "syspath": str(syspath.relative_to(dest)) if syspath is not None else "",
                "imported_at": _dt.datetime.now().isoformat(timespec="seconds"),
                "import_checked": bool(check), "import_ok": (not error) if check or error else None,
                "import_error": error}
    _write_json(dest.parent / f"{sha}.json", manifest)
    prev = current(year, e.entrant)
    if error and prev is not None and prev.get("sha256") != sha and prev.get("import_ok") is not False:
        # a broken re-upload does not replace a version that works: the earlier one keeps playing
        return ImportResult(e.entrant, "error", sha,
                            f"{error}; the earlier version {str(prev['sha256'])[:12]} keeps playing")
    _write_json(dest.parent / CURRENT_FILE, manifest)
    return ImportResult(e.entrant, "error" if error else status, sha, error)


def import_year(year: int, *, check: bool = True) -> tuple[list[ImportResult], list[str]]:
    """Import every entry of a year's index (see :func:`import_entry`)."""
    entries, problems = read_index(year)
    return [import_entry(year, e, check=check) for e in entries], problems


# --------------------------------------------------------------------------- #
# Groups                                                                       #
# --------------------------------------------------------------------------- #
_WARNED: set[str] = set()


def _warn_once(msg: str) -> None:
    if msg not in _WARNED:
        _WARNED.add(msg)
        print(f"[hani2] WARNING: {msg}")


def _usable(year: int, e: Entry) -> tuple[dict | None, Path | None]:
    m = current(year, e.entrant)
    if m is None:
        _warn_once(f"HAN {year}: {e.entrant} is in the index but not imported (run `hani2 han import --year {year}`)")
        return None, None
    if m.get("import_ok") is False:
        _warn_once(f"HAN {year}: {e.entrant} is left out: its class does not import ({m.get('import_error')})")
        return None, None
    if e.sha256 and e.sha256 != m.get("sha256"):
        _warn_once(f"HAN {year}: {e.entrant} has a new upload that is not imported yet; the imported version "
                   f"{str(m.get('sha256'))[:12]} plays (run `hani2 han import --year {year}`)")
    sp = version_dir(year, e.entrant, m["sha256"]) / (m.get("syspath") or "")
    if not sp.is_dir():
        _warn_once(f"HAN {year}: the imported folder of {e.entrant} is missing ({sp})")
        return None, None
    return m, sp


def group_specs(year: int, kind: str = "all") -> list[str]:
    """The class paths of a year's set from its submissions (only imported entries whose class
    imports). Their folders are added to ``sys.path``, so the dotted paths import."""
    if kind not in SETS:
        return []
    entries, problems = read_index(year)
    for p in problems:
        _warn_once(f"HAN {year}: {p}")
    out: list[str] = []
    for e in entries:
        if kind not in e.sets or not e.spec:
            continue
        m, sp = _usable(year, e)
        if m is None or sp is None:
            continue
        d = str(sp)
        if d not in sys.path:
            sys.path.append(d)
        spec = m.get("spec") or e.spec
        if spec not in out:
            out.append(spec)
    return out


def prime_syspaths() -> None:
    """Add the folders of the current year's imported submissions to ``sys.path`` (silent)."""
    try:
        y = current_year()
        if y is not None:
            group_specs(y, "all")
    except Exception:  # noqa: BLE001
        pass


# --------------------------------------------------------------------------- #
# What a game records                                                          #
# --------------------------------------------------------------------------- #
PROVENANCE_COLUMNS = ["opponent_han_year", "opponent_han_source", "opponent_han_version"]


def _from_file(path: str | None) -> dict | None:
    """``(year, entrant, sha)`` of a module file that lies in an imported submission."""
    if not path:
        return None
    try:
        rel = Path(path).resolve().relative_to(import_root().resolve())
    except (ValueError, OSError):
        return None
    parts = rel.parts
    if len(parts) < 4 or not parts[0].isdigit():
        return None
    return {"opponent_han_year": int(parts[0]), "opponent_han_source": SOURCE_SUBMISSIONS,
            "opponent_han_version": parts[2]}


def provenance(spec: Any, group: str = "", negotiator: Any = None) -> dict[str, Any]:
    """``opponent_han_year``, ``opponent_han_source`` (``submissions`` / ``han-agents``) and
    ``opponent_han_version`` (the zip's sha256 / the package version) of an opponent; empty values
    when it is no HAN agent. The loaded class's file decides when it is known (the version that
    really played); otherwise the spec is looked up in the HAN groups (the session's group first)."""
    empty = {k: "" for k in PROVENANCE_COLUMNS}
    if negotiator is not None:
        for klass in type(negotiator).__mro__:  # a wrapper class (see hani2.agents) has the agent as a base
            mod = sys.modules.get(getattr(klass, "__module__", ""))
            got = _from_file(getattr(mod, "__file__", None))
            if got is not None:
                return got
    s = str(spec or "").strip()
    if not s or "." not in s:
        return empty
    from hani2 import study_modes

    years: list[int] = []
    ht = study_modes.han_token(group)
    if ht is not None:
        years.append(ht[0])
    cy = current_year()
    if cy is not None and cy not in years:
        years.append(cy)
    years += [y for y in package_years() if y not in years]
    for y in years:
        src = source_of(y)
        if src == SOURCE_SUBMISSIONS:
            for e in read_index(y)[0]:
                m = current(y, e.entrant)
                if m is not None and (m.get("spec") or e.spec) == s:
                    return {"opponent_han_year": y, "opponent_han_source": src, "opponent_han_version": m["sha256"]}
        elif src == SOURCE_PACKAGE:
            from hani2.agents import AGENT_GROUPS

            if s in (AGENT_GROUPS.get(f":han{y}-all") or []):
                return {"opponent_han_year": y, "opponent_han_source": src, "opponent_han_version": package_version()}
    return empty


# --------------------------------------------------------------------------- #
# Checking a year                                                              #
# --------------------------------------------------------------------------- #
def check_year(year: int, *, import_check: bool = True) -> dict[str, Any]:
    """What ``hani2 han check`` prints: every entry with its sets, its imported version and
    whether its class imports; zips the index does not list; and module names two entrants share
    (only one of them can be loaded in a server process)."""
    entries, problems = read_index(year)
    d = submissions_dir(year)
    rows: list[dict[str, Any]] = []
    tops: dict[str, list[str]] = {}
    for e in entries:
        row: dict[str, Any] = {"entrant": e.entrant, "team": e.team, "class": e.cls, "sets": e.sets,
                               "zip": e.zip, "problems": list(e.problems), "version": "", "imports": None}
        zp = zip_path(year, e)
        if zp is None:
            row["problems"].append(f"zip {e.zip!r} not found")
        m = current(year, e.entrant)
        if m is None:
            row["problems"].append("not imported")
        else:
            row["version"] = m["sha256"]
            if zp is not None and sha256_of(zp) != m["sha256"]:
                row["problems"].append(f"the zip changed since it was imported (or its new version does not "
                                       f"import); the version {m['sha256'][:12]} plays")
            sp = version_dir(year, e.entrant, m["sha256"]) / (m.get("syspath") or "")
            if import_check and sp.is_dir() and e.spec:
                err = check_import(sp, m.get("spec") or e.spec)
            else:
                err = m.get("import_error") or ("" if m.get("import_ok") else None)
            row["imports"] = None if err is None else not err
            if err:
                row["problems"].append(f"the class does not import: {err}")
        if e.spec:
            tops.setdefault(e.spec.split(".", 1)[0], []).append(e.entrant)
        rows.append(row)
    listed = {Path(e.zip).name for e in entries if e.zip}
    unlisted = sorted(p.name for p in d.glob("*.zip") if p.name not in listed) if d is not None and d.is_dir() else []
    clashes = {k: v for k, v in tops.items() if len(v) > 1}
    return {"year": year, "source": source_of(year), "dir": str(d) if d else "", "entries": rows,
            "unlisted_zips": unlisted, "module_clashes": clashes, "problems": problems}
