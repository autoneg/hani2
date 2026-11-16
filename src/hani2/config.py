"""Configuration and file locations for HANI2.

All paths are resolved lazily so tests (and the CLI) can redirect the whole
installation with the ``HANI2_HOME`` environment variable.

Precedence for every settings file (first hit wins):

1. ``<experiment dir>/<file>``  (only when an experiment is active)
2. ``$HANI2_HOME/settings/<file>``  (default ``~/negmas/hani2/settings``)
3. ``<package>/default_settings/<file>``  (bundled defaults)
"""

from __future__ import annotations

import json
import os
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).parent
DEFAULT_SETTINGS_DIR = PACKAGE_DIR / "default_settings"
DEFAULT_SCENARIOS = PACKAGE_DIR / "sample_scenarios" / "Default"
# Backwards compatible aliases used by modules ported from HANI.
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
    return (os.environ.get("HANI2_EXPERIMENT") or "").strip() or None


def experiment_dir() -> Path | None:
    name = experiment_name()
    return experiments_root() / name if name else None


def results_root() -> Path:
    """Where results, events and per-user data are written."""
    exp = experiment_dir()
    path = (exp / "results") if exp is not None else home() / "db"
    path.mkdir(parents=True, exist_ok=True)
    return path


def scenarios_dir() -> Path:
    exp = experiment_dir()
    if exp is not None and (exp / "scenarios").is_dir():
        return exp / "scenarios"
    return settings_dir() / "scenarios"


def get_settings_file(filename: str) -> Path:
    exp = experiment_dir()
    if exp is not None and (exp / filename).exists():
        return exp / filename
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


def load_json_settings(filename: str, defaults: dict | None = None) -> dict:
    """Load a JSON settings file merged over the bundled default and ``defaults``."""
    merged: dict = deepcopy(defaults or {})
    bundled = DEFAULT_SETTINGS_DIR / filename
    if bundled.exists():
        try:
            merged = _deep_merge(merged, json.loads(bundled.read_text()))
        except json.JSONDecodeError:
            pass
    user = get_settings_file(filename)
    if user.exists() and user != bundled:
        try:
            merged = _deep_merge(merged, json.loads(user.read_text()))
        except json.JSONDecodeError:
            pass
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
    "title": "HANI",
    "subtitle": "Human-Agent Negotiation Interface",
    "admin": {"password": "adminpass", "emails": []},
    "auth": {
        "mode": "password",  # password | oauth | dual | none
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
    "agents": [],
    "negotiation": {
        "n_steps": 20,
        "time_limit": None,
        "step_time_limit": None,
        "human_starts": None,
        "allow_text": True,
        "show_agent_text": True,
    },
    "playground": {"enabled": True, "support_agent": None},
    "tools": {},
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
# LLM settings (offer generator / text extraction), ported from HANI           #
# --------------------------------------------------------------------------- #
try:
    from negmas_llm.common import DEFAULT_MODELS

    _default_ollama_model = DEFAULT_MODELS.get("ollama", "qwen3:4b-instruct")
except Exception:  # pragma: no cover - optional
    _default_ollama_model = "qwen3:4b-instruct"

from hani2._llm_prompts import EXTRACTION_PROMPT, GENERATION_PROMPT  # noqa: E402

DEFAULT_LLM_SETTINGS: dict[str, Any] = {
    "provider": "ollama",
    "model": _default_ollama_model,
    "api_key_env": "OPENAI_API_KEY",
    "ollama_base_url": "http://localhost:11434/v1",
    "temperature": 0.3,
    "max_tokens": 2000,
    "extraction_prompt": EXTRACTION_PROMPT,
    "generation_prompt": GENERATION_PROMPT,
}


def load_llm_settings() -> dict:
    return load_json_settings("llm_settings.json", DEFAULT_LLM_SETTINGS)


def save_llm_settings(settings: dict) -> None:
    save_json_settings("llm_settings.json", settings)
