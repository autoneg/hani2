"""Scenario statistics: every negmas scenario statistic, computed in the background and cached.

What is computed is negmas's :class:`~negmas.preferences.ops.ScenarioStats` (``Scenario.calc_stats``):
the opposition, each role's utility range, the fraction of outcomes rational for everybody, the
Pareto frontier and the bargaining solutions (Nash, Kalai, modified Kalai, Kalai-Smorodinsky,
modified KS, maximum welfare and maximum relative welfare), each as utilities and outcomes.

**Never in the way.** The work runs in a child process (``python -m hani2.scenario_stats``) with a
hard time limit, one scenario at a time per server, so a large scenario can never stall a session
or the server: a computation that takes longer than ``scenario_stats.timeout`` seconds is killed and
recorded as ``timeout``; one that raises is recorded as ``failed``; an outcome space larger than
``scenario_stats.max_outcomes`` (or a continuous one) as ``too_large``. All of them are ignored by
everything that shows stats (the page says why). A recorded failure is not retried until the
scenario's files change (or an administrator asks again).

**Cache.** For a scenario folder the statistics go into negmas's own stats file, ``_stats.yaml``
(:data:`negmas.inout.STATS_FILE_NAME`, read back by ``Scenario.load``), next to the scenario's
``_info.yaml``. The Pareto frontier is written into it only when the scenario has at most
``scenario_stats.pareto_max_outcomes`` outcomes (negmas has no default for this, so it is
:data:`DEFAULT_PARETO_MAX_OUTCOMES`, a million); larger scenarios cache every other statistic. What
HANI2 needs on top (a fingerprint of the scenario files, when and how fast it was computed, why it
failed) goes into ``_stats_meta.json`` beside it: negmas's stats file accepts no other keys. A cache
whose fingerprint does not match the scenario files any more is stale and ignored. HANI2 loads
scenarios without it (``Scenario.stats`` stays empty): it is for pages, the tool and negmas tooling.

Scenarios that are not a folder on disk (generated ones, or a saved one changed for a session, e.g.
with a forced value on disagreement) are cached in memory by a fingerprint of their content.
Bundled sample scenarios (inside the package) are never written to.

Settings (``env.json`` → ``scenario_stats``): ``enabled`` (default true), ``pareto_max_outcomes``,
``max_outcomes`` (default negmas's ``STATS_MAX_CARDINALITY``), ``timeout`` (seconds, default 300).
"""

from __future__ import annotations

import atexit
import datetime as _dt
import hashlib
import json
import math
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: negmas's stats file (``negmas.inout.STATS_FILE_NAME``; spelled out so this module imports fast)
STATS_FILE = "_stats.yaml"
#: what HANI2 records about the cached stats (negmas's stats file takes no other keys)
META_FILE = "_stats_meta.json"
LOCK_FILE = "_stats.lock"
#: negmas has no default for when to keep a Pareto frontier, so: a million outcomes
DEFAULT_PARETO_MAX_OUTCOMES = 1_000_000
DEFAULT_TIMEOUT = 300.0
#: rows of the Pareto frontier sent to a browser (the cache keeps all of them)
VIEW_MAX_PARETO = 500
#: statuses of a finished computation; ``pending`` (under way) and ``disabled`` are never stored
DONE = ("ok", "failed", "timeout", "too_large")

#: the solution concepts of negmas's ScenarioStats, in display order: (key, label)
SOLUTIONS: tuple[tuple[str, str], ...] = (
    ("nash", "Nash bargaining solution"),
    ("kalai", "Kalai-Smorodinsky (Kalai) point"),
    ("modified_kalai", "Modified Kalai point"),
    ("ks", "KS point"),
    ("modified_ks", "Modified KS point"),
    ("max_welfare", "Maximum welfare"),
    ("max_relative_welfare", "Maximum relative welfare"),
)


# --------------------------------------------------------------------------- #
# Settings                                                                     #
# --------------------------------------------------------------------------- #
def _negmas_max_outcomes() -> int:
    try:
        from negmas.inout import STATS_MAX_CARDINALITY

        return int(STATS_MAX_CARDINALITY)
    except Exception:  # pragma: no cover - older negmas
        return 10_000_000_000


