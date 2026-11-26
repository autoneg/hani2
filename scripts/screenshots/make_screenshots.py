"""Take the documentation screenshots: the app, every tool, the walkthroughs, the Assistant's character and
the tutorial levels.

Each run starts real HANI2 servers on fresh homes (in a temporary folder), drives them with
Playwright (Chromium) at a fixed window size and writes PNG files into ``docs/assets/screens``.
Run it from the repository root after ``uv pip install -e ".[e2e]"`` and
``.venv/bin/playwright install chromium``:

    .venv/bin/python scripts/screenshots/make_screenshots.py            # everything
    .venv/bin/python scripts/screenshots/make_screenshots.py tools      # only the tool screenshots
    .venv/bin/python scripts/screenshots/make_screenshots.py popup      # a tool in a popup (simple view)
    .venv/bin/python scripts/screenshots/make_screenshots.py tutorial --level 3
    .venv/bin/python scripts/screenshots/make_screenshots.py app han hi   # the page, the walkthroughs

Groups: ``tools`` (every tool), ``popup``, ``character``, ``app`` (login, the negotiation page in
each view and device, the admin console, the example tools), ``han`` and ``hi`` (the walkthrough
tutorials: against an AI opponent, and with the Assistant and against people) and ``tutorial``.

The tools need no language model except the LLM tool and the two LLM example tools (Summary,
Ask the AI); tutorial levels 0, 3, 4, 5 and 7 chat with the model. They use the default model,
``qwen3:4b-instruct`` on a local Ollama (``ollama pull qwen3:4b-instruct``). Without one those
screenshots are skipped (``--no-llm`` skips them on purpose). Model answers differ from run to
run, so look at every image before committing it.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "assets" / "screens"
TUTORIAL = ROOT / "examples" / "support_agent_tutorial"
EXAMPLE_TOOLS = ROOT / "examples" / "tools"
ASSISTANT = Path(__file__).resolve().parent / "docs_assistant.py"
VIEWPORT = {"width": 1440, "height": 900}
SCALE = 1.5
ACCEPT = re.compile(r"^Accept")
TIMEOUT = 20000

# The scenario and the information split the tool screenshots use: a private briefing, past
# negotiations and market research for the participant, so that those tools appear.
INFORMATION = {
    "past_negotiations": {"count": 4, "human_share": 1.0},
    "market_research": {"audience": "human"},
    "briefing": [{"text": "Your partner will only sign a lease of one year or less, and the rent must "
                          "stay below what you pay now. Keep this to yourself.", "pin": False}],
    "control": {"human_only_actions": ["accept"]},
}
SWITCHED_ON = ("Utility Plot", "Outcome Plot", "Trace")


def log(*a) -> None:
    print("[screenshots]", *a, flush=True)


def llm_available(model: str = "qwen3:4b-instruct") -> bool:
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            names = [m["name"] for m in json.load(r).get("models", [])]
    except Exception:  # noqa: BLE001
        return False
    return model in names


# --------------------------------------------------------------------------- #
# Servers                                                                      #
# --------------------------------------------------------------------------- #
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _merge_json(path: Path, data: dict) -> None:
    cur = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(cur.get(k), dict):
            cur[k] = {**cur[k], **v}
        else:
            cur[k] = v
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur, indent=2), encoding="utf-8")


@contextlib.contextmanager
def server(args: list[str], *, env_json: dict | None = None, assistant: dict | None = None,
           scenario: str | None = "Lease", extra_env: dict | None = None, opponent: str = "BoulwareTBNegotiator"):
    """A HANI2 server on a fresh home; yields its base URL.

    ``scenario`` is the only scenario it serves (``None``: the bundled order); ``opponent`` the
    opponent agent (later ``--opponents`` in ``args`` win)."""
    home = Path(tempfile.mkdtemp(prefix="hani2-shots-"))
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HANI2_", "PROLIFIC_", "SCMLWEB_"))}
    env.update(HANI2_HOME=str(home), HANI2_MODEL_PROBE="off", PYTHONUNBUFFERED="1", **(extra_env or {}))
    cli = [os.environ.get("HANI2_PYTHON", sys.executable), "-m", "hani2.cli"]
    subprocess.run([*cli, "setup"], env=env, check=True, capture_output=True)
    settings = home / "settings"
    if scenario:
        (settings / "scenario_order.txt").write_text(scenario + "\n", encoding="utf-8")
    _merge_json(settings / "env.json", {"negotiation": {"n_steps": 12, "time_limit": None}, **(env_json or {})})
    if assistant:
        _merge_json(settings / "assistant_settings.json", assistant)
    port = _free_port()
    logf = (home / "server.log").open("w")
    proc = subprocess.Popen([*cli, "--no-browser", "--port", str(port), "--opponents", opponent, *args],
                            env=env, stdout=logf, stderr=subprocess.STDOUT, cwd=str(TUTORIAL))
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(160):
            if proc.poll() is not None:
                break
            try:
                urllib.request.urlopen(url + "/api/config", timeout=1)
                break
            except OSError:
                time.sleep(0.25)
        if proc.poll() is not None:
            raise RuntimeError("the server did not start:\n" + (home / "server.log").read_text()[-3000:])
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        logf.close()
        shutil.rmtree(home, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Driving the page                                                             #
# --------------------------------------------------------------------------- #
def new_page(browser, url: str, *, viewport: dict | None = None, scale: float = SCALE, **kw):
    ctx = browser.new_context(base_url=url, viewport=viewport or VIEWPORT, device_scale_factor=scale,
                              color_scheme="light", reduced_motion="reduce", **kw)
    ctx.set_default_timeout(TIMEOUT)
    page = ctx.new_page()
    return ctx, page


def login(page, user: str, password: str) -> None:
    r = page.request.post("/api/auth/login", data={"username": user, "password": password})
    assert r.ok, r.text()


def start(page) -> None:
    page.get_by_role("button", name="Start negotiation").click()
    expect(page.get_by_role("button", name="Counter-offer").or_(page.locator("[data-anchor=send]").get_by_role("button", name="Send offer")).first
           ).to_be_visible()


def send_counter(page, message: str) -> None:
    if not page.locator("[data-anchor=send]").get_by_role("button", name="Send offer").count():
        page.get_by_role("button", name="Counter-offer").click()
    box = page.get_by_placeholder(re.compile("Explain your offer"))
    if box.count():
        box.fill(message)
    send = page.locator("[data-anchor=send]").get_by_role("button", name="Send offer")
    try:
        expect(send).to_be_enabled(timeout=8000)
    except AssertionError:
        debug = Path(tempfile.gettempdir()) / "hani2-shots-send-disabled.png"
        page.screenshot(path=str(debug))
        raise RuntimeError(f"Send offer stayed disabled; see {debug}") from None
    try:
        send.click(timeout=8000)
    except Exception:  # noqa: BLE001 - re-rendered under the click (an Assistant filling the offer)
        if ended(page) or not send.count():
            return  # the turn passed (the offer was sent or the negotiation moved on)
        debug = Path(tempfile.gettempdir()) / "hani2-shots-send-failed.png"
        page.screenshot(path=str(debug))
        send.click(force=True, timeout=5000)


def my_turn(page):
    accept = page.get_by_role("button", name=ACCEPT).first
    for _ in range(3):
        try:
            expect(accept).to_be_enabled(timeout=6000)
            return accept
        except AssertionError:
            send_counter(page, "Let us start here.")
    expect(accept).to_be_enabled()
    return accept


def ended(page) -> bool:
    """Whether the negotiation on the page has ended."""
    return bool(page.get_by_text(re.compile(r"^(Agreement reached|No agreement)")).count())


def play(page, rounds: int) -> None:
    """Send ``rounds`` counter-offers (fewer when the negotiation ends first) and wait for the turn."""
    messages = ["I can offer this.", "That is still too much for me.", "Let us meet somewhere here.",
                "I moved on the deposit.", "This is close to my limit."]
    for i in range(rounds):
        if ended(page):
            return
        my_turn(page)
        send_counter(page, messages[i % len(messages)])
    if not ended(page):
        my_turn(page)


def accept_offer(page) -> None:
    my_turn(page).click()
    page.get_by_role("button", name="Accept offer").click()
    expect(page.get_by_text("Agreement reached").first).to_be_visible()


def settle(page, ms: int = 900) -> None:
    """Let plots draw and animations end."""
    page.wait_for_timeout(ms)
    with contextlib.suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=3000)


def save(locator, name: str) -> None:
    path = OUT / f"{name}.png"
    locator.screenshot(path=str(path), animations="disabled")
    compress(path)
    log("wrote", path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)


def compress(path: Path) -> None:
    """Shrink a PNG with pngquant when it is installed (the docs ship every image)."""
    exe = shutil.which("pngquant")
    if exe:
        subprocess.run([exe, "--force", "--skip-if-larger", "--quality", "80-95", "--strip",
                        "--output", str(path), str(path)], check=False, capture_output=True)


def type_into(box, text: str) -> None:
    """Fill a tool's text box and leave it, so the value reaches the server before a button is pressed."""
    box.fill(text)
    box.press("Tab")
    box.page.wait_for_timeout(600)


