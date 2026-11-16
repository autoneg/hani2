# Support-agent template

A minimal, working starting point for your own negotiation support agent.

```bash
pip install hani2
hani2 setup
ollama pull qwen3:4b-instruct            # or configure any litellm provider
cp settings.example.json ~/negmas/hani2/settings/support_agent_settings.json
PYTHONPATH=$PWD hani2 --page play        # click Start, then open the Assistant
pytest                                   # offline smoke test
```

| File | Purpose |
|------|---------|
| `my_agent.py` | The agent. Edit the three `EDIT` markers. |
| `settings.example.json` | Loads your agent with suggest-only autonomy. |
| `test_my_agent.py` | Offline smoke test. |