def settings() -> dict[str, Any]:
    """``env.json`` → ``scenario_stats`` with the defaults filled in."""
    from hani2.config import get_env

    cfg = get_env("scenario_stats", {}) or {}
    cfg = cfg if isinstance(cfg, dict) else {}

    def num(key: str, default: float, cast=float) -> Any:
        try:
            v = cast(cfg.get(key, default))
            return v if v > 0 else default
        except (TypeError, ValueError):
            return default

    return {
        "enabled": bool(cfg.get("enabled", True)),
        "pareto_max_outcomes": num("pareto_max_outcomes", DEFAULT_PARETO_MAX_OUTCOMES, int),
        "max_outcomes": num("max_outcomes", _negmas_max_outcomes(), int),
        "timeout": num("timeout", DEFAULT_TIMEOUT, float),
    }


def enabled() -> bool:
    try:
        return settings()["enabled"]
    except Exception:  # noqa: BLE001 - never break a caller over a setting
        return False


# --------------------------------------------------------------------------- #
# Fingerprints                                                                 #
# --------------------------------------------------------------------------- #
def _scenario_files(folder: Path) -> list[Path]:
    """The files that define a scenario: the domain and the roles (``*.yml``/``*.yaml``/``*.xml``
    not starting with ``_``), not its info, pictures, display code or caches."""
    return sorted(f for f in folder.iterdir()
                  if f.is_file() and f.suffix.lower() in (".yml", ".yaml", ".xml") and not f.name.startswith(("_", ".")))


def files_fingerprint(folder: Path | str) -> str:
    """A hash of the files that define the scenario in ``folder`` (changes when it is edited)."""
    h = hashlib.sha256()
    for f in _scenario_files(Path(folder)):
        h.update(f.name.encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:32]


