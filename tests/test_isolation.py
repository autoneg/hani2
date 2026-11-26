"""Isolated Assistants (hani2.support_agent.isolation): untrusted Assistant code runs in a worker
process and learns nothing about other participants."""

import json
import os
import socket
import textwrap
import threading
import uuid

import pytest

from hani2 import matches
from hani2.support_agent import isolation
from hani2.testing import make_session

PEEK = '''
import gc, json, os, sys
from hani2.assistant import Assistant


class Peek(Assistant):
    name = "Peek"

    def handle_user_message(self, text):
        probe = json.loads(text)
        found = {"pid": os.getpid()}
        try:
            found["session"] = repr(self.session)
        except Exception as e:
            found["session"] = "denied: " + type(e).__name__
        found["gc_sessions"] = sum(1 for o in gc.get_objects()
                                   if type(o).__name__ in ("NegotiationSession", "TestSession", "Match"))
        try:
            from hani2.hub import hub
            found["hub_sessions"] = len(hub.sessions)
        except Exception as e:
            found["hub_sessions"] = "error " + type(e).__name__
        try:
            from hani2 import matches
            found["lobby"] = matches.LOBBY.n_waiting()
        except Exception as e:
            found["lobby"] = "error " + type(e).__name__
        for key, path in probe.get("files", {}).items():
            try:
                with open(path) as fh:
                    found[key] = fh.read()
            except Exception as e:
                found[key] = "denied: " + type(e).__name__
        for key, path in probe.get("dirs", {}).items():
            try:
                found[key] = sorted(os.listdir(path))
            except Exception as e:
                found[key] = "denied: " + type(e).__name__
        found["env"] = sorted(os.environ)
        port = probe.get("port")
        if port:
            import socket
            try:
                socket.create_connection(("127.0.0.1", port), timeout=3).close()
                found["network"] = "connected"
            except Exception as e:
                found["network"] = "denied: " + type(e).__name__
        found["context"] = self.context()
        found["private"] = self.private_information()
        found["opponent_view"] = self.opponent_view()
        found["actions"] = sorted(self.session_state.get("actions") or {})
        self.post("PEEK " + json.dumps(found, default=str))
'''

WORKER = '''
from hani2.assistant import Assistant, ToolDispatcher, make_function_schema


class Disp(ToolDispatcher):
    def register_extra_tools(self):
        self.register("double", lambda args: {"ok": True, "value": 2 * int(args.get("x", 0))},
                      lambda: make_function_schema("double", "Double x", {"x": {"type": "integer"}}, ["x"]))


class Helper(Assistant):
    name = "Helper"
    dispatcher_class = Disp

    def handle_user_message(self, text):
        names = sorted((s.get("function") or {}).get("name") for s in self.dispatcher.schemas())
        doubled = self.dispatcher.execute("double", {"x": 21})
        board = self.dispatcher.execute("show_on_board", {"content": "from the worker"})
        ctx = self.context()
        self.post(f"names={names} doubled={doubled['value']} board={board.get('ok')} turn={ctx.get('is_my_turn')}")

    def on_event(self, event_name, nmi=None):
        if event_name == "negotiation_started":
            self.post(f"started nmi={nmi}")
'''


def _write(tmp_path, name, code):
    d = tmp_path / "code" / uuid.uuid4().hex[:8]
    d.mkdir(parents=True)
    f = d / f"{name}.py"
    f.write_text(textwrap.dedent(code))
    return f


def _ready(s, timeout=120):
    sa = s.support_agent
    assert isinstance(sa, isolation.IsolatedAssistant), s.assistant_error
    assert sa._ready.wait(timeout), "the worker did not start"
    assert sa.alive, sa._dead
    return sa


def _chat_reply(s, prefix, timeout=60):
    assert s.wait(lambda: any(str(c.get("text", "")).startswith(prefix) for c in s.chat), timeout), \
        [c.get("text") for c in s.chat]
    return next(c["text"] for c in reversed(s.chat) if str(c.get("text", "")).startswith(prefix))


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv(isolation.ENV_VAR, "process")
    matches.LOBBY.clear()
    yield
    matches.LOBBY.clear()
    isolation.stop_all()


def test_an_isolated_assistant_runs_in_its_own_process_through_the_stock_functions(tmp_path):
    f = _write(tmp_path, "helper", WORKER)
    s = make_session(agent_class=f"{f}:Helper")
    sa = _ready(s)
    assert sa.name == "Helper"
    assert s.snapshot()["support"]["isolated"] is True
    s.start()
    assert s.wait_for_turn()
    s.user_chat("hello")
    reply = _chat_reply(s, "names=")
    assert "'double'" in reply and "'show_on_board'" in reply
    assert "doubled=42" in reply and "board=True" in reply
    assert "from the worker" in s.board
    assert s.wait(lambda: any("started nmi=None" in str(c.get("text")) for c in s.chat))  # no nmi crosses
    assert s.wait_agent_idle()
    s.close()
    assert not sa.alive
    assert sa._proc.wait(10) is not None


