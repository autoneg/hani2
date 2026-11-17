# Example tools

| File | Shows |
|------|-------|
| `offer_counter.py` | The smallest tool: read the trace, show numbers |
| `what_if.py` | Inputs, a button, and filling the user's offer |
| `concession_tracker.py` | A live Plotly chart updated every turn |
| `negotiation_summary.py` | `LLMTool`: an AI summary of the negotiation |
| `ask_ai.py` | `LLMTool` with its own input: ask the AI a question |

Load them all by pointing the server at this folder:

```bash
hani2 --tools examples/tools --page play
```

or copy the files you want into the tools folder (`hani2 tools path`), where new
sessions pick them up without a restart. `hani2 tools new "My Tool" [--llm]`
starts a new tool there. The tutorial is in the docs: *Tutorials → Build a tool*.