def content_fingerprint(scenario: Any) -> str:
    """A hash of what a scenario is (its outcome space and utility functions, not its info): equal
    for the same scenario loaded twice, different for one changed in memory."""
    ser = scenario.serialize()
    dom = ser.get("domain")
    if isinstance(dom, dict):
        dom = {k: v for k, v in dom.items() if k != "path"}
    ufuns = sorted((json.dumps(u, sort_keys=True, default=str) for u in ser.get("ufuns") or []))
    blob = json.dumps({"domain": dom, "ufuns": ufuns}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


# --------------------------------------------------------------------------- #
# The disk cache                                                               #
# --------------------------------------------------------------------------- #
def _read_json(path: Path) -> dict | None:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def writable(folder: Path | str | None) -> bool:
    """Whether stats may be cached in ``folder``: a scenario folder outside the package (bundled
    samples stay untouched) that this process can write to."""
    if folder is None:
        return False
    folder = Path(folder)
    try:
        pkg = Path(__file__).resolve().parent
        if folder.resolve().is_relative_to(pkg):
            return False
    except Exception:  # noqa: BLE001
        return False
    return folder.is_dir() and os.access(folder, os.W_OK)


def read_cached(folder: Path | str, with_stats: bool = True) -> dict | None:
    """The cached result for ``folder`` (``None``: none, or stale). An ``ok`` result carries
    negmas's statistics under ``stats`` (unless ``with_stats`` is false: a quick check)."""
    folder = Path(folder)
    meta = _read_json(folder / META_FILE)
    if not meta or meta.get("status") not in DONE:
        return None
    try:
        if meta.get("files") != files_fingerprint(folder):
            return None
    except OSError:
        return None
    out = dict(meta)
    if meta["status"] == "ok" and with_stats:
        try:
            from negmas.helpers.inout import load

            out["stats"] = _plain(load(folder / STATS_FILE))
        except Exception:  # noqa: BLE001 - the stats file went missing or is broken: compute again
            return None
    out["cache"] = "disk"
    return out


def clear(folder: Path | str) -> None:
    """Forget the cached stats of ``folder`` (its scenario was changed)."""
    folder = Path(folder)
    for n in (STATS_FILE, META_FILE):
        try:
            (folder / n).unlink()
        except FileNotFoundError:
            pass
        except OSError:  # pragma: no cover - read-only folder
            pass
    _MEMORY_DROP(str(folder))


# --------------------------------------------------------------------------- #
# The memory cache (scenarios that are not a folder, and folders we may not write)   #
# --------------------------------------------------------------------------- #
_MEMORY: OrderedDict[str, dict] = OrderedDict()
_MEMORY_MAX = 128
_LOCK = threading.Lock()


def _memory_get(key: str) -> dict | None:
    with _LOCK:
        hit = _MEMORY.get(key)
        if hit is not None:
            _MEMORY.move_to_end(key)
        return hit


def _memory_put(key: str, result: dict) -> None:
    with _LOCK:
        _MEMORY[key] = result
        _MEMORY.move_to_end(key)
        while len(_MEMORY) > _MEMORY_MAX:
            _MEMORY.popitem(last=False)


def _MEMORY_DROP(prefix: str) -> None:
    with _LOCK:
        for k in [k for k in _MEMORY if k.startswith(f"dir:{prefix}|")]:
            _MEMORY.pop(k, None)


# --------------------------------------------------------------------------- #
# Lookup and requests                                                          #
# --------------------------------------------------------------------------- #
def _key(folder: Path | None, content: str | None) -> str:
    if folder is not None:
        try:
            return f"dir:{folder}|{files_fingerprint(folder)}"
        except OSError:
            pass
    return f"mem:{content}"


def _source(scenario: Any = None, folder: Path | str | None = None) -> tuple[Path | None, str | None]:
    """``(folder, content fingerprint)`` of what to compute: the folder when the scenario is (still)
    the one on disk there, else ``None`` and the scenario's own fingerprint."""
    folder = Path(folder) if folder else None
    if folder is not None and not folder.is_dir():
        folder = None
    if scenario is None:
        return folder, None
    content = content_fingerprint(scenario)
    if folder is not None:
        meta = _read_json(folder / META_FILE)
        if meta and meta.get("content") and meta.get("content") != content:
            folder = None  # changed in memory (e.g. a forced value on disagreement): not the saved one
    return folder, content


def lookup(scenario: Any = None, folder: Path | str | None = None) -> dict | None:
    """The finished result for a scenario (given as its ``folder``, the ``scenario`` itself, or
    both), or ``None`` when there is none yet."""
    folder, content = _source(scenario, folder)
    if folder is not None:
        hit = read_cached(folder)
        if hit is not None and (content is None or not hit.get("content") or hit["content"] == content):
            return hit
    if folder is None and content is None:
        return None
    return _memory_get(_key(folder, content))


_QUEUE: "queue.Queue[tuple]" = queue.Queue()
_WORKER: threading.Thread | None = None
_INFLIGHT: dict[str, list[Callable[[dict], None]]] = {}
_CHILDREN: set[subprocess.Popen] = set()


def _submit(*job: Any) -> None:
    """Queue a computation for the worker: a daemon thread (one scenario at a time; the work is
    CPU-bound and runs in a child process), so a long queue never holds up the server's exit."""
    global _WORKER
    with _LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_work_loop, name="hani2-scenario-stats", daemon=True)
            _WORKER.start()
    _QUEUE.put(job)


def _work_loop() -> None:
    while True:
        job = _QUEUE.get()
        try:
            _run(*job)
        except Exception:  # noqa: BLE001 - keep serving the queue
            traceback.print_exc()


@atexit.register
def _kill_children() -> None:
    for p in list(_CHILDREN):
        try:
            p.kill()
        except Exception:  # noqa: BLE001
            pass