HIDE_TOASTS = ".pointer-events-none.fixed.right-4.top-16 { display: none !important; }"


def hide_toasts(page) -> None:
    """Keep notifications out of the tool screenshots (they sit above the enlarged window)."""
    page.add_style_tag(content=HIDE_TOASTS)


def tab(page, name: str):
    return page.get_by_role("tab", name=re.compile(rf"^{re.escape(name)}\b"))


def llm_shot(page, name: str, file: str, **kw) -> None:
    """``shot_tool`` for a tool that needs the language model: a slow or failed answer is logged and skipped
    (the old image stays) instead of stopping the run."""
    try:
        shot_tool(page, name, file, **kw)
    except Exception as e:  # noqa: BLE001
        debug = Path(tempfile.gettempdir()) / f"hani2-shots-{file}.png"
        page.screenshot(path=str(debug))
        log(f"skipped {file}: {type(e).__name__} (see {debug})")
        page.keyboard.press("Escape")
        page.set_viewport_size(VIEWPORT)


def shot_tool(page, name: str, file: str, *, prepare=None, wait_for: str | None = None, settle_ms: int = 1200) -> None:
    """Open the tool's tab, enlarge it and screenshot the enlarged window (fitted to its content)."""
    t = tab(page, name).first
    t.scroll_into_view_if_needed()
    t.click()
    page.get_by_role("button", name=f"Enlarge {name}").click()
    dlg = page.get_by_role("dialog", name=name)
    expect(dlg).to_be_visible()
    body = dlg.locator("div.overflow-y-auto").first
    expect(body.locator(".animate-pulse")).to_have_count(0)
    if prepare:
        prepare(dlg)
    if wait_for:
        expect(dlg.get_by_text(wait_for).first).to_be_visible(timeout=120000)
    settle(page, settle_ms)
    # make the window as tall as its content (up to a limit), so nothing is cut off
    need = page.evaluate("(el) => el.scrollHeight", body.element_handle())
    h = int(min(1800, max(VIEWPORT["height"], (need + 70) / 0.88 + 30)))
    if h != page.viewport_size["height"]:
        page.set_viewport_size({"width": VIEWPORT["width"], "height": h})
        settle(page, 600)
    # as tall as the content, not the usual 88% of the window
    dlg.evaluate("(el) => { el.style.height = 'auto'; el.style.maxHeight = '96vh'; }")
    settle(page, 400)
    save(dlg, file)
    page.keyboard.press("Escape")
    expect(dlg).to_have_count(0)
    page.set_viewport_size(VIEWPORT)


