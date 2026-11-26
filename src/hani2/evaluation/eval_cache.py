"""The evaluation cache of a study: one small file per game, so boards never re-read recordings.

``<study results>/eval_cache/<recording id>.json`` holds the evaluation row of one recorded game:
every metric that needs no language model, computed from its recording, plus the judge's values once
``hani2 leaderboard judge`` has run (kept apart, under ``judged``, so a refresh never drops or
re-bills them)::

    {"version": 1, "id": "20270314-…", "recording": "anac_7/recordings/20270314-….hrec",
     "size": 18234, "complete": true, "row": {...}, "judged": {...}, "updated": "2027-…"}

* **Live:** when a game's row is written, its entry is computed in a background worker from the
  recording (still open at that moment) and written; when the recording is closed (it is then
  compressed, and a post-game questionnaire may have been added), the entry is computed again.
* **Lazily:** :func:`rows` checks each recording against its entry (its file and size) and computes
  a missing or stale one, so a board is right even when the live step did not run (an older game,
  a server stopped in between).
* ``hani2 leaderboard refresh`` (:func:`refresh`) rebuilds every entry; ``hani2 leaderboard judge``
  (:func:`judge`) adds the judge's criteria to the entries that have none yet.

Setting ``HANI2_EVAL_CACHE=0`` (or ``evaluation.cache.live: false`` in ``env.json``) turns the live
step off; the lazy one always runs.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

CACHE_DIR = "eval_cache"
VERSION = 1
_LOCK = threading.RLock()


def _ref(ref: Any):
    from hani2 import projects

    return projects.parse_ref(ref) if isinstance(ref, str) else ref


def results_dir(ref: Any) -> Path:
    """The results folder of study ``ref`` (``None``: the server's own, outside any study)."""
    from hani2 import projects
    from hani2.config import results_root

    with projects.use_study(_ref(ref)):
        return results_root()


def cache_dir(ref: Any) -> Path:
    return results_dir(ref) / CACHE_DIR


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def recordings(ref: Any) -> dict[str, Path]:
    """Every recording of the study by id (a closed ``.hrec`` wins over an open ``.hrec.jsonl``)."""
    from hani2.recording.format import SUFFIX, is_recording, recording_id

    root = results_dir(ref)
    out: dict[str, Path] = {}
    if not root.is_dir():
        return out
    for f in sorted(root.glob("*/recordings/*")):
        if not f.is_file() or not is_recording(f):
            continue
        rid = recording_id(f)
        if rid not in out or f.name.endswith(SUFFIX):
            out[rid] = f
    return out


def _entry_path(ref: Any, rec_id: str) -> Path:
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in rec_id)
    return cache_dir(ref) / f"{safe}.json"


def read_entry(ref: Any, rec_id: str) -> dict | None:
    p = _entry_path(ref, rec_id)
    try:
        data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("version") == VERSION and isinstance(data.get("row"), dict) else None


def _write_entry(ref: Any, rec_id: str, entry: dict) -> None:
    p = _entry_path(ref, rec_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(entry, indent=1, default=str, allow_nan=False), encoding="utf-8")
    tmp.replace(p)


def _fresh(entry: dict | None, path: Path) -> bool:
    try:
        return entry is not None and entry.get("file") == path.name and entry.get("size") == path.stat().st_size
    except OSError:
        return False


def _clean_row(row: dict) -> dict:
    import math

    out = {}
    for k, v in row.items():
        if isinstance(v, float) and not math.isfinite(v):
            v = None
        out[k] = v
    return out


def evaluate_file(ref: Any, path: Path, *, previous: dict | None = None) -> dict | None:
    """Compute the entry of one recording (``None`` when it is not a finished game). The judge's
    values of ``previous`` are kept."""
    from hani2 import projects
    from hani2.evaluation import evaluate_recording
    from hani2.recording.format import Recording

    size = path.stat().st_size
    rec = Recording.load(path)
    if rec.result is None:
        return None
    with projects.use_study(_ref(ref)):
        ev = evaluate_recording(rec, use_llm=False, key=rec.id)
    root = results_dir(ref)
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = path.name
    return {"version": VERSION, "id": rec.id, "recording": rel, "file": path.name, "size": size,
            "complete": rec.complete, "row": _clean_row(ev["row"]), "errors": ev["errors"],
            "judged": dict((previous or {}).get("judged") or {}), "updated": _now()}


def update(ref: Any, path: Path) -> dict | None:
    """Compute and write the entry of one recording; ``None`` when it is not a finished game."""
    from hani2.recording.format import recording_id

    rid = recording_id(path)
    with _LOCK:
        prev = read_entry(ref, rid)
        if _fresh(prev, path):
            return prev
        entry = evaluate_file(ref, path, previous=prev)
        if entry is not None:
            _write_entry(ref, rid, entry)
        return entry


