"""Admin API for language models: connections (settings folder only) and model chains (per layer).

Connections hold secrets, so they live only in the settings folder and every answer masks them.
Model chains are a settings kind (``models.json``) of every layer; writes name the layer
explicitly (a console opened in a study without ``?layer=`` gets 409, as for every setting).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from hani2 import connections as conns
from hani2 import model_chain
from hani2 import providers as prov
from hani2.admin_common import admin_dep, get_layer
from hani2.layers import binding, write_json_own

router = APIRouter(dependencies=[Depends(admin_dep)])


def _only_settings(layer: str | None) -> None:
    if layer and layer != "settings":
        raise HTTPException(400, "connections hold secrets and live only in the settings folder (layer=settings)")


# --------------------------------------------------------------------------- #
# Providers and connections                                                    #
# --------------------------------------------------------------------------- #
@router.get("/api/admin/providers")
def admin_providers():
    from hani2 import harness

    hs = []
    for h in harness.capability_table():
        try:
            st = harness.adapter(h["id"]).status()
        except Exception as e:  # noqa: BLE001
            st = {"found": False, "error": conns.redact(e)}
        hs.append({**h, "status": st})
    return {"providers": prov.table(), "purposes": model_chain.PURPOSE_LABELS, "harnesses": hs}


@router.get("/api/admin/connections")
def admin_connections(implicit: bool = True):
    return {"connections": [conns.public(c) for c in conns.all_connections(include_implicit=implicit)]}


def _body_to_conn(body: dict) -> tuple[dict, str | None, dict | None]:
    data = {k: body.get(k) for k in ("name", "provider", "auth", "base_url", "api_key_env", "litellm_provider", "label",
                                     "upstream")
            if body.get(k)}
    key = body.get("api_key") or None
    headers = body.get("headers")
    if headers is not None and not isinstance(headers, dict):
        raise HTTPException(400, "headers must be a mapping of header names to values")
    return data, key, headers


@router.post("/api/admin/connections")
def admin_add_connection(body: dict = Body(...), layer: str | None = None):
    _only_settings(layer)
    data, key, headers = _body_to_conn(body)
    try:
        c = conns.add(data, api_key=key, headers=headers)
    except conns.ConnectionError_ as e:
        raise HTTPException(400, str(e)) from None
    return conns.public(c)


@router.put("/api/admin/connections/{name}")
def admin_change_connection(name: str, body: dict = Body(...), layer: str | None = None):
    _only_settings(layer)
    data, key, headers = _body_to_conn({**body, "name": name})
    if not any(c.name == name for c in conns.configured()):
        raise HTTPException(404, f"no connection named {name!r}")
    if headers is not None:  # "…" (masked) keeps a stored value
        old = conns._header_values(conns.get(name))  # type: ignore[arg-type]
        headers = {k: (old.get(k, "") if v in ("…", "***") else v) for k, v in headers.items()}
    try:
        c = conns.add(data, api_key=key, headers=headers, replace=True)
    except conns.ConnectionError_ as e:
        raise HTTPException(400, str(e)) from None
    return conns.public(c)


@router.delete("/api/admin/connections/{name}")
def admin_remove_connection(name: str, layer: str | None = None):
    _only_settings(layer)
    if not conns.remove(name):
        raise HTTPException(404, f"no connection named {name!r}")
    return {"ok": True}


@router.post("/api/admin/connections/{name}/test")
async def admin_test_connection(name: str, body: dict = Body(default={})):
    c = conns.get(name)
    if c is None:
        raise HTTPException(404, f"no connection named {name!r}")

    def _run() -> dict[str, Any]:
        conns.forget_probes(name)
        model = str(body.get("model") or "").strip()
        ok, why = conns.has_credentials(c)
        out: dict[str, Any] = {"name": name, "credentials": ok, "reason": why}
        if not ok:
            return {**out, "ok": False}
        if c.preset.harness:  # a tiny completion through the harness (a check sends nothing)
            from hani2 import harness

            model = model or harness.default_model(c)
            try:
                r = harness.complete(c, model, [{"role": "user", "content": "Reply with the word ok."}],
                                     {"timeout": 90})
            except Exception as e:  # noqa: BLE001
                return {**out, "ok": False, "model": model, "reason": conns.redact(f"{type(e).__name__}: {e}")[:300]}
            return {**out, "ok": True, "model": model, "verified": True, "reply": r.text[:200],
                    "reason": "", "models": []}
        if model:
            p = conns.probe(c, model, fresh=True)
            return {**out, "ok": p.ok, "model": model, "reason": conns.redact(p.reason), "verified": p.verified,
                    "models": (p.models or [])[:200]}
        p = conns._probe_now(c, "")
        return {**out, "ok": p.ok, "reason": conns.redact(p.reason), "verified": p.verified,
                "models": (p.models or [])[:200]}

    return await run_in_threadpool(_run)


@router.delete("/api/admin/connections/{name}/login")
def admin_logout(name: str):
    """Delete a connection's stored tokens (subscription sign-ins are no longer offered)."""
    conns.logout(name)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# Model chains                                                                 #
