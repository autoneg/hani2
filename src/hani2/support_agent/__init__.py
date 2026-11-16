"""The Negotiation Support Agent: an assistant that helps the human negotiator.

Public API::

    from hani2.support_agent import SupportAgent, ToolDispatcher, make_function_schema
    from hani2.support_agent import Capability, Autonomy
"""

from hani2.support_agent.capabilities import Autonomy, Capability, CapabilityState
from hani2.support_agent.runtime import SupportAgent, resolve_agent_class
from hani2.support_agent.tools import ToolDispatcher, make_function_schema

__all__ = [
    "SupportAgent",
    "ToolDispatcher",
    "make_function_schema",
    "Capability",
    "Autonomy",
    "CapabilityState",
    "resolve_agent_class",
]
