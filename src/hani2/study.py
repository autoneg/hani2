"""Study logic: which scenario / opponent each round uses, practice rounds,
quotas, questionnaires and completion.

* :class:`Study` — normal sessions: rounds follow ``scenario_order.txt`` (or
  random order), opponents are drawn from the opponent pool, and an optional
  per-negotiation questionnaire follows each round.
* :class:`ProlificStudy` — Prolific participants (``?PROLIFIC_PID=``): one
  practice round, ``PROLIFIC_N_REQUIRED`` counted rounds, an optional
  ``schedule.json``, the zero-action rule, auto-start / auto-load timers and
  a completion link.
* :class:`ParticipantStudy` — the same flow for participants of an online or
  lab study (``?pid=`` / ``?participant=`` / ``?code=``), ending with the
  study's completion link or end page.

Numbers such as the counted rounds and time limits come from the environment
(``PROLIFIC_*``, an outside system's explicit input) when set, else from the
study's ``study.yaml`` and its project's ``project.yaml``, else the defaults.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import random
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hani2 import projects
from hani2 import scenario_store as store
from hani2.agents import expand_agents
from hani2.config import settings_layers

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

SCHED_EXTERNAL = "external"
#: appended to a recorded ``external`` method when no outside input was found
MISSING = ":missing"
PROLIFIC_PREFIX = "prolific_"
#: results folder prefix of online / lab participants (``?pid=``, ``?participant=``, ``?code=``)
PARTICIPANT_PREFIX = "participant_"


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def questionnaire_spec() -> dict | None:
    """The per-negotiation questionnaire, if one is configured.

    Lookup: ``$HANI2_PER_NEG_YAML`` / ``$PROLIFIC_PER_NEG_YAML`` →
    ``<experiment>/questionnaires/per_negotiation.yaml`` →
    ``settings/questionnaires/per_negotiation.yaml``.
    """
    import yaml

    from hani2.config import DEFAULT_SETTINGS_DIR, get_env, settings_dir

    def named(v: str) -> list[Path]:
        # a bare name ("evaluation") is a questionnaire in the settings or bundled with HANI2
        if "/" in v or v.endswith((".yaml", ".yml")):
            return [Path(v).expanduser()]
        return [*(d / "questionnaires" / f"{v}.yaml" for d in settings_layers()),
                settings_dir() / "questionnaires" / f"{v}.yaml", DEFAULT_SETTINGS_DIR / "questionnaires" / f"{v}.yaml"]

    cands: list[Path] = []
    for var in ("HANI2_PER_NEG_YAML", "PROLIFIC_PER_NEG_YAML"):
        if os.environ.get(var):
            cands.extend(named(os.environ[var]))
    if get_env("questionnaire", None):
        cands.extend(named(str(get_env("questionnaire"))))
    for layer in settings_layers():  # the study, then its project
        cands.append(layer / "questionnaires" / "per_negotiation.yaml")
    cands.append(settings_dir() / "questionnaires" / "per_negotiation.yaml")
    for p in cands:
        if p.is_file():
            try:
                spec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                if not spec.get("questions"):
                    continue
            except Exception as e:  # pragma: no cover
                print(f"[hani2] questionnaire {p} failed to parse: {e}")
                continue
            from hani2.templates import render_data

            return render_data(spec)
    return None


#: where a participant's pre-questionnaire answers are kept (in their results folder)
PRE_FILE = "pre_questionnaire.json"


def pre_questionnaire_spec() -> dict | None:
    """The pre-questionnaire (shown once, before a participant's first negotiation), if one is
    configured. It is opt-in: ``"pre_questionnaire": "<name or path>"`` in env.json (``expertise``
    is bundled), ``$HANI2_PRE_YAML``, or ``questionnaires/pre_questionnaire.yaml`` in the study,
    its project or the settings folder. Its ``participant_type`` block names the question whose
    answer is the participant's type (see :func:`participant_type_of`)."""
    import yaml

    from hani2.config import DEFAULT_SETTINGS_DIR, get_env, settings_dir

    def named(v: str) -> list[Path]:
        if "/" in v or v.endswith((".yaml", ".yml")):
            return [Path(v).expanduser()]
        return [*(d / "questionnaires" / f"{v}.yaml" for d in settings_layers()),
                settings_dir() / "questionnaires" / f"{v}.yaml", DEFAULT_SETTINGS_DIR / "questionnaires" / f"{v}.yaml"]

    cands: list[Path] = []
    if os.environ.get("HANI2_PRE_YAML"):
        cands.extend(named(os.environ["HANI2_PRE_YAML"]))
    if get_env("pre_questionnaire", None):
        cands.extend(named(str(get_env("pre_questionnaire"))))
    for layer in settings_layers():
        cands.append(layer / "questionnaires" / "pre_questionnaire.yaml")
    cands.append(settings_dir() / "questionnaires" / "pre_questionnaire.yaml")
    for p in cands:
        if p.is_file():
            try:
                spec = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception as e:  # pragma: no cover
                print(f"[hani2] pre-questionnaire {p} failed to parse: {e}")
                continue
            if spec.get("questions"):
                from hani2.templates import render_data

                return render_data(spec)
    return None


def participant_type_of(spec: dict | None, answers: dict[str, Any]) -> str:
    """The participant type from pre-questionnaire answers: the answer to the question named by
    ``participant_type.question`` (default ``expertise``), mapped through ``participant_type.map``
    (answer → type; unmapped answers are used as they are). ``""`` when unanswered."""
    cfg = (spec or {}).get("participant_type") or {}
    if isinstance(cfg, str):
        cfg = {"question": cfg}
    v = answers.get(str(cfg.get("question") or "expertise"))
    if v in (None, "", []):
        return ""
    mapping = {str(k): str(x) for k, x in (cfg.get("map") or {}).items()}
    return mapping.get(str(v), str(v))


def read_pre_questionnaire(user_path: Path) -> dict | None:
    f = Path(user_path) / PRE_FILE
    try:
        return json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    except Exception:
        return None


def questionnaire_for(session: "NegotiationSession", spec: dict | None) -> dict | None:
    """The questionnaire as shown in this session: questions marked
    ``requires: support_agent`` are dropped when no assistant took part."""
    if not spec:
        return spec
    sa = session.support_agent
    has_agent = sa is not None and bool(getattr(sa, "user_enabled", True))
    qs = [q for q in spec.get("questions", []) if not (q.get("requires") == "support_agent" and not has_agent)]
    return {**spec, "questions": qs} if qs else None


def save_questionnaire(user_path: Path, row_meta: dict[str, Any], answers: dict[str, Any]) -> None:
    path = user_path / "negotiation_questionnaires.csv"
    base = ["mechanism_id", "scenario", "agent_type", "practice", "shown_at", "submitted_at", "duration_seconds"]
    fields = base + sorted(answers) + [k for k in ("project", "study") if k in row_meta]
    existing: list[str] = []
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            existing = next(csv.reader(fh), [])
    if existing and set(fields) - set(existing):
        # new questions: rewrite with the union header
        with path.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        fields = existing + [f for f in fields if f not in existing]
        with path.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        existing = fields
    with path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=existing or fields, extrasaction="ignore")
        if not existing:
            w.writeheader()
        w.writerow({**answers, **row_meta})


