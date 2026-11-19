"""The picture of a scenario, shown at the top of the *Scenario Info* tool.

A scenario folder (or its category folder) may carry one picture, with an optional
second one for the dark theme:

- ``picture.svg`` (or ``.png``, ``.jpg``, ``.jpeg``, ``.webp``, ``.gif``) — used in both
  themes, unless one of the next two files is there;
- ``picture_light.*`` — the light-theme picture;
- ``picture_dark.*`` — the dark-theme picture.

``_info.yaml`` may name the files instead (paths relative to the scenario folder, or
``http(s)``/``data:`` URLs)::

    picture: harbour.png
    picture: {light: harbour-day.svg, dark: harbour-night.svg}
    picture: false          # no picture, not even the category's

The first folder that has a picture wins: the scenario folder, its category folder,
then the bundled sample of the same scenario type (so generated scenarios of a bundled
type get the bundled picture).
"""

from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path
from typing import Any

EXTENSIONS = (".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif")
MIME = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".gif": "image/gif"}
#: Larger files are not sent (pictures travel inside the page state and recordings).
MAX_BYTES = 3_000_000


def _file(folder: Path, stem: str) -> Path | None:
    for ext in EXTENSIONS:
        f = folder / f"{stem}{ext}"
        if f.is_file():
            return f
    return None


def _ref(folder: Path, value: Any) -> str | Path | None:
    """A URL as it is, or a file inside ``folder`` (paths may not leave it)."""
    if not isinstance(value, str) or not value.strip():
        return None
    v = value.strip()
    if v.startswith(("http://", "https://", "data:image/")):
        return v
    f = (folder / v).resolve()
    try:
        f.relative_to(folder.resolve())
    except ValueError:
        return None
    return f if f.is_file() and f.suffix.lower() in MIME else None


def _in_folder(folder: Path, info: dict | None = None) -> dict[str, str | Path] | None:
    """The pictures of one folder: ``{"light": …, "dark": …}`` (either may be
    missing), ``{}`` when the folder turns pictures off, ``None`` when it has none."""
    spec = (info or {}).get("picture") if info else None
    if spec is False or (isinstance(spec, str) and spec.strip().lower() in ("none", "off", "false")):
        return {}
    out: dict[str, str | Path] = {}
    if isinstance(spec, dict):
        for k in ("light", "dark"):
            r = _ref(folder, spec.get(k))
            if r is not None:
                out[k] = r
    elif spec is not None:
        r = _ref(folder, spec)
        if r is not None:
            out["light"] = r
    if not out and folder.is_dir():
        light = _file(folder, "picture_light") or _file(folder, "picture")
        dark = _file(folder, "picture_dark")
        if light is not None:
            out["light"] = light
        if dark is not None:
            out["dark"] = dark
    if out and "light" not in out:  # only a dark picture: use it in both themes
        out["light"] = out["dark"]
    return out or None


def _read_info(folder: Path) -> dict:
    from hani2.scenario_store import _read_info

    return _read_info(folder) if folder.is_dir() else {}


def _bundled(name: Any) -> Path | None:
    from hani2.config import DEFAULT_SCENARIOS

    if not isinstance(name, str) or not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    d = DEFAULT_SCENARIOS / name
    return d if d.is_dir() else None


def candidate_folders(scenario_dir: str | Path | None, scenario_type: str | None,
                      info: dict | None = None) -> list[Path]:
    """Folders searched for a picture, in order: the scenario folder, its category
    folder, then the bundled scenario of the same type, folder name or story (so the
    installed copies in ``Examples`` and generated scenarios find the bundled pictures)."""
    from hani2.config import DEFAULT_SCENARIOS
    from hani2.scenario_store import category_dir

    out: list[Path] = []
    if scenario_dir:
        d = Path(scenario_dir)
        out.append(d)
        cat = category_dir(scenario_type) if scenario_type else None
        if cat is not None and d.parent.resolve() == cat.resolve():
            out.append(cat)
    if scenario_type and "/" not in scenario_type and not scenario_type.startswith("."):
        cat = category_dir(scenario_type)
        if cat is not None:
            out.append(cat)
        out.append(DEFAULT_SCENARIOS / scenario_type)
    for name in ((Path(scenario_dir).name if scenario_dir else None), (info or {}).get("story")):
        b = _bundled(name)
        if b is not None:
            out.append(b)
    seen: list[Path] = []
    for p in out:
        if p not in seen:
            seen.append(p)
    return seen


def find(scenario_dir: str | Path | None, scenario_type: str | None,
         info: dict | None = None) -> dict[str, str | Path]:
    """``{"light": …, "dark": …}`` for a scenario (``{}``: no picture).

    ``info`` is the scenario's own info (``_info.yaml``) when it has no folder."""
    folders = candidate_folders(scenario_dir, scenario_type, info)
    if not scenario_dir and info and "picture" in info:
        spec = info.get("picture")
        if spec is False:
            return {}
        if isinstance(spec, (str, dict)):
            urls = {k: v for k, v in ({"light": spec} if isinstance(spec, str) else spec).items()
                    if k in ("light", "dark") and isinstance(v, str) and v.startswith(("http://", "https://", "data:image/"))}
            if urls:
                urls.setdefault("light", urls.get("dark", ""))
                return urls  # type: ignore[return-value]
    for i, folder in enumerate(folders):
        own = info if (i == 0 and scenario_dir and info is not None) else _read_info(folder)
        found = _in_folder(folder, own)
        if found is not None:
            return found
    return {}


@lru_cache(maxsize=128)
def _data_uri(path: str, mtime: float, size: int) -> str | None:
    if size > MAX_BYTES:
        print(f"[hani2] scenario picture {path} is larger than {MAX_BYTES // 1_000_000} MB; not shown")
        return None
    p = Path(path)
    mime = MIME.get(p.suffix.lower())
    if mime is None:
        return None
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def source(ref: str | Path | None) -> str | None:
    """A URL the browser can show: a file becomes a ``data:`` URL."""
    if ref is None:
        return None
    if isinstance(ref, str):
        return ref
    try:
        st = ref.stat()
    except OSError:
        return None
    return _data_uri(str(ref), st.st_mtime, st.st_size)


def sources(scenario_dir: str | Path | None, scenario_type: str | None,
            info: dict | None = None) -> tuple[str | None, str | None]:
    """``(light, dark)`` browser URLs of a scenario's picture (``dark`` is
    ``None`` when the light one serves both themes)."""
    found = find(scenario_dir, scenario_type, info)
    light = source(found.get("light"))
    dark = source(found.get("dark")) if found.get("dark") not in (None, found.get("light")) else None
    if light is None and dark is not None:
        light, dark = dark, None
    return light, dark
