"""Isolated Assistants: the Assistant's class runs in a worker process of its own.

An Assistant written by a participant is untrusted code. In the server process it could read
everything the server holds: other sessions (``hub.sessions``), the match and the other
participant, the scenario with both utility functions, files of other participants. With the
setting ``assistant_isolation: process`` (``negotiation`` in env.json, any layer; or the environment
variable ``HANI2_ASSISTANT_ISOLATION=process``) the session runs an :class:`IsolatedAssistant`
instead: a stock Assistant on the server side, and the participant's class in a separate Python
process (:mod:`hani2.support_agent.worker`).

The two talk over pipes, in JSON only. The worker's Assistant has no session object. Whatever it
does goes through the stock Assistant's methods and functions on the server (``context()``,
``post()``, the language-model functions of :class:`~hani2.support_agent.tools.ToolDispatcher`,
``use_tool()``…), so capabilities, the information split (what only the participant knows), the
recording and the attribution apply exactly as for an Assistant in the server. Its language-model
calls are made by the server too (``complete``): the worker has no API keys.

The worker runs

- from an empty temporary folder that is also its ``HOME`` and ``TMPDIR``, with a scrubbed
  environment (no keys, no ``HANI2_*``), ``python -I``;
- with resource limits (CPU seconds, memory on Linux, file size, open files);
- inside an operating-system sandbox when one is available (``assistant_sandbox``): macOS
  ``sandbox-exec``, Linux ``bwrap`` (bubblewrap). The sandbox hides the server user's home folder,
  HANI2's home, the server's folder, other code folders on ``sys.path`` and other workers' folders,
  except what the worker needs (Python, the installed packages, HANI2's own package and the
  Assistant's own code); and it cuts the network unless ``assistant_network`` is true.

It fails closed: an Assistant that cannot be started isolated (no sandbox while one is required,
a crash, a timeout) leaves the session without an Assistant, never with an in-process one.
"""

from __future__ import annotations

import contextlib
import importlib.machinery
import itertools
import json
import os
import shutil
import site
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
import traceback
import uuid
import weakref
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING, Any

from hani2.support_agent.capabilities import Capability
from hani2.support_agent.runtime import SupportAgent
from hani2.support_agent.tools import ToolDispatcher
from hani2.support_agent.worker import FORWARDED

if TYPE_CHECKING:  # pragma: no cover
    from hani2.session import NegotiationSession

ENV_VAR = "HANI2_ASSISTANT_ISOLATION"
MODES = ("none", "process")
SANDBOXES = ("auto", "required", "off")
#: the most one protocol line may carry (a bigger one ends the worker)
MAX_LINE = 16 * 1024 * 1024
_WORKERS: "weakref.WeakSet[IsolatedAssistant]" = weakref.WeakSet()
_ids = itertools.count(1)


# --------------------------------------------------------------------------- #
# Settings                                                                    #
# --------------------------------------------------------------------------- #
def _pref(session: Any, key: str, default: Any) -> Any:
    try:
        v = (getattr(session, "admin_prefs", None) or {}).get(key, default)
    except Exception:  # noqa: BLE001
        v = default
    return default if v is None else v


def mode(session: Any) -> str:
    """``process`` or ``none``. The study's settings (``negotiation.assistant_isolation``) or the
    environment variable decide, never the page or a group file; the environment variable can only
    make it stricter."""
    env = (os.environ.get(ENV_VAR) or "").strip().lower()
    if env == "process":
        return "process"
    v = str(_pref(session, "assistant_isolation", "none") or "none").strip().lower()
    return "process" if v == "process" else "none"


def trusted(spec: str | None) -> bool:
    """Whether ``spec`` is one of HANI2's own Assistants (``hani2.…``), which may run in the server."""
    s = str(spec or "").strip()
    return s == "" or s.startswith(("hani2.", "hani2:"))