def rows(ref: Any, *, fill: bool = True) -> tuple[list[dict], dict[str, Any]]:
    """The evaluation rows of every finished game of study ``ref`` (the judge's values merged in),
    and what was done: ``{"games", "computed", "stale", "failed"}``. A missing or stale entry is
    computed and written (``fill``), else its game is left out and counted under ``stale``."""
    out: list[dict] = []
    info = {"games": 0, "computed": 0, "stale": 0, "failed": 0, "judged": 0}
    for rid, path in recordings(ref).items():
        entry = read_entry(ref, rid)
        if not _fresh(entry, path):
            if not fill:
                info["stale"] += 1
                if entry is None:
                    continue
            else:
                try:
                    with _LOCK:
                        entry = evaluate_file(ref, path, previous=entry)
                        if entry is not None:
                            _write_entry(ref, rid, entry)
                            info["computed"] += 1
                except Exception:  # noqa: BLE001 — one broken recording must not break a board
                    traceback.print_exc()
                    info["failed"] += 1
                    continue
        if entry is None:
            continue
        info["games"] += 1
        judged = entry.get("judged") or {}
        if judged:
            info["judged"] += 1
        out.append({**entry["row"], **judged})
    return out, info


def refresh(ref: Any) -> dict[str, int]:
    """Rebuild every entry of a study from its recordings (the judge's values are kept)."""
    n = {"games": 0, "failed": 0, "removed": 0}
    recs = recordings(ref)
    for rid, path in recs.items():
        try:
            with _LOCK:
                prev = read_entry(ref, rid)
                entry = evaluate_file(ref, path, previous=prev)
                if entry is not None:
                    _write_entry(ref, rid, entry)
                    n["games"] += 1
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            n["failed"] += 1
    d = cache_dir(ref)
    if d.is_dir():  # entries whose recording is gone
        for f in d.glob("*.json"):
            if f.stem not in recs:
                f.unlink(missing_ok=True)
                n["removed"] += 1
    return n


def soft_metrics() -> list[str]:
    from hani2.evaluation.base import REGISTRY

    return [m.name for m in REGISTRY.values() if m.needs_llm]


def judge(ref: Any, *, judge: str | None = None, limit: int | None = None, again: bool = False) -> dict[str, int]:
    """Run the language-model judge on the games of a study that have no judge's values yet (``again``:
    on every game), and store its criteria in their entries. ``judge``: exactly this model
    (``provider:model``) instead of the configured judge chain."""
    from hani2 import projects
    from hani2.evaluation import evaluate_recording
    from hani2.evaluation.base import REGISTRY
    from hani2.recording.format import Recording

    names = soft_metrics()
    cols = {c.name for n in names for c in REGISTRY[n].columns}
    n = {"judged": 0, "skipped": 0, "failed": 0}
    for rid, path in recordings(ref).items():
        if limit is not None and n["judged"] >= limit:
            break
        entry = read_entry(ref, rid)
        if not _fresh(entry, path):
            entry = update(ref, path)
        if entry is None or (entry.get("judged") and not again):
            n["skipped"] += 1
            continue
        try:
            rec = Recording.load(path)
            with projects.use_study(_ref(ref)):
                ev = evaluate_recording(rec, names, use_llm=True, key=rec.id, judge=judge)
            got = {k: v for k, v in _clean_row(ev["row"]).items() if k in cols or k == "judge_model"}
            if not any(k in cols and v is not None for k, v in got.items()):
                n["failed"] += 1
                continue
            with _LOCK:
                entry = read_entry(ref, rid) or entry
                entry["judged"] = got
                _write_entry(ref, rid, entry)
            n["judged"] += 1
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            n["failed"] += 1
    return n


# --------------------------------------------------------------------------- #
# The live step                                                                #
# --------------------------------------------------------------------------- #
_QUEUE: "queue.Queue[tuple[Any, Path]]" = queue.Queue()
_WORKER: threading.Thread | None = None


def live() -> bool:
    from hani2.config import get_env

    if os.environ.get("HANI2_EVAL_CACHE", "").strip().lower() in ("0", "false", "no", "off"):
        return False
    return get_env("evaluation.cache.live", True) is not False


def _work() -> None:
    while True:
        ref, path = _QUEUE.get()
        try:
            if path.is_file():
                update(ref, path)
        except Exception:  # noqa: BLE001 — the lazy step computes it later
            pass
        finally:
            _QUEUE.task_done()


def schedule(ref: Any, path: Path | None) -> None:
    """Compute the entry of a recording in the background (a game's row was written, or its recording
    was closed)."""
    global _WORKER
    if path is None or not live():
        return
    with _LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_work, name="hani2-eval-cache", daemon=True)
            _WORKER.start()
    _QUEUE.put((ref, Path(path)))


def wait(timeout: float | None = None) -> None:
    """Wait until the background worker is idle (for tests and ``hani2`` commands)."""
    import time

    end = None if timeout is None else time.time() + timeout
    while _QUEUE.unfinished_tasks:
        if end is not None and time.time() > end:
            return
        time.sleep(0.02)


def entries(ref: Any) -> Iterable[dict]:
    d = cache_dir(ref)
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            yield json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
