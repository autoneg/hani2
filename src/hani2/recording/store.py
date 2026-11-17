"""Finding, listing and resolving recordings.

Recordings live under the results root (``<user>/recordings/*.hrec``).
Extra folders can be added with ``HANI2_REPLAY_DIRS`` (``os.pathsep``
separated; ``hani2 replay`` sets it), and uploaded files go to
``<results root>/_uploads/``. A recording is addressed by a *key*:
``<root index>:<path relative to that root>`` — keys never escape their root.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from hani2.recording.format import FORMAT, Recording, is_recording, iter_recordings, read_records, recording_id


def roots() -> list[Path]:
    from hani2.config import results_root

    out = [results_root().resolve()]
    for p in (os.environ.get("HANI2_REPLAY_DIRS") or "").split(os.pathsep):
        if p.strip():
            q = Path(p).expanduser().resolve()
            if q not in out:
                out.append(q)
    return out


def uploads_dir() -> Path:
    from hani2.config import results_root

    d = results_root() / "_uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def key_for(path: Path) -> str | None:
    p = path.resolve()
    for i, r in enumerate(roots()):
        if r.is_file() and p == r:
            return f"{i}:"
        try:
            rel = p.relative_to(r)
        except ValueError:
            continue
        return f"{i}:{rel.as_posix()}"
    return None


def resolve(key: str) -> Path:
    """The file a key names (``ValueError`` if it is not a recording under a root)."""
    idx, _, rel = str(key).partition(":")
    try:
        root = roots()[int(idx)]
    except (ValueError, IndexError):
        raise ValueError(f"unknown recording {key!r}") from None
    p = (root / rel).resolve() if rel else root
    if p != root and root not in p.parents:
        raise ValueError(f"unknown recording {key!r}")
    if not p.is_file() or not is_recording(p):
        raise ValueError(f"unknown recording {key!r}")
    return p


def _quick_info(path: Path) -> dict:
    """A recording's summary: its ``<id>.json`` sidecar, else read from the file."""
    rid = recording_id(path)
    side = path.with_name(f"{rid}.json")
    if side.is_file() and path.name.endswith(".hrec"):
        try:
            return json.loads(side.read_text())
        except Exception:
            pass
    recs = read_records(path)
    if not recs or recs[0].get("k") != "header" or recs[0].get("format") != FORMAT:
        return {}
    rec = Recording.from_records(recs)
    sess = rec.header.get("session") or {}
    st = rec.start or {}
    summ = rec.summary or {}
    return dict(
        id=rec.id, file=path.name, user=sess.get("user"), sid=sess.get("sid"), mode=sess.get("mode"),
        started=rec.header.get("created"), duration=rec.duration, scenario=(rec.scenario or {}).get("name"),
        opponent=st.get("opponent"), mechanism_id=st.get("mechanism_id"), status=summ.get("status"),
        ended_by=summ.get("ended_by"), human_utility=summ.get("human_utility"), agent_utility=summ.get("agent_utility"),
        support_agent=bool((st.get("support_agent") or {}).get("enabled")) if st else None,
        questionnaire=rec.questionnaire is not None, experiment=rec.header.get("experiment"),
    )


def list_recordings(include_empty: bool = False) -> list[dict]:
    out = []
    seen: set[Path] = set()
    for r in roots():
        for f in iter_recordings(r):
            f = f.resolve()
            if f in seen:
                continue
            seen.add(f)
            try:
                info = _quick_info(f)
            except Exception as e:  # pragma: no cover
                info = {"error": str(e)}
            if not info:
                continue
            if not include_empty and not info.get("mechanism_id") and not info.get("status"):
                # a scenario was loaded but no negotiation was started
                continue
            info.update(key=key_for(f), file=f.name, size=f.stat().st_size,
                        complete=f.name.endswith(".hrec"), location=str(f.parent))
            out.append(info)
    out.sort(key=lambda d: str(d.get("started") or ""), reverse=True)
    return out


def load(key: str) -> Recording:
    return Recording.load(resolve(key))


def save_upload(name: str, data: bytes) -> str:
    """Store an uploaded recording; returns its key."""
    base = Path(name).name or "upload.hrec"
    if not is_recording(Path(base)):
        base += ".hrec"
    dest = uploads_dir() / f"{uuid.uuid4().hex[:6]}-{base}"
    dest.write_bytes(data)
    try:
        Recording.load(dest)
    except Exception:
        dest.unlink(missing_ok=True)
        raise ValueError("not a HANI2 recording") from None
    k = key_for(dest)
    assert k is not None
    return k
