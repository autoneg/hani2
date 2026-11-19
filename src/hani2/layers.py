"""Settings layers for the admin console.

A layer id is ``settings`` | ``project:<P>`` | ``study:<P>/<S>``. ``project:default`` is the
settings layer (the default project has no folder of its own). :func:`binding` resolves
settings *as they are at* a layer, whatever study the admin's request is bound to.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from hani2 import projects
from hani2.config import DEFAULT_SETTINGS_DIR, layer_view, settings_dir

#: JSON settings files by kind (the loader gives the effective, merged value)
def _env_effective() -> dict:
    """env.json in effect, with the built-in defaults of the per-session ``negotiation`` and
    ``interface`` sections filled in (so the console shows every value a session uses)."""
    from hani2.config import _deep_merge, load_env
    from hani2.session import ADMIN_PREFS, DEFAULT_INTERFACE

    base = {"negotiation": {k: v for k, v in ADMIN_PREFS.items()}, "interface": DEFAULT_INTERFACE}
    return _deep_merge(base, load_env())


SETTINGS_KINDS: dict[str, tuple[str, Any]] = {
    "env": ("env.json", _env_effective),
    "llm": ("llm_settings.json", lambda: __import__("hani2.config", fromlist=["x"]).load_llm_settings()),
    "assistant": ("assistant_settings.json",
                  lambda: __import__("hani2.support_agent.settings", fromlist=["x"]).load_assistant_settings()),
    "autopilot": ("autopilot_settings.json",
                  lambda: __import__("hani2.support_agent.autopilot", fromlist=["x"]).load_autopilot_settings()),
}
#: the model chains of a layer; "effective" is what each purpose uses there (hani2.model_chain)
SETTINGS_KINDS["models"] = ("models.json",
                            lambda: __import__("hani2.model_chain", fromlist=["x"]).effective_chains())
SETTINGS_KINDS["support_agent"] = SETTINGS_KINDS["assistant"]  # old name of the kind
TEXT_FILES = {"consent": "consent.md", "announcements": "announcements.md", "scenario_order": "scenario_order.txt",
              "scenario_sets": "scenario_sets.yaml"}


class LayerError(Exception):
    """``status`` is the HTTP status the admin API answers with (400 invalid, 404 unknown)."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Layer:
    id: str
    kind: str  # settings | project | study
    project: str | None = None
    study: str | None = None

    @property
    def ref(self) -> "projects.StudyRef | None":
        return projects.StudyRef(self.project, self.study) if self.kind == "study" else None

    @property
    def dir(self) -> Path:
        if self.kind == "study":
            return projects.study_dir(self.ref)  # type: ignore[arg-type]
        if self.kind == "project":
            return projects.project_dir(self.project)  # type: ignore[arg-type]
        return settings_dir()

    @property
    def label(self) -> str:
        if self.kind == "study":
            return f"Study {self.project}/{self.study}"
        if self.kind == "project":
            return f"Project {self.project}"
        return "All projects (settings folder)"

    @property
    def parent(self) -> "Layer | None":
        if self.kind == "study":
            return project_layer(self.project) if self.project != projects.DEFAULT_PROJECT else SETTINGS  # type: ignore[arg-type]
        if self.kind == "project":
            return SETTINGS
        return None


SETTINGS = Layer("settings", "settings")


def project_layer(project: str) -> Layer:
    return SETTINGS if project == projects.DEFAULT_PROJECT else Layer(f"project:{project}", "project", project)


def parse_layer(layer: str | None = None, study: str | None = None, project: str | None = None,
                default: Layer | None = SETTINGS) -> Layer | None:
    """The layer an admin call names (``layer``, else the old ``study`` / ``project`` parameters).
    ``default`` is returned when none is given. Raises :class:`LayerError`."""
    try:
        if layer:
            lay = layer.strip()
            if lay == "settings":
                return SETTINGS
            kind, _, rest = lay.partition(":")
            if kind == "project" and rest:
                study, project = None, rest
            elif kind == "study" and rest:
                study, project = rest, None
            else:
                raise LayerError(400, f"invalid layer {layer!r}: use settings, project:<P> or study:<P>/<S>")
        if study:
            ref = projects.parse_ref(study)
            if ref is None:
                raise LayerError(400, "invalid study")
            if not projects.study_exists(ref):
                raise LayerError(404, "Unknown study")
            return Layer(f"study:{ref}", "study", ref.project, ref.study)
        if project:
            projects.check_name(project, "project")
            if project == projects.DEFAULT_PROJECT:
                return SETTINGS
            if not projects.project_exists(project):
                raise LayerError(404, "Unknown project")
            return project_layer(project)
    except ValueError as e:
        raise LayerError(400, str(e)) from None
    return default


@contextlib.contextmanager
def binding(layer: Layer, skip_own: bool = False) -> Iterator[None]:
    """Resolve settings for ``layer`` (with ``skip_own``: for the layer below it, i.e. what it inherits)."""
    if skip_own:
        par = layer.parent
        if par is None:
            with projects.use_study(None), layer_view(None, skip_settings=True):
                yield
            return
        layer = par
    if layer.kind == "study":
        with projects.use_study(layer.ref):
            yield
    else:
        with projects.use_study(None), layer_view(layer.project if layer.kind == "project" else None):
            yield


def list_layers() -> list[Layer]:
    out = [SETTINGS]
    for p in projects.list_projects():
        if p != projects.DEFAULT_PROJECT:
            out.append(project_layer(p))
    for p in projects.list_projects():
        for s in projects.list_studies(p):
            out.append(Layer(f"study:{p}/{s}", "study", p, s))
    return out


def layer_of_path(path: Path) -> str:
    """The layer id a settings file belongs to (``bundled`` for the package defaults)."""
    try:
        parent = path.resolve().parent
    except OSError:
        return "settings"
    if parent == DEFAULT_SETTINGS_DIR.resolve():
        return "bundled"
    for lay in list_layers():
        try:
            if lay.dir.resolve() == parent:
                return lay.id
        except (OSError, ValueError):
            continue
    return "settings"


# --------------------------------------------------------------------------- #
# JSON helpers                                                                 #
# --------------------------------------------------------------------------- #
def read_json_own(path: Path) -> dict:
    """A layer's own JSON file (``{}`` when missing). Raises :class:`LayerError` 409 when it is not valid JSON."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        raise LayerError(409, f"{path.name} in this layer is not valid JSON") from None
    if not isinstance(data, dict):
        raise LayerError(409, f"{path.name} in this layer is not a JSON object")
    return data


def write_json_own(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    tmp.replace(path)


def remove_dotted(data: dict, key: str) -> bool:
    """Remove ``a.b.c`` from nested dicts (empty parents are dropped). Returns whether it existed."""
    parts = key.split(".")
    stack: list[tuple[dict, str]] = []
    cur: Any = data
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return False
        stack.append((cur, p))
        cur = cur[p]
    if not isinstance(cur, dict) or parts[-1] not in cur:
        return False
    del cur[parts[-1]]
    for parent, k in reversed(stack):
        if isinstance(parent[k], dict) and not parent[k]:
            del parent[k]
        else:
            break
    return True
