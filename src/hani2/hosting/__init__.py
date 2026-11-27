"""Self-hosted (remote) Assistants and opponents.

A team runs its agent on its own machine — with whatever language model it likes — and HANI2 calls it
over HTTP (protocol ``hani2-hosted/1``). Inside HANI2 the agent looks like a local one:

* :class:`~hani2.hosting.opponent.RemoteOpponent` — a negmas negotiator forwarding its turns;
* :class:`~hani2.hosting.assistant.RemoteAssistant` — an Assistant forwarding its events, whose
  actions run through the local Assistant helpers and functions (the admin's capabilities apply).

Specs: ``remote:<name>`` (a registered endpoint, :mod:`hani2.hosting.registry`) or
``remote+https://host:port`` (admins and files only). The host side is :func:`make_app` / :func:`serve`
(``hani2 host-assistant`` / ``hani2 host-opponent``). See the guide page "Self-hosting an Assistant or
opponent" and the design note.
"""

from __future__ import annotations

from typing import Any

from hani2.hosting.protocol import (PROTOCOL, Endpoint, HostedError, is_direct_address, is_remote_spec,
                                    normalise_spec, recorded_spec, short_label)

__all__ = ["PROTOCOL", "Endpoint", "HostedError", "is_remote_spec", "is_direct_address", "normalise_spec",
           "recorded_spec", "short_label", "make_app", "serve", "remote_opponent_class", "remote_assistant_class",
           "run_host"]


def make_app(kind: str, agent: Any, **kw: Any):
    from hani2.hosting.server import make_app as _m

    return _m(kind, agent, **kw)


def serve(kind: str, agent: Any, **kw: Any) -> None:
    from hani2.hosting.server import serve as _s

    _s(kind, agent, **kw)


def remote_opponent_class(spec: Any) -> type:
    from hani2.hosting.opponent import remote_opponent_class as _r

    return _r(spec)


def remote_assistant_class(spec: Any) -> type:
    from hani2.hosting.assistant import remote_assistant_class as _r

    return _r(spec)


def run_host(app: Any, host: str = "127.0.0.1", port: int = 0):
    """Run an app (from :func:`make_app`) in a background thread; a context manager giving its base URL.
    For tests: ``with run_host(make_app("opponent", MyNeg, token="t")) as url: ...``."""
    from hani2.hosting.testing import run_host as _r

    return _r(app, host, port)
