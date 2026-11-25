"""Write docs/downloads/hani2-assistant-template.zip from examples/agent_template.

The zip is reproducible (fixed timestamps, sorted names), so it only changes when the template
does. tests/test_template_zip.py fails when the two differ: run this script after changing the
template.

    .venv/bin/python scripts/make_template_zip.py
"""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "examples" / "agent_template"
OUT = ROOT / "docs" / "downloads" / "hani2-assistant-template.zip"
PREFIX = "hani2-assistant-template"


def template_files() -> list[Path]:
    return sorted(p for p in SRC.rglob("*") if p.is_file() and "__pycache__" not in p.parts
                  and not p.name.startswith("."))


def build(out: Path = OUT) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in template_files():
            info = zipfile.ZipInfo(f"{PREFIX}/{p.relative_to(SRC).as_posix()}", date_time=(2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, p.read_bytes())
    return out


if __name__ == "__main__":
    print(build().relative_to(ROOT))