def config(session: Any) -> dict[str, Any]:
    sb = str(_pref(session, "assistant_sandbox", "auto") or "auto").strip().lower()
    return {
        "sandbox": sb if sb in SANDBOXES else "auto",
        "network": bool(_pref(session, "assistant_network", False)),
        "start_timeout": float(_pref(session, "assistant_start_timeout", 90)),
        "call_timeout": float(_pref(session, "assistant_call_timeout", 600)),
        "limits": {"cpu_seconds": int(_pref(session, "assistant_cpu_seconds", 3600)),
                   "memory_mb": int(_pref(session, "assistant_memory_mb", 2048)),
                   "file_mb": 64, "open_files": 256},
    }


# --------------------------------------------------------------------------- #
# Where the Assistant's code is                                               #
# --------------------------------------------------------------------------- #
def _module_and_attr(spec: str) -> tuple[str, str]:
    if ":" in spec:
        mod, _, attr = spec.rpartition(":")
    else:
        mod, _, attr = spec.rpartition(".")
    return mod, attr


def code_location(spec: str, syspath: list[str]) -> tuple[list[str], list[str]]:
    """``(syspath, own)``: the folders the worker adds to ``sys.path`` and the paths of the Assistant's
    own code (what the sandbox lets it read). Found without importing anything."""
    mod, _ = _module_and_attr(spec)
    if mod.endswith(".py"):
        f = Path(mod).expanduser().resolve()
        return [], [str(f.parent)]
    top = mod.split(".")[0]
    search = [d for d in syspath if d] + [p for p in sys.path if p]
    found = importlib.machinery.PathFinder.find_spec(top, search) if top else None
    if found is None:
        return list(syspath), []
    if found.submodule_search_locations:  # a package: its folder
        locs = [str(Path(x).resolve()) for x in found.submodule_search_locations]
        roots = [str(Path(x).parent) for x in locs]
    elif found.origin:
        locs = [str(Path(found.origin).resolve())]
        roots = [str(Path(found.origin).resolve().parent)]
    else:  # pragma: no cover - namespace oddities
        return list(syspath), []
    return list(dict.fromkeys(list(syspath) + roots)), locs


def assistant_syspath(session: Any, choice: Any) -> list[str]:
    """The ``syspath`` of the group file the Assistant came from (when it came from one)."""
    from hani2 import groups

    out: list[str] = []
    key = str(getattr(choice, "group", "") or "")
    if key:
        for kind in (groups.OPPONENT, groups.ASSISTANT):
            try:
                g = groups.find_file(kind, key, session.study_ref)
            except Exception:  # noqa: BLE001
                g = None
            if g is not None:
                out += list(g.syspath)
    return list(dict.fromkeys(out))


# --------------------------------------------------------------------------- #
# The sandbox                                                                 #
# --------------------------------------------------------------------------- #
def _runtime_paths() -> list[str]:
    """What any worker must read: Python itself, the installed packages and HANI2's own package."""
    import hani2

    paths = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix,
             str(Path(os.path.realpath(sys.executable)).parent.parent)}
    for k in ("stdlib", "platstdlib", "purelib", "platlib"):
        p = sysconfig.get_paths().get(k)
        if p:
            paths.add(p)
    with contextlib.suppress(Exception):
        paths.update(site.getsitepackages())
    paths.add(str(Path(hani2.__file__).resolve().parent))
    paths.update(_link_chain(sys.executable))
    with contextlib.suppress(OSError):  # a virtual environment's base interpreter
        for line in (Path(sys.prefix) / "pyvenv.cfg").read_text().splitlines():
            k, _, v = line.partition("=")
            if k.strip() == "home" and v.strip():
                paths.update(_link_chain(v.strip()))
    return sorted(p for p in paths if p)


def _link_chain(path: str) -> set[str]:
    """``path`` and every symbolic link on the way to what it names (each must be readable to be followed)."""
    out: set[str] = set()
    todo, seen = [os.path.abspath(path)], set()
    while todo:
        p = todo.pop()
        if p in seen or len(seen) > 64:
            continue
        seen.add(p)
        cur = Path(p)
        for a in [cur, *cur.parents]:
            if a.is_symlink():
                out.add(str(a))
                t = os.readlink(a)
                todo.append(os.path.normpath(os.path.join(str(a.parent), t)))
        out.add(str(cur.parent if cur.is_file() or cur.is_symlink() else cur))
        out.add(os.path.realpath(p) if os.path.isdir(p) else os.path.dirname(os.path.realpath(p)))
    return out


