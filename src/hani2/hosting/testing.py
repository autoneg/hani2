"""Run a hosted agent in-process for tests (a real HTTP server on a free local port)."""

from __future__ import annotations

import contextlib
import socket
import threading
import time
from typing import Any, Iterator


def free_port(host: str = "127.0.0.1") -> int:
    with socket.socket() as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])


@contextlib.contextmanager
def run_host(app: Any, host: str = "127.0.0.1", port: int = 0) -> Iterator[str]:
    """Serve ``app`` with uvicorn in a daemon thread; yields ``http://host:port``; stops it on exit."""
    import uvicorn

    port = port or free_port(host)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning", lifespan="off"))
    th = threading.Thread(target=server.run, daemon=True, name="hosted-test-server")
    th.start()
    end = time.time() + 15
    while not server.started and time.time() < end:
        time.sleep(0.02)
    if not server.started:
        raise RuntimeError("the hosted agent's test server did not start")
    try:
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        th.join(timeout=5)