def test_the_study_setting_turns_isolation_on(tmp_path, monkeypatch, hani2_home):
    from conftest import write_settings

    monkeypatch.delenv(isolation.ENV_VAR)
    f = _write(tmp_path, "helper", WORKER)
    s = make_session(agent_class=f"{f}:Helper")
    assert not isinstance(s.support_agent, isolation.IsolatedAssistant)  # off by default
    s.close()
    write_settings(hani2_home, "env.json", {"negotiation": {"assistant_isolation": "process"}})
    s = make_session(agent_class=f"{f}:Helper")
    assert isinstance(s.support_agent, isolation.IsolatedAssistant)
    s.close()


def test_hani2s_own_assistant_stays_in_the_server():
    s = make_session()
    assert s.support_agent is not None and not isinstance(s.support_agent, isolation.IsolatedAssistant)


def test_it_fails_closed_when_the_worker_cannot_start(tmp_path):
    f = _write(tmp_path, "broken", "raise ImportError('boom')\n")
    s = make_session(agent_class=f"{f}:Nope")
    sa = s.support_agent
    assert isinstance(sa, isolation.IsolatedAssistant)
    assert s.wait(lambda: s.support_agent is None, 120)
    assert "boom" in (s.assistant_error or "")
    assert s.snapshot()["support"] is None


def test_it_fails_closed_without_a_required_sandbox(tmp_path, monkeypatch, hani2_home):
    from conftest import write_settings

    write_settings(hani2_home, "env.json",
                   {"negotiation": {"assistant_sandbox": "required"}})
    monkeypatch.setattr(isolation.shutil, "which", lambda _name: None)
    f = _write(tmp_path, "helper", WORKER)
    s = make_session(agent_class=f"{f}:Helper")
    assert s.wait(lambda: s.support_agent is None, 60)
    assert "sandbox" in (s.assistant_error or "")


def test_tool_classes_an_isolated_assistant_brings_are_not_added(tmp_path):
    code = WORKER + '''

from hani2.tools import Tool


class Spy(Tool):
    name = "Spy"


class WithTools(Helper):
    tools = [Spy]
'''
    f = _write(tmp_path, "withtools", code)
    s = make_session(agent_class=f"{f}:WithTools")
    sa = _ready(s)
    assert sa.refused_tools == ["Spy"]
    assert "Spy" not in sa.toolbox()
    assert sa._call("add_tool", ["Spy"], {})["ok"] is False


class _Listener:
    def __init__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.hits = 0
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while True:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            self.hits += 1
            c.close()


