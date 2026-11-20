"""Write the metric reference page (docs/guide/metrics.md) from the metric
definitions in src/hani2/evaluation (descriptions, formulas, details, figures).

Run it again whenever a metric or column changes::

    .venv/bin/python scripts/make_metric_reference.py

Without an argument it writes docs/guide/metrics.md next to this script;
``tests/test_metric_reference.py`` fails when the page is out of date.
"""
import sys
from pathlib import Path

from hani2.evaluation import metric_reference  # noqa: F401  (registers every metric)
from hani2.evaluation.reference import reference_markdown

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "docs" / "guide" / "metrics.md"
out.write_text(reference_markdown(), encoding="utf-8")
print(f"wrote {out}")
