First release of HANI2, a web interface for human–agent negotiation studies and the ANAC
Human-Agent Negotiation (HAN) and Hybrid Intelligence (HI) competitions.

```bash
pip install hani2
hani2 setup
hani2
```

Highlights:

- A FastAPI server and a React web app shipped in the wheel: negotiation desk, history thread,
  tools in resizable panes (desktop, tablet and phone layouts), admin console, playground.
- Opponent agents from negmas, Genius and negmas-llm (`--opponents`), and a support agent
  (`--support-agent on|off|<class>`) with sixteen capabilities: chat, highlights, layout control,
  custom panels, filling and sending offers, and finding, using and adding tools.
- Tools as Python classes with a declarative component API; teams can submit tools
  (`--tools file.py:Class`) that the support agent discovers and uses.
- Studies with experiments, questionnaires, results CSVs, an event log, and a Prolific flow.
- WebMCP tools for browser AI agents.

Documentation: https://autoneg.github.io/hani2/