# --------------------------------------------------------------------------- #
# The tools                                                                    #
# --------------------------------------------------------------------------- #
def tools_env() -> dict:
    return {
        "negotiation": {"n_steps": 12, "time_limit": None, "information": INFORMATION},
        "tools": {"paths": [str(EXAMPLE_TOOLS)], "overrides": {n: {"enabled": True} for n in SWITCHED_ON}},
    }


def take_tools(browser, use_llm: bool) -> None:
    with server(["--assistant", f"{ASSISTANT}:DocsAssistant"], env_json=tools_env()) as url:
        # an admin sees every tool, the admin-only ones too
        ctx, page = new_page(browser, url)
        login(page, "admin", "adminpass")
        page.goto("/app")
        start(page)
        play(page, 4)
        settle(page)
        save(page, "tools-overview")
        hide_toasts(page)
        for name, file in [
            ("Preferences", "tool-preferences"), ("Scenario Info", "tool-scenario-info"),
            ("Briefing", "tool-briefing"), ("Past Negotiations", "tool-past-negotiations"),
            ("Market Research", "tool-market-research"), ("Value Histogram", "tool-value-histogram"),
            ("Utility Plot", "tool-utility-plot"), ("Outcome Plot", "tool-outcome-plot"), ("Trace", "tool-trace"),
            ("Opponent Preferences", "tool-opponent-preferences"), ("Utility Bar", "tool-utility-bar"),
            ("Utility-based Selector", "tool-utility-selector"),
            ("Deal Compass", "tool-deal-compass"),
            ("Offer Counter", "tool-offer-counter"), ("What If", "tool-what-if"),
            ("Concession Tracker", "tool-concession-tracker"),
        ]:
            shot_tool(page, name, file)
        # Random after Generate: the generated deal and its Send offer button
        shot_tool(page, "Random", "tool-random",
                  prepare=lambda d: d.get_by_role("button", name="Generate").click(), wait_for="Generated deal")
        # the Negotiation Plot of an admin: the estimate by default, the real preferences on request
        shot_tool(page, "Negotiation Plot", "tool-negotiation-plot-estimate-admin")
        shot_tool(page, "Negotiation Plot", "tool-negotiation-plot",
                  prepare=lambda d: d.locator("select").first.select_option(label="The real preferences"))
        shot_tool(page, "Utility-based Selector", "tool-utility-selector-by-opponent",
                  prepare=lambda d: d.locator("select").first.select_option(label="The opponent's estimated utility"))
        if use_llm:
            def ask_llm(d):
                type_into(d.locator("textarea"), "Propose a fair middle ground on the rent and keep the lease short.")
                d.get_by_role("button", name="Generate").click()
            llm_shot(page, "LLM", "tool-llm", prepare=ask_llm, wait_for="Suggested offer")

            def answered(d, button: str, empty: str) -> None:
                d.get_by_role("button", name=button, exact=True).click()
                expect(d.get_by_text(empty)).to_have_count(0, timeout=120000)
                expect(d.get_by_role("button", name=button, exact=True)).to_be_visible(timeout=120000)

            llm_shot(page, "Summary", "tool-summary",
                      prepare=lambda d: answered(d, "Summarise", "Press Summarise once a few offers have been made."))

            def ask(d):
                type_into(d.locator("textarea"), "Which issue should I give up first?")
                answered(d, "Ask", "Type a question and press Ask.")
            llm_shot(page, "Ask the AI", "tool-ask-ai", prepare=ask)
        accept_offer(page)
        page.get_by_role("button", name="Next negotiation").click()
        expect(page.get_by_role("button", name="Start negotiation")).to_be_visible()
        shot_tool(page, "My Results", "tool-my-results")
        shot_tool(page, "All Results", "tool-all-results")
        ctx.close()

        # a participant: the Negotiation Plot appears only with the Assistant's estimate
        ctx, page = new_page(browser, url)
        login(page, "user", "userpass")
        page.goto("/app")
        start(page)
        play(page, 3)
        hide_toasts(page)
        expect(tab(page, "Negotiation Plot")).to_be_visible()
        settle(page)
        shot_tool(page, "Negotiation Plot", "tool-negotiation-plot-estimate")
        shot_tool(page, "Utility-based Selector", "tool-utility-selector-estimate")
        ctx.close()


