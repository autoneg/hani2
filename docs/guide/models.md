# Models and connections

HANI2 can use several language models and try them in order. You set this up in two steps:

1. **Connections** sign in to model providers, with an API key or nothing at all for a local
   server, or run an installed agent harness ([Harnesses](#harnesses)). Connections are shared
   by every project and study.
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
hani2 connections add pi-claude --provider pi --upstream anthropic --auth api_key_env   # a harness
hani2 connections list
hani2 connections test claude --model claude-sonnet-5-5
```

### Sign-in methods

| Method | What it is | Where the secret is kept |
| --- | --- | --- |
| `api_key` | A key pasted into the console (or typed after `--key`). | `settings/secrets/connections.json`, readable only by the server's user (mode 0600). |
| `api_key_env` | The name of an environment variable that holds the key. | The server's environment. |
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
| OpenAI (`openai`) | yes | **not offered** | See [Subscription sign-ins](#subscription-sign-ins-are-not-offered). |
| Ollama Cloud (`ollama_cloud`) | yes (`OLLAMA_API_KEY`) | no | Calls `https://ollama.com` directly with a key from `ollama.com/settings/keys` ([Ollama's authentication page](https://docs.ollama.com/api/authentication)). |
| Ollama, local server (`ollama`) | — | — | Local models (`qwen3:4b-instruct`). Cloud models through the server (names ending in `-cloud`) are accepted and use the server's `ollama signin` account; check that the account's plan covers your use. |
| GitHub Copilot (`github_copilot`) | — | **not offered** | See [Subscription sign-ins](#subscription-sign-ins-are-not-offered). |
| Google Gemini (`gemini`) | yes (`GEMINI_API_KEY`) | no | |
| OpenRouter (`openrouter`) | yes (`OPENROUTER_API_KEY`) | no | |
| Groq, Mistral, DeepSeek (`groq`, `mistral`, `deepseek`) | yes | no | |
| Azure OpenAI (`azure`) | yes (`AZURE_API_KEY`) | no | Give the resource endpoint as the address and `api_version` as a parameter. |
| Amazon Bedrock (`bedrock`) | — | — | Uses the server's AWS credentials. |
| OpenAI-compatible server (`openai_compatible`) | optional | — | vLLM, LM Studio, a gateway: give the `/v1` address. |
| Other litellm provider (`litellm`) | optional | — | Any litellm provider, by litellm's name. |
| Claude Code, Codex, pi (`claude-code`, `codex`, `pi`) | yes | no | Agent harnesses; see [Harnesses](#harnesses). |

`hani2 connections providers` prints the same table. The **Providers and sign-in methods** list on
the Connections page shows what each preset was checked against.

### Subscription sign-ins are not offered

HANI2 serves study participants, so a sign-in is offered only when the provider's terms clearly
allow a third-party application to use it that way. No personal plan sign-in passes that test
(checked on 2026-11-18):

| Sign-in | What the provider says | HANI2 |
| --- | --- | --- |
| Claude plans (Free, Pro, Max, Ultra) | "Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users." ([Anthropic's legal and compliance page](https://code.claude.com/docs/en/legal-and-compliance)) | API keys only. |
| ChatGPT plans | Requests "must originate from the user's local runtime or a remote runtime only that user controls"; prohibited: "Using one user's subscription to fulfill another user's requests." ([Sign in with ChatGPT terms](https://openai.com/policies/sign-in-with-chatgpt-terms/)); "You may not share your account credentials or make your account available to anyone else" ([Terms of Use](https://openai.com/policies/row-terms-of-use/)). | Not offered. |
| GitHub Copilot (device sign-in and Copilot token exchange) | The token exchange is not a documented public API; "Your login may only be used by one person" ([GitHub Terms of Service](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service)). The documented route for multi-user apps is the Copilot SDK with each user's own GitHub sign-in and plan ([Copilot SDK with GitHub OAuth](https://docs.github.com/en/copilot/how-tos/copilot-sdk/set-up-copilot-sdk/github-oauth)), a different mechanism. | Not offered. |
| Ollama account (`ollama signin`, `-cloud` models through a local server) | The feature is documented ([authentication](https://docs.ollama.com/api/authentication)); Ollama's [pricing](https://ollama.com/pricing) describes one account per person, with shared use on the Team plan, and the [terms](https://ollama.com/terms) apply. | Accepted: the model runs with the server's own sign-in. Check that the account's plan covers your use. |

A connection stored by an earlier version with a subscription sign-in (ChatGPT or Copilot) still
loads, **disabled**: it never resolves, every chain entry that names it is skipped with this reason,
and the Connections page shows it so you can remove it. The `chatgpt:` and `copilot:` entry
prefixes are skipped the same way.

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
HANI2_MODELS="openai:gpt-5,ollama:qwen3:4b" hani2
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
| A harness | The harness is installed, the key is present and the model is allowed (no request: a harness call is slow and costs money). |
| Bedrock, Azure, other litellm | The credentials are present (no request). |

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
HANI2 recognises these from the error's type and HTTP status (401, 402, 403, 404, 408, 429 and 5xx), or from a
message that says the model is not found or does not exist. Other errors are not retried, for example a request the
model rejects, or a message that only mentions that something else (a tool, a file) was not found. When no later entry is
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

**Claude 5 models**, through any provider (Anthropic, OpenRouter, Bedrock), get no
`temperature`, `top_p` or `top_k`. The Claude models that refuse a forced tool choice (Opus 5.5,
Sonnet 5.5, Fable 5.1 and 5.2) are asked for an action with `tool_choice: auto`.

**Old local Ollama fallback.** Old settings that point Ollama at a remote server (`api_base`, or
`OLLAMA_API_BASE`, for example `https://ollama.com`) read as two entries: the remote server first,
then the local server (`HANI2_OLLAMA_LOCAL_BASE`, default `http://localhost:11434`). A model the
remote server does not have is found locally.

## Harnesses

A **harness connection** calls the model through an installed agent harness instead of calling
the provider's API directly: **Claude Code** (through the Claude Agent SDK), the **Codex CLI** or
**pi**. It appears in model chains like any other connection (`{connection, model, params}`), has a
check and falls back the same way. Use one to compare the Assistant or the judge with what a
harness does with the same prompt, or to reach models through pi's provider set.

```bash
pip install 'hani2[harness]'      # the Claude Agent SDK (it bundles its own claude CLI); codex and pi need only their CLIs
hani2 connections add judge-claude --provider claude-code --auth api_key_env   # reads $ANTHROPIC_API_KEY
hani2 connections add judge-codex --provider codex --key                        # an OpenAI API key
hani2 connections add pi-claude --provider pi --upstream anthropic --key        # pi with an Anthropic key
hani2 connections add pi-local --provider pi --upstream ollama --auth none      # pi with a local Ollama
hani2 connections test pi-local --model qwen3:4b-instruct                      # a tiny request through the harness
```

`HANI2_CLAUDE_PATH`, `HANI2_CODEX_PATH` and `HANI2_PI_PATH` choose a harness's executable (default:
the SDK's bundled CLI, then `claude`, `codex` and `pi` on `PATH`).

### What each harness can do

| Harness | Completion | The Assistant's functions | Purposes | How it runs |
| --- | --- | --- | --- | --- |
| Claude Code (`claude-code`) | yes | yes (in-process MCP server) | `judge` and the console's Test only | One Agent SDK `query()` per call. |
| Codex CLI (`codex`) | yes | **no** | `judge` and the console's Test only | One `codex exec --json` per call, without any tool. |
| pi (`pi`) | yes | yes (a bridge extension over RPC) | every purpose | One `pi --mode rpc` per call. |

**Completion** (system prompt and messages in, text out) serves text extraction and writing,
`LLMTool` and `Tool.ask_llm()`, the judge and LLM opponents. Calls reach the harness through a
litellm custom provider, so code that calls litellm itself (negmas-llm opponents) works unchanged.
A call that passes function schemas through litellm is refused (only the Assistant's functions run
through a harness).

**The Assistant's functions.** The harness runs the turn. Each function it calls is executed by
the Assistant's own dispatcher, so capabilities, the `agent_action` events and the recording apply
as with any other model, and the call and its result are added to the Assistant's conversation as
an ordinary tool call. In an autopilot turn, the first action ends the turn's actions. A harness
without safe function calling (Codex) is skipped for the `assistant` purpose with the reason.

A conversation with earlier turns is sent as one prompt that writes out the history, with the
function calls and results. Each call starts a new harness session, so nothing is kept between
calls.

### Usage rules

Only API keys (or a local Ollama server for pi) are allowed: never a personal subscription, and
never the server user's own sign-in to the harness. Checked on 2026-11-18:

| Harness | Provider | What the sources say | Enforced in HANI2 |
| --- | --- | --- | --- |
| Claude Code | Anthropic | "Developers building products or services that interact with Claude's capabilities, including those using the Agent SDK, should use API key authentication through Claude Console or a supported cloud provider. Anthropic does not permit third-party developers to offer Claude.ai login into their own applications, or to route requests through Free, Pro, Max, or Ultra plan credentials on behalf of their users." On running Claude Code in products: "Customers may not pay for, resell, or intermediate Claude usage on their end users' behalf. Each end user must authenticate with their own Anthropic API key, Claude subscription plan credentials, or 3P inference provider credential" ([legal and compliance](https://code.claude.com/docs/en/legal-and-compliance); [Agent SDK overview](https://code.claude.com/docs/en/agent-sdk/overview)). | API key only (`--bare`: "OAuth and keychain are never read"); an isolated config folder. The Agent SDK's licence speaks of powering "products and services that you make available to your own customers and end users", but the end-user condition above cannot be met by study participants; where the terms leave doubt HANI2 does not take the risk, so Claude Code serves only the judge and the console's Test, never participants (HANI2's conservative reading; ask Anthropic for your case). For participants, use the `anthropic` provider (the API with a key). |
| Codex CLI | OpenAI | "Use API key authentication for programmatic Codex CLI workflows, such as CI/CD jobs. Don't expose Codex execution in untrusted or public environments." ([authentication](https://learn.chatgpt.com/docs/auth)); "App-server authentication has never been permitted for commercial or hosted services." ([app-server](https://learn.chatgpt.com/docs/app-server)); ChatGPT plans: see [above](#subscription-sign-ins-are-not-offered). | API key only, through a custom model provider that reads `OPENAI_API_KEY` (`requires_openai_auth = false`, `forced_login_method = "api"`); an isolated `CODEX_HOME`; no app-server; no tools; serves only the judge and the console's Test. |
| pi | any API-key provider; local Ollama | pi is open source ([github.com/earendil-works/pi](https://github.com/earendil-works/pi)) and can sign in to personal plans (Claude Pro/Max, ChatGPT, GitHub Copilot and others) by OAuth; those plans' own terms (above) apply. | An isolated agent folder (`PI_CODING_AGENT_DIR`) whose `auth.json` is reset to `{}` before every call, so no stored pi login is ever used; one API key, for one allowed upstream (Anthropic, OpenAI, Google Gemini, Mistral, Groq, DeepSeek, OpenRouter) or a local Ollama server; OAuth-only upstreams (`openai-codex`, `github-copilot`) are refused. |

### Safety

Participants' text reaches the prompts, so every harness runs locked down:

| | Claude Code | Codex CLI | pi |
| --- | --- | --- | --- |
| Built-in tools | none (`tools=[]`); only HANI2's functions (`mcp__hani2__…`) are allowed, with `permission_mode="dontAsk"` | none: shell, exec, image, goals, multi-agent, plugins, apps, hooks, memories, browser and computer use are disabled, web search is off, and the model's entry comes from Codex's bundled catalog with its patch and code-mode tools removed (a model not in the catalog is refused); read-only sandbox and `approval_policy = "never"` as a backstop | none (`--no-tools`, `--tools` lists only HANI2's functions) |
| Configuration | `setting_sources=[]`, `--strict-mcp-config`, `--bare`, `--disable-slash-commands`, no auto memory, `CLAUDE_CONFIG_DIR` and `HOME` isolated | `CODEX_HOME` and `HOME` isolated, `--ignore-user-config`, `--ignore-rules`, `project_doc_max_bytes = 0`, `--ephemeral` | `PI_CODING_AGENT_DIR` and `HOME` isolated, `--no-extensions` (only HANI2's bridge), `--no-mcp`, `--no-skills`, `--no-prompt-templates`, `--no-context-files`, `--no-approve`, `--offline`, `--no-session` |
| Participant text | sent verbatim (`verbatim_prompts`: no `@file` expansion, no slash commands) | on stdin, never in the command line | a leading `/`, `!` or `@` is escaped; no commands exist |
| System prompt | HANI2's (`system_prompt`) | HANI2's (`model_instructions_file`) | exactly HANI2's (the bridge replaces pi's) |

For every harness: the child's environment is built from an allowlist (`PATH`, locale, proxy and
certificate variables), never copied from the server's, so OAuth tokens and other keys of the
server never reach it; Claude Code's SDK merges its environment over the server's, so a launcher
reduces it again before the CLI starts. Each call runs in a new empty temporary folder, with caps on
time (`params.timeout`, default 120 s) and turns (`params.max_turns`, default 8 with functions, 1
without; Claude Code also takes `params.max_budget_usd`). `params.effort` sets the reasoning
effort where the harness has one. Keys never appear in a command line, an event, a result or a
recording, and errors are masked like every other error. Each connection's private folder is
`settings/secrets/<connection>/harness/` (0700); removing the connection deletes it.

### Limits

- **Speed.** A harness starts a process for each call (seconds, not milliseconds), so it is slower
  than an API call, most of all for LLM opponents, which call the model on every offer.
- **Cost.** The harness adds its own system prompt and, with functions, several model turns per
  call. Claude Code and pi report a cost (`cost` in the recording); Codex reports tokens only.
- **Checked against version.** The lockdown was checked against Claude Code 2.1.327 (Agent SDK
  0.2.184), Codex CLI 0.162.1 and pi 1.4.0 by capturing what each sends to a local stand-in
  server: only HANI2's system prompt, the prompt and HANI2's functions (Codex: none). A new
  harness version may add tools; Codex is run with `--strict-config`, so an option it no longer
  knows stops the call instead of being ignored.
- **Reproducibility.** The harness version changes what the model sees (system prompt, tool
  descriptions). The Connections page shows each harness's version; pin it for a study. The check
  sends no request, so a wrong model name shows only on the first call (then the chain falls back).
- Claude Code through Amazon Bedrock or Google Vertex is not offered yet; use an Anthropic API key.

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
| `GET /api/admin/providers` | The provider table, the purposes and the harnesses (`harnesses`: installed?, version, sign-in, purposes). |
| `GET /api/admin/connections` | The connections, masked (`?implicit=false` leaves out the implicit ones). |
| `POST /api/admin/connections` | Add one: `{name, provider, auth, api_key?, api_key_env?, base_url?, litellm_provider?, upstream?, headers?}`. |
| `PUT` / `DELETE /api/admin/connections/{name}` | Change (a missing `api_key` keeps the stored one) or remove one. |
| `POST /api/admin/connections/{name}/test` | Check the credentials, and `{model}` if given; lists the provider's models when it can. For a harness, sends a tiny request through it and returns the `reply`. |
| `DELETE /api/admin/connections/{name}/login` | Delete a connection's stored tokens (subscription sign-ins are not offered). |
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
