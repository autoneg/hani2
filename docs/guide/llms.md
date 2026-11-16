# Language models

HANI2 does not need a language model to run a negotiation. You need one for three things:

- the **support agent** (the assistant next to the negotiation),
- **LLM opponents**, the partners from negmas-llm that negotiate in natural language,
- the **message helpers**: writing a message for an offer, reading an offer out of a message, and the admin-only `LLM` tool that turns a plain-language instruction into an offer and a message.

There are two independent configurations, so the assistant can use a different model from the opponents.

| File | Used by | Client |
| --- | --- | --- |
| `support_agent_settings.json` | The support agent and its autopilot driver. | [litellm](https://docs.litellm.ai/docs/providers), so any provider litellm supports. |
| `llm_settings.json` | LLM opponents (`model` and `provider` are passed to them) and the message helpers. | Any litellm provider, for both the opponents (through negmas-llm) and the message helpers. |

Both files live in the settings folder and can be edited in the admin console, under **Language model** and **Support agent**. The [configuration reference](configuration.md) lists every key.

## The default: a local model with Ollama

Out of the box both configurations point to Ollama on the same machine, with the model `qwen3:4b-instruct`.

1. Install Ollama from [ollama.com/download](https://ollama.com/download) (or `brew install ollama` on macOS) and start it:

    ```bash
    ollama serve
    ```

2. Pull the model:

    ```bash
    ollama pull qwen3:4b-instruct
    ```

3. Start HANI2. Nothing else is needed; the defaults are:

    ```json title="llm_settings.json"
    {
      "provider": "ollama",
      "model": "qwen3:4b-instruct",
      "ollama_base_url": "http://localhost:11434/v1",
      "api_key_env": "OPENAI_API_KEY",
      "temperature": 0.3,
      "max_tokens": 2000
    }
    ```

    ```json title="support_agent_settings.json (model part)"
    {
      "provider": "ollama",
      "model": "qwen3:4b-instruct",
      "api_key_env": "OPENAI_API_KEY",
      "api_base": null,
      "temperature": 0.3,
      "max_tokens": 2000,
      "max_tool_iterations": 6
    }
    ```

Small models answer quickly but follow instructions less reliably. If the assistant calls the wrong functions or LLM opponents produce invalid offers, try a larger model, for example `ollama pull qwen3:8b` and set `"model": "qwen3:8b"` in both files.

To use an Ollama server on another machine, set `ollama_base_url` in `llm_settings.json` (for the message helpers) and `api_base` in `support_agent_settings.json` (for the assistant), for example `"api_base": "http://gpu-box:11434"`.

### Local fallback for missing models

When an Ollama call made through litellm (by an LLM opponent or the support agent) fails because the model is not found, and the call did not name a local `api_base` (no `api_base` at all also counts), HANI2 retries it once against the local Ollama daemon. The local address is `http://localhost:11434` unless you set `HANI2_OLLAMA_LOCAL_BASE`:

```bash
export HANI2_OLLAMA_LOCAL_BASE=http://127.0.0.1:11500
```

Calls that already target `localhost` or `127.0.0.1` are not retried.

## Hosted providers

### The support agent

`support_agent_settings.json` accepts any litellm provider name in `provider` and a model name in `model`. HANI2 builds the litellm model string from the two (for example `openai` + `gpt-4o-mini` becomes `openai/gpt-4o-mini`). The API key is read from the environment variable named in `api_key_env`; set `api_base` for OpenAI-compatible servers.

=== "OpenAI"

    ```json
    {"provider": "openai", "model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"}
    ```

=== "Anthropic"

    ```json
    {"provider": "anthropic", "model": "claude-sonnet-4-20250514", "api_key_env": "ANTHROPIC_API_KEY"}
    ```

=== "Gemini"

    ```json
    {"provider": "gemini", "model": "gemini-2.0-flash", "api_key_env": "GEMINI_API_KEY"}
    ```

=== "OpenRouter"

    ```json
    {"provider": "openrouter", "model": "openai/gpt-4o-mini", "api_key_env": "OPENROUTER_API_KEY"}
    ```

=== "OpenAI-compatible server"

    ```json
    {"provider": "openai", "model": "my-model", "api_key_env": "MY_SERVER_KEY",
     "api_base": "http://localhost:8000/v1"}
    ```

Export the key before you start the server:

```bash
export OPENAI_API_KEY=sk-...
hani2
```

The assistant uses function calling, so pick a model that supports tools. See the [support agent guide](support-agent.md) for the remaining keys.

### LLM opponents

When an opponent is an LLM negotiator (its spec starts with `LLM`, or its class derives from negmas-llm's `LLMNegotiator` or `LLMMetaNegotiator`), HANI2 passes `model` from `llm_settings.json`. It also passes `provider` when the spec is a string starting with `LLM`, and to meta negotiators whose constructor declares a `provider` parameter. negmas-llm calls litellm, so any litellm provider works. HANI2 passes no API key or endpoint to opponents, so `api_key_env` and `ollama_base_url` do not apply to them; provide credentials the way negmas-llm and litellm expect, usually the provider's standard environment variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY` and so on).

```json title="llm_settings.json"
{"provider": "openai", "model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"}
```

See [Opponents](opponents.md) for how to put LLM opponents in the pool.

### Message helpers

The message helpers accept any litellm provider:

| `provider` | How it is called | Key |
| --- | --- | --- |
| `ollama` | OpenAI-compatible client at `ollama_base_url`. Any OpenAI-compatible server works here. | none |
| anything else (`openai`, `anthropic`, `gemini`, `groq`, `mistral`, `azure`, `openrouter`, …) | litellm, with the model string built from `provider` and `model`; set `api_base` for a custom endpoint | the variable named in `api_key_env` |

The helpers are used by:

- the **Write message** and **Offer from message** buttons that admins see under the action panel,
- the admin settings **Write a message when none is given** (`auto_generate`) and the automatic extraction of an offer from the human's message (`auto_extract`),
- the admin-only `LLM` tool (see [Tools](tools.md)).

The **Language model** section of the admin console shows whether the configuration is usable: the provider, the model and whether the API key variable is set.

## Prompt templates

The message helpers use three prompt templates. Override any of them by adding the key to `llm_settings.json`; the value is a Python format string, so literal braces must be doubled (`{{` and `}}`).

| Key | Used for | Expected answer |
| --- | --- | --- |
| `extraction_prompt` | Reading an offer out of the human's message. | JSON: `has_offer`, `outcome` (issue → value), `confidence`, `reasoning`. |
| `generation_prompt` | Writing a message that goes with an offer. | Plain text. |
| `instruction_prompt` | The `LLM` tool: an instruction becomes an offer and a message. | JSON: `text`, `outcome`, `reasoning`. |

Every template can use these placeholders:

| Placeholder | Content |
| --- | --- |
| `{issues_description}` | One line per issue with its range or values. |
| `{outcome_space_json}` | The outcome space, serialized as JSON. |
| `{ufun_json}` | The human's utility function, serialized as JSON. |
| `{ufun_description}` | A short readable summary of the preferences (weights, or the best outcomes). |
| `{negotiation_history}` | The last turns, one per line. |
| `{last_offer}` | The latest offer in the history. |
| `{last_5_offers}`, `{last_10_offers}` | The latest offers. |
| `{current_offer_description}` | The partner's current offer, one issue per line. |
| `{current_offer_utility}` | The human's utility for it, as a percentage. |

Some placeholders are specific to one template:

| Template | Extra placeholders |
| --- | --- |
| `extraction_prompt` | `{message}`: the message to analyse. |
| `generation_prompt` | `{outcome_description}`: the offer to describe; `{rejected_outcome_description}`: the partner offer being rejected; `{utility_context}`: a qualitative assessment of both offers that does not reveal numbers. |
| `instruction_prompt` | `{instruction}`: what the user typed; `{history}`: the history text. |

If a template uses a placeholder that is not available, HANI2 retries the format with a reduced set (`issues_description` plus the template-specific fields) and fails if that is not enough either.

The support agent has its own prompt, `system_prompt` in `support_agent_settings.json`. See the [support agent guide](support-agent.md).

## Logging LLM calls of opponents

Set `HANI2_LLM_LOG=1` (also `true`, `yes` or `on`) to log every litellm call an opponent makes during a negotiation:

```bash
HANI2_LLM_LOG=1 hani2
```

Each negotiation gets one JSON-lines file, `<results>/<user>/llm_logs/<mechanism id>.jsonl`, and the server prints its path when the negotiation starts. Every line holds:

| Field | Content |
| --- | --- |
| `ts` | Timestamp. |
| `model` | The litellm model string. |
| `latency_s` | Call duration in seconds. |
| `num_predict` | The token budget (`num_predict` or `max_tokens`). |
| `temperature` | The temperature. |
| `messages` | The full prompt. |
| `response` | The answer text. |
| `empty_response` | `true` when the answer was empty. |
| `reasoning` | Hidden reasoning, when the model returned any. |
| `error` | The exception, when the call failed. |

Only calls made while the negotiation is being stepped are logged, so concurrent participants never write to each other's files. Logging errors are ignored and never interrupt a negotiation.

## Troubleshooting

**The assistant replies with an error about the model.** Check that the model exists (`ollama list`) and that the key variable named in `api_key_env` is exported in the shell that runs `hani2`.

**LLM opponents send empty or invalid offers.** Use a larger model and turn on `HANI2_LLM_LOG` to see the exact prompts and answers.

**The admin console says the LLM is not configured.** The provider is not `ollama` and the variable named in `api_key_env` is not set.
