# Language models

HANI2 does not need a language model to run a negotiation. You need one for three things:

- the **Assistant** (the AI helper next to the negotiation),
- **LLM opponents**, the opponents from negmas-llm that negotiate in natural language,
- the **message helpers**: writing a message for an offer, reading an offer out of a message, and the admin-only `LLM` tool that turns a plain-language instruction into an offer and a message.

!!! tip "Which model is used"
    The models to use are set as **model chains**: ordered lists of models HANI2 tries until one
    is available, per purpose, per project or study, with **connections** to any provider (API
    keys, local servers, agent harnesses), and as **named sequences** (`tiny`, `offline`, `small`,
    `medium`, `large` and your own) that the Assistant, tools and the judge can pick by name. See
    [Models and connections](models.md) and [Named sequences](models.md#named-sequences). The two files
    below are the old single-model settings: they are used when no chain is set, and their
    prompts and other keys always apply.

There are two independent configurations, so the assistant can use a different model from the opponents.

| File | Used by | Client |
| --- | --- | --- |
| `assistant_settings.json` | The Assistant and its autopilot driver. | [litellm](https://docs.litellm.ai/docs/providers), so any provider litellm supports. |
| `llm_settings.json` | LLM opponents (`model` and `provider` are passed to them) and the message helpers. | Any litellm provider, for both the opponents (through negmas-llm) and the message helpers. |

Both files live in the settings folder and can be edited in the admin console, under **Language model** and **Assistant settings**. The [configuration reference](configuration.md) lists every key.

## The default: a local model with Ollama

Out of the box both configurations point to Ollama on the same machine, with the model `qwen3:4b-instruct`.

1. Install Ollama and start it:

    === "macOS"

        ```bash
        brew install ollama      # or the app from ollama.com/download
        ollama serve
        ```

    === "Linux"

        ```bash
        curl -fsSL https://ollama.com/install.sh | sh
        ollama serve             # the installer usually starts it as a service already
        ```

    === "Windows"

        Run the installer from [ollama.com/download](https://ollama.com/download). Ollama then runs
        in the background.

    The server listens on `http://localhost:11434`.

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

    ```json title="assistant_settings.json (model part)"
    {
      "provider": "ollama",
      "model": "qwen3:4b-instruct",
      "api_key_env": "OPENAI_API_KEY",
      "api_base": null,
      "temperature": 0.3,
      "max_tokens": 2000,
      "max_tool_iterations": 10
    }
    ```

Small models answer quickly but follow instructions less reliably. If the assistant calls the wrong functions or LLM opponents produce invalid offers, try a larger model, for example `ollama pull qwen3:8b` and set `"model": "qwen3:8b"` in both files.

### Choosing a local model

| Model | Size | Speed | Notes |
|-------|------|-------|-------|
| `qwen3:4b-instruct` | 4B | fast | The default. Fine for testing and for the message helpers; follows long instructions less reliably. |
| `qwen3:8b` | 8B | medium | A good step up for the Assistant and LLM opponents. |
| `qwen3:30b-a3b` | 30B (3B active) | medium | Better reasoning, needs about 20 GB of memory. |
| `gpt-oss:20b` | 20B | slower | Strong function calling; needs about 16 GB of memory. |

The Assistant needs a model that supports function calling (tools); all of the above do. Pull a
model with `ollama pull NAME`, then set `"model": "NAME"` in both files (or in the model chain,
see [Models and connections](models.md)).

### Testing the setup

1. Check that Ollama answers and has the model:

    ```bash
    curl http://localhost:11434/api/tags      # lists the models you pulled
    ollama run qwen3:4b-instruct "Say hello"
    ```

2. Start HANI2 and log in as an admin. The **Language model** page of the admin console says
   whether the configuration is usable, and **Test chains** on the **Models** page tries every
   entry (see [Models and connections](models.md)). `hani2 models resolve` does the same from the
   command line.
3. Start a negotiation and open the **LLM** tool (admins have it). Type "Propose a fair middle
   ground" and press **Generate**: a suggested offer and message should appear within a few
   seconds. Then open the **Assistant** and ask "What do you think of this offer?".

### Editing the settings in the admin console

Admins edit both files in the admin console instead of by hand: **Language model** for
`llm_settings.json` (provider, model, address, key variable, temperature and the prompt templates)
and **Assistant settings** for `assistant_settings.json`, for the whole server, a project or a
study. Changes apply to sessions started after saving.

To use an Ollama server on another machine, set `ollama_base_url` in `llm_settings.json` (for the message helpers) and `api_base` in `assistant_settings.json` (for the assistant), for example `"api_base": "http://gpu-box:11434"`.

### Local fallback for missing models

When the old settings point Ollama at a remote server (`api_base`, or `OLLAMA_API_BASE`, for example
`https://ollama.com`), they read as a two-entry model chain: the remote server first, then the
local Ollama daemon. A model the remote server does not have is used from the local daemon. The
local address is `http://localhost:11434` unless you set `HANI2_OLLAMA_LOCAL_BASE`:

```bash
export HANI2_OLLAMA_LOCAL_BASE=http://127.0.0.1:11500
```

See [Choosing an entry](models.md#choosing-an-entry).

## Hosted providers

### The Assistant

`assistant_settings.json` accepts any litellm provider name in `provider` and a model name in `model`. HANI2 builds the litellm model string from the two (for example `openai` + `gpt-4o-mini` becomes `openai/gpt-4o-mini`). The API key is read from the environment variable named in `api_key_env`; set `api_base` for OpenAI-compatible servers.

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

The assistant uses function calling, so pick a model that supports tools. See the [Assistant guide](assistant.md) for the remaining keys.

### LLM opponents

When an opponent is an LLM negotiator (its spec starts with `LLM`, or its class derives from negmas-llm's `LLMNegotiator` or `LLMMetaNegotiator`), HANI2 gives it the `opponent` model chain's entry: the provider, the model, the connection's key, address and headers, and the entry's parameters. This also applies to the LLM layer a meta negotiator wraps. Without a chain, that entry comes from `llm_settings.json`. negmas-llm calls litellm, so any litellm provider works.

```json title="llm_settings.json"
{"provider": "openai", "model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"}
```

See [Opponents](opponents.md) for how to put LLM opponents in the pool.

### Message helpers

The message helpers accept any litellm provider:

| `provider` | How it is called | Key |
| --- | --- | --- |
| `ollama` | litellm's Ollama chat API at `ollama_base_url` (a trailing `/v1` is ignored). | none |
| anything else (`openai`, `anthropic`, `gemini`, `groq`, `mistral`, `azure`, `openrouter`, …) | litellm, with the model string built from `provider` and `model`; set `api_base` for a custom endpoint | the variable named in `api_key_env` (else the provider's usual variable) |

With a model chain, the helpers use the `text` chain and tools use the `tools` chain.

The helpers are used by:

- the **Write message** and **Offer from message** buttons that admins see under the action panel,
- the admin settings **Write a message when none is given** (`auto_generate`) and the automatic extraction of an offer from the human's message (`auto_extract`),
- the admin-only `LLM` tool (see [Tools](tools.md)),
- tools built on `LLMTool` or calling `Tool.ask_llm()`, such as the Summary and Ask the AI example tools (see [Build a tool](../tutorials/tools.md#step-4-a-tool-that-uses-a-language-model)). Your own code can call the same model with `hani2.llm_service.complete(prompt, system=None, session=None, **settings)`.

When the Assistant sends a counter-offer with `auto_extract` or `auto_generate` on, the model runs
without locking the session, so the interface stays responsive meanwhile. If the offer, the message
or the turn changes while the model works, its result is dropped and the send is refused (*The offer
or message changed while it was being prepared*), so the offer can be checked and sent again.

The **Language model** page of the admin console shows whether the configuration is usable: the provider, the model and whether the API key variable is set.

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
| `{current_offer_description}` | The opponent's current offer, one issue per line. |
| `{current_offer_utility}` | The human's utility for it, as a percentage. |

Some placeholders are specific to one template:

| Template | Extra placeholders |
| --- | --- |
| `extraction_prompt` | `{message}`: the message to analyse. |
| `generation_prompt` | `{outcome_description}`: the offer to describe; `{rejected_outcome_description}`: the opponent offer being rejected; `{utility_context}`: a qualitative assessment of both offers that does not reveal numbers. |
| `instruction_prompt` | `{instruction}`: what the user typed; `{history}`: the history text. |

If a template uses a placeholder that is not available, HANI2 retries the format with a reduced set (`issues_description` plus the template-specific fields) and fails if that is not enough either.

The Assistant has its own prompt, `system_prompt` in `assistant_settings.json`. See the [Assistant guide](assistant.md).

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

**Connection refused.** Ollama is not running or listens elsewhere. Start it with `ollama serve`
and check `curl http://localhost:11434/api/tags`. For a server on another machine, set
`ollama_base_url` and `api_base` as above, and start Ollama there with `OLLAMA_HOST=0.0.0.0` so it
accepts connections from other machines.

**Model not found.** The model was not pulled on the machine Ollama runs on. `ollama list` shows
what is there; `ollama pull NAME` fetches it. The name must match exactly, including the tag after
the colon.

**Slow answers.** Use a smaller model, close other programs that use the GPU or memory, and keep
`max_tokens` low. The first request after starting Ollama also loads the model, which takes longer.

**The assistant replies with an error about the model.** Check that the model exists (`ollama list`) and that the key variable named in `api_key_env` is exported in the shell that runs `hani2`.

**LLM opponents send empty or invalid offers.** Use a larger model and turn on `HANI2_LLM_LOG` to see the exact prompts and answers.

**The admin console says the LLM is not configured.** No entry of the chain has credentials: the provider is not `ollama` and the key variable is not set, or a harness is not installed. **Test chains** on the Models page says why each entry was skipped.

**A banner says no language model is available.** Every entry of the chain was skipped; the `model_unavailable` event lists why. Run `hani2 models resolve` to check from the command line.
