"""Refusing confusing combinations of settings.

Two settings that mean the same thing (a new name and its old alias) or that
contradict each other (a single Assistant class and an Assistant pool) are refused
with a message that says which one to use. Old names alone keep working.

* :func:`env_problems` checks environment variables and :func:`settings_problems`
  the settings folder's ``env.json`` (``hani2`` checks them before starting, and the
  server again when it starts, so a process launched without the command line is
  checked too);
* :func:`cli_problems` checks the options of ``hani2`` and ``hani2 experiment create`` (and
  ``--models`` against ``HANI2_MODELS``);
* :func:`models_problems` checks a start-time model list; :func:`settings_problems` also checks the
  settings folder's ``models.json``;
* :func:`hani2.projects.file_problems` checks project.yaml / study.yaml and
  :func:`hani2.groups.group_problems` checks group files.
"""

from __future__ import annotations

import os
from typing import Mapping

_OFF = ("off", "0", "false", "no", "disabled", "none")


class ConflictError(ValueError):
    """Confusing or contradictory settings."""


def _get(env: Mapping[str, str], name: str) -> str:
    return (env.get(name) or "").strip()


def _alias(env: Mapping[str, str], new: str, old: str, out: list[str]) -> None:
    a, b = _get(env, new), _get(env, old)
    if a and b and a != b:
        out.append(f"{new}={a!r} and its old name {old}={b!r} disagree; set only {new}")


def env_problems(env: Mapping[str, str] | None = None) -> list[str]:
    """What is confusing in the environment (``[]``: nothing)."""
    env = os.environ if env is None else env
    out: list[str] = []
    _alias(env, "HANI2_ASSISTANT", "HANI2_SUPPORT_AGENT", out)
    _alias(env, "HANI2_ASSISTANT_CLASS", "HANI2_SUPPORT_AGENT_CLASS", out)
    _alias(env, "HANI2_OPPONENTS", "HANI2_AGENTS", out)
    _alias(env, "PROLIFIC_PRACTICE_OPPONENTS", "PROLIFIC_PRACTICE_AGENTS", out)
    _alias(env, "HANI2_PER_NEG_YAML", "PROLIFIC_PER_NEG_YAML", out)
    pool = _get(env, "HANI2_ASSISTANTS")
    klass = _get(env, "HANI2_ASSISTANT_CLASS") or _get(env, "HANI2_SUPPORT_AGENT_CLASS")
    if pool and klass:
        out.append(f"HANI2_ASSISTANT_CLASS={klass!r} (one Assistant class, hani2 --assistant <class>) and "
                   f"HANI2_ASSISTANTS={pool!r} (an Assistant pool, hani2 --assistants) are both set; use "
                   "HANI2_ASSISTANTS alone (a pool may hold a single class) or HANI2_ASSISTANT_CLASS alone")
    mode = (_get(env, "HANI2_ASSISTANT") or _get(env, "HANI2_SUPPORT_AGENT")).lower()
    if pool and mode in _OFF:
        out.append(f"HANI2_ASSISTANT={mode!r} switches the Assistant off but HANI2_ASSISTANTS={pool!r} names "
                   "an Assistant pool; unset one of them")
    models = _get(env, "HANI2_MODELS")
    if models:
        out += models_problems(models, "HANI2_MODELS")
    study, exp = _get(env, "HANI2_STUDY"), _get(env, "HANI2_EXPERIMENT")
    if study and exp and study not in (exp, f"default/{exp}"):
        out.append(f"HANI2_STUDY={study!r} and HANI2_EXPERIMENT={exp!r} (its old name, a study of the default "
                   "project) are both set; set only HANI2_STUDY (project/study)")
    return out


def models_problems(value: str, where: str = "--models") -> list[str]:
    """What is wrong with a start-time model list (``provider:model,…``)."""
    from hani2 import model_chain

    try:
        if not model_chain.parse_chain(value):
            return [f"{where} is empty; give provider:model entries, e.g. anthropic:claude-sonnet-5-5,ollama:qwen3:4b"]
    except model_chain.ChainError as e:
        return [f"{where}: {e}"]
    return []


def settings_problems() -> list[str]:
    """What is confusing in the settings folder's ``env.json``: ``opponents`` and its old name
    ``agents`` both given with different values."""
    try:
        from hani2.config import get_env

        new, old = get_env("opponents", None) or [], get_env("agents", None) or []
    except Exception:  # noqa: BLE001 - a broken file is reported where it is read
        return []
    out: list[str] = []
    if new and old and list(new) != list(old):
        out.append(f"env.json gives 'opponents' ({new!r}) and its old name 'agents' ({old!r}) with different "
                   "values; keep only 'opponents'")
    try:
        import json

        from hani2.config import settings_dir
        from hani2.model_chain import FILE, check_chains

        f = settings_dir() / FILE
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                out.append(f"{f} is not valid JSON ({e})")
            else:
                out += [f"{f}: {p}" for p in check_chains(data)]
    except Exception:  # noqa: BLE001 - reported where it is read
        pass
    return out


def startup_problems(env: Mapping[str, str] | None = None) -> list[str]:
    """Everything :func:`check_environment` refuses at startup."""
    return env_problems(env) + settings_problems()


def check_environment(env: Mapping[str, str] | None = None) -> None:
    """Raise :class:`ConflictError` naming every problem of :func:`env_problems`."""
    problems = startup_problems(env)
    if problems:
        raise ConflictError("confusing settings: " + "; ".join(problems))


def cli_problems(*, assistant: str | None = None, support_agent: str | None = None, assistants: str | None = None,
                 no_assistant: bool = False, no_support_agent: bool = False, study: str | None = None,
                 experiment: str | None = None, opponents: str | None = None, agents: str | None = None,
                 scenario_set: str | None = None, set_alias: str | None = None, models: str | None = None,
                 env: Mapping[str, str] | None = None) -> list[str]:
    """What is confusing in a set of command-line options (``[]``: nothing)."""
    out: list[str] = []
    if models:
        out += models_problems(models)
        env_models = _get(os.environ if env is None else env, "HANI2_MODELS")
        if env_models and env_models != models.strip():
            out.append(f"--models {models} and HANI2_MODELS={env_models!r} disagree; give only one (--models "
                       "sets HANI2_MODELS for the server)")
    if assistant and support_agent:
        out.append("--support-agent is the old name of --assistant; give only --assistant")
    value = (assistant or support_agent or "").strip()
    off_flag = no_assistant or no_support_agent
    if off_flag and value and value.lower() not in _OFF:
        out.append(f"--no-assistant switches the Assistant off but --assistant {value} asks for one; give only one")
    if assistants:
        if off_flag or (value and value.lower() in _OFF):
            out.append(f"--assistants {assistants} names an Assistant pool but the Assistant is switched off "
                       "(--no-assistant / --assistant off); give only one")
        elif value and value.lower() not in ("on", "auto", "1", "true", "yes", "enabled", "admin", "admins"):
            out.append(f"--assistant {value} (one Assistant class) and --assistants {assistants} (an Assistant "
                       f"pool) are both given; use --assistants alone (a pool may hold a single class, e.g. "
                       f"--assistants {value}) or --assistant <class> alone. --assistant on|off|auto may be "
                       "combined with --assistants")
    if study and experiment:
        out.append("--experiment is the old name of --study (a study of the default project); give only "
                   "--study project/study")
    if opponents and agents:
        out.append("--agents is the old name of --opponents; give only --opponents")
    if scenario_set and set_alias:
        out.append("--set is the old name of --scenario-set; give only --scenario-set")
    return out
