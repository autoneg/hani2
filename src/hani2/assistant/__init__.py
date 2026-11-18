"""The Assistant (new name of :mod:`hani2.support_agent`).

``hani2.assistant`` is the same package under its new name: every submodule
(``hani2.assistant.runtime``, ``.settings``, ``.capabilities``, ``.tools``,
``.autopilot``) *is* the corresponding ``hani2.support_agent`` module, so
patches and class checks see one set of objects. ``hani2.support_agent`` stays
importable (old name)::

    from hani2.assistant import Assistant          # new
    from hani2.support_agent import SupportAgent   # old; the same class
"""

import importlib as _importlib
import sys as _sys

from hani2.support_agent import (
    Assistant,
    Autonomy,
    Capability,
    CapabilityState,
    SupportAgent,
    ToolDispatcher,
    make_function_schema,
    resolve_agent_class,
)

_SUBMODULES = ("autopilot", "capabilities", "runtime", "settings", "tools")
for _name in _SUBMODULES:
    _mod = _importlib.import_module(f"hani2.support_agent.{_name}")
    _sys.modules[f"{__name__}.{_name}"] = _mod
    globals()[_name] = _mod
del _name, _mod

__all__ = [
    "Assistant",
    "SupportAgent",
    "ToolDispatcher",
    "make_function_schema",
    "Capability",
    "Autonomy",
    "CapabilityState",
    "resolve_agent_class",
]