def request(scenario: Any = None, folder: Path | str | None = None, *, force: bool = False,
            on_done: Callable[[dict], None] | None = None, with_stats: bool = True) -> dict:
    """The stats of a scenario if they are known, else ``{"status": "pending"}`` after starting their
    computation in the background (at most once per scenario at a time). ``on_done(result)`` is
    called (from a worker thread) when a computation it waited for finishes. ``force`` computes
    again even when a result (or a failure) is cached. ``with_stats=False`` only makes sure they
    are (being) computed: a result read from disk then comes without the statistics. Never raises."""
    try:
        if not enabled():
            return {"status": "disabled", "message": "Scenario statistics are switched off (scenario_stats.enabled)."}
        folder_p, content = _source(scenario, folder)
        if folder_p is None and scenario is None:
            return {"status": "failed", "message": "No scenario."}
        key = _key(folder_p, content)
        with _LOCK:
            waiting = _INFLIGHT.get(key)
            if waiting is not None:  # under way (perhaps forced): not the older cached result
                if on_done is not None:
                    waiting.append(on_done)
                return {"status": "pending"}
        if not force:
            if not with_stats and scenario is None and folder_p is not None:
                hit = read_cached(folder_p, with_stats=False)
            else:
                hit = lookup(scenario, folder_p)
            if hit is not None:
                return hit
        with _LOCK:
            waiting = _INFLIGHT.get(key)
            if waiting is not None:
                if on_done is not None:
                    waiting.append(on_done)
                return {"status": "pending"}
            _INFLIGHT[key] = [on_done] if on_done is not None else []
        # a scenario not on disk is copied now: it may change after this call returns
        snapshot = None if folder_p is not None else _snapshot(scenario)
        _submit(key, folder_p, snapshot, content)
        return {"status": "pending"}
    except Exception as e:  # noqa: BLE001 - stats are a nicety: never break a session or a page
        traceback.print_exc()
        return {"status": "failed", "message": f"{type(e).__name__}: {e}"}


def _snapshot(scenario: Any) -> Path:
    from hani2 import scenario_store as store

    d = Path(tempfile.mkdtemp(prefix="hani2-stats-"))
    store.save_scenario(scenario, d)
    return d


def _run(key: str, folder: Path | None, snapshot: Path | None, content: str | None) -> None:
    result: dict
    try:
        src = folder if folder is not None else snapshot
        assert src is not None
        result = compute(src, cache=folder is not None and writable(folder))
        if content and not result.get("content"):
            result["content"] = content
    except Exception as e:  # noqa: BLE001
        traceback.print_exc()
        result = {"status": "failed", "message": f"{type(e).__name__}: {e}"}
    finally:
        if snapshot is not None:
            import shutil

            shutil.rmtree(snapshot, ignore_errors=True)
    if result.get("status") in DONE and result.get("cache") != "disk":
        result["cache"] = "memory"
        _memory_put(key, result)
    with _LOCK:
        waiting = _INFLIGHT.pop(key, [])
    for cb in waiting:
        try:
            cb(result)
        except Exception:  # noqa: BLE001
            traceback.print_exc()


# --------------------------------------------------------------------------- #
# The computation                                                              #
# --------------------------------------------------------------------------- #
def _lock(folder: Path, timeout: float) -> bool:
    """A lock file shared by every server process on this machine (the HAN and HI services share
    scenario folders). A lock older than the time limit is left over from a crash and is taken."""
    path = folder / LOCK_FILE
    for _ in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {time.time()}".encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > timeout + 60:
                    path.unlink()
                    continue
            except OSError:
                continue
            return False
        except OSError:
            return True  # cannot lock (read-only?): compute without
    return False


