# Models and connections

HANI2 can use several language models and try them in order. You set this up in two steps:

1. **Connections** sign in to model providers, with an API key, a subscription or nothing at all
   for a local server. Connections are shared by every project and study.
2. **Model chains** list the models to try, in order. Each entry names a connection, a model and
   optional parameters. The first entry that is available is used. A project or a study can have
   its own chain.

Each session picks a model once from the chain and keeps it. The choice is written to the
results, the events and the recording.

## Connections

A connection has a name, a provider, a sign-in method, an optional address (base URL) and optional
extra headers. Model chains refer to connections by name, so one provider can have more than one
connection, for example `ollama-local` and `ollama-cloud`, or two OpenAI keys.

Add connections on the **Connections** page of the admin console (**Language models** group), or
on the command line:

```bash
hani2 connections add claude --provider anthropic --key            # asks for the key, stores it
hani2 connections add openai --provider openai --auth api_key_env   # reads $OPENAI_API_KEY
hani2 connections add ollama-cloud --provider ollama_cloud --key
hani2 connections add gpu-box --provider ollama --base-url http://gpu-box:11434
hani2 connections add copilot --provider github_copilot --auth subscription
hani2 connections login copilot                                     # shows a code to enter on github.com
hani2 connections list
hani2 connections test claude --model claude-sonnet-5-5
```

### Sign-in methods

| Method | What it is | Where the secret is kept |
| --- | --- | --- |
| `api_key` | A key pasted into the console (or typed after `--key`). | `settings/secrets/connections.json`, readable only by the server's user (mode 0600). |
| `api_key_env` | The name of an environment variable that holds the key. | The server's environment. |
| `subscription` | A sign-in with the provider's device-code flow: the console shows a code, you enter it on the provider's site, and HANI2 keeps the token. | `settings/secrets/<connection>/`, readable only by the server's user. |
| `none` | Nothing: a local server, or credentials the provider reads from the environment (Amazon Bedrock). | — |

Connections and secrets live only in the settings folder, never in a project or study folder. The
console, the API and the command line show keys masked (`sk-…89`). Keys, tokens and header values
are never written to results, events, recordings or LLM call logs. Errors that contain a stored
secret are masked before they are shown or recorded.

**Implicit connections.** Every provider also has a connection you do not need to add. It is named
after the provider and reads the provider's usual environment variable, for example `anthropic`
reads `ANTHROPIC_API_KEY` and `openai` reads `OPENAI_API_KEY`. The implicit `ollama` connection is
the local server (`OLLAMA_API_BASE` or `http://localhost:11434`). There is also an `ollama-local`
connection (`HANI2_OLLAMA_LOCAL_BASE` or `http://localhost:11434`). Turn on **Show implicit** on the
Connections page to see them.

### Providers