# --------------------------------------------------------------------------- #
# The Assistant as a character                                                 #
# --------------------------------------------------------------------------- #
def take_character(browser) -> None:
    hello = TUTORIAL / "level1_hello.py"
    with server(["--assistant", f"{hello}:HelloAgent"],
                assistant={"presentation": {"style": "persona", "choice_default": "panel", "persona_movable": True}}) as url:
        ctx, page = new_page(browser, url)
        page.goto("/play")
        start(page)
        my_turn(page)
        page.locator("[data-persona]").hover()
        settle(page)
        save(page, "assistant-character")
        page.get_by_role("button", name=re.compile(r"^Hide ")).click()
        page.get_by_role("banner").get_by_role("button", name="Assistant", exact=True).click()
        settle(page)
        save(page, "assistant-character-hidden")
        ctx.close()


# --------------------------------------------------------------------------- #
# The tutorial                                                                 #
# --------------------------------------------------------------------------- #
TOASTS = ".pointer-events-none.fixed.right-4.top-16"


def assistant_idle(page, timeout: int = 120000) -> None:
    """Wait until the Assistant has finished its turn."""
    dock = page.get_by_role("complementary", name="Assistant")
    page.wait_for_timeout(1500)
    expect(dock.get_by_text("Working…")).to_have_count(0, timeout=timeout)


def open_assistant(page) -> None:
    btn = page.get_by_role("banner").get_by_role("button", name="Assistant", exact=True)
    if btn.get_attribute("aria-pressed") != "true":
        btn.click()
    expect(page.get_by_role("complementary", name="Assistant")).to_be_visible()


def chat(page, text: str, wait_text: str | None = None, timeout: int = 120000) -> None:
    dock = page.get_by_role("complementary", name="Assistant")
    box = dock.locator("textarea, input[type=text]").last
    box.fill(text)
    dock.get_by_role("button", name="Send").click()
    if wait_text:
        expect(dock.get_by_text(wait_text).first).to_be_visible(timeout=timeout)
    else:  # wait until the assistant has answered
        page.wait_for_timeout(1000)
        expect(dock.get_by_role("status", name="The assistant is working")).to_have_count(0, timeout=timeout)


