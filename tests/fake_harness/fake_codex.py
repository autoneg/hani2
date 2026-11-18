#!/usr/bin/env python3
"""A fake ``codex`` for the tests: records its command line and environment; answers
``--version``, ``debug models --bundled`` and ``exec --json`` (the prompt on stdin)."""

import json
import os
import sys

log = os.environ.get("FAKE_HARNESS_LOG")
args = sys.argv[1:]
if log:
    with open(log, "a") as f:
        cat = next((a.split("=", 1)[1] for a in args if a.startswith("model_catalog_json=")), None)
        files = {"catalog": open(json.loads(cat)).read()} if cat else {}
        f.write(json.dumps({"argv": args, "env": dict(os.environ), "cwd": os.getcwd(), "files": files}) + "\n")
if "--version" in args:
    print("codex-cli 0.162.1")
    sys.exit(0)
if args[:3] == ["debug", "models", "--bundled"]:
    print(json.dumps({"models": [
        {"slug": "gpt-5-mini", "tool_mode": None, "multi_agent_version": None, "apply_patch_tool_type": "freeform",
         "experimental_supported_tools": []},
        {"slug": "gpt-6-astra", "tool_mode": "code_mode_only", "multi_agent_version": "v2",
         "apply_patch_tool_type": "freeform", "experimental_supported_tools": ["clock"]}]}))
    sys.exit(0)
if args[:1] == ["exec"]:
    prompt = sys.stdin.read()
    cfg = dict(a.split("=", 1) for a in args[args.index("exec"):] if "=" in a and not a.startswith("-"))
    instr = open(json.loads(cfg["model_instructions_file"])).read()
    for ev in ({"type": "thread.started", "thread_id": "t1"}, {"type": "turn.started"},
               {"type": "item.completed", "item": {"id": "i1", "type": "agent_message",
                                                   "text": f"codex says: {prompt[:30]} | {instr[:20]}"}},
               {"type": "turn.completed", "usage": {"input_tokens": 9, "output_tokens": 3}}):
        print(json.dumps(ev))
    sys.exit(0)
sys.exit(2)