class Study:
    """Default (non-Prolific) study."""

    def __init__(self, session: "NegotiationSession"):
        self.session = session
        self._shown_at: str | None = None
        self._last_summary: dict | None = None

    def close(self) -> None:
        """Cancel the study's timers (the session is being closed)."""

    # -- planning -----------------------------------------------------------
    def plan_round(self, scenario_type: str | None, name: str | None) -> dict[str, Any]:
        plan: dict[str, Any] = {"type": scenario_type, "name": name}
        s = self.session
        q = s.query or {}
        url_pool = any(str(q.get(k) or "").strip() for k in ("opponents", "agents", "group"))
        sched = self.scheduling_methods()
        # a pool from the URL (a test link) or an admin-mode session keeps the random choice
        if sched is not None and not (url_pool or s.admin_mode):
            method = sched[0]["opponents"]
            pool = list(s.opponent_pool())
            if len(pool) >= 2:
                if method == SCHED_EXTERNAL:  # nothing outside names it: rotate, and say so
                    self._scheduling_missing("opponents")
                    partner = self._pick_opponent("cyclic", pool, s.round_number)
                    method += MISSING
                else:
                    partner = self._pick_opponent(method, pool, s.round_number)
                plan["partner"] = partner
                plan["opponent_group"] = s.opponent_group
                plan["opponent_scheduling"] = method
        if sched is not None and scenario_type is None and name is None:
            method = sched[1].get("scenarios")
            if method:  # chosen explicitly by the study or project (else: the set order, as always)
                counter = store.next_index(s.ss["user_path"])
                plan["index"] = counter
                if method == SCHED_EXTERNAL:
                    self._scheduling_missing("scenarios")
                    pick, method = "by_participant", method + MISSING
                else:
                    pick = method
                plan["type"] = self._pick_scenario(pick, s.round_number, counter)
                plan["scenario_scheduling"] = method
            else:
                plan["scenario_scheduling"] = "set_order" if s.admin_prefs.get("predefined_order", True) else "random"
        return plan

    # -- scheduling (see hani2.scheduling) -------------------------------------
    def scheduling_methods(self) -> tuple[dict[str, str], dict[str, str]] | None:
        """``(effective, explicit)`` scheduling methods of this human's study; ``None``
        when HANI2 does not schedule this session (outside a study, admins, playground guests)."""
        from hani2 import assignment, scheduling

        s = self.session
        if s.study_ref is None or not assignment.counts_as_human(s):
            return None
        eff, explicit, _ = scheduling.resolve(s.study_ref)
        return eff, explicit

    def _seed(self) -> str:
        return f"{self.session.study_ref}|{self.session.user}"

    def _pick_opponent(self, method: str, pool: list, slot: int) -> Any:
        from hani2 import scheduling

        idx = self.participant_index() or 0
        return scheduling.pick_opponent(method, pool, idx, slot, self._seed())

    def _pick_scenario(self, method: str, slot: int, counter: int) -> str | None:
        from hani2 import scheduling

        idx = self.participant_index() or 0
        types = store.scenario_order(self.session.admin_prefs.get("scenario_set"))
        return scheduling.pick_scenario_type(method, types, idx, slot, self._seed(), counter=counter)

    def _scheduling_missing(self, dimension: str) -> None:
        """``external`` scheduling found no outside input for this negotiation: log it loudly."""
        from hani2 import events as ev

        s = self.session
        msg = (f"the study's {dimension} scheduling is 'external' but no schedule.json names one for "
               f"{s.user}'s next negotiation; HANI2 filled in")
        print(f"[hani2] ERROR: {msg}")
        try:
            ev.log_event(s.sid, ev.EventType.ERROR, user=s.user, component="scheduling",
                         action="scheduling_missing", value={"dimension": dimension, "error": msg})
        except Exception:  # pragma: no cover
            pass

    def participant_index(self) -> int | None:
        """This human's index within the study (``None`` outside a study, for admins and guests)."""
        from hani2 import assignment

        if self.session.study_ref is None:
            return None
        return assignment.participant_index(self.session)

    def latin_square_partner(self, slot: int, pool: list | None = None) -> Any:
        """The opponent for ``slot`` from the balanced Latin square over the opponent pool,
        for humans of a study run by HANI2 itself (``None`` otherwise)."""
        from hani2 import assignment

        s = self.session
        if s.study_ref is None or not assignment.counts_as_human(s):
            return None
        pool = list(pool if pool is not None else s.opponent_pool())
        if len(pool) < 2:
            return None
        idx = self.participant_index()
        return None if idx is None else assignment.latin_pick(pool, idx, slot)

    def schedule_assistant(self) -> Any:
        """The Assistant a schedule.json names for the next negotiation (``None``: none)."""
        return None

    def after_load(self) -> None:
        pass

    def finished(self) -> bool:
        return False

    def completion_url(self) -> str | None:
        return None

    def finish_text(self) -> str | None:
        """The end page's text (``end_text`` in study.yaml, with placeholders filled)."""
        st = projects.get_study(self.session.study_ref)
        if st is None or not st.end_text:
            return None
        from hani2.templates import render, study_variables

        return render(st.end_text, study_variables(self.session.study_ref))

    def round_label(self) -> str:
        n = self.session.round_number + (0 if self.session.phase in ("running", "ended") else 1)
        return f"Negotiation {max(1, n)}"

    def client_state(self) -> dict[str, Any]:
        return {"kind": "default"}

    # -- after a round --------------------------------------------------------
    def wants_questionnaire(self, summary: dict) -> bool:
        return self.session.mode not in ("guest", "simulated") and summary.get("n_human_actions", 0) > 0 and not summary.get("agent_failed")

    def after_round(self, summary: dict) -> None:
        self._last_summary = summary
        spec = questionnaire_for(self.session, questionnaire_spec()) if self.wants_questionnaire(summary) else None
        if spec:
            self.session.questionnaire = spec
            self.session.phase = "questionnaire"
            self._shown_at = datetime.now().isoformat()

    # -- before the first round ---------------------------------------------
    def wants_pre_questionnaire(self) -> bool:
        from hani2 import assignment

        s = self.session
        return s.mode not in ("guest", "simulated") and assignment.counts_as_human(s)

    def maybe_pre_questionnaire(self) -> bool:
        """Open the pre-questionnaire if this participant has not answered it yet (after a scenario
        loaded, before the negotiation starts). Also sets ``participant_type`` from earlier answers.
        Returns whether it opened."""
        s = self.session
        done = read_pre_questionnaire(s.ss["user_path"])
        if done is not None:
            s.ss["participant_type"] = str(done.get("participant_type") or "")
            return False
        if not self.wants_pre_questionnaire() or s.phase != "ready":
            return False
        spec = pre_questionnaire_spec()
        if not spec:
            return False
        s.questionnaire = {**spec, "stage": "pre"}
        s.phase = "questionnaire"
        self._shown_at = datetime.now().isoformat()
        s.push_state()
        return True

    def _submit_pre(self, answers: dict[str, Any]) -> dict:
        s = self.session
        spec = s.questionnaire or {}
        ptype = participant_type_of(spec, answers)
        data = dict(answers=answers, participant_type=ptype, shown_at=getattr(self, "_shown_at", None) or "",
                    submitted_at=datetime.now().isoformat(), version=str(spec.get("version") or ""),
                    **projects.stamp(s.study_ref))
        path = Path(s.ss["user_path"]) / PRE_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=1, default=str), encoding="utf-8")
        s.ss["participant_type"] = ptype
        if getattr(s, "recorder", None) is not None:
            s.recorder.mark("pre_questionnaire", answers=answers, participant_type=ptype)
        s.questionnaire = None
        s.phase = "ready"
        s.push_state()
        self.after_load()
        return {"ok": True}

    def submit_questionnaire(self, answers: dict[str, Any]) -> dict:
        s = self.session
        if s.phase != "questionnaire" or not s.questionnaire:
            return {"ok": False, "error": "No questionnaire is open."}
        spec = s.questionnaire
        allowed = {q.get("id") for q in spec.get("questions", [])}
        answers = {k: v for k, v in (answers or {}).items() if k in allowed}  # never the row's own metadata
        missing = [q.get("text", q.get("id")) for q in spec.get("questions", [])
                   if q.get("required") and answers.get(q.get("id")) in (None, "", [])]
        if missing:
            return {"ok": False, "error": "Please answer every required question.", "missing": missing}
        if spec.get("stage") == "pre":
            return self._submit_pre(answers)
        m = s.mechanism
        shown = self._shown_at
        dur = None
        if shown:
            try:
                dur = (datetime.now() - datetime.fromisoformat(shown)).total_seconds()
            except ValueError:
                pass
        save_questionnaire(
            s.ss["user_path"],
            dict(mechanism_id=getattr(m, "id", ""), scenario=s._scenario_name(),
                 agent_type=s.ss.get("last_partner_type", ""), practice=bool(s.ss.get("is_practice_round")),
                 shown_at=shown or "", submitted_at=datetime.now().isoformat(),
                 duration_seconds=f"{dur:.3f}" if dur is not None else "",
                 **projects.stamp(s.study_ref)),
            answers,
        )
        if getattr(s, "recorder", None) is not None:
            s.recorder.questionnaire(spec, answers, shown)
        s.questionnaire = None
        s.phase = "ended"
        self.after_questionnaire()
        s.push_state()
        return {"ok": True}

    def after_questionnaire(self) -> None:
        pass