LEVELS: dict[int, dict] = {
    0: {"agent": None, "llm": True},
    1: {"agent": "level1_hello:HelloAgent"},
    2: {"agent": "level2_rules:RulesAgent"},
    3: {"agent": "level3_llm_coach:CoachAgent", "llm": True},
    4: {"agent": "level4_tools:ToolCoachAgent", "llm": True},
    5: {"agent": "level5_deal_coach:DealCoach", "llm": True, "proactive": True},
    6: {"agent": "level6_guided:GuidedAgent"},
    7: {"agent": "level7_asking:AskingCoach", "llm": True, "proactive": True},
    8: {"agent": "level8_spotlight:SpotlightAgent"},
    9: {"agent": "level9_panels:PanelAgent"},
    10: {"agent": "level10_toolsmith:ToolsmithAgent"},
    11: {"agent": "level11_interface:InterfaceAgent"},
}


def take_level(browser, level: int) -> None:
    spec = LEVELS[level]
    assistant: dict = {"autonomy": "suggest"}
    if spec.get("agent"):
        assistant["agent_class"] = spec["agent"]
    if spec.get("proactive"):
        assistant["proactive"] = {"on_action_requested": True}
    with server([], assistant=assistant, extra_env={"PYTHONPATH": str(TUTORIAL)}) as url:
        ctx, page = new_page(browser, url)
        page.goto("/play")
        if level == 7:
            start(page)
            expect(page.get_by_text("How should I help you").first).to_be_visible(timeout=30000)
            settle(page)
            save(page, "tutorial-level7")
            page.get_by_role("button", name="Balanced", exact=True).click()
            my_turn(page)
            assistant_idle(page)
            settle(page)
            save(page, "tutorial-level7-advice")
        elif level == 9:
            start(page)
            expect(page.get_by_text("How do you want to work?").first).to_be_visible()
            settle(page)
            save(page, "tutorial-level9-welcome")
            page.get_by_role("button", name="Show me everything").click()
            my_turn(page)
            expect(page.get_by_text("best offers for you").first).to_be_visible()
            settle(page)
            save(page, "tutorial-level9")
        elif level == 11:
            start(page)
            expect(page.get_by_text("How should your screen look?").first).to_be_visible(timeout=30000)
            settle(page)
            save(page, "tutorial-level11-welcome")
            page.get_by_role("button", name="No tools", exact=True).click()
            my_turn(page)
            hide_toasts(page)
            settle(page)
            save(page, "tutorial-level11-bare")
            for choice in ("Simple", "Offers as sentences", "Calm colours"):
                page.get_by_role("button", name=choice, exact=True).click()
                settle(page, 500)
            play(page, 1)
            hide_toasts(page)
            settle(page, 1500)
            save(page, "tutorial-level11-styled")
        elif level == 6:
            start(page)
            open_assistant(page)
            settle(page, 1500)
            save(page, "tutorial-level6")
            play(page, 2)
            settle(page, 1500)
            save(page, "tutorial-level6-back")
        elif level == 5:
            start(page)
            my_turn(page)
            expect(page.locator(TOASTS + " > div").first).to_be_visible(timeout=120000)  # the recommendation
            settle(page)
            save(page, "tutorial-level5")
        elif level in (8, 10):
            start(page)
            play(page, 1)
            settle(page, 2500)
            if level == 8:
                hl = page.locator(".hl-pulse, .hl-glow, .hl-spotlight").first
                hl.wait_for(timeout=30000)
                hl.evaluate("(el) => el.scrollIntoView({block: 'center'})")
                settle(page, 800)
            save(page, f"tutorial-level{level}")
        else:
            start(page)
            my_turn(page)
            open_assistant(page)
            question = {0: "What do you think of this offer?", 1: "hi", 2: "What do you think?",
                        3: "What do you think of this offer?", 4: "Should I accept?"}[level]
            chat(page, question, "You said: hi" if level == 1 else None)
            dock = page.get_by_role("complementary", name="Assistant")
            for _ in range(2):  # a small model sometimes writes a function call as text: ask again
                if not dock.get_by_text("[tool call").count():
                    break
                chat(page, question)
            settle(page)
            save(page, f"tutorial-level{level}")
        ctx.close()


