"""litellm's custom-provider hook for harness connections.

``litellm.completion(model="hani2_harness/<model>", api_base="hani2-harness://<connection>", …)``
lands in :class:`HarnessLLM`, which runs a plain completion through the connection's harness. The
connection's key never passes through litellm: the adapter reads it into the child's environment.
A call with function schemas (``tools``) is refused: function calling goes through
:func:`hani2.harness.run_tools` (the Assistant), never through this hook.
"""

from __future__ import annotations

import time
from typing import Any

from litellm import CustomLLM
from litellm.types.utils import ModelResponse, Usage


class HarnessLLM(CustomLLM):
    def completion(self, model: str, messages: list, api_base: str, custom_prompt_dict: dict,
                   model_response: ModelResponse, print_verbose: Any, encoding: Any, api_key: Any,
                   logging_obj: Any, optional_params: dict, acompletion: Any = None, litellm_params: Any = None,
                   logger_fn: Any = None, headers: Any = None, timeout: Any = None, client: Any = None) -> ModelResponse:
        from hani2 import harness

        c = harness.connection_from_base(api_base or (litellm_params or {}).get("api_base"))
        if (optional_params or {}).get("tools"):
            raise harness.HarnessUnavailable(
                f"{c.preset.label}: function schemas cannot be passed to a harness through litellm (only the "
                "Assistant's functions run through a harness); use an API connection for callers that need tools")
        params = {k: v for k, v in (optional_params or {}).items() if k not in ("tools", "tool_choice")}
        if isinstance(timeout, (int, float)) and "timeout" not in params:
            params["timeout"] = float(timeout)
        reply = harness.complete(c, model, list(messages), params)
        model_response.choices[0].message.content = reply.text  # type: ignore[union-attr]
        model_response.choices[0].finish_reason = "stop"
        model_response.model = f"{harness.LITELLM_PROVIDER}/{model}"
        model_response.created = int(time.time())
        u = reply.usage or {}
        model_response.usage = Usage(prompt_tokens=int(u.get("input_tokens", 0)), completion_tokens=int(u.get("output_tokens", 0)), total_tokens=int(u.get("input_tokens", 0)) + int(u.get("output_tokens", 0)))
        if reply.cost_usd is not None:
            model_response._hidden_params["response_cost"] = reply.cost_usd
        model_response._hidden_params["harness"] = {"id": c.preset.harness, **reply.meta}
        return model_response

    async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:  # type: ignore[override]
        import asyncio

        return await asyncio.to_thread(self.completion, *args, **kwargs)