Every call goes through [litellm](https://docs.litellm.ai/docs/providers), so any provider litellm
supports can be used. To use one that has no preset, pick **Other litellm provider** and give
litellm's name for it, for example `together_ai`, `xai` or `vertex_ai`. These providers have
presets:

| Provider (`provider`) | API key | Subscription | Notes |
| --- | --- | --- | --- |
| Anthropic (`anthropic`) | yes | **no** | Anthropic does not permit third-party applications to sign in with Claude Free, Pro, Max or Ultra plans, or to route requests through those plans' credentials. Developers must use an API key from the Claude Console ([Anthropic's legal and compliance page](https://code.claude.com/docs/en/legal-and-compliance)). Models: `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`, `claude-fable-5-2`. Claude 5 models refuse sampling parameters, so HANI2 leaves out `temperature`, `top_p` and `top_k` for them. |
| OpenAI (`openai`) | yes | yes: ChatGPT sign-in | A ChatGPT sign-in uses litellm's `chatgpt` provider, which calls the Codex backend with the plan's allowance. It takes models such as `gpt-5.5`. The device code is entered at `auth.openai.com/codex/device`. Turn on device-code sign-in in your ChatGPT security settings first. OpenAI recommends API keys for programmatic use ([OpenAI's authentication page](https://learn.chatgpt.com/docs/auth)). |
| Ollama Cloud (`ollama_cloud`) | yes (`OLLAMA_API_KEY`) | no | Calls `https://ollama.com` directly with a key from `ollama.com/settings/keys` ([Ollama's authentication page](https://docs.ollama.com/api/authentication)). |
| Ollama, local server (`ollama`) | — | through the server | Run `ollama signin` on the server once, then use cloud models through it: their names end in `-cloud`, for example `gpt-oss:120b-cloud`. Local models work as usual (`qwen3:4b-instruct`). |
| GitHub Copilot (`github_copilot`) | — | yes: GitHub device sign-in | Sign in with a GitHub account that has a Copilot plan; the code is entered at `github.com/login/device`. HANI2 uses the same device-code sign-in and token exchange as litellm's `github_copilot` provider, then calls the Copilot API with the short-lived token. That token endpoint is not a documented public API. GitHub supports Copilot plans in some third-party tools ([GitHub's changelog](https://github.blog/changelog/2026-01-16-github-copilot-now-supports-opencode/)). |
| Google Gemini (`gemini`) | yes (`GEMINI_API_KEY`) | no | |
| OpenRouter (`openrouter`) | yes (`OPENROUTER_API_KEY`) | no | |
| Groq, Mistral, DeepSeek (`groq`, `mistral`, `deepseek`) | yes | no | |
| Azure OpenAI (`azure`) | yes (`AZURE_API_KEY`) | no | Give the resource endpoint as the address and `api_version` as a parameter. |
| Amazon Bedrock (`bedrock`) | — | — | Uses the server's AWS credentials. |
| OpenAI-compatible server (`openai_compatible`) | optional | — | vLLM, LM Studio, a gateway: give the `/v1` address. |
| Other litellm provider (`litellm`) | optional | — | Any litellm provider, by litellm's name. |

The two subscription sign-ins (OpenAI with a ChatGPT plan, GitHub Copilot) are **experimental**.
They follow litellm's own implementation (litellm 1.109.1), and HANI2's tests run them against
simulated providers only. Neither OpenAI's nor GitHub's documentation says in general whether a
plan may be used from other applications, so check the plan's terms yourself.

`hani2 connections providers` prints the same table. The **Providers and sign-in methods** list on
the Connections page shows what each preset was checked against.

!!! warning "Subscriptions and studies"
    A subscription is a personal plan. Serving study participants from your personal subscription
    may breach the provider's terms, which are usually written for one person's own use. For
    studies, use API keys billed to your project.

## Model chains

A chain is a list of entries. Each entry gives:

| Key | Meaning |
| --- | --- |
| `connection` | The connection to use, by name. |
| `provider` | Instead of `connection`: use the provider's first connection (or its implicit one). |
| `model` | The model id, as the provider names it. |
| `params` | Optional parameters passed to the call: `temperature`, `max_tokens`, `top_p`, `effort` (or `reasoning`, sent as `reasoning_effort`) and any other litellm parameter. Keys, tokens, headers and addresses are refused here; they belong to a connection. |
| `label` | An optional name shown in the console and the results. |

Entries are identified by their position, so a model can appear more than once with different
parameters, and a provider can appear more than once with different models. An entry can also be
written as a short `connection:model` or `provider:model` text. Only the first colon splits it, so
`ollama:qwen3:4b` is the model `qwen3:4b` of Ollama.

Chains are kept per **purpose**, in a `models.json` file:

```json title="models.json"
{
  "default": [
    {"connection": "claude", "model": "claude-sonnet-5-5", "params": {"max_tokens": 1500}},
    {"connection": "ollama-cloud", "model": "gpt-oss:120b"},
    {"connection": "ollama-cloud", "model": "gpt-oss:120b", "params": {"temperature": 0.1}, "label": "cool"},
    "ollama:qwen3:4b-instruct"
  ],
  "judge": ["claude:claude-opus-5-5"]
}
```

| Purpose | Used by |
| --- | --- |
| `default` | Every purpose without its own chain. |
| `assistant` | The Assistant and its autopilot. |
| `opponent` | LLM opponents (negmas-llm negotiators). |
| `tools` | Tools built on `LLMTool` or calling `Tool.ask_llm()`, and `hani2.llm_service.complete()`. |
| `text` | Writing a message for an offer, reading an offer out of a message, and the admin `LLM` tool. |
| `judge` | The evaluation judge (LLM metrics of recordings). |

A bare list is the `default` chain. Edit chains on the **Models** page of the admin console. It
works per layer (settings folder, project or study, like every other setting). There you can
reorder, duplicate and remove entries, edit their parameters, test one entry, and press
**Test chains** to see which entry each purpose resolves to now, with the reason each skipped entry
was skipped.

### Where a chain comes from

For each purpose, HANI2 looks at these places in order. The first one that gives a chain for the
purpose, or a `default` chain, wins:

1. the active **study**'s `models.json`;
2. its **project**'s `models.json`;
3. the **start-time list**, from `hani2 --models …` or `HANI2_MODELS`;
4. the **settings folder**'s `models.json`, which is the admin's global chain;
5. the **old single-model settings**: `provider` and `model` in `assistant_settings.json` (for
   the Assistant) and in `llm_settings.json` (for everything else), read as a one-entry chain.

When a study is active, its settings override everything else, including the start-time list. A
study's `default` chain also beats a per-purpose chain set further down, for example an `assistant`
chain in the settings folder. Old `provider`/`model` keys written in a study's or project's own
`assistant_settings.json` or `llm_settings.json` count as that layer's chain, as long as the layer
has no `models.json`.

**Example.** The server runs with `hani2 --models "anthropic:claude-sonnet-5-5,ollama:qwen3:4b"`. The
settings folder's `models.json` has `{"default": ["openai:gpt-5"], "judge": ["openai:gpt-5-mini"]}`.
Study `HAN2027/pilot` has `models.json` with `["ollama-cloud:gpt-oss:120b"]`.

| Session | Assistant | Judge |
| --- | --- | --- |
| In study `HAN2027/pilot` | `ollama-cloud:gpt-oss:120b` (the study) | `ollama-cloud:gpt-oss:120b` (the study) |
| In another study, with no chain of its own | `claude-sonnet-5-5`, else `qwen3:4b` (start list) | the same (start list) |
| Server started without `--models` | `openai:gpt-5` (settings) | `openai:gpt-5-mini` (settings) |

`hani2 models list [--study P/S]` prints the chain each purpose uses and where it comes from.
`hani2 models resolve [--study P/S] [--purpose assistant]` also checks the providers and prints
the entry each purpose would use now.

### The start-time list

```bash
hani2 --models "anthropic:claude-sonnet-5-5,openai:gpt-5,ollama:qwen3:4b"
HANI2_MODELS="copilot:gpt-5,ollama:qwen3:4b" hani2
```

The list is a comma-separated `provider:model` or `connection:model` list. For each provider it
uses the provider's first connection, or its implicit one. It replaces the settings folder's chains
for every purpose. A project's or a study's own chain still wins. `hani2` refuses a list it cannot
read, and it refuses `--models` when `HANI2_MODELS` is set to a different list.

## Choosing an entry

An entry is **available** when its connection exists, has credentials (a key, a set environment
variable, a sign-in) and passes a quick check:

| Provider | Check |
| --- | --- |
| Ollama (local and cloud) | `/api/tags` lists the model. |
| Anthropic | `/v1/models` accepts the key and lists the model. |
| OpenAI, OpenRouter, Groq, Mistral, DeepSeek, OpenAI-compatible | `/models` accepts the key and lists the model. |
| Gemini | `/v1beta/models` lists the model. |
| GitHub Copilot | The token exchange works and the plan lists the model. |
| ChatGPT sign-in, Bedrock, Azure, other litellm | The credentials are present (no request). |

Checks time out after 3 seconds (`HANI2_MODEL_PROBE_TIMEOUT`). Their results are cached: for 5
minutes when the check passes and 30 seconds when it fails. So starting a session never waits long
for a provider that is down. With `HANI2_MODEL_PROBE=off`, only the credentials are checked and
nothing is sent over the network.

**When a session chooses.** The Assistant's model is chosen when the session starts. The models of
the other purposes are chosen the first time the session needs them, for example when an LLM
opponent is created. Each choice is then kept for the whole session.

**When a call fails.** A call can fail hard: it cannot connect, the sign-in is refused, the model
is not found, the provider is overloaded or rate limited. HANI2 then moves the session's purpose to
the next available entry and retries the call, and records the switch as a `model_fallback` event.
Other errors are not retried, for example a request the model rejects. When no later entry is
available, the call fails with its own error and the session keeps its entry, so the next call
tries it again. LLM opponents call the model
themselves, so they keep the entry they were created with until the end of their negotiation.

**When nothing is available.** A chain you set up (study, project, start-time list or settings
folder) with no available entry fails visibly. The session shows a banner and a toast, and logs an
`error` event (`model_unavailable`) with every skipped entry and why it was skipped. The old
single-model settings work as before: when their check fails, HANI2 still uses them unchecked
(`status: unverified`), so an install that never set up a chain behaves as it always did.

**An Assistant's own settings.** Without any chain, an Assistant whose own settings name a
different `provider` and `model` (for example from a group file) uses that model. Any chain wins
over those keys.

**Claude 5 models**, through any provider (Anthropic, Copilot, OpenRouter, Bedrock), get no
`temperature`, `top_p` or `top_k`. The Claude models that refuse a forced tool choice (Opus 5.5,
Sonnet 5.5, Fable 5.1 and 5.2) are asked for an action with `tool_choice: auto`.

**Old local Ollama fallback.** Old settings that point Ollama at a remote server (`api_base`, or
`OLLAMA_API_BASE`, for example `https://ollama.com`) read as two entries: the remote server first,
then the local server (`HANI2_OLLAMA_LOCAL_BASE`, default `http://localhost:11434`). A model the
remote server does not have is found locally.

## What is recorded

| Where | What |
| --- | --- |
| `results.csv` (columns added after the existing ones) | `assistant_llm` and `opponent_llm` (`connection:model`); `assistant_llm_entry` and `opponent_llm_entry` (`<source>#<position>`, e.g. `study:HAN2027/pilot#2`); `llm_models`: a JSON record of every purpose the session used. |
| Events | `model_resolved` when a purpose is chosen, `model_fallback` when a hard failure moves it on, `error`/`model_unavailable` when nothing is available. |
| Recordings (`.hrec`) | The same events, plus `models` in the `start` record and the Assistant's model in `support_agent`. |

Each record holds the purpose, the status (`ok`, `unverified` or `none`), the source layer, the
position in the chain and its length, the label, the connection, the provider, the sign-in method,
the model, the litellm model string, the entry's parameters, the skipped entries with their reasons,
and any error. It never holds a key, a token or a header value.

## Admin API

All of these are admin only.

| Endpoint | What it does |
| --- | --- |
| `GET /api/admin/providers` | The provider table and the purposes. |
| `GET /api/admin/connections` | The connections, masked (`?implicit=false` leaves out the implicit ones). |
| `POST /api/admin/connections` | Add one: `{name, provider, auth, api_key?, api_key_env?, base_url?, litellm_provider?, headers?}`. |
| `PUT` / `DELETE /api/admin/connections/{name}` | Change (a missing `api_key` keeps the stored one) or remove one. |
| `POST /api/admin/connections/{name}/test` | Check the credentials, and `{model}` if given; lists the provider's models when it can. |
| `POST` / `GET` / `DELETE /api/admin/connections/{name}/login` | Start a device-code sign-in (returns `user_code` and `verification_uri`), poll it, or sign out. |
| `GET /api/admin/models?layer=…` | A layer's own chains, the chains in effect there and what it inherits (with their sources). |
| `PUT /api/admin/models?layer=…` | Replace a layer's chains (`{}` removes them). As with every setting, a console opened in a study must name the layer (409 otherwise). |
| `POST /api/admin/models/resolve?layer=…` | Which entry each purpose resolves to; `{chains}` tries a chain you have not saved yet. |
| `POST /api/admin/models/test-entry` | Check one entry; with `"call": true`, also send a one-word request. |

Connection endpoints accept no layer other than `settings`. `models` is also a settings kind of
`/api/admin/settings/{kind}`, and that endpoint checks chains in the same way.

## From Python

```python
from hani2 import model_chain

res = model_chain.resolve("assistant")          # the first available entry
print(res.short(), res.record())                # "claude:claude-sonnet-5-5", the record above
reply = model_chain.completion("tools", [{"role": "user", "content": "Hi"}])
```

In a tool, `self.ask_llm(prompt)` uses the session's `tools` model. `session.models` holds the
entries the session uses (`session.models.get("opponent")`). See the
[Python API](../reference/api.md#models-and-connections).