def take_popup(browser) -> None:
    """The simple view: the Utility Bar opened from the offer area in a popup, a part of the bar
    dragged out and a deal picked into the counter-offer."""
    with server([], env_json={"negotiation": {"n_steps": 12, "time_limit": None}}) as url:
        ctx, page = new_page(browser, url)
        page.goto("/play?view=simple")
        start(page)
        play(page, 2)
        hide_toasts(page)
        page.get_by_test_id("launch-generator").click()
        pop = page.get_by_test_id("tool-popup")
        bar = pop.get_by_test_id("range-bar-area")
        expect(bar).to_be_visible()
        pop.locator("select").first.select_option(label="Up to 10 offers")
        box = bar.bounding_box()
        y = box["y"] + box["height"] / 2
        page.mouse.move(box["x"] + box["width"] * 0.5, y)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] * 0.85, y, steps=6)
        page.mouse.up()
        expect(pop.locator("tbody tr").first).to_be_visible()
        pop.locator("tbody tr").nth(1).click()
        settle(page)
        save(page, "tool-popup")
        ctx.close()


# --------------------------------------------------------------------------- #
# The app: login, the negotiation page in each view and device, the console    #
# --------------------------------------------------------------------------- #
#: The opponent of the walkthrough screenshots: it concedes steadily, so deals become possible.
WALK_OPPONENT = "LinearTBNegotiator"
WALK_ENV = {"negotiation": {"n_steps": 20, "time_limit": None}}
END = re.compile(r"^End\b")


def set_view(page, name: str) -> None:
    """Switch the view with the header's layout menu."""
    page.get_by_role("button", name="Layout").click()
    page.get_by_role("button", name=re.compile(rf"^{name}:")).click()
    settle(page, 800)


def take_app(browser, use_llm: bool) -> None:
    # a tough opponent, so that the negotiation is still running in every shot
    with server(["--assistant", f"{ASSISTANT}:DocsAssistant"], env_json=WALK_ENV) as url:
        ctx, page = new_page(browser, url)
        page.goto("/")
        expect(page.get_by_role("button", name="Log in")).to_be_visible()
        settle(page)
        save(page, "login")
        login(page, "user", "userpass")
        page.goto("/app")
        start(page)
        play(page, 3)
        hide_toasts(page)
        settle(page)
        save(page, "app-overview")  # the simple view, the default
        set_view(page, "Full")
        settle(page, 1500)
        save(page, "app-full-view")
        ctx.close()

        for name, vp, extra in [
            ("tablet-landscape", {"width": 1180, "height": 820}, None),
            ("tablet-portrait", {"width": 820, "height": 1180}, "tray"),
            ("mobile", {"width": 390, "height": 844}, None),
        ]:
            ctx, page = new_page(browser, url, viewport=vp, scale=2, is_mobile=True, has_touch=True)
            page.goto("/play")
            page.get_by_role("button", name="Start negotiation").click()
            page.wait_for_timeout(2500)
            # the start reveals the Preferences: in the Tools tab on phones, in the tray on tablets
            if page.get_by_role("button", name="Negotiate", exact=True).count():
                page.get_by_role("button", name="Negotiate", exact=True).click()
            tray = page.locator("[data-region=tools] > button[aria-expanded]")
            if tray.count() and tray.get_attribute("aria-expanded") == "true":
                tray.click()
            play(page, 2)
            hide_toasts(page)
            if extra == "tray":
                tray.click()
            settle(page, 1200)
            save(page, name)
            ctx.close()

        ctx, page = new_page(browser, url)
        login(page, "admin", "adminpass")
        for name, frag, wait in [("admin", "opponents", "Opponents"), ("admin-agent", "assistant", "Who gets the Assistant")]:
            page.goto(f"/admin#{frag}")
            expect(page.get_by_text(wait).first).to_be_visible()
            settle(page, 1500)
            save(page, name)
        ctx.close()

    # the example tools of the "Build a tool" tutorial, in the simple view next to the offer area
    env = {**WALK_ENV, "tools": {"paths": [str(EXAMPLE_TOOLS)]}}
    with server(["--no-assistant"], env_json=env, opponent=WALK_OPPONENT) as url:
        ctx, page = new_page(browser, url)
        page.goto("/play")
        start(page)
        play(page, 2)
        hide_toasts(page)
        tab(page, "What If").first.click()
        settle(page)
        save(page, "tools-whatif")
        if use_llm:
            tab(page, "Summary").first.click()
            page.get_by_role("button", name="Summarise", exact=True).click()
            expect(page.get_by_text("Press Summarise once a few offers have been made.")).to_have_count(0, timeout=120000)
            expect(page.get_by_role("button", name="Summarise", exact=True)).to_be_visible(timeout=120000)
            settle(page)
            save(page, "tools-summary")
        ctx.close()