class ProlificStudy(Study):
    META = "prolific_session.json"
    SCHEDULE = "schedule.json"
    PREFIX = PROLIFIC_PREFIX
    KIND = "prolific"

    def __init__(self, session: "NegotiationSession"):
        super().__init__(session)
        self.pid = session.user[len(self.PREFIX):]
        self.user_path: Path = session.ss["user_path"]
        ref = session.study_ref
        self.n_required = projects.setting("n_required", 5, env="PROLIFIC_N_REQUIRED", cast=int, ref=ref)
        self.practice_time = projects.setting("practice_time_limit", 300, env="PROLIFIC_PRACTICE_TIME_LIMIT", cast=int, ref=ref)
        self.counted_time = projects.setting("counted_time_limit", 600, env="PROLIFIC_COUNTED_TIME_LIMIT", cast=int, ref=ref)
        self.has_practice = projects.setting("practice", True, cast=bool, ref=ref)
        self.auto_start = _env_int("PROLIFIC_AUTO_START_SECONDS", 120)
        self.auto_load = _env_int("PROLIFIC_AUTO_LOAD_SECONDS", 30)
        self.auto_load_practice = _env_int("PROLIFIC_AUTO_LOAD_PRACTICE_SECONDS", 60)
        self.auto_load_warn = _env_int("PROLIFIC_AUTO_LOAD_WARN_SECONDS", 15)
        q = session.query
        self.no_auto = any(k in q for k in ("noautostart", "noAutoStart", "no_auto_start"))
        self.meta = self._meta()
        self._timer: threading.Timer | None = None
        self._warn_timer: threading.Timer | None = None
        self.auto_deadline: float | None = None
        self.auto_kind: str | None = None
        # The participant's Assistant starts switched off (still user-toggleable).
        session.ss.setdefault("support_agent_default_enabled", False)

    # -- persistent files ----------------------------------------------------
    def _meta(self) -> dict:
        path = self.user_path / self.META
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                pass
        types = store.scenario_order(self.session.admin_prefs.get("scenario_set"))
        h = int(hashlib.sha1(self.pid.encode()).hexdigest(), 16)
        # in a study: the scenario type cycles over the set by participant index (balanced)
        idx = self.participant_index()
        meta = {
            "started_at": datetime.now().isoformat(),
            "scenario_type": types[(h if idx is None else idx) % len(types)] if types else None,
            "max_minutes": projects.setting("minutes", 45, env="PROLIFIC_MAX_MINUTES", cast=int,
                                            ref=self.session.study_ref),
            "max_negs": self.n_required + 1,
        }
        if idx is not None:
            meta["participant_index"] = idx
        self.user_path.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(meta), encoding="utf-8")
        return meta

    def _rows(self) -> list[dict]:
        f = self.user_path / "results.csv"
        if not f.exists():
            return []
        try:
            with f.open(newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
        except Exception:
            return []

    def _since(self) -> datetime | None:
        try:
            return datetime.fromisoformat(self.meta.get("started_at", ""))
        except ValueError:
            return None

    def _this_session(self) -> list[dict]:
        since = self._since()
        out = []
        for r in self._rows():
            try:
                ended = datetime.fromisoformat(str(r.get("ended_at", ""))[:26])
            except ValueError:
                ended = None
            if since is None or ended is None or ended >= since:
                out.append(r)
        return out

    @staticmethod
    def _truthy(v: Any) -> bool:
        return str(v).strip().lower() in ("1", "true", "yes", "t")

    def is_returning(self) -> bool:
        return len(self._rows()) > len(self._this_session())

    def practice_done(self) -> bool:
        return any(self._truthy(r.get("practice")) and int(float(r.get("n_human_actions") or 0)) > 0
                   for r in self._this_session())

    def counted(self) -> int:
        n = 0
        for r in self._this_session():
            if self._truthy(r.get("practice")):
                continue
            if r.get("status") == "agent_failed":
                n += 1
                continue
            try:
                if int(float(r.get("n_human_actions") or 0)) <= 0:
                    continue
            except ValueError:
                pass
            n += 1
        return n

    def schedule_data(self) -> Any:
        """The participant's ``schedule.json`` as written (``None`` when missing or broken)."""
        path = self.user_path / self.SCHEDULE
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def schedule(self) -> list[dict]:
        data = self.schedule_data()
        if isinstance(data, dict):
            data = data.get("negotiations", [])
        return data if isinstance(data, list) else []

    def schedule_assistant(self, slot: int | None = None, practice: bool | None = None) -> Any:
        """The Assistant schedule.json names: the slot's ``assistant``, else the top-level one."""
        data = self.schedule_data()
        if data is None:
            return None
        if practice is None:
            practice = self.is_practice_next()
        if not practice:
            sched = self.schedule()
            i = self.counted() if slot is None else slot
            entry = sched[i] if 0 <= i < len(sched) and isinstance(sched[i], dict) else {}
            if entry.get("assistant"):
                return entry["assistant"]
        return data.get("assistant") if isinstance(data, dict) and data.get("assistant") else None

    def finalists(self) -> list[str]:
        raw = os.environ.get("PROLIFIC_FINALISTS", "")
        pool = expand_agents(raw) if raw.strip() else []
        if pool:
            from hani2.session import _group_name

            self._finalists_group = _group_name(raw)
            return pool
        pool = list(self.session.opponent_pool())
        self._finalists_group = self.session.opponent_group
        return pool

    _finalists_group = ""

    def _rotation_offset(self) -> int:
        from hani2.assignment import _locked

        try:
            per_user = self.user_path / "fallback_rotation.txt"
            if per_user.exists():
                return int(per_user.read_text(encoding="utf-8").strip() or 0)
            counter = self.user_path.parent / "_prolific_fallback_counter.txt"
            # one participant at a time, also across processes sharing the results folder
            with _locked(counter):
                if per_user.exists():
                    return int(per_user.read_text(encoding="utf-8").strip() or 0)
                n = int(counter.read_text(encoding="utf-8").strip() or 0) if counter.exists() else 0
                tmp = counter.with_name(f".{counter.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                tmp.write_text(str(n + 1), encoding="utf-8")
                tmp.replace(counter)
                tmp = per_user.with_name(f".{per_user.name}.{os.getpid()}.{threading.get_ident()}.tmp")
                tmp.write_text(str(n), encoding="utf-8")
                tmp.replace(per_user)
            return n
        except Exception:
            return 0

    def is_practice_next(self) -> bool:
        return self.has_practice and not self.is_returning() and not self.practice_done()

    # -- Study API ----------------------------------------------------------
    def _scenario_type(self, entry: dict, slot: int, counter: int, practice: bool = False) -> tuple[str, str]:
        """The scenario type of the next negotiation and the scheduling method that chose it."""
        types = store.scenario_order(self.session.admin_prefs.get("scenario_set"))
        own = self.meta.get("scenario_type") or random.choice(types)
        if entry.get("scenario_type"):  # the outside system's schedule.json wins
            return entry["scenario_type"], SCHED_EXTERNAL
        sched = self.scheduling_methods()
        if sched is None:
            return own, ""
        method = sched[0]["scenarios"]
        if method == "by_participant":
            return own, method
        if method == SCHED_EXTERNAL and practice:  # schedules name counted negotiations only
            return own, "practice"
        if method == SCHED_EXTERNAL:
            self._scheduling_missing("scenarios")
            return own, method + MISSING
        return self._pick_scenario(method, slot, counter) or own, method

    def plan_round(self, scenario_type: str | None, name: str | None) -> dict[str, Any]:
        practice = self.is_practice_next()
        slot = self.counted()
        sched = self.schedule()
        entry = sched[slot] if 0 <= slot < len(sched) and not practice else {}
        idx = entry.get("scenario_index") if isinstance(entry.get("scenario_index"), int) else None
        if idx is None:
            idx = store.next_index(self.user_path)
        stype, scen_method = self._scenario_type(entry, slot, idx, practice)
        partner = None
        group: str | None = None
        opp_method = ""
        if practice:
            practice_pool = expand_agents(os.environ.get("PROLIFIC_PRACTICE_OPPONENTS") or os.environ.get("PROLIFIC_PRACTICE_AGENTS", ":pan")) or self.session.opponent_pool()
            partner = random.choice(practice_pool)
            group = ""
            opp_method = "practice"
        else:
            want = entry.get("agent_class_name")
            pool = self.finalists()
            group = self._finalists_group
            if want:
                partner = next((p for p in pool if str(p) == want or str(p).endswith("." + str(want).split(".")[-1])), None)
                if partner is None:  # not a pool member: used as written, from no group
                    partner, group = want, ""
                opp_method = SCHED_EXTERNAL
            elif pool:
                # a study run by HANI2 itself: the study's opponents scheduling method (default: a
                # balanced Latin square by participant index); outside a study, when schedule.json
                # leaves the slot open, or for participants who started with it: the old rotation
                methods = self.scheduling_methods()
                method = methods[0]["opponents"] if methods is not None else ""
                legacy = (self.user_path / "fallback_rotation.txt").exists()
                if method == SCHED_EXTERNAL:
                    self._scheduling_missing("opponents")
                    partner = self._pick_opponent("cyclic", pool, slot)
                    opp_method = method + MISSING
                elif not method or sched or legacy:
                    partner = pool[(self._rotation_offset() + slot) % len(pool)]
                    opp_method = "cyclic" if method else ""
                elif len(pool) == 1:
                    partner, opp_method = pool[0], method
                else:
                    partner, opp_method = self._pick_opponent(method, pool, slot), method
        plan = {
            "type": stype,
            "index": idx,
            "partner": partner,
            "opponent_group": group,
            "practice": practice,
            "time_limit": entry.get("time_limit") or (self.practice_time if practice else self.counted_time),
            "load_existing": True,
            "opponent_scheduling": opp_method,
            "scenario_scheduling": scen_method,
        }
        assistant = self.schedule_assistant(slot, practice)
        if assistant:
            plan["assistant"] = assistant
        return plan

    def finished(self) -> bool:
        return self.counted() >= self.n_required

    def round_label(self) -> str:
        if self.session.ss.get("is_practice_round"):
            return "Practice negotiation"
        n = min(self.n_required, self.counted() + (0 if self.session.phase == "ended" else 1))
        return f"Negotiation {n} of {self.n_required}"

    def client_state(self) -> dict[str, Any]:
        return {
            "kind": self.KIND,
            "pid": self.pid,
            "required": self.n_required,
            "counted": self.counted(),
            "practice_next": self.is_practice_next(),
            "returning": self.is_returning(),
            "max_minutes": self.meta.get("max_minutes"),
            "auto_deadline": self.auto_deadline,
            "auto_kind": self.auto_kind,
        }

    def completion_url(self) -> str:
        """First match: ``PROLIFIC_COMPLETION_URL`` (``{pid}`` is the participant), the
        outside system's completion path (``SCMLWEB_BASE_URL`` / ``SCMLWEB_PROLIFIC_PATH``),
        ``completion_url`` in study.yaml, Prolific's completion link for
        ``completion_code`` in study.yaml, else the outside system's default path."""
        tmpl = os.environ.get("PROLIFIC_COMPLETION_URL", "").strip()
        if tmpl:
            return tmpl.replace("{pid}", self.pid)
        outside = any((os.environ.get(v) or "").strip() for v in ("SCMLWEB_BASE_URL", "SCMLWEB_PROLIFIC_PATH"))
        if not outside:
            own = self._study_completion_url()
            if own:
                return own
            st = projects.get_study(self.session.study_ref)
            if st is not None and st.completion_code:
                return f"https://app.prolific.com/submissions/complete?cc={st.completion_code}"
        base = os.environ.get("SCMLWEB_BASE_URL", "https://anac.cs.brown.edu").rstrip("/")
        path = "/" + os.environ.get("SCMLWEB_PROLIFIC_PATH", "/prolific").strip("/")
        return f"{base}{path}/done?PROLIFIC_PID={self.pid}"

    def _study_completion_url(self) -> str | None:
        st = projects.get_study(self.session.study_ref)
        if st is None or not st.completion_url:
            return None
        from hani2.templates import render, study_variables

        return render(st.completion_url, study_variables(self.session.study_ref)).replace("{pid}", self.pid)

    # -- timers ---------------------------------------------------------------
    def close(self) -> None:
        self._cancel()

    def _cancel(self) -> None:
        for t in (self._timer, self._warn_timer):
            if t is not None:
                t.cancel()
        self._timer = self._warn_timer = None
        self.auto_deadline = None
        self.auto_kind = None

    def _arm(self, seconds: int, kind: str) -> None:
        self._cancel()
        if self.no_auto or seconds <= 0 or self.session.closed:
            return
        self.auto_deadline = time.time() + seconds
        self.auto_kind = kind
        warn_at = max(0, seconds - self.auto_load_warn)

        def _warn():
            if not self.session.closed and self.auto_kind == kind and self.session.phase in ("ready", "ended"):
                self.session.toast(
                    f"The next negotiation starts automatically in {self.auto_load_warn} seconds.", "warning")

        if kind == "load" and warn_at > 0:
            self._warn_timer = threading.Timer(warn_at, self.session.in_study(_warn))
            self._warn_timer.daemon = True
            self._warn_timer.start()

        def _fire():
            s = self.session
            if s.closed or self.auto_kind != kind:
                return
            self.auto_deadline = None
            if kind == "start" and s.phase == "ready":
                s.start()
            elif kind == "load" and s.phase == "ended":
                s.load()
                if s.phase == "ready":
                    s.start()

        self._timer = threading.Timer(seconds, self.session.in_study(_fire))
        self._timer.daemon = True
        self._timer.start()

    def after_load(self) -> None:
        self._arm(self.auto_start, "start")

    # -- end of round ---------------------------------------------------------
    def after_round(self, summary: dict) -> None:
        self._cancel()
        s = self.session
        practice = bool(s.ss.get("is_practice_round"))
        counted = self.counted()
        uncounted = not practice and summary.get("n_human_actions", 0) == 0 and not summary.get("agent_failed")
        status, ended_by = summary.get("status"), summary.get("ended_by")
        if summary.get("agent_failed"):
            phrase = "could not start (the AI agent failed)"
        elif status == "timedout":
            phrase = "timed out"
        elif status == "broken" and ended_by == "human":
            phrase = "was ended by you"
        elif status == "broken":
            phrase = "was ended by the AI agent"
        elif status == "success":
            phrase = "reached an agreement"
        else:
            phrase = "ended"
        if practice:
            msg, level = (f"Practice complete (it {phrase}). The next {self.n_required} negotiation(s) count "
                          "toward your reward and bonus."), "success"
        elif counted >= self.n_required:
            msg, level = (f"All {self.n_required} counted negotiations are done. Complete the questionnaire to "
                          "finish."), "success"
        elif uncounted:
            msg, level = (f"This negotiation {phrase} without any action on your side, so it does NOT count. "
                          f"{counted} of {self.n_required} counted so far. Make at least one offer (or accept your "
                          "opponent's offer) in the next one so it counts."), "error"
        else:
            msg, level = f"{counted} of {self.n_required} counted negotiations complete — {self.n_required - counted} to go.", "info"
        s.notice = {"text": msg, "level": level}
        s.toast(msg, level, duration=0 if level != "info" else 10000)
        if not uncounted and not summary.get("agent_failed") and questionnaire_for(s, questionnaire_spec()):
            s.questionnaire = questionnaire_for(s, questionnaire_spec())
            s.phase = "questionnaire"
            self._shown_at = datetime.now().isoformat()
            return
        self.after_questionnaire()

    def after_questionnaire(self) -> None:
        s = self.session
        if self.finished():
            s.phase = "finished"
            s.finish_url = self.completion_url()
            s.finish_text = self.finish_text()
            return
        self._arm(self.auto_load_practice if self.is_practice_next() else self.auto_load, "load")


class ParticipantStudy(ProlificStudy):
    """An online or lab study's participant (``?pid=``, ``?participant=`` or ``?code=``):
    the Prolific flow (practice, counted rounds, questionnaires, schedule.json), ending
    with ``completion_url`` from study.yaml (online) or the end page."""

    PREFIX = PARTICIPANT_PREFIX
    KIND = "participant"

    def completion_url(self) -> str | None:  # type: ignore[override]
        return self._study_completion_url()

    def finish_text(self) -> str | None:
        text = super().finish_text()
        if text:
            return text
        from hani2.templates import study_variables

        code = study_variables(self.session.study_ref).get("completion_code")
        return "Thank you for taking part." + (f" Your completion code is {code}." if code else "")


def make_study(session: "NegotiationSession") -> Study:
    if session.user.startswith(PROLIFIC_PREFIX):
        return ProlificStudy(session)
    if session.user.startswith(PARTICIPANT_PREFIX):
        return ParticipantStudy(session)
    return Study(session)
