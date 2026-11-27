"""Configuration and file locations for HANI2.

All paths are resolved lazily so tests (and the CLI) can redirect the whole
installation with the ``HANI2_HOME`` environment variable.

Precedence for every settings file (first hit wins):

1. ``<study folder>/<file>``  (only when a study is active — see :mod:`hani2.projects`)
2. ``<project folder>/<file>``  (the study's project; not for the default project)
3. ``$HANI2_HOME/settings/<file>``  (default ``~/negmas/hani2/settings``)
4. ``<package>/default_settings/<file>``  (bundled defaults)

The active study is per session (see :func:`hani2.projects.current_study`); an
old experiment (``HANI2_EXPERIMENT``) is a study of the default project.
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).parent
DEFAULT_SETTINGS_DIR = PACKAGE_DIR / "default_settings"
DEFAULT_SCENARIOS = PACKAGE_DIR / "sample_scenarios" / "Default"
# Aliases used by the scenario modules.
DEFAULT_SCENRIOS = DEFAULT_SCENARIOS
INFO_FILE_NAME = "_info.yaml"
DEFAULT_PORT = 5006


def home() -> Path:
    return Path(os.environ.get("HANI2_HOME", Path.home() / "negmas" / "hani2")).expanduser()


def settings_dir() -> Path:
    return home() / "settings"


def experiments_root() -> Path:
    return Path(
        os.environ.get("HANI2_EXPERIMENTS", home() / "experiments")
    ).expanduser()


def experiment_name() -> str | None:
    """The current study's name (``project/study`` outside the default project); ``None`` without a study."""
    from hani2.projects import DEFAULT_PROJECT, current_study

    ref = current_study()
    if ref is None:
        return None
    return ref.study if ref.project == DEFAULT_PROJECT else str(ref)


def experiment_dir() -> Path | None:
    """The current study's folder (``None`` without a study). Old name, kept for callers."""
    from hani2.projects import current_study, study_dir

    ref = current_study()
    return study_dir(ref) if ref is not None else None


current_study_dir = experiment_dir


#: An admin view of one settings layer: ``(project, skip_settings)``. ``project`` replaces the
#: current study's project as the project layer; ``skip_settings`` hides the settings folder
#: (to see what the bundled defaults give). ``None``: no view (the normal resolution).
_VIEW: "contextvars.ContextVar[tuple[str | None, bool] | None]" = contextvars.ContextVar("hani2_layer_view", default=None)


def view_project() -> str | None:
    """The project of the active layer view (``None``: no view or no project)."""
    v = _VIEW.get()
    return v[0] if v else None


@contextlib.contextmanager
def layer_view(project: str | None = None, skip_settings: bool = False):
    """Resolve settings as if only ``project``'s folder (and the settings folder unless
    ``skip_settings``) applied; use together with ``projects.use_study(None)``."""
    tok = _VIEW.set((project, skip_settings))
    try:
        yield
    finally:
        _VIEW.reset(tok)


def project_dir() -> Path | None:
    """The current study's project folder (``None`` for the default project, whose layer is the settings folder)."""
    from hani2.projects import current_study, project_layer_dir

    ref = current_study()
    v = _VIEW.get()
    if v is not None and ref is None:
        return project_layer_dir(v[0])
    return project_layer_dir(ref.project if ref else None)


_LAYERS_OVERRIDE: "contextvars.ContextVar[list[Path] | None]" = contextvars.ContextVar("hani2_layers", default=None)


@contextlib.contextmanager
def use_layers(dirs: "list[Path] | None"):
    """Run a block with :func:`settings_layers` fixed to ``dirs`` (most specific
    first; ``None``: the current study's, as usual). The library uses it to read
    a project's settings without one of its studies."""
    tok = _LAYERS_OVERRIDE.set(None if dirs is None else list(dirs))
    try:
        yield
    finally:
        _LAYERS_OVERRIDE.reset(tok)


def settings_layers() -> list[Path]:
    """The study and project folders of the current study, most specific first."""
    fixed = _LAYERS_OVERRIDE.get()
    if fixed is not None:
        return list(fixed)
    return [d for d in (experiment_dir(), project_dir()) if d is not None]


def results_root() -> Path:
    """Where results, events and per-user data are written."""
    exp = experiment_dir()
    path = (exp / "results") if exp is not None else home() / "db"
    path.mkdir(parents=True, exist_ok=True)
    return path


def scenarios_dir() -> Path:
    for layer in settings_layers():
        if (layer / "scenarios").is_dir():
            return layer / "scenarios"
    return settings_dir() / "scenarios"