def compute(folder: Path | str, *, cache: bool = True, cfg: dict | None = None) -> dict:
    """Compute the stats of the scenario in ``folder`` now (in a child process, under the time
    limit) and, with ``cache``, write them next to it. Returns the result (see the module doc)."""
    folder = Path(folder)
    cfg = cfg or settings()
    started = time.perf_counter()
    files = files_fingerprint(folder)
    locked = cache and _lock(folder, cfg["timeout"])
    if cache and not locked:
        # another server process is computing them: wait for its result
        end = time.time() + cfg["timeout"] + 10
        while (folder / LOCK_FILE).exists() and time.time() < end:
            time.sleep(0.5)
        hit = read_cached(folder)
        return hit if hit is not None else {"status": "pending",
                                            "message": "Another server process is computing these statistics."}
    out_path = folder / f"_stats.{os.getpid()}.{threading.get_ident()}.tmp.yaml"
    try:
        cmd = [sys.executable, "-m", "hani2.scenario_stats", str(folder),
               "--pareto-max", str(cfg["pareto_max_outcomes"]), "--max-outcomes", str(cfg["max_outcomes"])]
        if cache:
            cmd += ["--out", str(out_path)]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    env={**os.environ, "PYTHONWARNINGS": "ignore"})
            _CHILDREN.add(proc)
            try:
                stdout, stderr = proc.communicate(timeout=cfg["timeout"])
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                raise
            finally:
                _CHILDREN.discard(proc)
            try:
                result = json.loads(stdout.strip().splitlines()[-1]) if stdout.strip() else None
            except (json.JSONDecodeError, IndexError):
                result = None
            if not isinstance(result, dict):
                err = (stderr or "").strip().splitlines()
                result = {"status": "failed",
                          "message": err[-1] if err else f"the computation ended with code {proc.returncode}"}
        except subprocess.TimeoutExpired:
            result = {"status": "timeout",
                      "message": f"Took longer than {cfg['timeout']:g} s and was stopped; ignored."}
        result.update({"files": files,
                       "computed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                       "seconds": round(time.perf_counter() - started, 3), "timeout": cfg["timeout"],
                       "pareto_max_outcomes": cfg["pareto_max_outcomes"]})
        if cache:
            try:
                if result["status"] == "ok" and out_path.exists():
                    os.replace(out_path, folder / STATS_FILE)
                elif (folder / STATS_FILE).exists():
                    (folder / STATS_FILE).unlink()  # stats of an older version of the scenario
                meta = {k: v for k, v in result.items() if k != "stats"}
                _write_atomic(folder / META_FILE, json.dumps(meta, indent=2, default=str))
                result["cache"] = "disk"
            except OSError as e:  # pragma: no cover - the folder became read-only
                print(f"[hani2] cannot cache scenario stats in {folder}: {e}")
        return result
    finally:
        if out_path.exists():
            try:
                out_path.unlink()
            except OSError:  # pragma: no cover
                pass
        if locked:
            try:
                (folder / LOCK_FILE).unlink()
            except OSError:
                pass


def _plain(x: Any) -> Any:
    """JSON-friendly: tuples to lists, numpy numbers to Python numbers."""
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if hasattr(x, "item") and callable(x.item):
        try:
            return x.item()
        except Exception:  # noqa: BLE001
            return str(x)
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)


def _child(folder: Path, pareto_max: int, max_outcomes: int, out: Path | None) -> dict:
    """In the child process: load, compute, optionally write negmas's stats file, describe."""
    from negmas import Scenario

    s = Scenario.load(folder, load_stats=False)
    if s is None:
        return {"status": "failed", "message": f"{folder} is not a scenario negmas can load"}
    roles = [str(getattr(u, "name", "") or f"role {i + 1}") for i, u in enumerate(s.ufuns)]
    issues = [str(i.name) for i in s.outcome_space.issues]
    base = {"roles": roles, "issues": issues, "n_issues": len(issues), "n_negotiators": len(roles),
            "content": content_fingerprint(s),
            "reserved_values": [_plain(getattr(u, "reserved_value", None)) for u in s.ufuns]}
    card = s.outcome_space.cardinality
    finite = isinstance(card, int) or (isinstance(card, float) and math.isfinite(card))
    n = int(card) if finite else None
    base["n_outcomes"] = n
    if n is None or n > max_outcomes:
        what = "a continuous outcome space" if n is None else f"{n:,} outcomes (the limit is {max_outcomes:,})"
        return {**base, "status": "too_large", "message": f"Not computed: {what}."}
    if len(roles) < 2:
        return {**base, "status": "failed", "message": f"needs two or more roles, found {len(roles)}"}
    st = s.calc_stats()
    keep_pareto = n <= pareto_max
    if out is not None:
        from negmas.helpers.inout import dump

        dump(st.to_dict(include_pareto_frontier=keep_pareto), out)
    d = _plain(st.to_dict(include_pareto_frontier=True))
    return {**base, "status": "ok", "stats": d, "pareto_cached": keep_pareto,
            "pareto_size": len(d.get("pareto_utils") or [])}


