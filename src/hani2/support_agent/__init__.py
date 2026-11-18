"""The Assistant: the AI helper that advises the human negotiator and can act for them.

The package is also importable as :mod:`hani2.assistant` (the new name);
``hani2.support_agent`` and ``SupportAgent`` are the old names and keep working.

Public API::

    from hani2.assistant import Assistant, ToolDispatcher, make_function_schema
    from hani2.assistant import Capability, Autonomy
    # old names, the same objects
    from hani2.support_agent import SupportAgent
"""

from hani2.support_agent.capabilities import Autonomy, Capability, CapabilityState
from hani2.support_agent.runtime import Assistant, SupportAgent, resolve_agent_class
from hani2.support_agent.tools import ToolDispatcher, make_function_schema

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
