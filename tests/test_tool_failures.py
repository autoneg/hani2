# pyright: reportOptionalSubscript=false
"""A failing tool never breaks HANI2: its failure shows in its own pane only (hani2.tools.failure)."""

import asyncio
import json
import textwrap
import time

import pytest
from conftest import write_settings

from hani2.testing import make_session
from hani2.tools import builtin as b
from hani2.tools import registry
from hani2.tools.failure import FailedTool


def _run(coro):
    """``asyncio.run`` in a thread of its own: a Playwright session of the e2e tests (run earlier in
    the same process) keeps an event loop running in the main thread, where ``asyncio.run`` refuses."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(1) as ex:
        return ex.submit(asyncio.run, coro).result()

BROKEN_TOOLS = textwrap.dedent('''
    import os
    import sys
    import time
    from hani2.tools import Tool, ui

    class _Base(Tool):
        pane = "side"
        timing = "always"
        fail_in = ""
        def _maybe(self, where):
            if self.fail_in == where and not getattr(self, "healed", False):
                raise RuntimeError(f"boom in {where}")
        def init(self, ss):
            self._maybe("init")
        def scenario_loaded(self, ss, scenario):
            self._maybe("scenario_loaded")
            self.n_loaded = getattr(self, "n_loaded", 0) + 1
            self.refresh()
        def negotiation_started(self, ss, nmi):
            self.n_started = getattr(self, "n_started", 0) + 1
            self.refresh()
        def action_executed(self, ss, nmi, action):
            self._maybe("action_executed")
            self.refresh()
        def on_input(self, name, value):
            self._maybe("on_input")
            super().on_input(name, value)
        def on_action(self, action, payload):
            self._maybe("on_action")
        def view(self):
            self._maybe("render")
            if self.fail_in == "slow" and not getattr(self, "healed", False):
                time.sleep(1.5)
            return [ui.markdown(f"{self.name} works"), ui.button("Go", "go")]

    class GoodTool(_Base):
        pass

    class BadCtor(_Base):
        def __init__(self, *a, **kw):
            raise RuntimeError("boom in __init__")

    class BadInit(_Base):
        fail_in = "init"

    class BadLoad(_Base):
        fail_in = "scenario_loaded"

    class BadRender(_Base):
        fail_in = "render"

    class BadInput(_Base):
        fail_in = "on_input"

    class BadAction(_Base):
        fail_in = "on_action"

    class BadHook(_Base):
        fail_in = "action_executed"

    class SlowRender(_Base):
        fail_in = "slow"

    # misbehave only when a test arms them (HANI_TEST_ARM=Name,Name), so other sessions stay quick
    def _armed(name):
        return name in os.environ.get("HANI_TEST_ARM", "").split(",")

    class HangAction(_Base):
        def on_action(self, action, payload):
            if _armed("HangAction"):
                time.sleep(1.0)

    class HangInit(_Base):
        def init(self, ss):
            if _armed(type(self).__name__):
                time.sleep(1.0)

    class HangInit2(HangInit):
        pass

    class HangInit3(HangInit):
        pass

    class HangInit4(HangInit):
        pass

    class HangHelp(_Base):
        @classmethod
        def help_text(cls):
            if _armed("HangHelp"):
                time.sleep(3.0)
            return "help"

    class HangPrivate(_Base):
        def private_now(self):
            if _armed("HangPrivate"):
                time.sleep(3.0)
            return False

    class RaiseAvail(_Base):
        def available(self):
            if _armed("RaiseAvail"):
                raise RuntimeError("boom in available")
            return True

    class HangAvail(_Base):
        def available(self):
            if _armed(type(self).__name__):
                time.sleep(1.0)
            return True

    class HangAvail2(HangAvail):
        pass

    class HangAvail3(HangAvail):
        pass

    class ExitAvail(_Base):
        def available(self):
            if _armed("ExitAvail"):
                sys.exit(7)
            return True

    class HangHook(_Base):
        def action_executed(self, ss, nmi, action):
            if _armed("HangHook"):
                time.sleep(1.0)
            self.refresh()

    class ExitView(_Base):
        def view(self):
            if _armed("ExitView"):
                raise SystemExit(3)
            return super().view()

    class ExitAction(_Base):
        def on_action(self, action, payload):
            if _armed("ExitAction"):
                sys.exit(2)

    class AlwaysSlow(_Base):
        calls = 0
        def view(self):
            type(self).calls += 1
            if _armed("AlwaysSlow"):
                time.sleep(0.5)
            return super().view()

    class ExitCtor(_Base):
        def __init__(self, *a, **kw):
            if _armed("ExitCtor"):
                sys.exit(4)
            super().__init__(*a, **kw)

    class FenceView(_Base):
        def view(self):
            if _armed("FenceView"):
                raise RuntimeError("a ``` fence ```` inside")
            return super().view()
''')

SECRETS = ("boom", "RuntimeError", "Traceback")


@pytest.fixture
def broken_tools(hani2_home):
    folder = hani2_home / "tools"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "broken_tools.py").write_text(BROKEN_TOOLS, encoding="utf-8")
    return folder


def _tool(s, name):
    return next(t for t in s.tools if t.name == name)


def _view(s, name):
    return s.render_tool(s.tool_state(_tool(s, name))["id"])["view"]


def _text(view) -> str:
    return json.dumps(view)


def _shows_tool(view) -> bool:
    return any(c["type"] == "markdown" and c["text"].endswith(" works") for c in view)


def _is_failure_view(view) -> bool:
    return view[0]["type"] == "alert" and view[0]["kind"] == "error" and not _shows_tool(view)


def _has_banner(view) -> bool:
    return view[0]["type"] == "alert" and view[0]["kind"] == "error" and _shows_tool(view)


def test_external_tools_are_not_builtin(broken_tools):
    specs = {s.name: s for s in registry.tool_specs()}
    assert specs["Preferences"].builtin and specs["Trace"].builtin
    assert not specs["BadRender"].builtin and not specs["GoodTool"].builtin


def test_a_failing_tool_shows_its_failure_in_its_pane_only(broken_tools):
    s = make_session()
    names = [t.name for t in s.tools]
    assert "BadCtor" in names  # kept, as a placeholder showing the failure
    assert isinstance(_tool(s, "BadCtor"), FailedTool)
    s.start()
    assert s.wait_for_turn()
    s.play_counters(3)  # BadHook fails after every action
    assert s.phase == "running" and len(s.history) >= 3  # the session keeps negotiating

    t_in, t_act = (s.tool_state(_tool(s, n))["id"] for n in ("BadInput", "BadAction"))
    s.tool_input(t_in, "x", 1)
    s.tool_action(t_act, "go", {})
    assert any(m.get("level") == "error" and "BadAction" in m.get("message", "") for m in s.hub.of_type("toast"))

    # start and render failures: the failure view instead of the tool
    for name in ("BadCtor", "BadInit", "BadRender"):
        view = _view(s, name)
        assert _is_failure_view(view), (name, view)
        assert "not working right now" in _text(view)
        assert not any(x in _text(view) for x in SECRETS), (name, view)  # nothing technical for participants
    # hook, input and button failures: the tool's view under an error banner
    for name in ("BadLoad", "BadInput", "BadAction", "BadHook"):
        view = _view(s, name)
        assert _has_banner(view), (name, view)
        assert not any(x in _text(view) for x in SECRETS), (name, view)
    # every other tool renders as usual
    assert _view(s, "GoodTool")[0] == {"type": "markdown", "text": "GoodTool works"}
    for t in s.tools:
        if t.name in ("BadCtor", "BadInit", "BadLoad", "BadRender", "BadInput", "BadAction", "BadHook", "SlowRender"):
            continue
        if not s.tool_available(t) or not s.tool_state(t)["enabled"]:
            continue
        assert "failure" not in s.tool_state(t), t.name
        assert "not working right now" not in _text(_view(s, t.name)), t.name
    # the page still renders, and says which tools failed
    snap = s.snapshot()
    failed = {x["name"] for x in snap["tools"] if x["failed"]}
    assert failed == {"BadCtor", "BadInit", "BadLoad", "BadRender", "BadInput", "BadAction", "BadHook"}
    s.end()
    assert s.wait_until_done()


def test_admins_see_the_error_and_the_traceback(broken_tools):
    s = make_session(is_admin=True)
    view = _view(s, "BadRender")
    assert "RuntimeError" in _text(view) and "boom in render" in _text(view) and "failed to render" in _text(view)
    card = next(c for c in view if c["type"] == "card")
    assert card["title"] == "Traceback" and card["collapsible"] and card["collapsed"]
    assert "boom in render" in card["children"][0]["text"]
    assert "failed to start" in _text(_view(s, "BadCtor")) and "boom in __init__" in _text(_view(s, "BadCtor"))
    assert "boom in init" in _text(_view(s, "BadInit"))
    banner = _view(s, "BadLoad")
    assert _has_banner(banner) and "scenario_loaded" in _text(banner) and "boom in scenario_loaded" in _text(banner)


def test_a_render_failure_clears_but_a_failed_start_stays(broken_tools):
    s = make_session()
    bad, init = _tool(s, "BadRender"), _tool(s, "BadInit")
    assert _is_failure_view(_view(s, "BadRender"))
    bad.healed = True
    assert _view(s, "BadRender")[0]["text"] == "BadRender works"
    assert s.tool_failure(bad) is None
    init.healed = True
    assert _is_failure_view(_view(s, "BadInit"))  # never initialised: stays failed
    assert s.tool_unusable(init)


def test_a_hook_failure_clears_when_the_hook_works_again(broken_tools):
    s = make_session()
    s.start()
    assert s.wait_for_turn()
    s.play_counters(1)
    hook = _tool(s, "BadHook")
    assert s.wait(lambda: s.tool_failure(hook) is not None, 10)
    assert _has_banner(_view(s, "BadHook"))
    assert _has_banner(_view(s, "BadHook"))  # a render does not clear it
    hook.healed = True
    s.play_counters(1)
    assert s.wait(lambda: s.tool_failure(hook) is None, 10)
    assert _view(s, "BadHook")[0]["text"] == "BadHook works"
    s.end()


def test_a_failure_is_logged_once(broken_tools, capsys):
    s = make_session()
    s.start()
    assert s.wait_for_turn()
    s.play_counters(3)
    s.end()
    s.wait_until_done()
    out = capsys.readouterr().out
    assert out.count("tool 'BadHook' failed in action_executed") == 1


def test_a_slow_render_times_out_without_holding_up_the_others(broken_tools):
    from hani2.hub import Hub

    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.3}})
    s = make_session(is_admin=True)
    slow, good = s.tool_state(_tool(s, "SlowRender"))["id"], s.tool_state(_tool(s, "GoodTool"))["id"]
    hub = Hub()

    async def run():
        hub.attach_loop(asyncio.get_running_loop())
        t0 = time.monotonic()
        view, other = await asyncio.gather(hub.render_tool_view(s, slow), hub.render_tool_view(s, good))
        assert time.monotonic() - t0 < 1.2  # did not wait for the slow tool
        assert "took too long to render" in _text(view["view"]) and "TimeoutError" in _text(view["view"])
        assert other["view"][0]["text"] == "GoodTool works"
        assert s.tool_unusable(_tool(s, "SlowRender"))
        again = await hub.render_tool_view(s, slow)  # not called again while the first render hangs
        assert "took too long" in _text(again["view"])
        _tool(s, "SlowRender").healed = True
        await asyncio.sleep(1.6)  # the first render returns
        assert not s.tool_unusable(_tool(s, "SlowRender"))
        healed = await hub.render_tool_view(s, slow)
        assert healed["view"][0]["text"] == "SlowRender works"

    _run(run())
    assert s.tool_failure(_tool(s, "SlowRender")) is None


def test_slow_renders_do_not_hold_up_others_when_slots_run_out(broken_tools, monkeypatch):
    from hani2 import hub as hub_mod

    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 3}})
    monkeypatch.setattr(hub_mod, "TOOL_RENDER_SLOTS", 1)
    monkeypatch.setattr(hub_mod, "TOOL_RENDER_GRACE", 0.1)
    s = make_session()
    slow, good = s.tool_state(_tool(s, "SlowRender"))["id"], s.tool_state(_tool(s, "GoodTool"))["id"]
    hub = hub_mod.Hub()

    async def run():
        slow_task = asyncio.create_task(hub.render_tool_view(s, slow))
        await asyncio.sleep(0.01)
        t0 = time.monotonic()
        other = await hub.render_tool_view(s, good)
        assert time.monotonic() - t0 < 0.6  # waited for the grace period, not the slow render
        assert other["view"][0]["text"] == "GoodTool works"
        assert (await slow_task)["view"][0]["text"] == "SlowRender works"  # within its 3 s

    _run(run())


def test_participants_see_no_detail_of_a_timeout(broken_tools):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.2}})
    s = make_session()
    tid = s.tool_state(_tool(s, "SlowRender"))["id"]
    view = s.tool_render_timed_out(tid, 0.2)["view"]
    assert "not working right now" in _text(view) and "TimeoutError" not in _text(view)


def test_the_assistant_cannot_use_a_failed_tool_and_its_failures_are_recorded(broken_tools):
    s = make_session(support_settings={"autonomy": "suggest"})
    sa = s.support_agent
    s.start()
    assert s.wait_for_turn()
    res = sa.use_tool("BadInit", action="go")
    assert not res["ok"] and "not working" in res["error"]
    res = sa.use_tool("BadRender", action="go")
    assert not res["ok"] and "not working" in res["error"]
    res = sa.use_tool("BadAction", action="go")
    assert not res["ok"] and s.tool_failure(_tool(s, "BadAction"))["where"] == "on_action"
    assert sa.use_tool("GoodTool", action="go")["ok"]
    s.end()


def test_a_broken_help_text_does_not_break_the_page(broken_tools, monkeypatch):
    s = make_session()
    good = _tool(s, "GoodTool")

    def broken():
        raise ValueError("no help")

    monkeypatch.setattr(good, "help_text", broken)
    s.tool_state(good).pop("help", None)  # the answer is kept from the last refresh
    snap = s.snapshot()
    assert next(x for x in snap["tools"] if x["name"] == "GoodTool")["help"] == ""
    assert s.tool_failure(good)["where"] == "help_text"


@pytest.mark.parametrize("isolate", [True, False])
def test_isolate_builtin(hani2_home, monkeypatch, isolate):
    write_settings(hani2_home, "env.json", {"tools": {"isolate_builtin": isolate}})

    def broken_view(self):
        raise RuntimeError("builtin boom")

    def broken_hook(self, ss, nmi):
        raise RuntimeError("builtin hook boom")

    monkeypatch.setattr(b.ScenarioInfoTool, "view", broken_view)
    monkeypatch.setattr(b.ScenarioInfoTool, "negotiation_started", broken_hook)
    s = make_session()
    info = _tool(s, "Scenario Info")
    s.start()
    assert s.wait_for_turn()
    view = _view(s, "Scenario Info")
    if isolate:
        assert _is_failure_view(view) and "builtin boom" not in _text(view)
        assert s.tool_failure(info)["where"] == "render"
        assert s.snapshot()["tools"] and s.tool_render_timeout(s.tool_state(info)["id"]) == 20
    else:  # exactly as before: Tool.render's own alert, nothing recorded, no time limit
        assert "failed to render" in _text(view) and "builtin boom" in _text(view)
        assert s.tool_failure(info) is None
        assert s.tool_render_timeout(s.tool_state(info)["id"]) is None
    assert s.phase == "running"
    s.end()


@pytest.mark.parametrize("isolate", [True, False])
def test_isolate_builtin_constructor(hani2_home, monkeypatch, isolate):
    write_settings(hani2_home, "env.json", {"tools": {"isolate_builtin": isolate}})

    def broken_init(self, *a, **kw):
        raise RuntimeError("builtin ctor boom")

    monkeypatch.setattr(b.ScenarioInfoTool, "__init__", broken_init)
    s = make_session()
    present = [t for t in s.tools if t.name == "Scenario Info"]
    if isolate:
        assert len(present) == 1 and isinstance(present[0], FailedTool)
        assert _is_failure_view(_view(s, "Scenario Info"))
    else:
        assert not present  # left out, as before


def test_load_errors_are_listed_for_admins(hani2_home, monkeypatch):
    monkeypatch.setattr(registry, "LOAD_ERRORS", {})
    folder = hani2_home / "tools"
    folder.mkdir(parents=True, exist_ok=True)
    bad = folder / "syntax_error.py"
    bad.write_text("def oops(:\n", encoding="utf-8")
    from hani2 import library

    errors = library.tool_load_errors()["errors"]
    assert [e["source"] for e in errors] == [str(bad)] and "SyntaxError" in errors[0]["error"]
    bad.write_text("from hani2.tools import Tool\n\nclass Fixed(Tool):\n    pass\n", encoding="utf-8")
    import os

    os.utime(bad, (time.time() + 5, time.time() + 5))  # a new mtime: read again
    assert library.tool_load_errors()["errors"] == []


def test_load_errors_endpoint(hani2_home, monkeypatch):
    from fastapi.testclient import TestClient

    monkeypatch.setattr(registry, "LOAD_ERRORS", {})
    folder = hani2_home / "tools"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "raises.py").write_text("raise ImportError('missing dependency')\n", encoding="utf-8")
    from hani2.server import app, hub

    hub.sessions.clear()
    with TestClient(app) as c:
        assert c.get("/api/admin/library/tools/load-errors").status_code == 401
        assert c.post("/api/auth/login", json={"username": "admin", "password": "adminpass"}).status_code == 200
        r = c.get("/api/admin/library/tools/load-errors")
        assert r.status_code == 200
        assert any("missing dependency" in e["error"] for e in r.json()["errors"])
    hub.sessions.clear()


# -- review fixes -------------------------------------------------------------- #
def _arm(monkeypatch, *names):
    monkeypatch.setenv("HANI_TEST_ARM", ",".join(names))


def _assistant(s):
    s.start()
    assert s.wait_for_turn()
    return s.support_agent


def test_the_assistant_is_not_blocked_by_a_hung_tool(broken_tools):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.3}})
    s = make_session(support_settings={"autonomy": "suggest"})
    sa = _assistant(s)
    t0 = time.monotonic()
    res = sa.read_tool("SlowRender")  # its view sleeps 1.5 s
    assert time.monotonic() - t0 < 1.2
    assert res["ok"] and "not available" in res["text"]
    assert s.tool_unusable(_tool(s, "SlowRender"))
    res = sa.use_tool("SlowRender", action="go")
    assert not res["ok"] and "not working" in res["error"]
    assert sa.use_tool("GoodTool", action="go")["ok"]  # other tools are fine
    s.end()


def test_describe_for_agent_uses_the_guarded_path(broken_tools):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.3}})
    s = make_session()
    bad, slow = _tool(s, "BadRender"), _tool(s, "SlowRender")
    assert "not available" in bad.describe_for_agent() and "boom" not in bad.describe_for_agent()
    assert s.tool_failure(bad)["where"] == "render"
    t0 = time.monotonic()
    assert "not available" in slow.describe_for_agent()
    assert time.monotonic() - t0 < 1.2


def test_a_finish_at_the_limit_never_leaves_a_tool_hung():
    from hani2.hub import Hub

    class Fake:
        sid = "fake"

        def __init__(self):
            self.hung = False
            self.lock = __import__("threading").Lock()

        def tool_render_timeout(self, tid):
            return 0.05

        def render_tool(self, tid):
            time.sleep(0.05)  # finishes right at the limit
            return {"id": tid, "view": []}

        def tool_render_timed_out(self, tid, seconds):
            with self.lock:
                self.hung = True
            return {"id": tid, "view": ["timeout"]}

        def tool_render_returned(self, tid):
            with self.lock:
                self.hung = False
            return True

        def tool_render_in_time(self, tid):
            pass

    async def run():
        hub = Hub()
        hub.attach_loop(asyncio.get_running_loop())
        for _ in range(150):
            s = Fake()
            await hub.render_tool_view(s, "t")
            await asyncio.sleep(0.15)
            assert not s.hung

    asyncio.run(run())


def test_participants_never_see_exception_text(broken_tools, monkeypatch):
    toasts = []
    for admin in (False, True):
        s = make_session(is_admin=admin, support_settings={"autonomy": "suggest"})
        monkeypatch.setattr(s, "toast", lambda m, level="info", **kw: toasts.append((admin, m)))
        s.tool_action(s.tool_state(_tool(s, "BadAction"))["id"], "go", {})
        res = _assistant(s).use_tool("BadAction", action="go")
        text = json.dumps(res)
        assert ("boom" in text) == admin and ("RuntimeError" in text) == admin
        s.end()
    shown = {a: m for a, m in toasts}
    assert "boom" not in shown[False] and "RuntimeError" not in shown[False] and "BadAction" in shown[False]
    assert "boom" in shown[True]


def test_a_hung_action_does_not_block_the_session(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.3}})
    _arm(monkeypatch, "HangAction")
    s = make_session()
    hang, good = _tool(s, "HangAction"), _tool(s, "GoodTool")
    hid, gid = s.tool_state(hang)["id"], s.tool_state(good)["id"]
    t0 = time.monotonic()
    s.submit_ui(s.tool_action, hid, "go", {}).result()  # the single-worker UI executor
    assert time.monotonic() - t0 < 0.9
    assert s.tool_unusable(hang) and s.tool_failure(hang)["where"] == "on_action"
    t0 = time.monotonic()
    s.submit_ui(s.tool_action, hid, "go", {}).result()  # skipped while the first call hangs
    s.submit_ui(s.tool_input, hid, "x", 1).result()
    s.submit_ui(s.tool_action, gid, "go", {}).result()  # other tools carry on
    assert time.monotonic() - t0 < 0.3
    assert _is_failure_view(_view(s, "HangAction")) and _shows_tool(_view(s, "GoodTool"))
    assert s.wait(lambda: not s.tool_unusable(hang), 5)  # the abandoned call returned
    _arm(monkeypatch)
    s.tool_action(hid, "go", {})
    assert s.tool_failure(hang) is None


def test_a_hung_init_and_hook_are_abandoned(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.3}})
    _arm(monkeypatch, "HangInit", "HangHook")
    t0 = time.monotonic()
    s = make_session()
    assert time.monotonic() - t0 < 3
    init = _tool(s, "HangInit")
    assert s.tool_failure(init)["where"] == "init" and s.tool_failure(init)["error_type"] == "TimeoutError"
    assert _is_failure_view(_view(s, "HangInit"))
    s.start()
    assert s.wait_for_turn()
    t0 = time.monotonic()
    s.play_counters(1)
    hook = _tool(s, "HangHook")
    assert s.wait(lambda: s.tool_failure(hook) is not None, 10)
    assert s.tool_failure(hook)["where"] == "action_executed"
    assert time.monotonic() - t0 < 1.5  # not held up by the 1 s hang
    s.end()


def test_sys_exit_in_a_tool_is_caught(broken_tools, monkeypatch):
    _arm(monkeypatch, "ExitView", "ExitAction")
    s = make_session(is_admin=True)
    view = _view(s, "ExitView")
    assert _is_failure_view(view) and "SystemExit" in _text(view)
    s.tool_action(s.tool_state(_tool(s, "ExitAction"))["id"], "go", {})  # does not raise
    assert s.tool_failure(_tool(s, "ExitAction"))["error_type"] == "SystemExit"
    sa = _assistant(s)
    assert not sa.use_tool("ExitAction", action="go")["ok"]
    s.end()


def test_an_always_slow_tool_stops_being_retried(broken_tools, monkeypatch):
    from hani2.hub import Hub
    from hani2.tools import failure

    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.2}})
    monkeypatch.setattr(failure, "MAX_TIMEOUTS", 2)
    _arm(monkeypatch, "AlwaysSlow")
    s = make_session(is_admin=True)
    tool = _tool(s, "AlwaysSlow")
    tid = s.tool_state(tool)["id"]
    hub = Hub()
    refreshed = []
    real_refresh = tool.refresh
    tool.refresh = lambda: (refreshed.append(1), real_refresh())

    async def run():
        hub.attach_loop(asyncio.get_running_loop())
        for _ in range(2):
            view = await hub.render_tool_view(s, tid)
            assert "took too long" in _text(view["view"])
            skipped = await hub.render_tool_view(s, tid)  # while it hangs: skipped, and proves nothing
            assert "took too long" in _text(skipped["view"])
            await asyncio.sleep(0.7)  # the slow render returns
        assert s.tool_state(tool).get("gave_up") and refreshed  # the pane is refreshed to say so
        calls = type(tool).calls
        view = await hub.render_tool_view(s, tid)
        assert "not tried again" in _text(view["view"]) and type(tool).calls == calls  # not called any more
        assert s.tool_unusable(tool)
        # the pane says so and has a button; the Assistant is not kept waiting for a tool that gave up
        assert any(c["type"] == "button" and c["action"] == failure.RETRY_ACTION for c in view["view"])
        t0 = time.monotonic()
        assert s.guard_tool(tool, "render", lambda: 1 / 0, default="d", timed=True) == "d"
        assert time.monotonic() - t0 < 0.1 and type(tool).calls == calls
        assert s.tool_private_to_human(tool)  # an unusable tool counts as private
        s.tool_action(tid, failure.RETRY_ACTION, {})  # the button: no tab switch needed
        assert not s.tool_unusable(tool)
        s.tool_state(tool)["render_timeouts"] = 2
        s.tool_state(tool)["gave_up"] = True
        s.retry_tool(tool)  # explicit retry: the tab is opened again
        _arm(monkeypatch)
        view = await hub.render_tool_view(s, tid)
        assert view["view"][0]["text"] == "AlwaysSlow works"

    asyncio.run(run())
    assert s.tool_failure(tool) is None


def test_a_fence_in_the_exception_text_does_not_break_the_traceback(broken_tools, monkeypatch):
    _arm(monkeypatch, "FenceView")
    s = make_session(is_admin=True)
    view = _view(s, "FenceView")
    md = next(c for c in view if c["type"] == "card")["children"][0]["text"]
    fence = md.split("text\n", 1)[0]
    assert len(fence) >= 5 and set(fence) == {"`"} and md.rstrip().endswith(fence)  # longer than the ```` inside


def test_help_text_in_describe_for_agent_is_guarded(broken_tools, monkeypatch):
    s = make_session()
    good = _tool(s, "GoodTool")

    def broken():
        raise ValueError("no help")

    monkeypatch.setattr(good, "help_text", broken)
    assert "GoodTool works" in good.describe_for_agent()
    assert good.describe_for_agent().startswith("Tool: GoodTool")


def test_sys_exit_in_a_constructor_or_at_import_does_not_end_the_server(broken_tools, monkeypatch):
    (broken_tools / "exits_on_import.py").write_text("import sys\nsys.exit(5)\n", encoding="utf-8")
    _arm(monkeypatch, "ExitCtor")
    s = make_session(is_admin=True)
    tool = _tool(s, "ExitCtor")
    assert isinstance(tool, FailedTool)
    assert "failed to start" in _text(_view(s, "ExitCtor")) and "SystemExit" in _text(_view(s, "ExitCtor"))
    assert any("exits_on_import" in k and "SystemExit" in v["error"] for k, v in registry.LOAD_ERRORS.items())
    assert _shows_tool(_view(s, "GoodTool"))


# -- second review ----------------------------------------------------------- #
def _lock_wait(s, during):
    """How long another thread waits for the session lock while ``during()`` runs."""
    import threading

    th = threading.Thread(target=during)
    th.start()
    time.sleep(0.05)
    t0 = time.monotonic()
    with s.lock:
        pass
    waited = time.monotonic() - t0
    th.join()
    return waited


def test_no_tool_code_runs_under_the_session_lock(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.3}})
    _arm(monkeypatch, "HangHelp", "HangPrivate", "ExitAvail")
    t0 = time.monotonic()
    s = make_session()  # help_text, private_now and available are asked outside the lock, time-limited
    assert time.monotonic() - t0 < 3
    assert _lock_wait(s, s.snapshot) < 0.5  # help_text is kept, not asked while the lock is held
    start = time.monotonic()
    snap = s.snapshot()
    assert time.monotonic() - start < 1
    assert any(x["name"] == "GoodTool" for x in snap["tools"])
    # private_now hangs: the tool counts as private (fail closed), listed without waiting
    start = time.monotonic()
    listed = s.run_on_doc(s.tool_controller.list_tools)
    assert time.monotonic() - start < 1
    assert next(x for x in listed if x["name"] == "HangPrivate").get("private") is True
    # SystemExit from available() does not escape
    assert s.tool_available(_tool(s, "ExitAvail")) in (True, False)
    assert isinstance(s.shown_tool_names(), set)


def test_guard_tool_refuses_to_run_a_tool_from_outside_while_the_lock_is_held(broken_tools):
    import threading

    s = make_session()
    good, ran = _tool(s, "GoodTool"), []

    def fn():
        ran.append(threading.get_ident())
        return "ran"

    with s.lock:
        assert s.guard_tool(good, "on_input", fn, default="skipped") == "skipped"
        assert not ran  # not here, and not before the lock is free
    assert s.wait(lambda: ran, 5)
    assert ran[0] != threading.get_ident()  # later, in a thread of its own


def test_calls_use_daemon_threads_and_an_abandoned_call_never_runs(broken_tools, monkeypatch):
    import threading

    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.1}})
    s = make_session()
    good = _tool(s, "GoodTool")
    assert not hasattr(__import__("hani2.session", fromlist=["x"]), "_CALL_POOL")
    seen = []

    def slow():
        time.sleep(0.5)
        return 1

    th = threading.Thread(target=lambda: s.guard_tool(good, "on_input", slow))
    th.start()
    time.sleep(0.03)
    assert all(t.daemon for t in threading.enumerate() if t.name == "hani2-tool-call")
    th.join()
    assert s.wait(lambda: not s.tool_unusable(good), 5)

    real = threading.Thread

    class Late(real):  # the call's thread starts only after the caller has given up
        def run(self):
            if self.name == "hani2-tool-call":
                time.sleep(0.4)
            super().run()

    monkeypatch.setattr(threading, "Thread", Late)
    try:
        assert s.guard_tool(good, "on_input", lambda: seen.append(1), default="d") == "d"
    finally:
        monkeypatch.setattr(threading, "Thread", real)
    assert s.tool_unusable(good)
    assert s.wait(lambda: not s.tool_unusable(good), 5)  # the skipped call counted as returned
    assert seen == []


def test_the_tool_stays_hung_until_every_abandoned_call_has_returned(broken_tools):
    import threading

    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.2}})
    s = make_session()
    good = _tool(s, "GoodTool")
    gate = threading.Barrier(2)

    def sleeper(sec):
        def fn():
            time.sleep(sec)
        return fn

    def call(sec):
        gate.wait()
        s.guard_tool(good, "on_input", sleeper(sec))

    ths = [threading.Thread(target=call, args=(sec,)) for sec in (0.5, 1.6)]
    for t in ths:
        t.start()
    for t in ths:
        t.join()
    assert s.tool_unusable(good)
    time.sleep(0.6)  # the first one has returned, the second has not
    assert s.tool_unusable(good)
    assert s.wait(lambda: not s.tool_unusable(good), 5)


def test_a_slow_init_gets_the_missed_hooks_when_it_returns(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.3}})
    _arm(monkeypatch, "HangInit")
    s = make_session()
    tool = _tool(s, "HangInit")
    assert s.tool_unusable(tool)
    s.start()  # negotiation_started comes while the tool is hung
    assert s.wait_for_turn()
    assert s.wait(lambda: not s.tool_unusable(tool), 5)
    assert s.wait(lambda: getattr(tool, "n_loaded", 0) >= 1 and getattr(tool, "n_started", 0) >= 1, 5)
    s.end()


def test_several_hung_inits_cost_one_time_limit(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.4}})
    t0 = time.monotonic()
    make_session()
    base = time.monotonic() - t0
    _arm(monkeypatch, "HangInit", "HangInit2", "HangInit3", "HangInit4")
    t0 = time.monotonic()
    s = make_session()
    assert time.monotonic() - t0 - base < 0.9  # four in a row would add 1.6 s
    assert all(s.tool_failure(_tool(s, n))["where"] == "init" for n in ("HangInit", "HangInit2", "HangInit3", "HangInit4"))


def test_a_tool_is_never_left_starting(broken_tools):
    s = make_session()
    good = _tool(s, "GoodTool")
    st = s.tool_state(good)
    st["starting"] = True
    assert s.tool_unusable(good) and s.tool_private_to_human(good)
    assert s.render_tool(st["id"]) is None  # not rendered while it starts

    class Boom(BaseException):
        pass

    def boom(*a, **kw):
        raise Boom()

    real = s.guard_tool
    s.guard_tool = boom
    try:
        with pytest.raises(Boom):
            s._start_tool(good, scenario=True)
    finally:
        s.guard_tool = real
    assert "starting" not in st


def test_add_tool_marks_the_tool_starting_before_it_is_listed(broken_tools):
    from hani2.tools import Tool, ui

    s = make_session()
    seen = []

    class StartProbe(Tool):
        pane = "side"

        def init(self, ss):
            sess = ss["_session"]
            seen.append((self in sess.tools, sess.tool_unusable(self)))

        def view(self):
            return [ui.markdown("probe")]

    assert s.add_tool(StartProbe)["ok"]
    assert seen == [(True, True)]
    assert "starting" not in s.tool_state(next(t for t in s.tools if isinstance(t, StartProbe)))


def test_input_timeout_is_shorter_than_the_render_timeout(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 5, "input_timeout": 0.2}})
    _arm(monkeypatch, "HangAction")
    s = make_session()
    hang = _tool(s, "HangAction")
    t0 = time.monotonic()
    s.submit_ui(s.tool_action, s.tool_state(hang)["id"], "go", {}).result()
    assert time.monotonic() - t0 < 0.9
    assert s.tool_failure(hang)["where"] == "on_action"


# -- third review ------------------------------------------------------------ #
class _LoopHub:
    """Behaves like Hub.tool_changed: asks whether the tool is shown (on the caller's thread)."""

    def __init__(self, s):
        self.s, self.calls = s, 0

    def tool_changed(self, sid, tid):
        self.calls += 1
        assert self.calls < 60, "tool_changed recursed"
        self.s.tool_is_shown(tid)

    def push(self, *a, **kw):
        pass

    def push_state(self, *a, **kw):
        pass


def test_the_event_loop_path_never_asks_tool_code_and_failures_do_not_recurse(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.3}})
    _arm(monkeypatch, "RaiseAvail", "HangAvail")
    s = make_session()
    s.hub = hub = _LoopHub(s)
    good = _tool(s, "GoodTool")
    time.sleep(0.4)  # past the cache time
    t0 = time.monotonic()
    for name in ("RaiseAvail", "HangAvail", "GoodTool"):
        s.tool_changed(_tool(s, name))
        assert s.shown_tool_names() is not None
        assert s.tool_is_shown(s.tool_state(good)["id"]) in (True, False)
    assert time.monotonic() - t0 < 0.2  # nothing waited for a tool
    before = hub.calls
    s.snapshot()  # the off-loop path asks (and a failed ask must not refresh in a loop)
    assert hub.calls - before <= 6
    assert s.tool_failure(_tool(s, "RaiseAvail"))["where"] == "available"


