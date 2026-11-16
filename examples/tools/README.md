# Example tools

| File | Shows |
|------|-------|
| `offer_counter.py` | The smallest tool: read the trace, show numbers |
| `what_if.py` | Inputs, a button, and filling the user's offer |
| `concession_tracker.py` | A live Plotly chart updated every turn |

Enable them in `<settings>/env.json` and start the server with this folder on `PYTHONPATH`:

```json
{"tools": {"extra": ["offer_counter:OfferCounter", "what_if:WhatIf", "concession_tracker:ConcessionTracker"]}}
```

```bash
PYTHONPATH=$PWD hani2
```
