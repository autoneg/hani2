"""The HTTP client HANI2 uses to call a hosted agent (``hani2-hosted/1``)."""

from __future__ import annotations

import time
from typing import Any

from hani2.hosting.protocol import PROTOCOL, Endpoint, HostedError


class HostedClient:
    """Calls one hosted agent. Every call has a time limit (``endpoint.timeout``); every failure is a
    :class:`HostedError` whose message names the agent, never its token."""

    def __init__(self, endpoint: Endpoint, *, transport: Any = None):
        import httpx

        self.endpoint = endpoint
        headers = {"X-HANI2-Protocol": PROTOCOL, "User-Agent": "hani2-hosted-client"}
        if endpoint.token:
            headers["Authorization"] = f"Bearer {endpoint.token}"
        kw: dict[str, Any] = {"transport": transport} if transport is not None else {}
        self._http = httpx.Client(base_url=endpoint.url, headers=headers, timeout=endpoint.timeout,
                                  follow_redirects=False, **kw)
        #: seconds the last call took
        self.last_latency = 0.0

    def close(self) -> None:
        try:
            self._http.close()
        except Exception:  # noqa: BLE001
            pass

    def _call(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> dict:
        import httpx

        name = self.endpoint.name
        t0 = time.time()
        try:
            r = self._http.request(method, path, json=body, timeout=timeout or self.endpoint.timeout)
        except httpx.TimeoutException:
            raise HostedError(f"the hosted agent {name} did not answer within {timeout or self.endpoint.timeout:g} s") from None
        except httpx.HTTPError as e:
            raise HostedError(f"the hosted agent {name} cannot be reached ({type(e).__name__})") from None
        finally:
            self.last_latency = time.time() - t0
        if r.status_code in (401, 403):
            raise HostedError(f"the hosted agent {name} refused HANI2's token (HTTP {r.status_code})")
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code >= 400:
            detail = (data or {}).get("error") or (data or {}).get("detail") if isinstance(data, dict) else None
            raise HostedError(f"the hosted agent {name} answered HTTP {r.status_code}"
                              + (f": {str(detail)[:300]}" if detail else ""))
        if not isinstance(data, dict):
            raise HostedError(f"the hosted agent {name} did not answer with a JSON object")
        return data

    def info(self, timeout: float | None = None) -> dict:
        return self._call("GET", "/info", timeout=timeout)

    def create(self, session_id: str, kind: str, setup: dict) -> dict:
        return self._call("POST", "/sessions", {"session_id": session_id, "kind": kind, "setup": setup})

    def step(self, session_id: str, body: dict, timeout: float | None = None) -> dict:
        return self._call("POST", f"/sessions/{session_id}/step", body, timeout=timeout)

    def end(self, session_id: str) -> dict:
        return self._call("DELETE", f"/sessions/{session_id}", timeout=min(10.0, self.endpoint.timeout))


def check(endpoint: Endpoint, timeout: float = 10.0) -> dict[str, Any]:
    """``GET /info`` of a hosted agent: ``{"ok", "info"?, "error"?, "latency"}`` (for the console and CLI)."""
    c = HostedClient(endpoint)
    try:
        info = c.info(timeout=timeout)
        ok = info.get("protocol", PROTOCOL).split("/")[0] == PROTOCOL.split("/")[0]
        out: dict[str, Any] = {"ok": ok, "info": {k: info.get(k) for k in ("protocol", "kind", "name", "version",
                                                                          "events", "model")},
                               "latency": round(c.last_latency, 3)}
        if not ok:
            out["error"] = f"unknown protocol {info.get('protocol')!r} (HANI2 speaks {PROTOCOL})"
        elif endpoint.kind and info.get("kind") and info["kind"] != endpoint.kind:
            out["ok"] = False
            out["error"] = f"registered as {endpoint.kind} but the host serves an {info['kind']}"
        return out
    except HostedError as e:
        return {"ok": False, "error": str(e), "latency": round(c.last_latency, 3)}
    finally:
        c.close()
