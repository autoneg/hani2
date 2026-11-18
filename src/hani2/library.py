"""The library: one model for scenarios, opponents, Assistants and tools.

Every *kind* has **items** and **groups**:

========== ======================================= ===========================================
kind       items                                   groups
========== ======================================= ===========================================
scenarios  scenario types (registered generators,  scenario sets (``scenario_sets.yaml``)
           category folders, linked folders)
opponents  negotiator classes                      ``groups/<key>.json``
assistants Assistant classes                       ``assistant_groups/<key>.json``
tools      tool classes                            ``tools.yaml`` → ``groups`` (+ built-in
                                                   groups from tool metadata)
========== ======================================= ===========================================

An item's *source* is ``builtin`` (ships with HANI2), ``registered`` (made
available another way: a plugin, env.json, an environment variable, a group
file), ``uploaded`` (a copy the library owns, under ``<layer>/library/<kind>/``
or, for scenarios, ``<layer>/scenarios/``) or ``linked`` (a path or class spec
left where it is).

**Layers** say where the library writes: ``settings`` (the settings folder),
``project:P`` (the project folder; the default project's is the settings
folder) and ``study:P/S`` (the study folder). A layer sees its own items and
those of the less specific layers. Uploaded and linked code items are listed in
``<layer>/library.yaml``; scenario links in ``<layer>/scenario_links.yaml``.

Uploaded code (opponents, Assistants, tools, a scenario's ``display.py``) runs
inside the HANI2 server with its permissions. Only administrators can add it.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import inspect
import json
import re
import shutil
import stat
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import yaml

from hani2 import composition

__all__ = ["KINDS", "Layer", "parse_layer", "layer_context", "list_items", "add_upload", "add_link", "remove_item",
           "list_groups", "put_group", "delete_group", "get_placement", "put_placement", "get_offer", "put_offer",
           "tool_classes", "prime_syspaths", "LibraryError", "safe_extract", "CODE_WARNING", "group_warnings",
           "get_default_set", "put_default_set", "describe", "trash"]

KINDS = ("scenarios", "opponents", "assistants", "tools")
INDEX = "library.yaml"
LIB_DIR = "library"
CODE_WARNING = "Uploaded code runs inside the HANI2 server with its permissions."
#: zip limits
MAX_ZIP_FILES = 5000
MAX_ZIP_BYTES = 200 * 1024 * 1024
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,63}$")
_FOLDER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class LibraryError(ValueError):
    """A request the library refuses (bad name, clash, broken item ...). ``status`` is an HTTP hint."""

    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


def check_kind(kind: str) -> str:
    k = str(kind).strip().lower()
    k = {"scenario": "scenarios", "opponent": "opponents", "assistant": "assistants", "tool": "tools"}.get(k, k)
    if k not in KINDS:
        raise LibraryError(f"kind must be one of {', '.join(KINDS)}")
    return k


def check_name(name: Any, what: str = "name") -> str:
    if not isinstance(name, str) or not _NAME.match(name.strip()) or ".." in name:
        raise LibraryError(f"invalid {what} {name!r}: use letters, digits, spaces, '.', '_' and '-' (at most 64)")
    return name.strip()


def check_folder_name(name: Any, what: str = "name") -> str:
    if not isinstance(name, str) or not _FOLDER.match(name) or ".." in name:
        raise LibraryError(f"invalid {what} {name!r}: use letters, digits, '.', '_' and '-' (at most 64)")
    return name


# --------------------------------------------------------------------------- #
# Layers                                                                       #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Layer:
    #: settings | project | study
    level: str
    dir: Path
    project: str | None = None
    study: str | None = None

    @property
    def name(self) -> str:
        if self.level == "settings":
            return "settings"
        if self.level == "project":
            return f"project:{self.project}"
        return f"study:{self.project}/{self.study}"

    @property
    def ref(self):
        from hani2.projects import StudyRef

        return StudyRef(self.project, self.study) if self.level == "study" else None

    def chain(self) -> list["Layer"]:
        """This layer and the less specific ones, least specific first."""
        from hani2.config import settings_dir
        from hani2.projects import DEFAULT_PROJECT, project_dir

        out = [Layer("settings", settings_dir())]
        if self.level in ("project", "study") and self.project and self.project != DEFAULT_PROJECT:
            out.append(Layer("project", project_dir(self.project), self.project))
        if self.level == "study":
            out.append(self)
        return out

    def group_dir(self, gkind: str) -> Path:
        from hani2 import groups

        return self.dir / groups.SUBDIR[groups.check_kind(gkind)]


def parse_layer(text: str | None) -> Layer:
    """``settings`` (default), ``project:P`` or ``study:P/S`` (or a bare ``P/S``)."""
    from hani2 import projects
    from hani2.config import settings_dir

    t = (text or "settings").strip()
    if t in ("", "settings"):
        return Layer("settings", settings_dir())
    level, _, rest = t.partition(":")
    if not rest and "/" in t:
        level, rest = "study", t
    try:
        if level == "project":
            p = projects.check_name(rest, "project")
            if p == projects.DEFAULT_PROJECT:
                return Layer("settings", settings_dir())
            if not projects.project_exists(p):
                raise LibraryError(f"unknown project {p!r}", 404)
            return Layer("project", projects.project_dir(p), p)
        if level == "study":
            ref = projects.parse_ref(rest)
            if ref is None or not projects.project_exists(ref.project) or not projects.study_exists(ref):
                raise LibraryError(f"unknown study {rest!r}", 404)
            return Layer("study", projects.study_dir(ref), ref.project, ref.study)
    except LibraryError:
        raise
    except ValueError as e:
        raise LibraryError(str(e)) from None
    raise LibraryError("layer must be settings, project:<P> or study:<P>/<S>")


def _layer(layer: "str | Layer | None") -> Layer:
    return layer if isinstance(layer, Layer) else parse_layer(layer)


@contextlib.contextmanager
def layer_context(layer: Layer) -> Iterator[Layer]:
    """Run a block as a session of ``layer`` would see the settings (a study's,
    or a project's without one of its studies, or the plain settings)."""
    from hani2 import projects
    from hani2.config import use_layers

    with projects.use_study(layer.ref):
        if layer.level == "study":
            yield layer
            return
        from hani2.config import layer_view

        dirs = [x.dir for x in reversed(layer.chain()) if x.level != "settings"]
        # the project's group files and folders too (groups.search_dirs, config.project_dir)
        with use_layers(dirs), layer_view(layer.project if layer.level == "project" else None):
            yield layer


def _layer_of(path: Path, layers: list[Layer]) -> str | None:
    p = Path(path).resolve()
    for la in reversed(layers):  # most specific first
        if p == la.dir.resolve() or la.dir.resolve() in p.parents:
            return la.name
    return None


# --------------------------------------------------------------------------- #
# library.yaml                                                                 #
# --------------------------------------------------------------------------- #
def read_index(layer_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    f = Path(layer_dir) / INDEX
    if not f.is_file():
        return {}
    try:
        data = yaml.safe_load(f.read_text()) or {}
        if not isinstance(data, dict):
            raise ValueError("expected a mapping of kinds")
        return {k: {str(n): dict(e) for n, e in (v or {}).items() if isinstance(e, dict)}
                for k, v in data.items() if k in KINDS and isinstance(v, dict)}
    except Exception as e:  # noqa: BLE001
        print(f"[hani2] ignoring {f}: {e}")
        return {}


def check_writable(path: Path) -> None:
    """Refuse to rewrite a YAML file that exists but cannot be read (409): reading it as empty
    and writing it back would lose what an admin wrote by hand."""
    f = Path(path)
    if not f.is_file():
        return
    try:
        data = yaml.safe_load(f.read_text())
    except Exception as e:  # noqa: BLE001
        raise LibraryError(f"{f.name} at {f.parent} is not valid YAML ({e}); fix it by hand first", 409) from None
    if data is not None and not isinstance(data, dict):
        raise LibraryError(f"{f.name} at {f.parent} is not a mapping; fix it by hand first", 409)


def read_index_strict(layer_dir: Path) -> dict[str, dict[str, dict[str, Any]]]:
    """:func:`read_index` for a write: a broken ``library.yaml`` is refused (409), not emptied."""
    check_writable(Path(layer_dir) / INDEX)
    return read_index(layer_dir)


#: removed and replaced uploads go to a ``.trash`` folder next to them (names starting with ``.``
#: are never served), so nothing an admin added is lost by one click
TRASH = ".trash"


def trash(path: Path) -> Path:
    """Move ``path`` into ``<its folder>/.trash/<name>-<time>``; returns where it went."""
    import time

    d = Path(path).parent / TRASH
    d.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = d / f"{Path(path).name}-{stamp}"
    n = 1
    while dest.exists():
        dest = d / f"{Path(path).name}-{stamp}-{n}"
        n += 1
    shutil.move(str(path), str(dest))
    return dest


def write_index(layer_dir: Path, data: dict[str, Any]) -> Path:
    f = Path(layer_dir) / INDEX
    f.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: v for k, v in data.items() if v}
    tmp = f.with_suffix(".yaml.tmp")
    tmp.write_text(yaml.safe_dump(clean, sort_keys=False, allow_unicode=True))
    tmp.replace(f)
    return f


def _abs(layer_dir: Path, p: str) -> Path:
    q = Path(p).expanduser()
    return q if q.is_absolute() else (Path(layer_dir) / q).resolve()


def entry_spec(kind: str, entry: dict[str, Any], layer_dir: Path) -> str:
    """The class spec an index entry stands for, in the form the kind's loader reads."""
    if entry.get("spec"):
        return str(entry["spec"])
    f = _abs(layer_dir, str(entry["file"]))
    cls = str(entry["class"])
    if kind == "opponents":
        return f"file:{f.with_suffix('')}.{cls}"
    return f"{f}:{cls}"


def _entry_syspath(entry: dict[str, Any], layer_dir: Path) -> list[str]:
    return [str(_abs(layer_dir, str(x))) for x in entry.get("syspath") or []]


def index_entries(kind: str, layers: list[Layer]) -> list[dict[str, Any]]:
    """The library entries of ``kind`` visible from the most specific of ``layers``
    (a more specific layer's entry hides one of the same name)."""
    out: dict[str, dict[str, Any]] = {}
    for la in layers:
        for name, e in read_index(la.dir).get(kind, {}).items():
            try:
                spec = entry_spec(kind, e, la.dir)
            except KeyError:
                continue
            out[name.lower()] = dict(e, name=name, layer=la.name, spec=spec, syspath=_entry_syspath(e, la.dir))
    return list(out.values())


def _current_layers() -> list[Layer]:
    """The layers of the current study (or the settings alone)."""
    from hani2 import projects

    ref = projects.current_study()
    try:
        if ref is not None and projects.study_exists(ref):
            return Layer("study", projects.study_dir(ref), ref.project, ref.study).chain()
        if ref is not None and ref.project != projects.DEFAULT_PROJECT and projects.project_exists(ref.project):
            return Layer("project", projects.project_dir(ref.project), ref.project).chain()
    except ValueError:
        pass
    return parse_layer("settings").chain()


def prime_syspaths(ref: Any = None) -> None:
    """Add the ``syspath`` of every library entry the current study sees to ``sys.path``."""
    from hani2 import projects

    with projects.use_study(ref) if ref is not None else contextlib.nullcontext():
        layers = _current_layers()
    for kind in ("opponents", "assistants", "tools"):
        for e in index_entries(kind, layers):
            for d in e["syspath"]:
                if d not in sys.path:
                    sys.path.append(d)


def tool_classes() -> list[tuple[type, str]]:
    """Tool classes from the library entries the current study sees (for the registry)."""
    from hani2.tools.registry import import_tool

    out: list[tuple[type, str]] = []
    for e in index_entries("tools", _current_layers()):
        for d in e["syspath"]:
            if d not in sys.path:
                sys.path.append(d)
        try:
            out.append((import_tool(e["spec"]), f"library {e.get('source', 'uploaded')} ({e['layer']}: {e['name']})"))
        except Exception as ex:  # noqa: BLE001 - one broken tool must not hide the others
            print(f"[hani2] library tool {e['name']!r} ({e['layer']}) cannot be loaded: {ex}")
    return out


# --------------------------------------------------------------------------- #
# Archives                                                                     #
# --------------------------------------------------------------------------- #
def safe_extract(zip_path: Path, dest: Path, enter: bool = True) -> Path:
    """Extract a zip into ``dest`` refusing absolute paths, ``..``, symlinks and
    oversize archives. Returns the folder holding the content (with ``enter``, a
    single top folder that is no Python package is entered)."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    root = dest.resolve()
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile:
        raise LibraryError("not a valid .zip file") from None
    with zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_FILES:
            raise LibraryError(f"the archive has more than {MAX_ZIP_FILES} entries")
        if sum(i.file_size for i in infos) > MAX_ZIP_BYTES:
            raise LibraryError(f"the archive unpacks to more than {MAX_ZIP_BYTES // (1024 * 1024)} MB")
        for i in infos:
            n = i.filename
            if n.startswith(("/", "\\")) or "\\" in n or re.match(r"^[A-Za-z]:", n) or ".." in Path(n).parts:
                raise LibraryError(f"unsafe path in the archive: {n!r}")
            if stat.S_ISLNK(i.external_attr >> 16):
                raise LibraryError(f"the archive holds a symbolic link: {n!r}")
            target = (root / n).resolve()
            if target != root and root not in target.parents:
                raise LibraryError(f"unsafe path in the archive: {n!r}")
        total = 0
        for i in infos:
            parts = Path(i.filename).parts
            if not parts or parts[0] == "__MACOSX" or parts[-1] == ".DS_Store":
                continue
            target = (root / i.filename).resolve()
            if i.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # count the bytes actually written: the sizes in the archive's directory may lie
            with zf.open(i) as src, open(target, "wb") as dst:
                while chunk := src.read(1 << 20):
                    total += len(chunk)
                    if total > MAX_ZIP_BYTES:
                        raise LibraryError(f"the archive unpacks to more than {MAX_ZIP_BYTES // (1024 * 1024)} MB")
                    dst.write(chunk)
    top = [p for p in root.iterdir() if not p.name.startswith(".") and p.name != "__MACOSX"]
    if enter and len(top) == 1 and top[0].is_dir() and not (top[0] / "__init__.py").exists():
        return top[0]
    return root


def _stage_upload(filename: str, content: bytes, tmp: Path) -> tuple[Path, str]:
    """Write an upload into ``tmp``: a ``.zip`` is extracted (``(folder, stem)``),
    a ``.py`` is kept as is (``(file, stem)``)."""
    base = Path(str(filename or "upload")).name
    stem = Path(base).stem
    if base.lower().endswith(".zip"):
        z = tmp / "upload.zip"
        z.write_bytes(content)
        folder = safe_extract(z, tmp / "x")
        # a single top folder names the upload (``Rentals/...`` → Rentals)
        return folder, (folder.name if folder != (tmp / "x").resolve() else stem)
    if base.lower().endswith(".py"):
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.py$", base):
            raise LibraryError(f"{base!r}: a Python file name must be a valid module name")
        f = tmp / "py" / base
        f.parent.mkdir(parents=True)
        f.write_bytes(content)
        return f, stem
    raise LibraryError("upload a .zip package or a .py file")


# --------------------------------------------------------------------------- #
# Finding classes in code                                                      #
# --------------------------------------------------------------------------- #
def _base_class(kind: str) -> type:
    if kind == "opponents":
        from negmas import Negotiator

        return Negotiator
    if kind == "assistants":
        from hani2.support_agent.runtime import SupportAgent

        return SupportAgent
    from hani2.tools.base import Tool

    return Tool


def _candidates(kind: str, module) -> list[type]:
    if kind == "tools":
        from hani2.tools.registry import _classes_in

        return _classes_in(module)
    base = _base_class(kind)
    return [c for _, c in inspect.getmembers(module, inspect.isclass)
            if issubclass(c, base) and c is not base and c.__module__ == module.__name__
            and not c.__name__.startswith("_") and not inspect.isabstract(c)
            and not c.__dict__.get("abstract", False)]


def _py_files(folder: Path) -> list[Path]:
    out = []
    for f in sorted(folder.rglob("*.py")):
        rel = f.relative_to(folder)
        if any(p.startswith((".", "_")) and p != "__init__.py" for p in rel.parts):
            continue
        if f.name.startswith("test_") or f.name in ("setup.py", "conftest.py", "__main__.py"):
            continue
        if any(not p.isidentifier() for p in rel.with_suffix("").parts):
            continue
        out.append(f)
    return out


def _import_file(path: Path):
    name = f"hani2_library_probe_{abs(hash(str(path)))}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    folder = str(path.parent)
    added = folder not in sys.path
    if added:
        sys.path.insert(0, folder)
    try:
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    finally:
        sys.modules.pop(name, None)
        if added:
            with contextlib.suppress(ValueError):
                sys.path.remove(folder)
    return mod


def _check_top_modules(folder: Path, allowed: list[Path] | None = None) -> None:
    """Refuse a package whose top-level modules already import from elsewhere
    (``allowed``: folders an earlier copy of the same package may come from)."""
    for p in folder.iterdir():
        mod = p.stem if p.suffix == ".py" else p.name if p.is_dir() else None
        if not mod or not mod.isidentifier():
            continue
        found = sys.modules.get(mod)
        if found is not None:
            origin = getattr(found, "__file__", None) or next(iter(getattr(found, "__path__", []) or []), None)
        else:
            try:
                s = importlib.util.find_spec(mod)
            except (ImportError, ValueError):
                s = None
            if s is None:
                continue
            origin = s.origin or next(iter(s.submodule_search_locations or []), None)
        if origin and any(Path(origin).resolve().is_relative_to(Path(r).resolve()) for r in [folder, *(allowed or [])]):
            continue
        raise LibraryError(f"the package's module {mod!r} clashes with an installed module of that name; rename it", 409)


def discover(kind: str, path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """The classes of ``kind`` in a ``.py`` file or a package folder:
    ``([{"class", "file" | "spec", "title", "description"}], errors)``. Package
    modules (opponents, Assistants) are imported by their dotted name with the
    folder on ``sys.path``; tool files are loaded on their own."""
    found: list[dict[str, Any]] = []
    errors: list[str] = []
    files = [path] if path.is_file() else _py_files(path)
    for f in files:
        dotted = None
        try:
            if path.is_dir() and kind != "tools":
                parts = f.relative_to(path).with_suffix("").parts
                if parts[-1] == "__init__":
                    parts = parts[:-1]
                if not parts:
                    continue
                dotted = ".".join(parts)
                if str(path) not in sys.path:
                    sys.path.insert(0, str(path))
                mod = importlib.import_module(dotted)
            else:
                mod = _import_file(f)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{f.name}: {type(e).__name__}: {e}")
            continue
        for c in _candidates(kind, mod):
            doc = inspect.getdoc(c) or ""
            title = str(getattr(c, "name", "") or c.__name__) if kind == "tools" else c.__name__
            desc = str(getattr(c, "description", "") or "").strip() if kind == "tools" else ""
            item = {"class": c.__name__, "title": title, "description": desc or (doc.splitlines()[0] if doc else "")}
            if dotted is not None:
                item["spec"] = f"{dotted}.{c.__name__}" if kind == "opponents" else f"{dotted}:{c.__name__}"
            else:
                item["file"] = str(f)
            if not any(x["class"] == item["class"] for x in found):
                found.append(item)
    return found, errors


def verify(kind: str, spec: str) -> type:
    """Load ``spec`` the way HANI2 will when it is used (raises :class:`LibraryError`)."""
    try:
        if kind == "opponents":
            from hani2.agents import get_agent_type

            cls = get_agent_type(spec)
        elif kind == "assistants":
            from hani2.support_agent.runtime import load_class

            cls = load_class(spec)
        else:
            from hani2.tools.registry import import_tool

            cls = import_tool(spec)
    except Exception as e:  # noqa: BLE001
        raise LibraryError(f"cannot load {spec!r}: {type(e).__name__}: {e}", 422) from None
    base = _base_class(kind)
    if not (isinstance(cls, type) and issubclass(cls, base)):
        raise LibraryError(f"{spec!r} is not a {base.__name__} subclass", 422)
    return cls


# --------------------------------------------------------------------------- #
# Items                                                                        #
# --------------------------------------------------------------------------- #
def _with_groups(items: list[dict[str, Any]], expanded: dict[str, list[Any]]) -> list[dict[str, Any]]:
    for it in items:
        keys = {str(it.get("spec") or "").lower(), str(it["name"]).lower()} - {""}
        it["groups"] = [g for g, members in expanded.items() if any(str(m).lower() in keys for m in members)]
    return items


def list_items(kind: str, layer: "str | Layer | None" = None) -> list[dict[str, Any]]:
    """Every item of ``kind`` seen from ``layer``: ``{name, title, description,
    source, layer, spec?, path?, groups, removable}``."""
    kind = check_kind(kind)
    la = _layer(layer)
    with layer_context(la):
        if kind == "scenarios":
            items = _scenario_items(la)
        elif kind == "tools":
            items = _tool_items(la)
        else:
            items = _class_items(kind, la)
    expanded = {g["name"]: g["expanded"] for g in list_groups(kind, la) if g.get("active", True)}
    for it in items:
        it["removable"] = it.get("layer") == la.name and it["source"] in ("uploaded", "linked")
    return _with_groups(items, expanded)


def _scenario_items(la: Layer) -> list[dict[str, Any]]:
    from hani2 import scenario_links, scenario_store
    from hani2.scenarios import registry

    registry.load_plugins()
    layers = la.chain()
    links = scenario_links.load_links()
    items = []
    for t in scenario_store.available_types():
        st = registry.get(t)
        d = scenario_store.category_dir(t)
        if st is not None:
            source = "builtin" if st.builtin else "registered"
        elif t in links and d is not None and d == links[t]:
            source = "linked"
        elif d is not None and _uploaded_scenario(d, layers):
            source = "uploaded"
        else:
            source = "registered"  # a folder put there by hand, `hani2 setup` or `hani2 generate`
        title, desc = "", ""
        if st is not None and st.story is not None:
            title, desc = st.story.title, st.story.short_description
        pool = scenario_store._pool(t) if d is not None else []
        if pool and not title:
            info = scenario_store._read_info(pool[0])
            title, desc = str(info.get("title") or ""), str(info.get("short_description") or "")
        layer = None
        if source == "linked":
            layer = _layer_of_link(t, layers)
        elif source == "uploaded" and d is not None:
            layer = _layer_of(d, layers)
        items.append({"name": t, "title": title or t, "description": desc, "source": source,
                      "path": str(d) if d is not None else None, "n_scenarios": len(pool), "layer": layer})
    return items


def _uploaded_scenario(folder: Path, layers: list[Layer]) -> bool:
    """Whether ``folder`` is a category the library uploaded (listed in its layer's library.yaml)."""
    for la in layers:
        if folder.parent.resolve() == (la.dir / "scenarios").resolve() and \
                folder.name in read_index(la.dir).get("scenarios", {}):
            return True
    return False


def _layer_of_link(name: str, layers: list[Layer]) -> str | None:
    from hani2 import scenario_links

    for la in reversed(layers):
        if name in scenario_links.read_file(la.dir / scenario_links.FILE):
            return la.name
    return None


def _gkind(kind: str) -> str:
    from hani2 import groups

    return groups.OPPONENT if kind == "opponents" else groups.ASSISTANT


def _class_items(kind: str, la: Layer) -> list[dict[str, Any]]:
    import os

    from hani2 import groups

    gk = _gkind(kind)
    items: dict[str, dict[str, Any]] = {}

    def add(name: str, source: str, title: str | None = None, description: str = "") -> None:
        if name.lower() not in items:
            items[name.lower()] = {"name": name, "title": title or name, "description": description,
                                   "source": source, "layer": None, "spec": name}

    if kind == "opponents":
        from hani2 import agents

        for key in ("llm", "template", "notext", "negmas", "classic", "genius"):
            for spec in agents._resolve_builtin(":" + key):
                add(str(spec), "builtin")
        raw = os.environ.get("HANI2_CUSTOM_AGENTS") or os.environ.get("HANI_CUSTOM_AGENTS", "")
        for spec in [s.strip() for s in raw.split(",") if s.strip() and not composition.is_ref(s)]:
            add(spec, "registered", description="HANI2_CUSTOM_AGENTS")
    else:
        add(groups.DEFAULT_ASSISTANT_SPEC, "builtin", "Assistant", "The built-in Assistant")
        for spec in groups.tutorial_assistants():
            add(spec, "builtin", description="Tutorial Assistant")
        add(groups.default_assistant_spec(), "registered", description="agent_class in assistant_settings.json")
    for e in index_entries(kind, la.chain()):
        items[e["name"].lower()] = {"name": e["name"], "title": e.get("title") or e["name"],
                                    "description": e.get("description") or "", "source": e.get("source", "uploaded"),
                                    "layer": e["layer"], "spec": e["spec"],
                                    "path": e.get("target") or e.get("path") or e.get("file")}
    # members of group files that are no item yet (an outside system's specs, say)
    lk = _group_lookup(gk, la)
    known = {str(i.get("spec")).lower() for i in items.values()} | set(items)
    for g in _group_files(gk, la):
        for m in g["members"]:
            if not composition.is_ref(m) and lk(m, False) is None and m.lower() not in known:
                known.add(m.lower())
                add(m, "registered", description=f"listed in group {g['name']}")
    return list(items.values())


def _tool_items(la: Layer) -> list[dict[str, Any]]:
    from hani2 import tool_groups
    from hani2.tools import registry

    specs = registry.tool_specs(offered_only=False)
    offer = tool_groups.offered(specs)
    lib = {e["name"].lower(): e for e in index_entries("tools", la.chain())}
    items = []
    for s in specs:
        src = registry.SOURCES.get(s.cls, "")
        e = lib.get(s.name.lower())
        if src == "built-in":
            source = "builtin"
        elif e is not None and src.startswith("library"):
            source = e.get("source", "uploaded")
        else:
            source = "registered"
        items.append({"name": s.name, "title": s.name, "description": s.cls.description or "", "source": source,
                      "layer": e["layer"] if e is not None and source in ("uploaded", "linked") else None,
                      "spec": f"{s.cls.__module__}:{s.cls.__name__}", "origin": src, "pane": s.pane,
                      "timing": s.timing, "admin_only": s.admin_only, "guest": s.guest, "enabled": s.enabled,
                      "tool_groups": list(s.groups), "placement": s.placement,
                      "offered": offer is None or s.name.lower() in offer})
    return items


def _item_names(kind: str, la: Layer) -> set[str]:
    with layer_context(la):
        if kind == "scenarios":
            from hani2 import scenario_store

            return {t.lower() for t in scenario_store.available_types()}
        if kind == "tools":
            from hani2.tools import registry

            return {s.name.lower() for s in registry.tool_specs(offered_only=False)}
        return {i["name"].lower() for i in _class_items(kind, la)}


def _owned_root(la: Layer, kind: str) -> Path:
    return la.dir / LIB_DIR / kind


def add_upload(kind: str, filename: str, content: bytes, layer: "str | Layer | None" = None, *,
               name: str | None = None, group: str | None = None, classes: list[str] | None = None,
               allow_code: bool = False, replace: bool = False) -> dict[str, Any]:
    """Add items from an uploaded ``.zip`` (or ``.py`` for code). Returns
    ``{"ok", "items", "warnings", "notice"}``. Scenario archives holding Python
    files (``display.py``) need ``allow_code``."""
    kind = check_kind(kind)
    la = _layer(layer)
    with tempfile.TemporaryDirectory() as tmp:
        staged, stem = _stage_upload(filename, content, Path(tmp))
        if kind == "scenarios":
            if staged.is_file():
                raise LibraryError("upload scenarios as a .zip of scenario folders")
            return _add_scenarios(la, staged, name or stem, copy=True, allow_code=allow_code, replace=replace,
                                  group=group)
        folder = check_folder_name(re.sub(r"[^A-Za-z0-9._-]", "_", name or stem), "upload name")
        dest = _owned_root(la, kind) / folder
        if dest.exists() and not replace:
            raise LibraryError(f"an upload called {folder!r} exists at {la.name}; remove it first or replace it", 409)
        _forget_modules_under(str(dest))  # a replaced upload must not keep serving its old code
        if staged.is_dir() and kind != "tools":
            _check_top_modules(staged, allowed=[dest])
        found, errors = discover(kind, staged)
        found = _select(found, classes)
        if not found:
            raise LibraryError("no usable class found" + (": " + "; ".join(errors) if errors else ""), 422)
        # import from the library copy, not from the temporary folder
        _forget_modules_under(tmp)
        with contextlib.suppress(ValueError):
            sys.path.remove(str(staged))
        read_index_strict(la.dir)  # refuse before touching files when library.yaml is broken
        if dest.exists():
            trash(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if staged.is_file():
            dest.mkdir()
            shutil.copy2(staged, dest / staged.name)
            base = staged.parent
        else:
            shutil.copytree(staged, dest)
            base = staged
        rel = str(dest.relative_to(la.dir))
        entries = []
        for it in found:
            e: dict[str, Any] = {"source": "uploaded", "path": rel, "class": it["class"], "title": it["title"],
                                 "description": it["description"]}
            if "spec" in it:
                e["spec"], e["syspath"] = it["spec"], [rel]
            else:
                e["file"] = str((dest / Path(it["file"]).relative_to(base)).relative_to(la.dir))
            entries.append(e)
        try:
            result = _register(kind, la, entries, name if len(found) == 1 else None, group, replace)
        except Exception:
            shutil.rmtree(dest, ignore_errors=True)
            raise
    result["warnings"] = errors
    result["notice"] = CODE_WARNING
    return result


def _forget_modules_under(folder: str) -> None:
    _DESCRIBED.clear()
    prefixes = (str(folder), str(Path(folder).resolve()))
    for k, v in list(sys.modules.items()):
        locs = [str(getattr(v, "__file__", "") or "")] + [str(x) for x in (getattr(v, "__path__", None) or [])]
        if any(loc.startswith(prefixes) for loc in locs if loc):
            sys.modules.pop(k, None)


def _select(found: list[dict[str, Any]], classes: list[str] | None) -> list[dict[str, Any]]:
    if not classes:
        return found
    want = {c.strip() for c in classes if c.strip()}
    picked = [f for f in found if f["class"] in want or f["title"] in want]
    missing = want - {f["class"] for f in picked} - {f["title"] for f in picked}
    if missing:
        raise LibraryError(f"no class {', '.join(sorted(missing))} found", 422)
    return picked


def _register(kind: str, la: Layer, entries: list[dict[str, Any]], name: str | None, group: str | None,
              replace: bool) -> dict[str, Any]:
    """Check that every entry loads and its name is free, write the index (and the group)."""
    _DESCRIBED.clear()
    idx = read_index_strict(la.dir)
    mine = idx.setdefault(kind, {})
    existing = _item_names(kind, la)
    added = []
    for e in entries:
        spec = entry_spec(kind, e, la.dir)
        for d in _entry_syspath(e, la.dir):
            if d not in sys.path:
                sys.path.append(d)
        cls = verify(kind, spec)
        # a tool is known by its name; other items by the given name or the class name
        n = check_name((getattr(cls, "name", "") or cls.__name__) if kind == "tools" else (name or e["class"]),
                       "item name")
        own = next((k for k in mine if k.lower() == n.lower()), None)
        if n.lower() in existing and not (replace and own is not None):
            raise LibraryError(f"an item called {n!r} already exists; choose another name", 409)
        if own is not None:
            del mine[own]
        mine[n] = e
        added.append({"name": n, "spec": spec, "layer": la.name, "source": e["source"]})
    write_index(la.dir, idx)
    if group:
        for a in added:
            _add_to_group(kind, la, group, a["name"])
    return {"ok": True, "items": added, "layer": la.name}


def add_link(kind: str, target: str, layer: "str | Layer | None" = None, *, name: str | None = None,
             group: str | None = None, classes: list[str] | None = None, syspath: list[str] | None = None,
             allow_code: bool = False, replace: bool = False) -> dict[str, Any]:
    """Link a path on disk (a scenario folder or category; a ``.py`` file or a
    package folder) or a class spec (``pkg.module:Class`` / ``pkg.module.Class``)."""
    kind = check_kind(kind)
    la = _layer(layer)
    t = str(target or "").strip()
    if not t:
        raise LibraryError("give a path or a class spec to link")
    p = Path(t).expanduser()
    if kind == "scenarios":
        if not p.is_absolute() or not p.is_dir():
            raise LibraryError("link an existing scenario folder by its absolute path", 404)
        return _add_scenarios(la, p, name or p.name, copy=False, allow_code=allow_code, replace=replace, group=group)
    if p.is_absolute() and p.exists():
        if p.is_dir() and kind != "tools":
            _check_top_modules(p)
        found, errors = discover(kind, p)
        found = _select(found, classes)
        if not found:
            raise LibraryError("no usable class found" + (": " + "; ".join(errors) if errors else ""), 422)
        entries = []
        for it in found:
            e: dict[str, Any] = {"source": "linked", "class": it["class"], "title": it["title"],
                                 "description": it["description"], "target": str(p)}
            if "spec" in it:
                e["spec"], e["syspath"] = it["spec"], [str(p)]
            else:
                e["file"] = it["file"]
            entries.append(e)
        out = _register(kind, la, entries, name if len(found) == 1 else None, group, replace)
        out["warnings"] = errors
    elif "/" in t or "\\" in t or t.endswith(".py"):
        raise LibraryError(f"{t!r} does not exist (link a path by its absolute path)", 404)
    else:  # a class spec
        sp = [str(Path(x).expanduser()) for x in (syspath or []) if str(x).strip()]
        for d in sp:
            if not Path(d).is_absolute() or not Path(d).is_dir():
                raise LibraryError(f"syspath {d!r} is not an existing absolute folder")
            if d not in sys.path:
                sys.path.append(d)
        cls = verify(kind, t)
        doc = (inspect.getdoc(cls) or "").split("\n")[0]
        e = {"source": "linked", "spec": t, "class": cls.__name__,
             "title": (getattr(cls, "name", "") or cls.__name__) if kind == "tools" else cls.__name__,
             "description": (str(getattr(cls, "description", "") or "") if kind == "tools" else "") or doc}
        if sp:
            e["syspath"] = sp
        out = _register(kind, la, [e], name, group, replace)
        out["warnings"] = []
    out["notice"] = CODE_WARNING
    return out


def _add_scenarios(la: Layer, src: Path, name: str, *, copy: bool, allow_code: bool, replace: bool,
                   group: str | None) -> dict[str, Any]:
    from hani2 import scenario_links, scenario_store
    from hani2.scenarios import registry

    name = check_folder_name(name, "scenario type name")
    folders = scenario_store.scenario_folders(src)
    if not folders:
        raise LibraryError("no scenario folder found (a scenario folder holds <Type>.yml and one file per role)", 422)
    has_code = any(src.rglob("*.py"))
    if has_code and not allow_code:
        raise LibraryError("the scenarios contain Python files (a display.py runs on the server); "
                           "allow code to add them", 422)
    with layer_context(la):
        registry.load_plugins()
        names = registry.names()
    low = name.lower()
    for reg in names:
        r = reg.lower()
        if r == low:
            raise LibraryError(f"{name!r} is a registered scenario type; choose another name", 409)
        if low.startswith(r) or r.startswith(low):
            raise LibraryError(f"{name!r} and the registered scenario type {reg!r} start alike, so the scenarios "
                               "could be shown with the wrong display; choose another name", 409)
    dest = la.dir / "scenarios" / name
    own_link = name in scenario_links.read_file(la.dir / scenario_links.FILE)
    own_folder = dest.is_dir() and name in read_index(la.dir).get("scenarios", {})
    if low in _item_names("scenarios", la) and not (replace and (own_link or own_folder)):
        raise LibraryError(f"a scenario type called {name!r} already exists; choose another name", 409)
    errors: list[str] = []
    warnings: list[str] = []
    for f in folders:
        s, errs, warns = scenario_store.check_scenario(f)
        rel = f.relative_to(src) if f != src else Path(f.name)
        errors += [f"{rel}: {e}" for e in errs]
        warnings += [f"{rel}: {w}" for w in warns]
        if s is not None:
            osn = str(getattr(s.outcome_space, "name", "") or "")
            hit = next((reg for reg in names if osn.startswith(reg)), None)
            if hit is not None:
                warnings.append(f"{rel}: its outcome space is called {osn!r}, so it is shown like {hit!r} scenarios")
    if errors:
        raise LibraryError("invalid scenario: " + "; ".join(errors[:10]), 422)
    check_writable(la.dir / scenario_links.FILE)
    if copy:
        idx = read_index_strict(la.dir)
        if dest.exists():
            trash(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest)
        if own_link:
            scenario_links.remove_link(la.dir, name)
        idx.setdefault("scenarios", {})[name] = {"source": "uploaded", "path": str(dest.relative_to(la.dir)),
                                                 "n_scenarios": len(folders)}
        write_index(la.dir, idx)
        source, path = "uploaded", dest
    else:
        scenario_links.write_link(la.dir, name, src.resolve())
        source, path = "linked", src.resolve()
    if group:
        _add_to_group("scenarios", la, group, name)
    return {"ok": True, "items": [{"name": name, "source": source, "layer": la.name, "path": str(path),
                                   "n_scenarios": len(folders)}], "warnings": warnings, "layer": la.name,
            "notice": CODE_WARNING if has_code else None}


def remove_item(kind: str, name: str, layer: "str | Layer | None" = None) -> dict[str, Any]:
    """Remove an uploaded item (and its files, when no other item uses them) or
    unlink a linked one (its target is left alone)."""
    from hani2 import scenario_links

    kind = check_kind(kind)
    la = _layer(layer)
    name = check_name(name, "item name")
    _DESCRIBED.clear()
    if kind == "scenarios":
        from hani2.scenarios import registry

        check_folder_name(name, "scenario type name")
        check_writable(la.dir / scenario_links.FILE)
        if scenario_links.remove_link(la.dir, name):
            return {"ok": True, "removed": name, "how": "unlinked", "layer": la.name}
        if registry.get(name) is not None:
            raise LibraryError(f"{name!r} is a registered scenario type; it cannot be removed here", 409)
        idx = read_index_strict(la.dir)
        if name not in idx.get("scenarios", {}):
            raise LibraryError(f"no uploaded or linked scenario type {name!r} at {la.name} (the library only "
                               "removes what it added)", 404)
        del idx["scenarios"][name]
        write_index(la.dir, idx)
        root = (la.dir / "scenarios").resolve()
        d = la.dir / "scenarios" / name
        out = {"ok": True, "removed": name, "how": "deleted", "layer": la.name}
        if d.is_dir() and not d.is_symlink() and d.resolve().parent == root:
            out["trash"] = str(trash(d))
        return out
    idx = read_index_strict(la.dir)
    mine = idx.get(kind, {})
    key = next((k for k in mine if k.lower() == name.lower()), None)
    if key is None:
        raise LibraryError(f"no uploaded or linked {kind[:-1]} {name!r} at {la.name}", 404)
    e = mine.pop(key)
    write_index(la.dir, idx)
    how = "unlinked" if e.get("source") == "linked" else "removed"
    owned = e.get("path")
    if owned and e.get("source") == "uploaded" and not any(x.get("path") == owned for x in mine.values()):
        d = _abs(la.dir, owned)
        root = _owned_root(la, kind).resolve()
        if d.is_dir() and not d.is_symlink() and root in d.resolve().parents:
            _forget_modules_under(str(d))
            with contextlib.suppress(ValueError):
                sys.path.remove(str(d))
            moved = trash(d)
            return {"ok": True, "removed": key, "how": "deleted", "layer": la.name, "trash": str(moved)}
    return {"ok": True, "removed": key, "how": how, "layer": la.name}


# --------------------------------------------------------------------------- #
# Groups                                                                       #
# --------------------------------------------------------------------------- #
def _group_dirs(gk: str, la: Layer) -> list[tuple[Path, str]]:
    """Group folders seen from ``la``, most specific first (as :func:`hani2.groups.search_dirs`)."""
    from hani2 import groups

    sub = groups.SUBDIR[gk]
    out: list[tuple[Path, str]] = []
    if la.level == "study":
        out.append((la.dir / "results" / sub, "results"))
    for x in reversed(la.chain()):
        out.append((x.dir / sub, x.name))
    return out


def _group_files(gk: str, la: Layer) -> list[dict[str, Any]]:
    from hani2 import groups

    out, seen = [], set()
    for d, source in _group_dirs(gk, la):
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            if not groups.valid_key(f.stem):
                continue
            g = groups.load_file(f, gk, f.stem, source)
            if g is None:
                continue
            out.append({"name": f.stem, "members": list(g.members), "description": g.description,
                        "layer": source, "path": str(f), "active": f.stem.lower() not in seen,
                        "assistant": g.assistant if gk == groups.OPPONENT else None, "syspath": g.syspath})
            seen.add(f.stem.lower())
    return out


def _group_lookup(gk: str, la: Layer):
    """The composition lookup of ``la``'s groups of ``gk`` (same rule as the
    session's: files first, built-ins for ``@``/``:`` references only)."""
    from hani2 import agents, groups

    by = {g["name"].lower(): g for g in _group_files(gk, la) if g["active"]}

    def lookup(name: str, explicit: bool):
        n = name.strip()
        if gk == groups.ASSISTANT and not explicit and ("." in n or ":" in n):
            return None
        g = by.get(n.lower())
        if g is not None:
            return g["name"], g["members"]
        if explicit:
            if gk == groups.ASSISTANT:
                m = groups.builtin_members(gk, n)
                if m is not None:
                    return n.lower(), m, True
            elif n.lower() != "pan" and agents._builtin_known(":" + n):
                return n.lower(), agents._resolve_builtin(":" + n), True
        return None

    return lookup


def list_groups(kind: str, layer: "str | Layer | None" = None) -> list[dict[str, Any]]:
    """Every group of ``kind`` seen from ``layer``: ``{name, entries (raw),
    expanded, source (file | builtin | custom), layer, editable, active, description}``."""
    kind = check_kind(kind)
    la = _layer(layer)
    with layer_context(la):
        if kind == "scenarios":
            return _set_groups(la)
        if kind == "tools":
            return _tool_groups(la)
        from hani2 import groups

        gk = _gkind(kind)
        lk = _group_lookup(gk, la)
        out = []
        for g in _group_files(gk, la):
            exp = composition.expand_entries(g["members"], lk, name=g["name"], label=f"{gk} group") if g["active"] else []
            out.append({"name": g["name"], "entries": g["members"], "expanded": [str(x) for x in exp],
                        "description": g["description"], "source": "file", "layer": g["layer"], "path": g["path"],
                        "active": g["active"], "editable": g["layer"] == la.name,
                        **({"assistant": g["assistant"]} if gk == groups.OPPONENT else {})})
        files = {g["name"].lower() for g in out if g["active"]}
        for k in groups.builtin_keys(gk):
            hit = lk(k, True) if k != "pan" else None  # importing the pan pool here is slow and noisy
            members = [str(x) for x in hit[1]] if hit and len(hit) > 2 else []
            out.append({"name": k, "entries": members, "expanded": members, "source": "builtin", "layer": None,
                        "description": groups.BUILTIN_DESCRIPTIONS.get((gk, k), ""), "path": None,
                        "active": k.lower() not in files, "editable": False})
        return out


def _set_groups(la: Layer) -> list[dict[str, Any]]:
    from hani2 import scenario_sets

    raw, default = scenario_sets.raw_sets()
    expanded = scenario_sets.expand(raw)
    where: dict[str, str] = {}
    files = [(scenario_sets.DEFAULT_SETTINGS_DIR / scenario_sets.FILE, "builtin")] + \
        [(x.dir / scenario_sets.FILE, x.name) for x in la.chain()]
    for f, source in files:
        if f.is_file():
            for n in (scenario_sets._read(f).get("sets") or {}):
                for old in [k for k in where if k.lower() == str(n).lower()]:
                    del where[old]
                where[str(n)] = source
    out = []
    for n, entries in raw.items():
        src = "custom" if n == scenario_sets.CUSTOM else where.get(n, "builtin")
        out.append({"name": n, "entries": list(entries), "expanded": list(expanded.get(n, [])),
                    "source": src if src in ("builtin", "custom") else "file",
                    "layer": None if src in ("builtin", "custom") else src, "default": n == default,
                    "editable": src == la.name, "active": True, "description": ""})
    return out


def _tool_groups(la: Layer) -> list[dict[str, Any]]:
    from hani2 import tool_groups
    from hani2.tools import registry

    specs = registry.tool_specs(offered_only=False)
    cfg = tool_groups.load_config()
    expanded = tool_groups.expanded_groups(specs, cfg)
    where: dict[str, str] = {}
    for x in la.chain():
        for n in tool_groups.read_file(x.dir / tool_groups.FILE)["groups"]:
            for old in [k for k in where if k.lower() == n.lower()]:
                del where[old]
            where[n] = x.name
    out = []
    for n, entries in cfg["groups"].items():
        out.append({"name": n, "entries": entries, "expanded": expanded.get(n, []), "source": "file",
                    "layer": where.get(n), "editable": where.get(n) == la.name, "active": True, "description": ""})
    for n, members in tool_groups.builtin_groups(specs).items():
        out.append({"name": n, "entries": members, "expanded": members, "source": "builtin", "layer": None,
                    "editable": False, "active": not any(o["name"].lower() == n for o in out),
                    "description": tool_groups.BUILTIN_GROUPS.get(n, "")})
    return out


def _normalise_entries(kind: str, la: Layer, entries: Any) -> list[str]:
    """Raw group entries as written; a library item's name becomes its spec
    (opponents and Assistants), so group files work without the library."""
    if not isinstance(entries, list) or not all(isinstance(x, str) for x in entries):
        raise LibraryError("entries must be a list of strings")
    clean = [x.strip() for x in entries if x.strip()]
    if kind in ("opponents", "assistants"):
        lib = {e["name"].lower(): e["spec"] for e in index_entries(kind, la.chain())}
        clean = [x if composition.is_ref(x) else lib.get(x.lower(), x) for x in clean]
    return clean


def put_group(kind: str, name: str, entries: list[str], layer: "str | Layer | None" = None, *,
              description: str | None = None, rename_from: str | None = None,
              extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create or replace group ``name`` at ``layer`` with raw ``entries``
    (``@group`` / ``:group`` references allowed). Other fields of an existing
    group file (``syspath``, ``assistant``, ``description``) are kept.
    ``rename_from`` renames a group of this layer (the old one is removed)."""
    kind = check_kind(kind)
    la = _layer(layer)
    name = composition.ref_name(str(name))
    if kind in ("opponents", "assistants"):
        from hani2 import groups

        if not groups.valid_key(name):
            raise LibraryError(f"invalid group name {name!r}: use letters, digits, '.', '_' and '-'")
    else:
        name = check_name(name, "group name")
    clean = _normalise_entries(kind, la, entries)
    with layer_context(la):
        if kind == "scenarios":
            path = _put_set(la, name, clean, rename_from)
        elif kind == "tools":
            from hani2 import tool_groups

            check_writable(la.dir / tool_groups.FILE)
            if name.lower() in tool_groups.BUILTIN_GROUPS:
                raise LibraryError(f"{name!r} is a built-in tool group; choose another name", 409)
            if rename_from and not tool_groups.delete_group(la.dir, composition.ref_name(rename_from)):
                raise LibraryError(f"no tool group {rename_from!r} at {la.name}", 404)
            path = tool_groups.write_group(la.dir, name, clean)
        else:
            path = _put_group_file(kind, la, name, clean, description, rename_from, extra)
    after = list_groups(kind, la)
    expanded = next((g["expanded"] for g in after if g["name"].lower() == name.lower() and g.get("active", True)), [])
    return {"ok": True, "name": name, "entries": clean, "expanded": expanded, "layer": la.name, "path": str(path),
            "warnings": group_warnings(kind, la, name, clean, after)}


def group_warnings(kind: str, layer: "str | Layer | None", name: str, entries: list[str],
                   groups_now: list[dict[str, Any]] | None = None) -> list[str]:
    """What looks wrong in group ``name``'s ``entries`` (saved anyway): a reference to an unknown
    group, an entry that is no known item or group, a cycle through other groups."""
    kind = check_kind(kind)
    la = _layer(layer)
    gs = [g for g in (groups_now if groups_now is not None else list_groups(kind, la)) if g.get("active", True)]
    by = {g["name"].lower(): g for g in gs}
    code = kind in ("opponents", "assistants")
    known: set[str] = set()
    if not code:
        for it in list_items_quick(kind, la):
            known.add(str(it.get("name", "")).lower())
    out: list[str] = []
    for e in entries:
        ref = composition.ref_name(e)
        is_group = ref.lower() in by and (composition.is_ref(e) or ref.lower() != name.lower())
        if composition.is_ref(e) and not is_group:
            out.append(f"{name}: unknown group {ref!r}")
        elif not is_group and code:
            # opponents and Assistants are class specs: say when one does not load
            info = _load_info(kind, e, la)
            if not info["ok"]:
                out.append(f"{name}: {info['error']}")
        elif not is_group and e.lower() not in known:
            out.append(f"{name}: {e!r} is no known {kind[:-1].replace('scenario', 'scenario type')} or group")
    # cycles: follow group references from this group
    graph = {g["name"].lower(): [composition.ref_name(x).lower() for x in g.get("entries") or []
                                 if composition.is_ref(x) or (composition.ref_name(x).lower() in by
                                                              and composition.ref_name(x).lower() != g["name"].lower())]
             for g in gs if g.get("source") != "builtin"}
    graph[name.lower()] = [composition.ref_name(x).lower() for x in entries
                           if composition.is_ref(x) or (x.lower() in by and x.lower() != name.lower())]
    seen: set[str] = set()

    def walk(n: str, stack: list[str]) -> None:
        if n in stack:
            cyc = stack[stack.index(n):] + [n]
            key = "->".join(sorted(set(cyc)))
            if key not in seen:
                seen.add(key)
                out.append(f"{name}: cycle {' -> '.join(cyc)} (the last step is ignored)")
            return
        if len(stack) > 50:
            return
        for m in graph.get(n, []):
            walk(m, stack + [n])

    walk(name.lower(), [])
    return out


def list_items_quick(kind: str, la: Layer) -> list[dict[str, Any]]:
    """The items of ``kind`` at ``la`` without their groups (what :func:`group_warnings` checks against)."""
    with layer_context(la):
        if kind == "scenarios":
            return _scenario_items(la)
        if kind == "tools":
            return _tool_items(la)
        return _class_items(kind, la)


# --------------------------------------------------------------------------- #
# Scenarios: the default set                                                   #
# --------------------------------------------------------------------------- #
def get_default_set(layer: "str | Layer | None" = None) -> dict[str, Any]:
    """``{layer, here, effective, sets}``: this layer's ``default`` in ``scenario_sets.yaml``
    (``None``: not set here), the default sessions of this layer get, and the set names."""
    from hani2 import scenario_sets

    la = _layer(layer)
    f = la.dir / scenario_sets.FILE
    here = scenario_sets._read(f).get("default") if f.is_file() else None
    with layer_context(la):
        raw, default = scenario_sets.raw_sets()
    return {"layer": la.name, "here": str(here) if here else None, "effective": default, "sets": list(raw)}


def put_default_set(name: str | None, layer: "str | Layer | None" = None) -> dict[str, Any]:
    """Set (``None``: remove) the default scenario set at ``layer``. The set must exist there."""
    from hani2 import scenario_sets

    la = _layer(layer)
    f = la.dir / scenario_sets.FILE
    check_writable(f)
    data = scenario_sets._read(f) if f.is_file() else {}
    if name is not None and str(name).strip():
        with layer_context(la):
            raw, _ = scenario_sets.raw_sets()
        n = composition.ref_name(str(name))
        hit = next((k for k in [*raw, scenario_sets.CUSTOM] if k.lower() == n.lower()), None)
        if hit is None:
            raise LibraryError(f"no scenario set {n!r} at {la.name}", 404)
        data["default"] = hit
    else:
        data.pop("default", None)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return get_default_set(la)


# --------------------------------------------------------------------------- #
# Describing entries (members of groups, pools)                                #
# --------------------------------------------------------------------------- #
_DESCRIBED: dict[tuple[str, str, str], dict[str, Any]] = {}


def describe(kind: str, entries: list[str], layer: "str | Layer | None" = None) -> list[dict[str, Any]]:
    """What each entry is: ``{entry, kind: item | group | unknown, name, title, description, ok,
    error}``. Opponent, Assistant and tool classes that are no library item are loaded (cached)
    to say whether they import."""
    kind = check_kind(kind)
    la = _layer(layer)
    if not isinstance(entries, list) or not all(isinstance(x, str) for x in entries):
        raise LibraryError("entries must be a list of strings")
    entries = list(dict.fromkeys(x.strip() for x in entries if x.strip()))[:2000]
    gs = {g["name"].lower(): g for g in list_groups(kind, la) if g.get("active", True)}
    items: dict[str, dict[str, Any]] = {}
    for it in list_items_quick(kind, la):
        for k in (it.get("name"), it.get("spec")):
            if k:
                items.setdefault(str(k).lower(), it)
    out = []
    for e in entries:
        ref = composition.ref_name(e)
        g = gs.get(ref.lower())
        if g is not None and (composition.is_ref(e) or e.lower() not in items):
            out.append({"entry": e, "kind": "group", "name": g["name"], "title": g["name"],
                        "description": g.get("description") or "", "n": len(g.get("expanded") or []), "ok": True,
                        "error": ""})
            continue
        if composition.is_ref(e):
            out.append({"entry": e, "kind": "unknown", "name": ref, "title": ref, "description": "", "ok": False,
                        "error": f"no group {ref!r}"})
            continue
        it = items.get(e.lower())
        d: dict[str, Any] = {"entry": e, "kind": "item" if it else "unknown", "name": (it or {}).get("name", e),
                             "title": (it or {}).get("title") or e, "description": (it or {}).get("description") or "",
                             "ok": it is not None, "error": "" if it else f"no {kind[:-1]} {e!r}"}
        if kind in ("opponents", "assistants") and not d["description"]:
            d.update(_load_info(kind, str((it or {}).get("spec") or e), la))
        out.append(d)
    return out


def _load_info(kind: str, spec: str, la: Layer) -> dict[str, Any]:
    key = (kind, spec, la.name)
    if key not in _DESCRIBED:
        try:
            with layer_context(la):
                cls = verify(kind, spec)
            doc = (inspect.getdoc(cls) or "").strip().splitlines()
            _DESCRIBED[key] = {"ok": True, "error": "", "description": doc[0] if doc else "",
                               "module": getattr(cls, "__module__", "")}
        except LibraryError as e:
            _DESCRIBED[key] = {"ok": False, "error": str(e), "description": ""}
    return dict(_DESCRIBED[key])


def _put_set(la: Layer, name: str, entries: list[str], rename_from: str | None) -> Path:
    from hani2 import scenario_sets

    if scenario_sets.CUSTOM.lower() in (name.lower(), (rename_from or "").lower()):
        raise LibraryError("Custom is the list in scenario_order.txt; edit that file instead", 409)
    f = la.dir / scenario_sets.FILE
    check_writable(f)
    data = scenario_sets._read(f) if f.is_file() else {}
    sets = dict(data.get("sets") or {})
    if rename_from:
        old = [k for k in sets if str(k).lower() == composition.ref_name(rename_from).lower()]
        if not old:
            raise LibraryError(f"no scenario set {rename_from!r} at {la.name}", 404)
        for k in old:
            del sets[k]
        if str(data.get("default") or "").lower() == composition.ref_name(rename_from).lower():
            data["default"] = name
    for k in [k for k in sets if str(k).lower() == name.lower()]:
        del sets[k]
    sets[name] = entries
    data["sets"] = sets
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    return f


def _put_group_file(kind: str, la: Layer, name: str, entries: list[str], description: str | None,
                    rename_from: str | None, extra: dict[str, Any] | None) -> Path:
    from hani2 import groups

    gk = _gkind(kind)
    d = la.group_dir(gk)
    if rename_from:
        old = d / f"{composition.ref_name(rename_from)}.json"
        if not groups.valid_key(old.stem) or not old.is_file():
            raise LibraryError(f"no {kind[:-1]} group {rename_from!r} at {la.name}", 404)
    else:
        old = next((x for x in sorted(d.glob("*.json")) if x.stem.lower() == name.lower()), d / f"{name}.json") \
            if d.is_dir() else d / f"{name}.json"
    current: dict[str, Any] = {}
    src = old if old.is_file() else None
    if src is None and not rename_from:
        # copying a group of a less specific layer here: start from its other fields
        lower = next((g for g in _group_files(gk, la) if g["active"] and g["name"].lower() == name.lower()), None)
        src = Path(lower["path"]) if lower else None
    if src is not None:
        try:
            data = json.loads(src.read_text())
            current = dict(data) if isinstance(data, dict) else {groups.MEMBERS_KEY[gk]: data}
        except Exception:  # noqa: BLE001 - a broken file is replaced
            current = {}
    for k in ("agents", "assistants", "members"):
        current.pop(k, None)
    current[groups.MEMBERS_KEY[gk]] = entries
    if description is not None:
        current["description"] = description
    for k, v in (extra or {}).items():
        if k in ("syspath", "assistant"):
            current[k] = v
    # the syspath of library items in the group, so the file works on its own
    lib = {e["spec"]: e["syspath"] for e in index_entries(kind, la.chain())}
    sp = list(current.get("syspath") or [])
    for x in entries:
        sp += [p for p in lib.get(x, []) if p not in sp]
    if sp:
        current["syspath"] = sp
    try:
        clean = groups.validate_data(gk, current)
    except ValueError as e:
        raise LibraryError(str(e)) from None
    clean.update({k: v for k, v in current.items() if k not in clean and k not in ("agents", "assistants", "support_agent")})
    f = d / f"{name}.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean, indent=2))
    if old.is_file() and old.resolve() != f.resolve():
        old.unlink()
    tmp.replace(f)
    return f


def delete_group(kind: str, name: str, layer: "str | Layer | None" = None) -> dict[str, Any]:
    """Delete a group defined at ``layer`` (a group of another layer, a built-in
    group or ``Custom`` cannot be deleted here: HTTP 409)."""
    kind = check_kind(kind)
    la = _layer(layer)
    name = composition.ref_name(str(name))
    mine = [g for g in list_groups(kind, la) if g["name"].lower() == name.lower()]
    g = next((x for x in mine if x.get("editable")), None)
    if g is None:
        if not mine:
            raise LibraryError(f"no group {name!r}", 404)
        where = mine[0].get("layer") or mine[0].get("source")
        raise LibraryError(f"{mine[0]['name']!r} comes from {where}; it is not defined at {la.name} and cannot be "
                           "deleted here (define a group of the same name here to replace it)", 409)
    if kind == "scenarios":
        from hani2 import scenario_sets

        f = la.dir / scenario_sets.FILE
        check_writable(f)
        data = scenario_sets._read(f)
        data["sets"] = {k: v for k, v in (data.get("sets") or {}).items() if str(k).lower() != name.lower()}
        f.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    elif kind == "tools":
        from hani2 import tool_groups

        check_writable(la.dir / tool_groups.FILE)
        tool_groups.delete_group(la.dir, name)
    else:
        Path(g["path"]).unlink()
    return {"ok": True, "deleted": g["name"], "layer": la.name}


def _add_to_group(kind: str, la: Layer, group: str, item: str) -> None:
    """Append ``item`` to group ``group`` at ``la`` (created when missing; a group
    of a lower layer is copied to this layer first)."""
    gname = composition.ref_name(group)
    current = next((g for g in list_groups(kind, la) if g["name"].lower() == gname.lower() and g.get("active", True)),
                   None)
    if current is not None and current["source"] in ("builtin", "custom"):
        raise LibraryError(f"{current['name']!r} is a built-in group; add the item to a group of your own", 409)
    entries = list(current["entries"]) if current else []
    if item not in entries:
        entries.append(item)
    put_group(kind, current["name"] if current else gname, entries, la)


# --------------------------------------------------------------------------- #
# Tools: placement and offer                                                   #
# --------------------------------------------------------------------------- #
def get_placement(layer: "str | Layer | None" = None) -> dict[str, Any]:
    """``{layer, views, panes, tools: {name: {effective: {view: placement}, here: <this layer's entry>}}}``."""
    from hani2 import tool_groups
    from hani2.tools import registry

    la = _layer(layer)
    with layer_context(la):
        specs = registry.tool_specs(offered_only=False)
    here = {k.lower(): v for k, v in tool_groups.read_file(la.dir / tool_groups.FILE)["placement"].items()}
    return {"layer": la.name, "views": list(tool_groups.VIEWS), "panes": list(tool_groups.PANES),
            "tools": {s.name: {"effective": s.placement, "here": here.get(s.name.lower())} for s in specs}}


def put_placement(placement: dict[str, Any], layer: "str | Layer | None" = None, replace: bool = False) -> dict[str, Any]:
    """Merge per-tool placements into ``layer``'s ``tools.yaml`` (``None`` removes a tool's entry)."""
    from hani2 import tool_groups

    la = _layer(layer)
    if not isinstance(placement, dict):
        raise LibraryError("placement must map tool names to placements")
    check_writable(la.dir / tool_groups.FILE)
    try:
        tool_groups.write_placement(la.dir, placement, replace=replace)
    except ValueError as e:
        raise LibraryError(str(e)) from None
    return get_placement(la)


def get_offer(layer: "str | Layer | None" = None) -> dict[str, Any]:
    """The tools offered at ``layer``: ``{layer, here, effective, tools}`` (``effective`` ``None``: every tool)."""
    from hani2 import tool_groups
    from hani2.tools import registry

    la = _layer(layer)
    with layer_context(la):
        specs = registry.tool_specs(offered_only=False)
        cfg = tool_groups.load_config()
        offered = tool_groups.offered(specs, cfg)
    return {"layer": la.name, "here": tool_groups.read_file(la.dir / tool_groups.FILE)["offer"],
            "effective": cfg.get("offer"),
            "tools": [s.name for s in specs if offered is None or s.name.lower() in offered]}


def put_offer(entries: list[str] | None, layer: "str | Layer | None" = None) -> dict[str, Any]:
    from hani2 import tool_groups

    la = _layer(layer)
    if entries is not None and (not isinstance(entries, list) or not all(isinstance(x, str) for x in entries)):
        raise LibraryError("offer must be a list of tool names and groups, or null")
    check_writable(la.dir / tool_groups.FILE)
    tool_groups.write_offer(la.dir, entries)
    return get_offer(la)
