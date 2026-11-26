"""The documentation builds with ``mkdocs build --strict``: no broken links, no broken anchors
(``validation.links.anchors: warn`` in ``mkdocs.yml`` turns them into warnings, which strict mode
makes fatal), no page missing from the nav. Skipped when the docs extras are not installed."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mkdocs")
pytest.importorskip("material")
pytest.importorskip("mkdocstrings")

ROOT = Path(__file__).resolve().parents[1]


def test_mkdocs_build_strict(tmp_path: Path) -> None:
    config = ROOT / "mkdocs.yml"
    if not config.exists():
        pytest.skip("mkdocs.yml is not available (installed package without the sources)")
    env = {**os.environ, "NO_MKDOCS_2_WARNING": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--strict", "-f", str(config), "-d", str(tmp_path / "site")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    output = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"mkdocs build --strict failed:\n{output}"
    assert (tmp_path / "site" / "guide" / "project-management" / "index.html").exists()
    assert (tmp_path / "site" / "guide" / "study-management" / "index.html").exists()