def get_settings_file(filename: str) -> Path:
    for layer in settings_layers():
        if (layer / filename).exists():
            return layer / filename
    user = settings_dir() / filename
    v = _VIEW.get()
    if user.exists() and not (v and v[1]):
        return user
    default = DEFAULT_SETTINGS_DIR / filename
    if default.exists():
        return default
    return user


def read_settings_text(filename: str, default: str = "") -> str:
    path = get_settings_file(filename)
    return path.read_text(encoding="utf-8") if path.exists() else default


def _deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# --------------------------------------------------------------------------- #
# Start-time overrides: ``hani2 --settings overrides.yaml``                     #
# --------------------------------------------------------------------------- #
#: the environment variable that carries the overrides file to the server process
OVERRIDES_ENV_VAR = "HANI2_SETTINGS_OVERRIDES"
#: top-level keys of an overrides file → the settings file they override
OVERRIDE_KINDS: dict[str, str] = {
    "env": "env.json",
    "llm": "llm_settings.json",
    "assistant": "assistant_settings.json",
    "support_agent": "assistant_settings.json",  # old name
    "autopilot": "autopilot_settings.json",
    "models": "models.json",
}
_OVERRIDES_CACHE: dict[str, Any] = {"key": None, "data": {}}


def overrides_path() -> Path | None:
    """The start-time overrides file (``hani2 --settings FILE``), if any."""
    v = (os.environ.get(OVERRIDES_ENV_VAR) or "").strip()
    return Path(v).expanduser() if v else None


def read_overrides_file(path: Path) -> dict[str, Any]:
    """``{settings file name: values}`` from an overrides YAML (or JSON) file.

    Top-level keys ``env``, ``llm``, ``assistant``, ``autopilot`` and ``models``
    override that settings file; any other top-level key (``negotiation``,
    ``interface``, ``tools``, …) is a key of ``env.json``. Raises ``ValueError``
    when the file cannot be read."""
    import yaml

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        raise ValueError(f"{path}: {e}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path}: the overrides must be a mapping")
    out: dict[str, Any] = {}
    for k, v in data.items():
        target = OVERRIDE_KINDS.get(str(k))
        if target is None:
            out.setdefault("env.json", {})[str(k)] = v
        elif target == "models.json":
            out[target] = v if isinstance(v, (dict, list)) else {}
        elif isinstance(v, dict):
            out[target] = _deep_merge(out.get(target, {}), v)
        else:
            raise ValueError(f"{path}: '{k}' must be a mapping")
    return out


def overrides() -> dict[str, Any]:
    """The start-time overrides (cached; re-read when the file changes)."""
    path = overrides_path()
    if path is None:
        return {}
    try:
        key = (str(path), path.stat().st_mtime)
    except OSError:
        print(f"[hani2] the settings overrides file {path} is missing; ignoring it")
        return {}
    if _OVERRIDES_CACHE["key"] != key:
        try:
            _OVERRIDES_CACHE["data"] = read_overrides_file(path)
        except ValueError as e:
            print(f"[hani2] ERROR: {e}; ignoring it")
            _OVERRIDES_CACHE["data"] = {}
        _OVERRIDES_CACHE["key"] = key
    return _OVERRIDES_CACHE["data"]


def override_for(filename: str) -> Any:
    """The start-time override of one settings file (``None``: none)."""
    return overrides().get(filename)


