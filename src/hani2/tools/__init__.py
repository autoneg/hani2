"""HANI2 tools: modular panels that help the human negotiate.

See :class:`hani2.tools.base.Tool`, :class:`hani2.tools.llm_tool.LLMTool`
and :mod:`hani2.tools.ui`. Register a tool by saving its file in the tools
folder (``hani2 tools path``), with :func:`register_tool`, in ``env.json`` or
through a ``hani2.tools`` entry point.
"""

from hani2.tools import ui
from hani2.tools.base import OutcomeSelector, Tool
from hani2.tools.llm_tool import LLMTool
from hani2.tools.registry import register_tool

__all__ = ["Tool", "OutcomeSelector", "LLMTool", "register_tool", "ui"]
