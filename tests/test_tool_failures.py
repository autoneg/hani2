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

BROKEN_TOOLS = textwrap.dedent('''
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

    asyncio.run(run())
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

    asyncio.run(run())


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
    snap = s.snapshot()
    assert next(x for x in snap["tools"] if x["name"] == "GoodTool")["help"] == ""


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