def _hidden_paths(workroot: str) -> list[str]:
    """What the sandbox hides: the server user's home, HANI2's home, the server's folder, other code on
    ``sys.path`` (other participants' agents), and the folder of all workers."""
    from hani2 import config as cfg

    out = {str(Path.home()), str(cfg.home()), os.getcwd(), workroot}
    with contextlib.suppress(Exception):
        out.add(str(cfg.settings_dir()))
    with contextlib.suppress(Exception):
        out.add(str(cfg.results_root()))
    runtime = _runtime_paths()
    for p in sys.path:
        if p and os.path.isdir(p) and not any(_under(p, r) for r in runtime):
            out.add(p)
    real = {os.path.realpath(p) for p in out if p}
    # never a system root (a server started from / would hide Python itself)
    return sorted(p for p in real if len(Path(p).parts) > 2)


def _under(p: str, root: str) -> bool:
    p, root = os.path.realpath(p), os.path.realpath(root)
    return p == root or p.startswith(root.rstrip("/") + "/")


def _ancestors(p: str) -> list[str]:
    out = []
    cur = Path(p)
    while cur.parent != cur:
        cur = cur.parent
        out.append(str(cur))
    return out


def _sbpl(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def macos_profile(hidden: list[str], readable: list[str], workdir: str, network: bool,
                  listable: list[str] | None = None) -> str:
    """A ``sandbox-exec`` profile: everything as usual, except the hidden folders (minus what the worker
    must read), its own folder (read and write) and, unless allowed, the network."""
    rules = ["(version 1)", "(allow default)"]
    if not network:
        rules.append("(deny network*)")
    rules.append("(deny file-read* file-write* " + " ".join(f"(subpath {_sbpl(h)})" for h in hidden) + ")")
    readable = sorted({x for r in readable if r for x in (os.path.abspath(r), os.path.realpath(r))})
    rules.append("(allow file-read* " + " ".join(f"(subpath {_sbpl(r)})" for r in readable) + ")")
    listable = sorted({x for r in listable or [] if r for x in (os.path.abspath(r), os.path.realpath(r))})
    if listable:  # folders on sys.path: Python lists them to import from them (the names, not the files)
        rules.append("(allow file-read* " + " ".join(f"(literal {_sbpl(r)})" for r in listable) + ")")
    meta = sorted({a for r in readable + listable + [workdir] for a in _ancestors(r)})
    if meta:  # to reach an allowed folder, its parents must be visible (not listable)
        rules.append("(allow file-read-metadata " + " ".join(f"(literal {_sbpl(m)})" for m in meta) + ")")
    rules.append(f"(allow file-read* file-write* (subpath {_sbpl(os.path.realpath(workdir))}))")
    return "\n".join(rules)


def bwrap_args(hidden: list[str], readable: list[str], workdir: str, network: bool) -> list[str]:
    """bubblewrap arguments: the root read-only, the hidden folders replaced by empty ones, what the
    worker must read bound back, its own folder writable, new namespaces (no network unless allowed)."""
    args = ["--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--die-with-parent", "--new-session",
            "--unshare-user-try", "--unshare-ipc", "--unshare-pid", "--unshare-uts", "--unshare-cgroup-try"]
    if not network:
        args.append("--unshare-net")
    for h in sorted(hidden, key=len):
        if os.path.isdir(h):
            args += ["--tmpfs", h]
    for r in sorted({os.path.realpath(x) for x in readable if x and os.path.exists(x)}, key=len):
        args += ["--ro-bind", r, r]
    args += ["--bind", workdir, workdir, "--chdir", workdir]
    return args


def sandbox_prefix(kind: str, hidden: list[str], readable: list[str], workdir: str, network: bool,
                   listable: list[str] | None = None) -> list[str] | None:
    """The command prefix that runs the worker in a sandbox; ``[]`` for none (``off``, or ``auto`` without
    one); ``None`` when one is ``required`` and none is available."""
    if kind == "off":
        return []
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return ["sandbox-exec", "-p", macos_profile(hidden, readable, workdir, network, listable)]
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return ["bwrap", *bwrap_args(hidden, readable, workdir, network)]
    return None if kind == "required" else []


def sandbox_available() -> bool:
    return (sys.platform == "darwin" and bool(shutil.which("sandbox-exec"))) or \
        (sys.platform.startswith("linux") and bool(shutil.which("bwrap")))


def _workroot() -> str:
    root = Path(tempfile.gettempdir()) / "hani2-assistants"
    root.mkdir(mode=0o700, exist_ok=True)
    return str(root.resolve())


def _clean_settings(settings: dict) -> dict:
    """The Assistant's settings without anything secret (keys, endpoints): the worker never calls a model."""
    bad = ("key", "secret", "token", "password", "api_base", "base_url", "endpoint")

    def clean(x: Any) -> Any:
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if not any(b in str(k).lower() for b in bad)}
        if isinstance(x, list):
            return [clean(v) for v in x]
        return x

    out = clean(dict(settings or {}))
    return json.loads(json.dumps(out, default=str))


