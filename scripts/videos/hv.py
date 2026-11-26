"""Shared helpers for the walkthrough videos (``scripts/videos/film_*.py``).

The films are recorded with the ``demo-video`` toolkit (``dv.py``: Kokoro narration, a 1920x1080
stage recorded by Playwright, ffmpeg assembly). This module adds what the HANI2 films need:

- a HANI2 server on a fresh home (the same helper the documentation screenshots use);
- one wide window whose page is laid out at a desktop width (``pane``);
- drags inside a window (``drag``) and typing into a field (``type_into``);
- subtitles (``.srt``) and YouTube chapters written from the film's cue log.

Run a film from the repository root (see ``scripts/videos/README.md``)::

    uv run --with kokoro-onnx==0.6.1 --with numpy --with playwright \
        python scripts/videos/film_han_basics.py
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "screenshots"))
DV = Path(os.environ.get("HANI2_DV", Path.home() / ".claude" / "skills" / "demo-video" / "scripts"))
sys.path.insert(0, str(DV))
# the films run under `uv run --with kokoro-onnx ...`; the servers use the project's environment
if (ROOT / ".venv" / "bin" / "python").exists():
    os.environ.setdefault("HANI2_PYTHON", str(ROOT / ".venv" / "bin" / "python"))

import make_screenshots as shots
from dv import NEC, Film

#: Where the films go (large files, outside git).
VIDEOS = Path(os.environ.get("HANI2_VIDEOS", Path.home() / "negmas" / "hani2-videos"))
#: Spoken respellings; the captions keep the written form.
SAY_MAP = {"HANI2": "Hanny two", "HAN": "han", "HI": "H I", "AI": "A I", "Kokoro": "Kokoro",
           "0%": "zero percent", "100%": "one hundred percent", "e.g.": "for example"}
BRAND = "HANI2 <b>·</b> WALKTHROUGH"


def server(*args, **kw):
    """A HANI2 server on a fresh home (see ``make_screenshots.server``); yields its base URL."""
    return shots.server(*args, **kw)


_STAGE_URL: str | None = None


def _stage_url() -> str:
    """The stage page over http://127.0.0.1 (a file:// stage makes the app's iframe cross-site, and
    the browser then drops the app's SameSite=Lax session cookie)."""
    global _STAGE_URL
    if _STAGE_URL is None:
        import functools
        import http.server
        import threading

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DV))
        handler.log_message = lambda *a, **k: None  # type: ignore[attr-defined]
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        _STAGE_URL = f"http://127.0.0.1:{httpd.server_address[1]}/stage.html"
    return _STAGE_URL


class HaniFilm(Film):
    """A Film whose stage is served over http on 127.0.0.1, so the app's pages keep their session."""

    def __enter__(self):
        import time

        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        W, H = self.size
        args = ["--hide-scrollbars", f"--window-size={W},{H}"]
        try:
            self.browser = self._pw.chromium.launch(channel="chrome", headless=self.headless, args=args)
        except Exception:  # noqa: BLE001
            self.browser = self._pw.chromium.launch(headless=self.headless, args=args)
        rec = self.out / "rec"
        rec.mkdir(exist_ok=True)
        for old in rec.glob("*.webm"):
            old.unlink()
        self.ctx = self.browser.new_context(viewport={"width": W, "height": H}, screen={"width": W, "height": H},
                                            record_video_dir=str(rec), record_video_size={"width": W, "height": H})
        self.ctx.add_init_script(self._init_script())
        self.t0 = time.monotonic()
        self.page = self.ctx.new_page()
        self.page.goto(_stage_url())
        self.sleep(0.6)
        return self


def film(name: str) -> Film:
    """A Film whose work files go to ``VIDEOS/work/<name>``."""
    out = VIDEOS / "work" / name
    return HaniFilm(out, voice="af_heart", say_map=SAY_MAP, brand=BRAND, headless="--show" not in sys.argv)


def pane(f: Film, pid: str, url: str, name: str = "HANI2", sub: str = "", color: str = NEC["bright"],
         base: int = 1280) -> None:
    """One window in the middle of the stage, its page laid out ``base`` px wide (desktop layout)."""
    f.panes([{"id": pid, "name": name, "sub": sub, "url": url, "color": color}])
    _rebase(f, base)


def panes2(f: Film, specs: list[dict], base: int = 1024) -> None:
    """Two windows side by side, each laid out ``base`` px wide (desktop layout from 1024 px)."""
    f.panes(specs)
    _rebase(f, base)