# --------------------------------------------------------------------------- #
def check_body(body: Any) -> None:
    problems = model_chain.check_chains(body)
    if problems:
        raise HTTPException(400, "; ".join(problems))


@router.get("/api/admin/models")
def admin_models(layer: str | None = None):
    lay = get_layer(layer)
    assert lay is not None
    own = model_chain.read_layer_file(lay.dir / model_chain.FILE)
    with binding(lay):
        eff = model_chain.effective_chains()
        seqs = model_chain.effective_sequences()
    with binding(lay, skip_own=True):
        inh = model_chain.effective_chains()
        inh_seqs = model_chain.effective_sequences()
    return {"layer": lay.id, "own": own, "effective": eff, "inherited": inh,
            "sequences": seqs, "inherited_sequences": inh_seqs,
            "builtin_sequences": sorted(model_chain.BUILTIN_SEQUENCES),
            "start": (__import__("os").environ.get(model_chain.ENV) or ""), "purposes": model_chain.PURPOSE_LABELS}


@router.put("/api/admin/models")
def admin_put_models(request: Request, body: dict = Body(...), layer: str | None = None):
    from hani2.admin_api import write_target

    check_body(body)
    lay = write_target(request, layer, None, None)
    with binding(lay):
        bad = model_chain.unknown_refs(body)
    if bad:
        raise HTTPException(400, "; ".join(bad))
    clean = {k: v for k, v in body.items() if v not in (None, [], "")}
    f = lay.dir / model_chain.FILE
    if clean:
        write_json_own(f, clean)
    elif f.exists():
        f.unlink()
    return {"ok": True, "layer": lay.id}


@router.post("/api/admin/models/resolve")
async def admin_resolve_models(body: dict = Body(default={}), layer: str | None = None):
    """Which entry each purpose and each named sequence resolves to at a layer (``chains`` in the
    body: try an unsaved models.json; ``purpose`` or ``sequence``: only that one)."""
    lay = get_layer(layer)
    assert lay is not None
    draft = body.get("chains")
    if draft is not None:
        check_body(draft)
    only = body.get("purpose")
    only_seq = body.get("sequence")

    def _run() -> dict[str, Any]:
        out: dict[str, Any] = {}
        seqs: dict[str, Any] = {}
        conns.forget_probes()
        with binding(lay):
            parsed = model_chain.parse_models(draft) if draft is not None else None
            unsaved = model_chain.Source(f"{lay.id} (unsaved)", {})

            def _named(name: str, purpose: str):
                if parsed is not None and name in parsed.sequences:
                    seq = parsed.sequences[name]
                    if seq.disabled:
                        r = model_chain.Resolution(purpose, source=unsaved.id, sequence=name)
                        r.error = f"the model sequence {name!r} is disabled ({unsaved.id})"
                        return r
                    return model_chain.resolve(purpose, chain=seq.entries, source=unsaved, fresh=True, sequence=name)
                return model_chain.resolve(purpose, sequence=name, fresh=True)

            for p in model_chain.PURPOSES:
                if (only and p != only) or only_seq:
                    continue
                ref = parsed.refs.get(p) or (None if parsed.chains.get(p) else parsed.refs.get("default")) \
                    if parsed is not None else None
                if ref:
                    res = _named(ref, p)
                elif parsed is not None and (parsed.chains.get(p) or parsed.chains.get("default")):
                    ch = parsed.chains.get(p) or parsed.chains["default"]
                    res = model_chain.resolve(p, chain=ch, source=unsaved, fresh=True)
                else:
                    res = model_chain.resolve(p, fresh=True)
                out[p] = res.record()
            if not only:
                names = model_chain.sequence_names(include_disabled=True)
                if parsed is not None:
                    names += [n for n in parsed.sequences if n not in names]
                for n in names:
                    if n in ("default", *model_chain.PURPOSES) or (only_seq and n != only_seq):
                        continue
                    seqs[n] = _named(n, "assistant").record()
        return {"layer": lay.id, "purposes": out, "sequences": seqs}

    return await run_in_threadpool(_run)


@router.post("/api/admin/models/test-entry")
async def admin_test_entry(body: dict = Body(...)):
    """Check one entry; with ``call: true`` also send a one-word request."""
    try:
        e = model_chain.parse_entry(body.get("entry"))
    except model_chain.ChainError as err:
        raise HTTPException(400, str(err)) from None

    def _run() -> dict[str, Any]:
        res = model_chain.resolve_entry(e)
        out = res.record()
        if res.ok and body.get("call"):
            try:
                r = model_chain.completion("test", [{"role": "user", "content": "Reply with the word ok."}],
                                           resolution=res, params={"max_tokens": 16})
                out["reply"] = (r.choices[0].message.content or "")[:200]
            except Exception as err:  # noqa: BLE001
                out["status"] = "none"
                out["error"] = conns.redact(f"{type(err).__name__}: {err}")[:300]
        return out

    return await run_in_threadpool(_run)