# --------------------------------------------------------------------------- #
# The server side                                                             #
# --------------------------------------------------------------------------- #
class _HostDispatcher(ToolDispatcher):
    """The stock functions; during a harness turn, the worker's own functions too."""

    def execute(self, name: str, args: dict) -> dict:
        rt = self.runtime
        if name not in self._registry and getattr(rt, "_harness_active", False):
            out = rt._invoke("execute", name, args or {})
            return out if isinstance(out, dict) else {"ok": out is not None, "result": out}
        return super().execute(name, args)


class IsolatedAssistant(SupportAgent):
    """The server side of an isolated Assistant (see the module docs)."""

    dispatcher_class = _HostDispatcher
    tools: list = []  # an isolated Assistant brings no tool classes: they would run in the server
    isolated = True

    def __init__(self, session_state: dict[str, Any], settings: dict, *, spec: str, syspath: list[str] | None = None,
                 cfg: dict | None = None):
        self.spec = spec
        self.cfg = dict(cfg or {})
        self._syspath = list(syspath or [])
        self._proc: subprocess.Popen | None = None
        self._ready = threading.Event()
        self._dead: str | None = None
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[str, dict] = {}
        self._cond = threading.Condition()
        self._actors: dict[str, str | None] = {}
        self._inflight = 0
        self._remote_busy = False
        self._harness_active = False
        self._harness_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="hani2-assistant-rpc")
        self.workdir: str | None = None
        self.sandboxed = False
        self.refused_tools: list[str] = []
        self.worker_id = next(_ids)
        super().__init__(session_state, settings)
        _WORKERS.add(self)
        threading.Thread(target=self._start, daemon=True, name=f"hani2-assistant-start-{self.worker_id}").start()

    # -- life cycle ----------------------------------------------------------------
    @property
    def _session_obj(self) -> NegotiationSession | None:
        return self.session_state.get("_session")

    def _start(self) -> None:
        try:
            self._spawn()
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            self._fail(f"the isolated Assistant {self.spec!r} could not be started: {type(e).__name__}: {e}")
            return
        if not self._ready.wait(self.cfg.get("start_timeout", 90)):
            self._fail(f"the isolated Assistant {self.spec!r} did not start within "
                       f"{self.cfg.get('start_timeout', 90):g} s")

    def _spawn(self) -> None:
        root = _workroot()
        self.workdir = tempfile.mkdtemp(prefix=f"w{os.getpid()}-", dir=root)
        syspath, own = code_location(self.spec, self._syspath)
        # only the Assistant's own package goes to the worker, copied into its private folder: the
        # folder it came from (shared by every submission) stays hidden
        code = os.path.join(self.workdir, "code")
        os.makedirs(code)
        for loc in own:
            dest = os.path.join(code, os.path.basename(loc))
            if os.path.isdir(loc):
                shutil.copytree(loc, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"), symlinks=False)
            elif os.path.isfile(loc):
                shutil.copy2(loc, dest)
        if own:
            syspath = [code]
        spec = self.spec
        mod, attr = _module_and_attr(spec)
        if mod.endswith(".py") and own:  # a file spec: the copy of its folder
            spec = f"{os.path.join(code, os.path.basename(own[0]), os.path.basename(mod))}:{attr}"
        readable = _runtime_paths()
        hidden = sorted(set(_hidden_paths(root)) | {os.path.realpath(d) for d in [*self._syspath, *own]
                                                     if d and len(Path(d).parts) > 2})
        import hani2

        listable = [str(Path(hani2.__file__).resolve().parent.parent)]
        prefix = sandbox_prefix(self.cfg.get("sandbox", "auto"), hidden, readable, self.workdir,
                                bool(self.cfg.get("network", False)), listable)
        if prefix is None:
            raise RuntimeError("assistant_sandbox is 'required' but no sandbox (macOS sandbox-exec, Linux bwrap) "
                               "is available on this server")
        self.sandboxed = bool(prefix)
        if not prefix:
            print(f"[hani2] WARNING: the isolated Assistant {self.spec!r} runs without a file-system sandbox "
                  f"(no sandbox-exec / bwrap here, or assistant_sandbox is off): it is a separate process, "
                  f"but it can read files the server's user can read")
        env = {"PATH": "/usr/bin:/bin", "HOME": self.workdir, "TMPDIR": self.workdir, "LANG": "C.UTF-8",
               "LC_ALL": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
               "PYTHONHASHSEED": str(uuid.uuid4().int % 4_000_000_000),
               "HANI2_HOME": os.path.join(self.workdir, "hani2"), "LITELLM_LOCAL_MODEL_COST_MAP": "True"}
        cmd = [*prefix, sys.executable, "-I", "-m", "hani2.support_agent.worker"]
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      cwd=self.workdir, env=env, close_fds=True, start_new_session=True)
        threading.Thread(target=self._read, daemon=True, name=f"hani2-assistant-read-{self.worker_id}").start()
        threading.Thread(target=self._read_err, daemon=True, name=f"hani2-assistant-err-{self.worker_id}").start()
        sess = self._session_obj
        self._send({"t": "init", "spec": spec, "syspath": syspath,
                    "settings": _clean_settings(self.settings), "limits": self.cfg.get("limits") or {},
                    "state": {"user": getattr(sess, "user", ""),
                              "support_agent_user_enabled": self.user_enabled,
                              "support_agent_default_enabled": self.session_state.get("support_agent_default_enabled", True),
                              "support_proactive_delivery": self.user_proactive_delivery},
                    "sync": self._sync_state()})

    def _sync_state(self) -> dict[str, Any]:
        return {"user_enabled": self.user_enabled, "autopilot": self.autopilot,
                "proactive_delivery": self.user_proactive_delivery}

    def _on_ready(self, msg: dict) -> None:
        self.name = str(msg.get("name") or self.name)[:80]
        self.refused_tools = [str(x) for x in msg.get("refused_tools") or []]
        if self.refused_tools:
            print(f"[hani2] the isolated Assistant {self.spec!r} brings tools {self.refused_tools}: not added "
                  f"(tool classes would run in the server); use the admin's toolbox instead")
        pres = msg.get("presentation")
        if isinstance(pres, dict) and self.capabilities.has(Capability.PRESENTATION):
            ov = {k: pres[k] for k in ("style", "may_hide", "may_show") if pres.get(k) is not None}
            if ov.get("style") not in (None, "panel", "persona", "both"):
                ov.pop("style")
            self.session_state["assistant_presentation_override"] = ov
            sess = self._session_obj
            if sess is not None and (ov.get("style") in ("persona", "both") or ov.get("may_hide") is False):
                sess.prefs["persona_hidden"] = False
        self._ready.set()
        self._push()

    def _push(self) -> None:
        sess = self._session_obj
        if sess is not None:
            with contextlib.suppress(Exception):
                sess.push_state()

    def _fail(self, reason: str) -> None:
        """Fail closed: the session has no Assistant from now on (never an in-process one)."""
        with self._lock:
            if self._dead is not None:
                return
            self._dead = reason
        self._ready.set()
        self._kill()
        with self._cond:
            for k in list(self._pending):
                if not self._pending[k]:
                    self._pending[k] = {"t": "error", "error": reason}
            self._cond.notify_all()
        sess = self._session_obj
        if sess is None or getattr(sess, "closed", False) or getattr(self, "_shut", False):
            return
        if getattr(sess, "support_agent", None) is self:
            from hani2.support_agent.runtime import _assistant_failed

            _assistant_failed(sess, getattr(sess, "assistant_choice", None), reason)
            sess.support_agent = None
            self._push()

    def _kill(self) -> None:
        p = self._proc
        if p is not None and p.poll() is None:
            with contextlib.suppress(Exception):
                p.stdin.close()  # type: ignore[union-attr]
            with contextlib.suppress(Exception):
                p.kill()
        with contextlib.suppress(Exception):
            self._pool.shutdown(wait=False, cancel_futures=True)
        if self.workdir:
            shutil.rmtree(self.workdir, ignore_errors=True)

    def shutdown(self) -> None:
        self._shut = True
        with self._lock:
            if self._dead is None:
                self._dead = "the Assistant was stopped"
        self._kill()

    @property
    def alive(self) -> bool:
        return self._dead is None

    # -- the pipe ------------------------------------------------------------------
    def _send(self, msg: dict) -> None:
        p = self._proc
        if p is None or p.stdin is None:
            raise RuntimeError("the Assistant's worker is not running")
        data = (json.dumps(msg, default=str) + "\n").encode("utf-8")
        with self._write_lock:
            p.stdin.write(data)
            p.stdin.flush()

    def _read(self) -> None:
        p = self._proc
        assert p is not None and p.stdout is not None
        try:
            while True:
                line = p.stdout.readline(MAX_LINE + 1)
                if not line:
                    break
                if len(line) > MAX_LINE:
                    self._fail("the isolated Assistant sent a message that is too large")
                    return
                try:
                    msg = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(msg, dict):
                    continue
                t = msg.get("t")
                if t == "ready":
                    self._on_ready(msg)
                elif t == "fatal":
                    self._fail(f"the Assistant {self.spec!r} failed to start: {str(msg.get('error'))[:500]}")
                    return
                elif t in ("result", "error"):
                    with self._cond:
                        if msg.get("id") in self._pending:
                            self._pending[msg["id"]] = msg
                            self._cond.notify_all()
                elif t == "call":
                    try:
                        self._pool.submit(self._serve, msg)
                    except RuntimeError:
                        return
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        self._fail(f"the isolated Assistant {self.spec!r} stopped"
                   + (f" (exit code {p.poll()})" if p.poll() is not None else ""))

    def _read_err(self) -> None:
        p = self._proc
        assert p is not None and p.stderr is not None
        n = 0
        for raw in p.stderr:
            n += 1
            if n > 5000:  # a chatty Assistant must not fill the server log
                continue
            line = raw.decode("utf-8", "replace").rstrip()[:2000]
            print(f"[assistant {self.worker_id}] {line}", file=sys.stderr)

    def _invoke(self, fn: str, *args: Any, timeout: float | None = None) -> Any:
        """Run ``fn`` of the Assistant in the worker and wait for its result (``None`` when it failed)."""
        from hani2.recording.recorder import current_actor

        if not self._ready.wait(self.cfg.get("start_timeout", 90)) or self._dead is not None:
            return None
        iid = "h" + uuid.uuid4().hex[:12]
        with self._cond:
            self._pending[iid] = {}
            self._actors[iid] = current_actor()
            self._inflight += 1
        try:
            self._send({"t": "invoke", "id": iid, "fn": fn, "args": list(args), "state": self._sync_state()})
            limit = float(timeout if timeout is not None else self.cfg.get("call_timeout", 600))
            deadline = time.monotonic() + limit
            with self._cond:
                while not self._pending[iid]:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        break
                    self._cond.wait(min(left, 1.0))
                reply = self._pending.pop(iid, {})
            if not reply:
                self._fail(f"the isolated Assistant did not answer {fn} within {limit:g} s")
                return None
            if reply.get("t") == "error":
                print(f"[hani2] isolated Assistant {fn} failed: {str(reply.get('error'))[:500]}")
                return None
            return reply.get("value")
        except (OSError, ValueError, RuntimeError) as e:
            self._fail(f"the isolated Assistant stopped: {e}")
            return None
        finally:
            with self._cond:
                self._pending.pop(iid, None)
                self._actors.pop(iid, None)
                self._inflight -= 1
            self._push()

    def _invoke_async(self, fn: str, *args: Any) -> None:
        threading.Thread(target=self._invoke, args=(fn, *args), daemon=True).start()

    # -- the worker's calls ----------------------------------------------------------
    def _serve(self, msg: dict) -> None:
        from hani2 import projects
        from hani2.recording import recorder as rec

        cid = msg.get("id")
        sess = self._session_obj
        actor = None
        with self._cond:
            if self._actors:
                actor = next(reversed(self._actors.values()))
        try:
            with rec.bind(getattr(sess, "sid", None)), projects.use_study(getattr(sess, "study_ref", None)), \
                    rec.acting(actor or "agent"):
                value = self._call(str(msg.get("fn")), list(msg.get("args") or []), dict(msg.get("kwargs") or {}))
            reply = {"t": "result", "id": cid, "value": value}
            try:
                self._send(json.loads(json.dumps(reply, default=str)))
            except (TypeError, ValueError):
                self._send({"t": "result", "id": cid, "value": str(value)})
        except Exception as e:  # noqa: BLE001
            with contextlib.suppress(Exception):
                self._send({"t": "error", "id": cid, "error": f"{type(e).__name__}: {e}"[:2000]})

    def _call(self, fn: str, args: list, kwargs: dict) -> Any:
        if fn in FORWARDED:
            if fn == "add_tool":
                tool = args[0] if args else kwargs.get("tool")
                if not isinstance(tool, str):
                    return {"ok": False, "error": "an isolated Assistant adds tools by name only"}
            if fn == "set_opponent_estimate":
                est = args[0] if args else kwargs.get("estimate")
                if est is not None and not isinstance(est, dict):
                    return {"ok": False, "error": "an isolated Assistant gives the estimate as a spec (a dict)"}
            return getattr(SupportAgent, fn)(self, *args, **kwargs)
        if fn == "action":
            return self._action(str(args[0]) if args else "", list(args[1:]), kwargs)
        if fn == "dispatch":
            return self.dispatcher.execute(str(args[0]), dict(args[1] or {}) if len(args) > 1 else {})
        if fn == "schemas":
            return self.dispatcher.schemas()
        if fn == "caps":
            return self._caps(str(args[0]), *args[1:])
        if fn == "complete":
            conv, tools = _conversation(args[0]), list(args[1] or []) if len(args) > 1 else []
            force = bool(args[2]) if len(args) > 2 else False
            no_tools = bool(args[3]) if len(args) > 3 else False
            return self._completion(conv, tools, force_action=force, no_tools=no_tools)
        if fn == "harness":
            return self._harness(_conversation(args[0]), list(args[1] or []), str(args[2] or "chat"), bool(args[3]))
        if fn == "record":
            sess = self._session_obj
            r = getattr(sess, "recorder", None)
            if r is not None:
                r.function_call(str(args[0]), dict(args[1] or {}), args[2], float(args[3] or 0.0))
            return None
        if fn == "_set_busy_state":
            self._remote_busy = bool(args[0]) if args else False
            self._push()
            return None
        if fn == "_autopilot_fallback":
            self._autopilot_stalls = int(args[0]) if args else self._autopilot_stalls + 1
            return SupportAgent._autopilot_fallback(self)
        raise PermissionError(f"an isolated Assistant cannot call {fn!r}")

    def _action(self, name: str, args: list, kwargs: dict) -> Any:
        """One of the session's ``actions`` (as ``session_state["actions"]`` gives an Assistant in the
        server). ``context`` is always the Assistant's view."""
        from hani2.support_agent.worker import ACTIONS

        sess = self._session_obj
        actions = self.session_state.get("actions") or {}
        if name not in ACTIONS or name not in actions or sess is None:
            raise PermissionError(f"an isolated Assistant has no action {name!r}")
        if name == "context":
            return sess.run_on_doc(sess.context)
        if name in ("get_offer", "get_partner_offer", "can_act"):
            return sess.run_on_doc(actions[name])
        if name == "set_offer":
            return actions[name](dict(args[0] or {}) if args else dict(kwargs.get("outcome") or {}))
        return actions[name](*args, **kwargs)

    def _caps(self, name: str, *args: Any) -> Any:
        c = self.capabilities
        if name == "has":
            return c.has(str(args[0]))
        if name == "effective":
            return sorted(x.value for x in c.effective())
        if name in ("autonomy_allows_execute", "autonomy_allows_confirm"):
            return getattr(c, name)(Capability(str(args[0])))
        if name in ("autonomy", "admin_autonomy", "user_autonomy"):
            return getattr(c, name).value
        if name == "admin_capabilities":
            return dict(c.admin_capabilities)
        raise PermissionError(f"unknown capability query {name!r}")

    def _harness(self, conv: list[dict], tools: list[dict], channel: str, force: bool) -> dict:
        with self._harness_lock:
            self.messages = list(conv)
            n0 = len(self.messages)
            executed: set[str] = set()
            self._harness_active = True
            try:
                handled = SupportAgent._harness_turn(self, tools, executed, channel, force)
            finally:
                self._harness_active = False
            return {"handled": bool(handled), "messages": self.messages[n0:] if handled else [],
                    "executed": sorted(executed)}

    # -- what the session calls --------------------------------------------------------
    @property
    def busy(self) -> bool:
        return self._inflight > 0 or self._remote_busy

    def handle_user_message(self, text: str) -> None:
        if not self.user_enabled:
            self.post("(The assistant is turned off. Switch it on to chat.)")
            return
        if self._answer_question(text):
            return
        self._invoke("handle_user_message", text)

    def on_event(self, event_name: str, nmi=None) -> None:
        if event_name == "action_requested":
            self._below_reserved_warned = False
        self._invoke("on_event", event_name)

    def on_draft_changed(self, draft: dict[str, Any]) -> None:
        self._invoke_async("on_draft_changed", dict(draft or {}))

    def on_panel_action(self, panel_id: str, action: str, payload: dict[str, Any]) -> None:
        self._invoke("on_panel_action", panel_id, action, payload or {})

    def autopilot_step(self, delay: float = 0.0) -> None:
        self._invoke("autopilot_step", float(delay or 0.0))

    def clear_conversation(self) -> None:
        self._invoke_async("clear_conversation")

    def client_state(self) -> dict[str, Any]:
        out = super().client_state()
        out["isolated"] = True
        return out


def _conversation(x: Any) -> list[dict]:
    """The worker's conversation, as plain messages (anything else is dropped)."""
    out = []
    for m in x or []:
        if isinstance(m, dict) and isinstance(m.get("role"), str):
            out.append({k: v for k, v in m.items() if isinstance(k, str)})
    return out


def create(session: NegotiationSession, choice: Any, settings: dict) -> IsolatedAssistant:
    return IsolatedAssistant(session.ss, settings, spec=str(choice.spec),
                             syspath=assistant_syspath(session, choice), cfg=config(session))


def stop_all() -> None:
    for w in list(_WORKERS):
        with contextlib.suppress(Exception):
            w.shutdown()


import atexit  # noqa: E402

atexit.register(stop_all)