def _rebase(f: Film, base: int) -> None:
    f.page.evaluate(
        """(base) => document.querySelectorAll('.win').forEach(w => {
            const f = w.querySelector('iframe'); const W = w.getBoundingClientRect().width;
            const H = w.getBoundingClientRect().height; const sc = W / base;
            f.style.width = base + 'px'; f.style.height = ((H - 38) / sc) + 'px'; f.style.transform = `scale(${sc})`;
        })""", base)
    f.sleep(0.8)


def prewarm(f: Film, texts) -> None:
    """Synthesize every narration line before the recording starts (cached on disk), so the picture
    never stands still while the voice is generated."""
    for t in texts:
        f.tts(t)


def narration(module_globals: dict) -> list[str]:
    """Every narration line of a film: the string values of its ``N`` dict."""
    return [v for v in module_globals["N"].values() if isinstance(v, str)]


#: CSS selectors of the negotiation page (inside a window).
START = "button:has-text('Start negotiation')"
ACCEPT_ON = "button.btn-success:not([disabled]):not(:has-text('Accept offer'))"
COUNTER = "button:has-text('Counter-offer')"
SEND = "button:has-text('Send offer')"
END_BTN = "button.btn-danger:not(:has-text('negotiation'))"
MESSAGE = "textarea[placeholder^='Explain']"
CONFIRM_ACCEPT = "button:has-text('Accept offer')"
CONFIRM_END = "button:has-text('End negotiation')"
CANCEL = "button:has-text('Cancel')"


def tab(name: str) -> str:
    return f"[role=tab]:has-text('{name}')"


def option(issue: str, n: int) -> str:
    """The ``n``-th option (1-based) of an issue in the counter-offer editor."""
    return f"[role=radiogroup][aria-label='{issue}'] > :nth-child({n})"


def my_turn(f: Film, pid: str, timeout: float = 90) -> None:
    """Block until it is the participant's turn (Accept is enabled)."""
    wait_for(f, pid, ACCEPT_ON, timeout)


def wait_for(f: Film, pid: str, selector: str, timeout: float = 60) -> None:
    """Block (recording) until the element is visible in the window."""
    f.loc(pid, selector).wait_for(state="visible", timeout=int(timeout * 1000))


def drag(f: Film, pid: str, selector: str, x0: float, x1: float, y: float = 0.5, steps: int = 18) -> None:
    """Drag across the element from fraction ``x0`` to ``x1`` of its width, with the stage cursor following."""
    loc = f.loc(pid, selector)
    loc.wait_for(state="visible", timeout=20000)
    r = f.rect(pid, loc)
    yy = r["y"] + r["height"] * y
    xa, xb = r["x"] + r["width"] * x0, r["x"] + r["width"] * x1
    f.js("cursor", xa, yy)
    f.sleep(0.8)
    m = f.page.mouse
    m.move(xa, yy)
    m.down()
    for i in range(1, steps + 1):
        x = xa + (xb - xa) * i / steps
        m.move(x, yy)
        f.js("cursor", x, yy)
        f.sleep(0.04)
    m.up()
    f.sleep(0.5)


def type_into(f: Film, pid: str, selector: str, text: str, delay: float = 0.03) -> None:
    """Glide to a field, click it and type ``text`` letter by letter."""
    f.click(pid, selector)
    loc = f.loc(pid, selector)
    loc.press_sequentially(text, delay=int(delay * 1000))
    f.sleep(0.3)


def hide(f: Film, pid: str, css: str) -> None:
    """Add CSS to the page in a window (for example to hide toasts that would cover a target)."""
    with contextlib.suppress(Exception):
        f.frame(pid).add_style_tag(content=css)


# --------------------------------------------------------------------------- #
# Subtitles and chapters                                                       #
# --------------------------------------------------------------------------- #
def _ts(t: float, sep: str = ",") -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _chunks(text: str, limit: int = 84) -> list[str]:
    """Split a narration line into subtitle-sized pieces at sentence or clause ends."""
    parts = re.split(r"(?<=[.!?;:])\s+", text.strip())
    out: list[str] = []
    for p in parts:
        while len(p) > limit:
            cut = p.rfind(", ", 0, limit)
            cut = cut + 1 if cut > limit // 3 else p.rfind(" ", 0, limit)
            out.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            out.append(p)
    return out


def write_srt(out: Path, srt: Path) -> None:
    """Subtitles from ``cues.json``: each cue split into pieces timed by their length."""
    cues = json.loads((out / "cues.json").read_text())["cues"]
    lines, n = [], 0
    for c in cues:
        pieces = _chunks(c["text"])
        total = sum(len(p) for p in pieces) or 1
        t = c["t"]
        for p in pieces:
            d = c["dur"] * len(p) / total
            n += 1
            lines += [str(n), f"{_ts(t)} --> {_ts(t + d)}", p, ""]
            t += d
    srt.write_text("\n".join(lines), encoding="utf-8")