def view(result: dict | None, human_role: str | None = None) -> dict:
    """A result as pages and tools show it: ``status`` and ``message``, the scenario's size, the
    one-number statistics, each role's utility range, the bargaining solutions (each a list of
    points: the utility of every role and the outcome by issue) and the Pareto frontier (at most
    :data:`VIEW_MAX_PARETO` points)."""
    r = dict(result or {"status": "pending"})
    out: dict[str, Any] = {k: r.get(k) for k in ("status", "message", "n_outcomes", "n_issues", "n_negotiators",
                                                  "computed_at", "seconds", "cache", "pareto_cached",
                                                  "pareto_size", "pareto_max_outcomes", "timeout")}
    roles = list(r.get("roles") or [])
    issues = list(r.get("issues") or [])
    out["roles"] = [{"name": n, "human": human_role is not None and n == human_role,
                     "reserved_value": _finite((r.get("reserved_values") or [None] * len(roles))[i]
                                               if i < len(r.get("reserved_values") or []) else None)}
                    for i, n in enumerate(roles)]
    st = r.get("stats") if r.get("status") == "ok" else None
    if not isinstance(st, dict):
        return out

    def point(utils: Any, outcome: Any) -> dict:
        u = list(utils or [])
        o = list(outcome) if isinstance(outcome, (list, tuple)) else None
        return {"utilities": {roles[j] if j < len(roles) else str(j): _finite(v) for j, v in enumerate(u)},
                "welfare": _finite(sum(v for v in u if isinstance(v, (int, float)))) if u else None,
                "outcome": {issues[j] if j < len(issues) else str(j): v for j, v in enumerate(o)} if o is not None else None}

    out["opposition"] = _finite(st.get("opposition"))
    out["rational_fraction"] = _finite(st.get("rational_fraction"))
    out["convex_hull"] = bool(st.get("convex_hull", False))
    out["utility_ranges"] = [{"role": roles[j] if j < len(roles) else str(j), "min": _finite(lo), "max": _finite(hi)}
                             for j, (lo, hi) in enumerate(st.get("utility_ranges") or [])]
    sols = []
    for key, label in SOLUTIONS:
        us, os_ = list(st.get(f"{key}_utils") or []), list(st.get(f"{key}_outcomes") or [])
        sols.append({"key": key, "label": label,
                     "points": [point(u, os_[k] if k < len(os_) else None) for k, u in enumerate(us)]})
    out["solutions"] = sols
    pu, po = list(st.get("pareto_utils") or []), list(st.get("pareto_outcomes") or [])
    out["pareto"] = [point(u, po[k] if k < len(po) else None) for k, u in enumerate(pu[:VIEW_MAX_PARETO])]
    out["pareto_truncated"] = len(pu) > VIEW_MAX_PARETO
    return out


def _finite(x: Any) -> Any:
    """Numbers as JSON can carry them (no NaN or infinity)."""
    if isinstance(x, bool) or x is None:
        return x
    if isinstance(x, (int, float)):
        return x if math.isfinite(x) else None
    return x


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="Compute a scenario's negmas statistics (used by HANI2 in a child process).")
    p.add_argument("folder")
    p.add_argument("--pareto-max", type=int, default=DEFAULT_PARETO_MAX_OUTCOMES)
    p.add_argument("--max-outcomes", type=int, default=_negmas_max_outcomes())
    p.add_argument("--out", default=None, help="Write negmas's stats file here.")
    a = p.parse_args(argv)
    try:
        res = _child(Path(a.folder), a.pareto_max, a.max_outcomes, Path(a.out) if a.out else None)
    except Exception as e:  # noqa: BLE001
        res = {"status": "failed", "message": f"{type(e).__name__}: {e}"}
    sys.stdout.write("\n" + json.dumps(res, default=str) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover - run by compute()
    raise SystemExit(main())