def test_an_assistant_cannot_peek_at_the_other_participant(tmp_path, hani2_home, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-server-secret")
    monkeypatch.setenv("HANI2_SSO_SCMLWEB_SECRET", "x" * 40)
    secret = hani2_home / "settings" / "secret.txt"
    secret.parent.mkdir(parents=True, exist_ok=True)
    secret.write_text("server secret")
    # every submission is unpacked into one shared folder (a<id> packages), as a competition site does
    shared = tmp_path / "submissions"
    for pkg, body in (("a1", PEEK), ("a2", "SECRET = 'a2 strategy'\n")):
        (shared / pkg).mkdir(parents=True)
        (shared / pkg / "__init__.py").write_text("")
        (shared / pkg / "agent.py").write_text(textwrap.dedent(body))
    (shared / "a1" / "stolen.py").symlink_to(shared / "a2" / "agent.py")  # a link to a sibling submission
    monkeypatch.syspath_prepend(str(shared))
    projects_root = tmp_path / "elsewhere" / "projects"  # a projects root outside every other hidden folder
    (projects_root / "p" / "results").mkdir(parents=True)
    (projects_root / "p" / "results" / "keys.txt").write_text("group keys")
    monkeypatch.setenv("HANI2_PROJECTS", str(projects_root))
    code = uuid.uuid4().hex[:6]
    a = make_session(user="alice", opponent="human+assistant", query={"match": code}, agent_class="a1.agent:Peek",
                     n_steps=10)
    b = make_session(user="bob", opponent="human+assistant", query={"match": code}, agent_class="a1.agent:Peek",
                     n_steps=10)
    assert a.match is not None and a.match is b.match
    _ready(a)
    a.start()
    b.start()
    assert a.wait(lambda: a.phase == "running" and b.phase == "running")
    first, second = (a, b) if a.wait_for_turn(5) and a.is_my_turn() else (b, a)
    assert first.send_counter("first offer").get("ok", True)
    assert second.wait_for_turn()
    other_results = first.ss["user_path"]  # the other participant's results folder (absolute)
    (other_results / "notes.txt").write_text("bob's notes")
    listener = _Listener()
    probe = {"files": {"secret": str(secret), "other_notes": str(other_results / "notes.txt"),
                       "server_code": str(isolation.__file__),
                       "other_submission": str(shared / "a2" / "agent.py"),
                       "own_original": str(shared / "a1" / "agent.py"),
                       "projects": str(projects_root / "p" / "results" / "keys.txt"),
                       "linked_copy": "code/a1/stolen.py"},
             "dirs": {"submissions": str(shared), "home_db": str(hani2_home / "db"), "user_home": os.path.expanduser("~")},
             "port": listener.port}
    second.user_chat(json.dumps(probe))
    found = json.loads(_chat_reply(second, "PEEK ")[5:])
    # another process, without the session, the hub, the lobby or the match
    assert found["pid"] != os.getpid()
    assert found["session"].startswith("denied")
    assert found["gc_sessions"] == 0
    assert found["hub_sessions"] in (0,) or str(found["hub_sessions"]).startswith("error")
    assert found["lobby"] in (0,) or str(found["lobby"]).startswith("error")
    # no keys, no HANI2 settings in its environment
    assert "OPENAI_API_KEY" not in found["env"] and not any(k.startswith("HANI2_SSO") for k in found["env"])
    # nothing about the other side in what it is given
    blob = json.dumps(found["context"]) + json.dumps(found["private"]) + json.dumps(found["opponent_view"])
    assert first.user not in blob and "match" not in json.dumps(found["context"]).lower()
    assert found["opponent_view"].get("ok") is False
    assert "first offer" in json.dumps(found["context"])  # its own negotiation it does see
    assert found["linked_copy"].startswith("denied")  # the link was not copied into its folder
    if second.support_agent.sandboxed:
        assert found["secret"].startswith("denied")
        assert found["other_notes"].startswith("denied")
        assert found["server_code"].startswith("denied") or "hani2" in found["server_code"]
        assert str(found["home_db"]).startswith("denied")
        assert found["other_submission"].startswith("denied") and found["own_original"].startswith("denied")
        assert str(found["submissions"]).startswith("denied")
        assert found["projects"].startswith("denied")
        assert str(found["user_home"]).startswith("denied")
        assert found["network"].startswith("denied") and listener.hits == 0
    else:  # pragma: no cover - a server without sandbox-exec / bwrap
        pytest.skip("no file-system sandbox on this machine: only the process boundary was checked")


def test_sandbox_is_available_here():
    """This development machine (macOS or Linux with bwrap) runs the sandboxed checks above."""
    if not isolation.sandbox_available():  # pragma: no cover
        pytest.skip("no sandbox-exec / bwrap")
    assert isolation.sandbox_prefix("required", [], [], "/tmp", False)


def test_the_profile_hides_home_and_keeps_python(tmp_path):
    root = isolation._workroot()
    hidden = isolation._hidden_paths(root)
    assert os.path.realpath(os.path.expanduser("~")) in hidden
    assert all(len(p.split("/")) > 2 for p in hidden)
    readable = isolation._runtime_paths()
    import hani2

    assert any(os.path.dirname(hani2.__file__).startswith(r) or r == os.path.dirname(hani2.__file__) for r in readable)
    prof = isolation.macos_profile(hidden, readable, str(tmp_path), False)
    assert "(deny network*)" in prof
    args = isolation.bwrap_args(hidden, readable, str(tmp_path), False)
    assert "--unshare-net" in args and args.count("--tmpfs") >= 1


def test_a_group_file_assistant_is_never_imported_by_the_server(tmp_path, monkeypatch, hani2_home):
    import sys

    code = tmp_path / "subs"
    (code / "a77").mkdir(parents=True)
    (code / "a77" / "__init__.py").write_text("")
    (code / "a77" / "agent.py").write_text(textwrap.dedent(WORKER))
    groups = hani2_home / "settings" / "groups"
    groups.mkdir(parents=True, exist_ok=True)
    (groups / "test_hi_77.json").write_text(json.dumps({"syspath": [str(code)], "agents": ["BoulwareTBNegotiator"],
                                                       "support_agent": "a77.agent.Helper"}))
    s = make_session(query={"group": "test_hi_77"}, opponent=None, partner=None)
    sa = _ready(s)
    assert sa.name == "Helper"
    assert "a77" not in sys.modules and "a77.agent" not in sys.modules
    s.user_chat("hi")
    assert "doubled=42" in _chat_reply(s, "names=")
    assert "a77" not in sys.modules
    snap = s.snapshot()
    assert "a77" not in sys.modules and snap["support"]["name"] == "Helper"
