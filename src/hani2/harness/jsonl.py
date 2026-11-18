"""A child process that speaks JSON lines on stdin/stdout (pi's RPC mode, Codex's app-server)."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from typing import Any

from hani2.harness.base import HarnessError, HarnessTimeout


class JsonlProcess:
    def __init__(self, argv: list[str], *, env: dict[str, str], cwd: str, label: str):
        self.label = label
        self._q: queue.Queue = queue.Queue()
        self._err: list[str] = []
        try:
            self.p = subprocess.Popen(argv, env=env, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE)
        except OSError as e:
            raise HarnessError(f"{label} could not start: {type(e).__name__}") from None
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()

    def _read(self) -> None:
        assert self.p.stdout is not None
        for line in self.p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self._q.put(json.loads(line))
            except json.JSONDecodeError:
                continue
        self._q.put(None)

    def _read_err(self) -> None:
        assert self.p.stderr is not None
        for line in self.p.stderr:
            if len(self._err) < 50:
                self._err.append(line.decode("utf-8", "replace").rstrip())

    def stderr_tail(self) -> str:
        from hani2.connections import redact

        return redact(" | ".join(self._err[-5:]))[:400]

    def send(self, obj: dict[str, Any]) -> None:
        assert self.p.stdin is not None
        try:
            self.p.stdin.write(json.dumps(obj).encode() + b"\n")
            self.p.stdin.flush()
        except (BrokenPipeError, OSError):
            raise HarnessError(f"{self.label} stopped: {self.stderr_tail()}") from None

    def next(self, deadline: float) -> dict[str, Any]:
        """The next message (raises :class:`HarnessTimeout` after ``deadline``, :class:`HarnessError`
        when the process ends)."""
        while True:
            left = deadline - time.time()
            if left <= 0:
                raise HarnessTimeout(f"{self.label}: no answer in time")
            try:
                msg = self._q.get(timeout=min(left, 0.5))
            except queue.Empty:
                continue
            if msg is None:
                raise HarnessError(f"{self.label} stopped (exit {self.p.poll()}): {self.stderr_tail()}")
            if isinstance(msg, dict):
                return msg

    def close(self) -> None:
        try:
            if self.p.stdin:
                self.p.stdin.close()
        except OSError:
            pass
        try:
            self.p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.p.kill()
            try:
                self.p.wait(timeout=3)
            except subprocess.TimeoutExpired:  # pragma: no cover
                pass

    def __enter__(self) -> JsonlProcess:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
