"""Linked scenario categories: ``scenario_links.yaml``.

A link serves a scenario category from a folder anywhere on disk without
copying it. Each settings layer may have a ``scenario_links.yaml``::

    links:
      Rental: /data/scenarios/rental        # a category (numbered or named scenarios)
      Kyoto: ../shared/kyoto-trip           # or one scenario folder; relative: to this file

Layers merge in the usual order (settings folder, then the project, then the
study; a later layer replaces a link of the same name). The file may also be a
plain ``{name: path}`` mapping.
"""

from __future__ import annotations

from pathlib import Path

import yaml

__all__ = ["FILE", "layer_files", "read_file", "load_links", "find", "write_link", "remove_link"]

FILE = "scenario_links.yaml"


def layer_files() -> list[Path]:
    """The link files that apply now, least specific first (existing or not)."""
    from hani2.config import settings_dir, settings_layers

    out = [settings_dir() / FILE] + [d / FILE for d in reversed(settings_layers())]
    seen: list[Path] = []
    for p in out:
        if p not in seen:
            seen.append(p)
    return seen


def read_file(path: Path) -> dict[str, str]:
    """The raw ``{name: path}`` links of one file (``{}`` when missing or broken)."""
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
        if isinstance(data, dict) and isinstance(data.get("links"), dict):
            data = data["links"]
        if not isinstance(data, dict):
            raise ValueError("expected a mapping of names to folders")
        return {str(k).strip(): str(v).strip() for k, v in data.items() if str(k).strip() and v}
    except Exception as e:  # noqa: BLE001 - a broken edit must not break the server
        print(f"[hani2] ignoring {path}: {e}")
        return {}


def _resolve(base: Path, target: str) -> Path:
    p = Path(target).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def load_links() -> dict[str, Path]:
    """``{name: folder}`` merged over the layers (the most specific layer wins)."""
    out: dict[str, Path] = {}
    for f in layer_files():
        for name, target in read_file(f).items():
            out[name] = _resolve(f.parent, target)
    return out


def find(name: str) -> Path | None:
    """The linked folder of category ``name`` (``None``: no link, or its folder is gone)."""
    p = load_links().get(name)
    return p if p is not None and p.is_dir() else None


def write_link(layer_dir: Path, name: str, target: Path | str) -> Path:
    f = Path(layer_dir) / FILE
    links = read_file(f)
    links[name] = str(target)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(yaml.safe_dump({"links": links}, sort_keys=False, allow_unicode=True))
    return f


def remove_link(layer_dir: Path, name: str) -> bool:
    f = Path(layer_dir) / FILE
    links = read_file(f)
    if name not in links:
        return False
    del links[name]
    f.write_text(yaml.safe_dump({"links": links}, sort_keys=False, allow_unicode=True))
    return True
