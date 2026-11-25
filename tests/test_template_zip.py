"""The downloadable Assistant template in the docs matches examples/agent_template."""

import importlib.util
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_template_zip_is_up_to_date():
    spec = importlib.util.spec_from_file_location("make_template_zip", ROOT / "scripts" / "make_template_zip.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    with zipfile.ZipFile(mod.OUT) as z:
        got = {n: z.read(n) for n in z.namelist()}
    want = {f"{mod.PREFIX}/{p.relative_to(mod.SRC).as_posix()}": p.read_bytes() for p in mod.template_files()}
    assert got == want, "run: .venv/bin/python scripts/make_template_zip.py"