def load_json_settings(filename: str, defaults: dict | None = None, old_names: tuple[str, ...] = ()) -> dict:
    """Load a JSON settings file merged over the bundled default and ``defaults``.

    ``old_names`` are earlier names of the same file, still read. The layers,
    lowest precedence first: ``defaults``, the bundled default, then in the
    settings folder each old name followed by ``filename`` (so the new name wins
    over an old one at each level), then the start-time overrides
    (``hani2 --settings``), then the same files in the project folder and then
    in the study folder. Guest sessions and sessions outside a project or study
    therefore see the overrides over the settings folder, while a project's or a
    study's own settings still win over them."""
    merged: dict = deepcopy(defaults or {})
    bundled = DEFAULT_SETTINGS_DIR / filename
    if bundled.exists():
        try:
            merged = _deep_merge(merged, json.loads(bundled.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    names = [*old_names, filename]
    skip = _VIEW.get()
    layers: list[Path | dict] = [] if skip and skip[1] else [settings_dir() / n for n in names]
    ov = override_for(filename)
    if isinstance(ov, dict) and ov and not (skip and skip[1]):
        layers.append(ov)
    for folder in reversed(settings_layers()):
        layers += [folder / n for n in names]
    for layer in layers:
        if isinstance(layer, dict):
            merged = _deep_merge(merged, layer)
        elif layer.exists():
            try:
                merged = _deep_merge(merged, json.loads(layer.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                print(f"[hani2] could not parse {layer}; ignoring it")
    merged.pop("_comment", None)
    return merged


def read_json_own_file(path: Path) -> dict:
    """One layer's own JSON file as a mapping (``{}`` when missing or unreadable)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_json_settings(filename: str, data: dict) -> Path:
    path = settings_dir() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# env.json — the main deployment configuration                                 #
# --------------------------------------------------------------------------- #
DEFAULT_ENV: dict[str, Any] = {
    "title": "HANI2",
    "subtitle": "Human-Agent Negotiation Interface",
    "admin": {"password": "adminpass", "emails": []},
    "auth": {
        "mode": "password",  # password | oauth | dual | none | auto
        "cookie_secret": "",
        "enforce_consent": False,
        "allow_registration": True,
        "default_password_login": "auto",  # auto | refuse | allow (admins with a default password)
    },
    "oauth": {
        "redirect_uri": "http://localhost:5006",
        "providers": {
            "github": {"enabled": False, "key": "", "secret": ""},
            "google": {"enabled": False, "key": "", "secret": ""},
        },
    },
    "opponents": [],
    "negotiation": {"n_steps": 100, "time_limit": 300},
    "playground": {"enabled": True},
    # WebMCP: expose the negotiation to AI agents running in the browser.
    "webmcp": {"enabled": True, "actions": True, "studies": False},
    # the Preferences tools: weights as a bar (``donut`` in the tool's window when
    # weights_chart_window says so), normalized percentages or raw numbers, a line
    # instead of bars above values_line_above options;
    # tools.isolate_builtin: built-in tools' failures are shown in their pane too (external tools' always are);
    # tools.render_timeout: seconds a guarded tool may take for one call; tools.input_timeout: the same for
    # an input or a button, so the interface is not stuck behind a hung tool for long (see hani2.tools.failure)
    "tools": {"maximize": "window", "weights_chart": "bar", "weights_chart_window": "same",
              "preferences_scale": "normalized", "values_line_above": 12, "isolate_builtin": True,
              "render_timeout": 20, "input_timeout": 8},
    # negmas statistics of each scenario, computed in the background (see hani2.scenario_stats)
    "scenario_stats": {"enabled": True, "pareto_max_outcomes": 1_000_000, "timeout": 300},
    # HAN league agents: the current year comes from its submitted zips (see hani2.han_submissions),
    # every other year from the han-agents package; None: every year from the package
    "han": {"current_year": None, "submissions": {}},
}


def load_env() -> dict[str, Any]:
    env = load_json_settings("env.json", DEFAULT_ENV)
    if not env["auth"].get("cookie_secret"):
        # Persist a random secret so sessions survive restarts.
        secret_file = settings_dir() / ".cookie_secret"
        if secret_file.exists():
            env["auth"]["cookie_secret"] = secret_file.read_text(encoding="utf-8").strip()
        else:
            s = secrets.token_hex(32)
            try:
                secret_file.parent.mkdir(parents=True, exist_ok=True)
                secret_file.write_text(s, encoding="utf-8")
            except OSError:
                pass
            env["auth"]["cookie_secret"] = s
    return env


def get_env(key_path: str, default: Any = None) -> Any:
    value: Any = load_env()
    for key in key_path.split("."):
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


# --------------------------------------------------------------------------- #
# LLM settings (offer generator / text extraction)                            #
# --------------------------------------------------------------------------- #
try:
    from negmas_llm.common import DEFAULT_MODELS

    _default_ollama_model = DEFAULT_MODELS.get("ollama", "qwen3:4b-instruct")
except Exception:  # pragma: no cover - optional
    _default_ollama_model = "qwen3:4b-instruct"

from hani2._llm_prompts import EXTRACTION_PROMPT, GENERATION_PROMPT, INSTRUCTION_PROMPT  # noqa: E402

DEFAULT_LLM_SETTINGS: dict[str, Any] = {
    "provider": "ollama",
    "model": _default_ollama_model,
    "api_key_env": "OPENAI_API_KEY",
    "ollama_base_url": "http://localhost:11434/v1",
    "temperature": 0.3,
    "max_tokens": 2000,
    "extraction_prompt": EXTRACTION_PROMPT,
    "generation_prompt": GENERATION_PROMPT,
    "instruction_prompt": INSTRUCTION_PROMPT,
}


def load_llm_settings() -> dict:
    return load_json_settings("llm_settings.json", DEFAULT_LLM_SETTINGS)


def save_llm_settings(settings: dict) -> None:
    save_json_settings("llm_settings.json", settings)
