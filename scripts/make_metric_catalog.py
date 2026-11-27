"""Write the metric catalogue (docs/guide/metric-catalog.md) and the questionnaires page
(docs/guide/questionnaires.md) from src/hani2/evaluation/catalog.py, the metric registry and the
bundled questionnaires.

Run it again whenever a metric, a group, a validation or a bundled questionnaire changes::

    .venv/bin/python scripts/make_metric_catalog.py

``tests/test_metric_catalog.py`` fails when a page is out of date.
"""
from pathlib import Path

import hani2.evaluation  # noqa: F401  (registers every metric)
from hani2.evaluation.catalog_docs import write

root = Path(__file__).resolve().parents[1]
changed = write(root)
print("updated: " + ", ".join(changed) if changed else "up to date")
