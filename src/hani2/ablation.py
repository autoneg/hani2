"""Run the *No-Human* ablation headlessly: the Assistant on autopilot drives the human's seat.

The No-Human runs give the Assistant's negotiation ceiling (and, with ``oracle``, its information
ceiling); :func:`hani2.evaluation.ablation_report` compares them, cell by cell, with the team and the
human-alone sessions of a study. Example::

    from hani2.ablation import cells_of, run_no_human

    cells = cells_of(["~/negmas/hani2/results"])           # the cells humans played
    runs = run_no_human(cells=cells, reps=3)                 # the Assistant alone on each of them
    runs += run_no_human(cells=cells, reps=3, oracle=True)   # and knowing the opponent

Every run is an ordinary recorded negotiation of the user ``ablation_autopilot`` (in the current study
unless ``study`` is given), so it is evaluated like any other recording; its ``condition`` is
``no_human`` (``oracle_no_human`` with the oracle). Runs are *uncounted*: they take no participant
index, no Assistant slot and no scheduled opponent or scenario; the Assistant, the opponent, the
scenario and the human's side are the ones asked for. The command line is ``hani2 ablation run``.
"""

from __future__ import annotations

import contextlib
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Iterable

__all__ = ["run_no_human", "cells_of", "study_assistants", "DEFAULT_USER"]

#: the user the No-Human runs are recorded under
DEFAULT_USER = "ablation_autopilot"


@contextlib.contextmanager
def _autopilot_settings(driver: str):
    """Allow autopilot with ``driver`` for this process only (the settings file is not touched)."""
    from hani2.support_agent import autopilot as ap

    original = ap.load_autopilot_settings
    settings = dict(ap.DEFAULT_AUTOPILOT_SETTINGS, allowed=True, driver=driver, allowed_drivers=None, step_delay=0,
                    user_can_choose=False)
    ap.load_autopilot_settings = lambda: dict(settings)  # type: ignore[assignment]
    try:
        yield
    finally:
        ap.load_autopilot_settings = original  # type: ignore[assignment]


def cells_of(paths: Iterable[str | Path], conditions: Iterable[str] = ("team", "human_alone", "oracle_team")) -> list[dict]:
    """The distinct cells (``scenario_type``, ``scenario_name``, ``opponent``, ``human_index``) of the
    recordings under ``paths`` that ran in one of ``conditions`` (practice rounds left out): the cells
    to run the No-Human ablation on so that it matches the study's sessions."""
    from hani2.evaluation.ablation import condition_of
    from hani2.recording.format import Recording, iter_recordings

    seen: dict[tuple, dict] = {}
    wanted = set(conditions)
    for p in paths:
        p = Path(p).expanduser()
        files = [p] if p.is_file() else list(iter_recordings(p))
        for f in files:
            try:
                rec = Recording.load(f)
            except Exception:  # noqa: BLE001
                continue
            st = rec.start or {}
            if not st or st.get("practice"):
                continue
            if condition_of(st, rec.of("act"), rec.of("ev"))["condition"] not in wanted:
                continue
            info = (rec.scenario or {}).get("info") or {}
            cell = dict(scenario_type=info.get("scenario_type"), scenario_name=info.get("scenario_name"),
                        opponent=st.get("opponent"), human_index=st.get("human_index"))
            if cell["scenario_type"] and cell["opponent"]:
                seen.setdefault(tuple(cell.values()), cell)
    return list(seen.values())


def study_assistants(study: Any = None) -> list[str | None]:
    """The Assistants to run: the study's pool without ``none`` (``[None]``, the configured Assistant,
    when the study names none)."""
    from hani2 import groups, projects
    from hani2.assignment import is_no_assistant

    try:
        ref = projects.parse_ref(study) if study is not None else projects.current_study()
    except Exception:  # noqa: BLE001
        ref = None
    try:
        items = projects.setting("assistants", None, ref=ref)
        pool = groups.expand_assistants(items, ref) if items else []
    except Exception:  # noqa: BLE001
        pool = []
    pool = [a for a in pool if not is_no_assistant(a)]
    return list(pool) or [None]


def _session_class(assistant: str | None):
    from hani2.testing import TestSession

    class AblationSession(TestSession):
        __test__ = False
        #: not a participant: no index, no Assistant slot, no scheduled opponent or scenario
        uncounted = True
        fixed_assistant = assistant

        def can_choose_scenario(self) -> bool:
            return True

    return AblationSession