def write_chapters(out: Path, path: Path) -> list[tuple[str, float]]:
    """YouTube chapters from the film's marks (``f.mark("Title")``); the first is moved to 0:00."""
    meta = json.loads((out / "cues.json").read_text())
    marks = [(n, float(t)) for n, t in meta["marks"]]
    if not marks or marks[0][1] > 0:
        marks = [("Introduction", 0.0), *marks] if not marks or marks[0][1] > 5 else [(marks[0][0], 0.0), *marks[1:]]
    marks[0] = (marks[0][0], 0.0)
    # YouTube wants every chapter to last at least 10 s: a shorter one joins the chapter before it
    length = float(meta.get("length") or marks[-1][1] + 10)
    kept: list[tuple[str, float]] = []
    for i, (n, t) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else length
        if kept and end - t < 10:
            continue
        kept.append((n, t))
    marks = kept
    text = []
    for n, t in marks:
        m, s = divmod(int(t), 60)
        text.append(f"{m}:{s:02d} {n}")
    path.write_text("\n".join(text) + "\n", encoding="utf-8")
    return marks


def finish(f: Film, name: str) -> Path:
    """Assemble the mp4 and write its .srt and chapters next to it; returns the mp4's path."""
    VIDEOS.mkdir(parents=True, exist_ok=True)
    mp4 = VIDEOS / f"{name}.mp4"
    f.assemble(mp4)
    write_srt(f.out, mp4.with_suffix(".srt"))
    write_chapters(f.out, mp4.with_suffix(".chapters.txt"))
    print("wrote", mp4, mp4.with_suffix(".srt"), mp4.with_suffix(".chapters.txt"))
    return mp4


@contextlib.contextmanager
def trial_server(*, assistant: bool = True, time_limit: int = 900, scenario: str = "Lease",
                 assistant_settings: dict | None = None):
    """``hani2 human-trial`` on a fresh home; yields the two participants' URLs (A, B).

    The links point at 127.0.0.1, like the stage, so the pages keep their session cookies."""
    import shutil
    import socket
    import subprocess
    import tempfile
    import time
    import urllib.request

    home = Path(tempfile.mkdtemp(prefix="hani2-film-trial-"))
    py = os.environ.get("HANI2_PYTHON", sys.executable)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("HANI2_", "PROLIFIC_", "SCMLWEB_"))}
    env.update(HANI2_HOME=str(home), PYTHONUNBUFFERED="1")
    subprocess.run([py, "-m", "hani2.cli", "setup"], env=env, check=True, capture_output=True)
    (home / "settings" / "scenario_order.txt").write_text(scenario + "\n", encoding="utf-8")
    if assistant_settings:
        p = home / "settings" / "assistant_settings.json"
        cur = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        p.write_text(json.dumps({**cur, **assistant_settings}, indent=2), encoding="utf-8")
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    log = (home / "trial.log").open("w")
    args = [py, "-m", "hani2.cli", "human-trial", "--no-browser", "--home", str(home), "--port", str(port),
            "--time-limit", str(time_limit), "--assistant" if assistant else "--no-assistant"]
    proc = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        links: list[str] = []
        for _ in range(600):
            text = (home / "trial.log").read_text(encoding="utf-8", errors="replace")
            links = re.findall(r"Participant [AB]\s+(\S+)", text)
            if len(links) == 2:
                try:
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=1)
                    break
                except OSError:
                    pass
            if proc.poll() is not None:
                raise RuntimeError("human-trial did not start:\n" + text[-3000:])
            time.sleep(0.25)
        yield tuple(u.replace("//localhost:", "//127.0.0.1:") for u in links)
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()
        shutil.rmtree(home, ignore_errors=True)


ASSISTANT_PANEL = "aside[aria-label='Assistant']"


def ask(f: Film, pid: str, question: str, timeout: float = 180) -> None:
    """Type a question to the Assistant, send it and block until it has answered."""
    box = f"{ASSISTANT_PANEL} textarea"
    type_into(f, pid, box, question, delay=0.025)
    f.click(pid, f"{ASSISTANT_PANEL} button[aria-label='Send']")
    f.sleep(1.5)
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if not f.frame(pid).locator(f"{ASSISTANT_PANEL} [aria-label='The assistant is working']").count():
            break
        f.sleep(0.5)
    f.sleep(0.8)