def test_help_text_is_kept_only_when_it_was_answered(broken_tools):
    s = make_session()
    tool = _tool(s, "HangHelp")
    st = s.tool_state(tool)
    st.pop("help", None)
    st["hung"] = 1  # the ask is skipped
    s._refresh_predicates(tool)
    assert "help" not in st
    st.pop("hung")
    s._refresh_predicates(tool)
    assert st["help"] == "help"


def test_predicates_are_asked_in_parallel_and_available_is_reused_briefly(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0.4}})
    s = make_session()
    time.sleep(0.35)
    _arm(monkeypatch, "HangAvail", "HangAvail2", "HangAvail3")
    t0 = time.monotonic()
    s.refresh_tool_predicates()
    assert time.monotonic() - t0 < 0.9  # three in a row would take 1.2 s
    t0 = time.monotonic()
    s.refresh_tool_predicates()  # answers are fresh (and the tools are hung): nothing to wait for
    assert time.monotonic() - t0 < 0.2
    assert s.wait(lambda: not any(s.tool_unusable(_tool(s, n)) for n in ("HangAvail", "HangAvail2", "HangAvail3")), 5)


def test_retrying_a_tool_delivers_the_hooks_it_missed(broken_tools):
    s = make_session()
    tool = _tool(s, "GoodTool")
    st = s.tool_state(tool)
    before = getattr(tool, "n_loaded", 0)
    st["gave_up"] = True
    st["missed"] = {"scenario_loaded"}
    s.retry_tool(tool)
    assert tool.n_loaded == before + 1
    st["gave_up"] = True  # a tool that gave up rendering still gets hooks
    st["missed"] = {"scenario_loaded"}
    s._replay_missed(tool)
    assert tool.n_loaded == before + 2


def test_no_render_limit_means_no_input_limit_either(broken_tools, monkeypatch):
    write_settings(broken_tools.parent, "env.json", {"tools": {"render_timeout": 0, "input_timeout": 0.2}})
    _arm(monkeypatch, "HangAction")
    s = make_session()
    hang = _tool(s, "HangAction")
    t0 = time.monotonic()
    s.tool_action(s.tool_state(hang)["id"], "go", {})
    assert time.monotonic() - t0 >= 0.9
    assert s.tool_failure(hang) is None
