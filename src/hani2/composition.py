"""Groups made of items and of other groups: one expansion algorithm for every kind.

Scenario sets, opponent groups, Assistant groups and tool groups all share the
same rule for their entries:

* ``@name`` and ``:name`` always name a group (``:`` is the older spelling, kept
  for opponents and Assistants); an unknown group is reported and skipped;
* a bare entry names a group when the kind looks bare words up (scenario sets:
  any set; opponents, Assistants and tools: a group of the kind, see each kind)
  and is an item otherwise; a bare entry equal to the name of the group being
  expanded is always an item (a set ``Trade: [Trade]`` holds the type ``Trade``);
* groups expand recursively, in place; duplicates are dropped, the first
  occurrence keeping its position;
* a cycle (``A -> B -> A``) is reported once and broken by ignoring the step
  that closes it;
* group names are matched case-insensitively (the lookup decides; see
  :func:`dict_lookup`).

A kind supplies a *lookup*: ``lookup(name, explicit) -> (canonical, entries)``
(or ``(canonical, entries, True)`` when the entries are final items that are not
looked up again, e.g. the members of a built-in group) or ``None``. ``explicit`` is true for ``@``/``:`` references, so a kind can look
bare words up in fewer places (e.g. only group files, never built-ins).
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

__all__ = ["REF_PREFIXES", "is_ref", "ref_name", "dict_lookup", "expand_entries", "expand_groups"]

#: prefixes that make an entry a group reference
REF_PREFIXES = ("@", ":")

Lookup = Callable[[str, bool], "tuple[Any, ...] | None"]


def is_ref(entry: Any) -> bool:
    return isinstance(entry, str) and entry.strip().startswith(REF_PREFIXES)


def ref_name(entry: str) -> str:
    """``@Name`` / ``:Name`` → ``Name`` (a bare entry unchanged)."""
    e = entry.strip()
    return e[1:].strip() if e.startswith(REF_PREFIXES) else e


def dict_lookup(groups: Mapping[str, Iterable[Any]]) -> Lookup:
    """A case-insensitive lookup over ``{name: entries}`` (bare and explicit alike)."""
    lower = {str(k).lower(): k for k in groups}

    def lookup(name: str, explicit: bool) -> "tuple[str, list[Any]] | None":
        k = lower.get(str(name).lower())
        return None if k is None else (str(k), list(groups[k] or []))

    return lookup


def _key(item: Any) -> Any:
    return item if isinstance(item, str) else getattr(item, "__name__", repr(item))


def expand_entries(entries: Iterable[Any], lookup: Lookup, *, name: str | None = None, label: str = "group",
                   prefixes: tuple[str, ...] = REF_PREFIXES, bare: bool = True,
                   report: Callable[[str], None] | None = print, leaf: Callable[[Any], list[Any]] | None = None,
                   _stack: tuple[str, ...] = (), _reported: set | None = None) -> list[Any]:
    """Expand ``entries`` (the members of group ``name``, or a free list when
    ``name`` is ``None``) into a flat list of items.

    ``prefixes``: the reference prefixes this kind accepts (scenario sets: ``@``
    only, since ``:`` never starts a scenario type). ``bare``: whether a bare
    entry may name a group. ``leaf`` turns an item into its final items (for
    example a built-in group token handled by the kind itself); default: the item."""
    reported = set() if _reported is None else _reported
    stack = _stack + ((name,) if name is not None else ())
    out: list[Any] = []
    seen: set = set()

    def add(items: Iterable[Any]) -> None:
        for it in items:
            k = _key(it)
            if k not in seen:
                seen.add(k)
                out.append(it)

    for entry in entries or []:
        if not isinstance(entry, str):
            add([entry])
            continue
        e = entry.strip()
        if not e:
            continue
        explicit = e.startswith(prefixes)
        ref = e[1:].strip() if explicit else e
        hit = lookup(ref, True) if explicit else (lookup(ref, False) if bare else None)
        if hit is not None and not explicit and name is not None and hit[0].lower() == name.lower():
            hit = None  # a bare entry equal to its own group's name is an item
        if hit is None:
            if explicit:
                if report:
                    report(f"[hani2] {label} {name!r}: unknown group {ref!r}" if name else f"[hani2] unknown {label} {ref!r}")
                continue
            add(leaf(e) if leaf else [e])
            continue
        target, members = hit[0], hit[1]
        final = len(hit) > 2 and bool(hit[2])
        if target.lower() in [s.lower() for s in stack]:
            i = [s.lower() for s in stack].index(target.lower())
            cycle = frozenset(x.lower() for x in stack[i:])
            if cycle not in reported:
                reported.add(cycle)
                if report:
                    report(f"[hani2] {label} cycle: {' -> '.join(stack + (target,))}; ignoring the last step")
            continue
        if final:
            add(x for m in members for x in (leaf(m) if leaf else [m]))
            continue
        add(expand_entries(members, lookup, name=target, label=label, prefixes=prefixes, bare=bare,
                           report=report, leaf=leaf, _stack=stack, _reported=reported))
    return out


def expand_groups(raw: Mapping[str, Iterable[Any]], *, label: str = "group", prefixes: tuple[str, ...] = REF_PREFIXES,
                  bare: bool = True, report: Callable[[str], None] | None = print,
                  lookup: Lookup | None = None) -> dict[str, list[Any]]:
    """Expand every group of ``raw`` (``{name: entries}``) on its own, so a cycle
    never leaves a half-expanded group behind. ``lookup`` defaults to a
    case-insensitive lookup over ``raw``."""
    lk = lookup or dict_lookup(raw)
    reported: set = set()
    return {k: expand_entries(v, lk, name=str(k), label=label, prefixes=prefixes, bare=bare, report=report,
                              _reported=reported) for k, v in raw.items()}