# --------------------------------------------------------------------------- #
# Walkthrough: negotiating against an AI opponent (HAN)                        #
# --------------------------------------------------------------------------- #
def pick_options(page, n: int = 2) -> None:
    """Change ``n`` issues of the counter-offer: the second option of each of the first issues."""
    editor = page.locator("[data-region=dock]")
    groups = editor.locator("[role=radiogroup], fieldset")
    for i in range(min(n, groups.count())):
        opts = groups.nth(i).get_by_role("radio").or_(groups.nth(i).get_by_role("button"))
        if opts.count() > 1:
            opts.nth(1).click()
            page.wait_for_timeout(300)


def take_walk_han(browser) -> None:
    with server(["--no-assistant"], env_json=WALK_ENV, opponent=WALK_OPPONENT) as url:
        ctx, page = new_page(browser, url)
        page.goto("/play")
        expect(page.get_by_role("button", name="Start negotiation")).to_be_visible()
        settle(page, 1500)
        save(page, "walk-han-start")
        start(page)
        my_turn(page)
        hide_toasts(page)
        settle(page, 1500)
        save(page, "walk-han-first-offer")
        save(page.get_by_role("banner"), "walk-han-header")
        page.get_by_role("button", name="Counter-offer").click()
        pick_options(page, 2)
        box = page.get_by_placeholder(re.compile("Explain your offer"))
        box.fill("I can pay a little more if the deposit is lower.")
        settle(page)
        save(page, "walk-han-counter")
        page.get_by_role("button", name="Send offer").click()
        play(page, 3)
        hide_toasts(page)
        settle(page)
        save(page, "walk-han-history")
        page.get_by_role("button", name=END).first.click()
        expect(page.get_by_role("button", name="End negotiation")).to_be_visible()
        settle(page, 600)
        save(page, "walk-han-end-confirm")
        page.keyboard.press("Escape")
        expect(page.get_by_role("button", name="End negotiation")).to_have_count(0)
        my_turn(page).click()
        expect(page.get_by_role("button", name="Accept offer")).to_be_visible()
        settle(page, 600)
        save(page, "walk-han-accept-confirm")
        page.get_by_role("button", name="Accept offer").click()
        expect(page.get_by_text("Agreement reached").first).to_be_visible()
        settle(page, 1200)
        save(page, "walk-han-agreement")
        ctx.close()

        # the advanced part: the Utility Bar, the Tools menu, the settings, the views
        ctx, page = new_page(browser, url)
        page.goto("/play")
        start(page)
        play(page, 2)
        hide_toasts(page)
        page.get_by_test_id("launch-tools").click()
        settle(page, 600)
        save(page, "walk-han-tools-menu")
        page.keyboard.press("Escape")
        page.get_by_role("button", name="Layout").click()
        settle(page, 600)
        save(page, "walk-han-layout-menu")
        page.keyboard.press("Escape")
        page.get_by_role("button", name="My settings").click()
        toggle = page.get_by_text("Colour the utility bars by issue").first
        expect(toggle).to_be_visible()
        settle(page, 600)
        save(page, "walk-han-settings")
        toggle.click()
        settle(page, 600)
        page.keyboard.press("Escape")
        settle(page, 600)
        play(page, 1)
        hide_toasts(page)
        settle(page, 1200)
        save(page, "walk-han-by-issue")
        set_view(page, "Focus")
        settle(page, 800)
        save(page, "walk-han-focus")
        ctx.close()


# --------------------------------------------------------------------------- #
# Walkthrough: negotiating with the Assistant (HI)                             #
# --------------------------------------------------------------------------- #
LLM_ASSISTANT = f"{ASSISTANT}:LLMDocsAssistant"


