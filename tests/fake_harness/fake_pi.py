#!/usr/bin/env python3
"""A fake ``pi --mode rpc`` for the tests: records its command line and environment, then
answers one prompt. With HANI2's functions on offer (``--tools``) it first calls the first one
through the bridge's extension UI request and echoes the host's answer."""

import json
import os
import sys

log = os.environ.get("FAKE_HARNESS_LOG")
if log:
    with open(log, "a") as f:
        agent = os.environ.get("PI_CODING_AGENT_DIR", "")
        files = {n: open(os.path.join(agent, n)).read() for n in ("auth.json", "models.json")
                 if agent and os.path.exists(os.path.join(agent, n))}
        f.write(json.dumps({"argv": sys.argv[1:], "env": dict(os.environ), "cwd": os.getcwd(), "files": files}) + "\n")
if "--version" in sys.argv:
    print("1.4.0")
    sys.exit(0)


def send(o):
    sys.stdout.write(json.dumps(o) + "\n")
    sys.stdout.flush()


tools = json.load(open(os.environ["HANI2_PI_TOOLS_FILE"])) if os.environ.get("HANI2_PI_TOOLS_FILE") else []
system = open(os.environ["HANI2_PI_SYSTEM_FILE"]).read() if os.environ.get("HANI2_PI_SYSTEM_FILE") else ""
for line in sys.stdin:
    cmd = json.loads(line)
    if cmd.get("type") != "prompt":
        continue
    send({"id": cmd["id"], "type": "response", "command": "prompt", "success": True, "data": {"disposition": "started"}})
    send({"type": "agent_start"})
    send({"type": "turn_start"})
    text = f"pi says: {cmd['message'][:40]} | system: {system[:20]}"
    if tools:
        t = tools[0]
        send({"type": "extension_ui_request", "id": "ui-1", "method": "input", "title": "hani2_function_call",
              "placeholder": json.dumps({"name": t["name"], "id": "call-1", "arguments": {"probe": True}})})
        ans = json.loads(sys.stdin.readline())
        text = f"called {t['name']}: {ans.get('value')}"
        send({"type": "turn_start"})
    send({"type": "message_end", "message": {"role": "assistant", "stopReason": "stop",
                                             "content": [{"type": "text", "text": text}],
                                             "usage": {"input": 11, "output": 5, "cost": {"total": 0.001}}}})
    send({"type": "agent_end", "messages": []})
    send({"type": "agent_settled", "aborted": False})