def _end_if_stalled(s: Any, timeout: float) -> str | None:
    """Wait until the negotiation ends; if autopilot let go of the seat (its stall net) or the time ran
    out, end it so it counts as no deal (dropping it would flatter the Assistant). Returns a note."""
    end = time.time() + timeout
    while time.time() < end:
        if s.phase in ("ended", "questionnaire", "finished") and not getattr(s, "_finishing", False):
            return None
        if not s.autopilot_active and s.phase == "running":
            break
        time.sleep(0.05)
    note = "autopilot disengaged" if not s.autopilot_active else f"no end within {timeout:g} s"
    if s.phase == "running":
        from hani2.recording.recorder import acting

        s.autopilot_active = False
        with acting("autopilot"):  # the runner ends it for the autopilot, not for a human
            s.end()
        s.wait_until_done(timeout=30)
    return note


def _cells(cells: Iterable[dict] | None, scenario_types: Iterable[str | None], opponents: Iterable[str]) -> list[dict]:
    if cells is not None:
        return [dict(c) for c in cells]
    return [dict(scenario_type=t, opponent=o) for t in scenario_types for o in opponents]


def run_no_human(*, scenario_types: Iterable[str | None] = ("Trade",), opponents: Iterable[str] = ("BoulwareTBNegotiator",),
                 cells: Iterable[dict] | None = None, reps: int = 1, oracle: bool = False,
                 assistants: Iterable[str | None] | str | None = None,
                 assistant_settings: dict[str, Any] | None = None, n_steps: int | None = 20,
                 time_limit: float | None = None, user: str = DEFAULT_USER, study: Any = None,
                 timeout: float = 900.0, progress: Callable[[dict], None] | None = None) -> list[dict]:
    """Run the Assistant on autopilot ``reps`` times per cell and Assistant.

    The cells are ``cells`` (dicts with ``scenario_type``, ``opponent`` and optionally
    ``scenario_name`` and ``human_index``, e.g. from :func:`cells_of`), else every scenario type ×
    opponent. ``assistants`` (class specs, comma-separated or a list) default to the study's pool
    without ``none``. ``oracle`` grants the ``opponent_utility`` capability. A negotiation the
    autopilot gives up on is ended (no deal) and reported with a ``note``. Returns one dict per run:
    the cell, ``assistant``, ``rep``, ``oracle``, ``ok``, ``result``, ``recording``, ``note``, ``error``."""
    from hani2 import config
    from hani2.support_agent.autopilot import ASSISTANT_DRIVER
    from hani2.support_agent.settings import load_assistant_settings
    from hani2.testing import make_session

    if isinstance(assistants, str):
        assistants = [a.strip() for a in assistants.split(",") if a.strip()]
    pool = list(assistants) if assistants else study_assistants(study)
    caps = dict(load_assistant_settings().get("capabilities") or {})
    caps.update((assistant_settings or {}).get("capabilities") or {})
    caps["opponent_utility"] = bool(oracle)
    settings = dict(assistant_settings or {}, capabilities=caps, autonomy="full")
    out: list[dict] = []
    with _autopilot_settings(ASSISTANT_DRIVER):
        for assistant in pool:
            for cell in _cells(cells, scenario_types, opponents):
                for rep in range(int(reps)):
                    info: dict[str, Any] = dict(cell, assistant=assistant or "", rep=rep, oracle=bool(oracle), ok=False,
                                                result=None, recording=None, note=None, error=None)
                    s = None
                    try:
                        s = make_session(user=user, opponent=cell["opponent"], assistant_settings=settings, load=False,
                                         n_steps=n_steps, time_limit=time_limit, study=study,
                                         session_class=_session_class(assistant),
                                         home=str(config.home()))  # the real home, not a temporary one
                        if cell.get("human_index") is not None:
                            s.admin_prefs["role_rule"] = "index"
                            s.admin_prefs["human_index"] = int(cell["human_index"])
                        s.load(cell.get("scenario_type"), cell.get("scenario_name"))
                        if s.phase != "ready":
                            raise RuntimeError(f"could not load {cell.get('scenario_type')}/{cell.get('scenario_name')}")
                        s.ss["is_practice_round"] = False
                        if s.support_agent is None:
                            raise RuntimeError(s.__dict__.get("assistant_error") or "the Assistant did not start")
                        s.start()
                        s.wait_for_turn()
                        r = s.set_autopilot(True, ASSISTANT_DRIVER)
                        if not r.get("ok"):
                            raise RuntimeError(r.get("error") or "autopilot refused")
                        info["note"] = _end_if_stalled(s, timeout)
                        info["result"] = s.result
                        info["ok"] = True
                    except Exception as e:  # noqa: BLE001
                        traceback.print_exc()
                        info["error"] = f"{type(e).__name__}: {e}"
                    finally:
                        if s is not None:
                            try:
                                if s.recorder is not None:
                                    p = s.recorder.finalize()
                                    info["recording"] = str(p) if p else None
                                s.close()
                            except Exception:  # noqa: BLE001
                                traceback.print_exc()
                    out.append(info)
                    if progress is not None:
                        progress(info)
    return out