def take_walk_hi(browser, use_llm: bool) -> None:
    env = {**WALK_ENV, "playground": {"choices": {"scenario": True, "opponent": [
        "LinearTBNegotiator", "BoulwareTBNegotiator", "ConcederTBNegotiator"]}}}
    with server(["--assistant", LLM_ASSISTANT], env_json=env, opponent=WALK_OPPONENT) as url:
        ctx, page = new_page(browser, url)
        page.goto("/play")
        expect(page.get_by_role("button", name="Start negotiation")).to_be_visible()
        settle(page, 1500)
        save(page, "walk-hi-start")
        if page.get_by_role("button", name=re.compile("Different scenario|Choose")).count():
            page.get_by_role("button", name=re.compile("Different scenario|Choose")).first.click()
            settle(page, 800)
        if page.get_by_test_id("choice-pickers").count():
            save(page.get_by_test_id("choice-pickers"), "walk-hi-choices")
        start(page)
        my_turn(page)
        hide_toasts(page)
        open_assistant(page)
        settle(page, 1200)
        save(page, "walk-hi-assistant-open")
        if use_llm:
            chat(page, "I have never negotiated before. What does the offer on the table mean for me?")
            settle(page)
            save(page, "walk-hi-assistant")
        btn = page.get_by_role("banner").get_by_role("button", name="Assistant", exact=True)
        if btn.get_attribute("aria-pressed") == "true":
            btn.click()  # close it: on screens under 1600 px it covers the tools
            settle(page, 600)
        tab(page, "Negotiation Plot").first.click()
        settle(page, 1500)
        save(page, "walk-hi-estimate")
        open_assistant(page)
        page.get_by_role("button", name="Assistant settings").click()
        expect(page.get_by_text("How much may the assistant do?")).to_be_visible()
        settle(page, 800)
        save(page, "walk-hi-assistant-settings")
        ctx.close()

    # the Assistant opens in the tool area, in the open tool's place
    with server(["--assistant", LLM_ASSISTANT], env_json=WALK_ENV, opponent=WALK_OPPONENT,
                assistant={"presentation": {"place": "tools"}}) as url:
        ctx, page = new_page(browser, url)
        page.goto("/play")
        start(page)
        my_turn(page)
        hide_toasts(page)
        open_assistant(page)
        settle(page, 1500)
        save(page, "walk-hi-assistant-in-tools")
        ctx.close()

    # a game against people: the person / AI choice, waiting, and two people negotiating
    env = {"negotiation": {"n_steps": 12, "time_limit": 600, "human_opponent_choice": True,
                           "human_opponents_first": True, "human_opponent_wait": 0}}
    with server(["--assistant", LLM_ASSISTANT], env_json=env,
                opponent=f"human+assistant,{WALK_OPPONENT}") as url:
        (ca, a), (cb, b) = new_page(browser, url), new_page(browser, url)
        try:
            a.goto("/play")
            expect(a.get_by_test_id("opponent-choice")).to_be_visible()
            settle(a, 1200)
            save(a, "walk-hi-person-or-ai")
            a.get_by_role("button", name=re.compile(r"^Play a person")).click()
            a.get_by_role("button", name="Start negotiation").click()
            expect(a.get_by_text("Waiting for the other participant…").first).to_be_visible()
            settle(a, 1200)
            save(a, "walk-hi-waiting")
            b.goto("/play")
            expect(b.get_by_test_id("opponent-choice")).to_be_visible()
            expect(b.get_by_test_id("people-waiting")).to_be_visible()
            settle(b, 800)
            save(b.get_by_test_id("opponent-choice"), "walk-hi-people-waiting")
            b.get_by_role("button", name=re.compile(r"^Play a person")).click()
            b.get_by_role("button", name="Start negotiation").click()
            # one of the two moves first
            mover = None
            for _ in range(300):
                for p in (a, b):
                    s = p.get_by_role("button", name="Send offer")
                    if s.count() and s.is_enabled():
                        mover = p
                if mover:
                    break
                a.wait_for_timeout(100)
            other = b if mover is a else a
            box = mover.get_by_placeholder(re.compile("Explain your offer"))
            if box.count():
                box.fill("Hello! Let us find a deal that works for both of us.")
            mover.get_by_role("button", name="Send offer").click()
            expect(other.get_by_role("button", name=ACCEPT).first).to_be_enabled(timeout=30000)
            hide_toasts(other)
            settle(other, 1500)
            save(other, "walk-hi-person-offer")
        finally:
            ca.close()
            cb.close()


GROUPS = ("tools", "popup", "character", "app", "han", "hi", "tutorial")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", nargs="*", default=[*GROUPS],
                    help=f"any of {', '.join(GROUPS)} (default: all)")
    ap.add_argument("--level", type=int, action="append", help="only these tutorial levels")
    ap.add_argument("--no-llm", action="store_true", help="skip the screenshots that need a language model")
    a = ap.parse_args()
    use_llm = not a.no_llm and llm_available()
    if not use_llm:
        log("no local qwen3:4b-instruct on Ollama (or --no-llm): skipping the screenshots that need a model")
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            if "tools" in a.what:
                take_tools(browser, use_llm)
            if "popup" in a.what:
                take_popup(browser)
            if "character" in a.what:
                take_character(browser)
            if "app" in a.what:
                take_app(browser, use_llm)
            if "han" in a.what:
                take_walk_han(browser)
            if "hi" in a.what:
                take_walk_hi(browser, use_llm)
            if "tutorial" in a.what:
                for level in a.level or sorted(LEVELS):
                    if LEVELS[level].get("llm") and not use_llm:
                        log(f"skipping tutorial level {level} (needs a model)")
                        continue
                    log(f"tutorial level {level}")
                    take_level(browser, level)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
