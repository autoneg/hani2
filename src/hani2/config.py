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


def project_dir() -> Path | None:
    """The current study's project folder (``None`` for the default project, whose layer is the settings folder)."""
    from hani2.projects import current_study, project_layer_dir

    ref = current_study()
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
    if user.exists():
        return user
    default = DEFAULT_SETTINGS_DIR / filename
    if default.exists():
        return default
    return user


def read_settings_text(filename: str, default: str = "") -> str:
    path = get_settings_file(filename)
    return path.read_text() if path.exists() else default


def _deep_merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_json_settings(filename: str, defaults: dict | None = None, old_names: tuple[str, ...] = ()) -> dict:
    """Load a JSON settings file merged over the bundled default and ``defaults``.

    ``old_names`` are earlier names of the same file, still read. The layers,
    lowest precedence first: ``defaults``, the bundled default, then in the
    settings folder, then in the project folder and then in the study folder
    each old name followed by ``filename`` (so the new name wins over an old
    one at each level)."""
    merged: dict = deepcopy(defaults or {})
    bundled = DEFAULT_SETTINGS_DIR / filename
    if bundled.exists():
        try:
            merged = _deep_merge(merged, json.loads(bundled.read_text()))
        except json.JSONDecodeError:
            pass
    names = [*old_names, filename]
    layers = [settings_dir() / n for n in names]
    for folder in reversed(settings_layers()):
        layers += [folder / n for n in names]
    for layer in layers:
        if layer.exists():
            try:
                merged = _deep_merge(merged, json.loads(layer.read_text()))
            except json.JSONDecodeError:
                print(f"[hani2] could not parse {layer}; ignoring it")
    merged.pop("_comment", None)
    return merged


def save_json_settings(filename: str, data: dict) -> Path:
    path = settings_dir() / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
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
    "tools": {"maximize": "window"},
}


def load_env() -> dict[str, Any]:
    env = load_json_settings("env.json", DEFAULT_ENV)
    if not env["auth"].get("cookie_secret"):
        # Persist a random secret so sessions survive restarts.
        secret_file = settings_dir() / ".cookie_secret"
        if secret_file.exists():
            env["auth"]["cookie_secret"] = secret_file.read_text().strip()
        else:
            s = secrets.token_hex(32)
            try:
                secret_file.parent.mkdir(parents=True, exist_ok=True)
                secret_file.write_text(s)
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
