"""Language-model providers HANI2 can connect to, and how each one signs in.

Every call goes through `litellm <https://docs.litellm.ai>`_, so any provider litellm
supports can be used (the ``litellm`` provider below takes litellm's own provider name).
The presets here add a default address, the environment variable that usually holds the
key, a cheap availability check and the sign-in methods the provider supports.

Sign-in methods (``auth``):

``api_key``       a key pasted into the admin console (stored only in the settings folder, 0600)
``api_key_env``   the name of an environment variable that holds the key
``subscription``  a sign-in with a personal plan. **Not offered by any provider**: see
                  :data:`NOT_OFFERED`. Stored connections of that kind load disabled.
``none``          nothing (a local server, or credentials from the environment such as AWS)

*Harnesses* (``claude-code``, ``codex``, ``pi``) are providers too: the call goes through an
installed agent harness (see :mod:`hani2.harness`), signed in with an API key only.

What was checked for each sign-in method is in :data:`PROVIDERS` (``sources``) and in the
models guide of the documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

AUTH_METHODS = ("api_key", "api_key_env", "subscription", "none")

#: why the subscription sign-ins (ChatGPT plans, GitHub Copilot) are not offered
NOT_OFFERED = "not offered: the provider's terms do not clearly allow use by third-party applications"


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    #: the litellm provider prefix of a model (``anthropic/claude-…``)
    litellm: str
    auth: tuple[str, ...]
    #: the environment variable that usually holds the key (``api_key_env`` default)
    env: str = ""
    base_url: str = ""
    #: how :mod:`hani2.connections` checks that a model can be used
    probe: str = "credentials"  # anthropic | openai_models | ollama_tags | gemini | harness | credentials
    #: where to get a key / how to sign in (shown in the console)
    help: str = ""
    #: why a subscription is not offered (shown in the console and the docs)
    no_subscription: str = ""
    #: notes shown next to the provider
    notes: str = ""
    #: sources checked for the sign-in methods
    sources: tuple[str, ...] = ()
    #: example model ids (placeholders in the console)
    examples: tuple[str, ...] = ()
    #: the connection needs a base URL
    needs_base_url: bool = False
    #: sampling parameters the provider's current models refuse (dropped from the request)
    drop_params: tuple[str, ...] = ()
    #: first-class provider (shown first)
    featured: bool = False
    #: the provider can be chosen for new connections (``False``: listed only to say why not)
    offered: bool = True
    #: why the provider is not offered
    not_offered: str = ""
    #: the agent harness this provider runs (``claude-code``, ``codex``, ``pi``; see :mod:`hani2.harness`)
    harness: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "litellm": self.litellm, "auth": list(self.auth), "env": self.env,
            "base_url": self.base_url, "help": self.help, "no_subscription": self.no_subscription,
            "notes": self.notes, "sources": list(self.sources), "examples": list(self.examples),
            "needs_base_url": self.needs_base_url, "featured": self.featured,
            "subscription": "subscription" in self.auth, "offered": self.offered, "not_offered": self.not_offered,
            "harness": self.harness,
        }


_ANTHROPIC_TERMS = "https://code.claude.com/docs/en/legal-and-compliance"
# checked for the decision not to offer ChatGPT-plan and Copilot sign-ins (2026-11-18)
_HARNESS_SOURCES = {
    "claude-code": (_ANTHROPIC_TERMS, "https://code.claude.com/docs/en/agent-sdk/overview"),
    "codex": ("https://learn.chatgpt.com/docs/auth", "https://openai.com/policies/sign-in-with-chatgpt-terms/"),
    "pi": ("https://github.com/earendil-works/pi", _ANTHROPIC_TERMS),
}
# ChatGPT plans: the Sign in with ChatGPT terms require requests from a runtime only the user
# controls and forbid "using one user's subscription to fulfill another user's requests".
_CHATGPT_SOURCES = ("https://openai.com/policies/sign-in-with-chatgpt-terms/",
                    "https://openai.com/policies/row-terms-of-use/",
                    "https://learn.chatgpt.com/docs/auth")
# Copilot: the copilot_internal token exchange is not a documented public API; GitHub's terms say a
# login is for one person; the documented multi-user route (the Copilot SDK with each user's own
# GitHub sign-in and plan) is a different mechanism, not this one.
_COPILOT_SOURCES = ("https://docs.github.com/en/site-policy/github-terms/github-terms-of-service",
                    "https://docs.github.com/en/copilot/how-tos/copilot-sdk/set-up-copilot-sdk/github-oauth",
                    "https://github.blog/changelog/2026-01-16-github-copilot-now-supports-opencode/")

PROVIDERS: dict[str, Provider] = {p.id: p for p in [
    Provider(
        "anthropic", "Anthropic (Claude API)", "anthropic", ("api_key", "api_key_env"), env="ANTHROPIC_API_KEY",
        base_url="https://api.anthropic.com", probe="anthropic", featured=True,
        help="Create a key in the Claude Console (platform.claude.com).",
        no_subscription="Anthropic does not permit third-party applications to sign in with Claude Free, Pro, "
                        "Max or Ultra plans or to route requests through those plan credentials; developers "
                        "must use an API key.",
        sources=(_ANTHROPIC_TERMS,),
        examples=("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5", "claude-fable-5-2"),
        # Claude 5 models refuse non-default sampling parameters
        drop_params=("temperature", "top_p", "top_k"),
    ),
    Provider(
        "openai", "OpenAI", "openai", ("api_key", "api_key_env"), env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1", probe="openai_models", featured=True,
        help="Create a key at platform.openai.com/api-keys.",
        no_subscription=f"ChatGPT plan sign-in is {NOT_OFFERED}. Use an API key.",
        sources=_CHATGPT_SOURCES,
        examples=("gpt-5.5", "gpt-5", "gpt-5-mini"),
    ),
    Provider(
        "ollama_cloud", "Ollama Cloud (ollama.com)", "ollama", ("api_key", "api_key_env"), env="OLLAMA_API_KEY",
        base_url="https://ollama.com", probe="ollama_tags", featured=True,
        help="Create a key at ollama.com/settings/keys.",
        no_subscription="ollama.com accepts API keys. An Ollama account sign-in (`ollama signin`, cloud "
                        "models through a local server) is not used: Ollama is one account per person.",
        sources=("https://docs.ollama.com/api/authentication", "https://docs.ollama.com/cloud"),
        examples=("gpt-oss:120b", "qwen3-coder:480b", "deepseek-v3.1:671b"),
    ),
    Provider(
        "ollama", "Ollama (local server)", "ollama", ("none",), base_url="http://localhost:11434",
        probe="ollama_tags", featured=True,
        help="A local Ollama server with local models. Cloud models through it (names ending in -cloud, "
             "after `ollama signin`) are refused: use an Ollama Cloud connection with an API key.",
        sources=("https://docs.ollama.com/api/authentication", "https://ollama.com/pricing", "https://ollama.com/terms"),
        examples=("qwen3:4b-instruct", "llama3.2", "gemma3:4b"),
    ),
    Provider(
        "github_copilot", "GitHub Copilot", "openai", (), offered=False, not_offered=f"Copilot sign-in is {NOT_OFFERED}.",
        help="Not offered.", sources=_COPILOT_SOURCES,
    ),
    Provider("gemini", "Google Gemini", "gemini", ("api_key", "api_key_env"), env="GEMINI_API_KEY",
             base_url="https://generativelanguage.googleapis.com", probe="gemini",
             help="Create a key in Google AI Studio.", examples=("gemini-2.5-pro", "gemini-2.5-flash")),
    Provider("openrouter", "OpenRouter", "openrouter", ("api_key", "api_key_env"), env="OPENROUTER_API_KEY",
             base_url="https://openrouter.ai/api/v1", probe="openai_models",
             help="Create a key at openrouter.ai/keys.", examples=("anthropic/claude-sonnet-5-5", "openai/gpt-5")),
    Provider("groq", "Groq", "groq", ("api_key", "api_key_env"), env="GROQ_API_KEY",
             base_url="https://api.groq.com/openai/v1", probe="openai_models", examples=("llama-3.3-70b-versatile",)),
    Provider("mistral", "Mistral", "mistral", ("api_key", "api_key_env"), env="MISTRAL_API_KEY",
             base_url="https://api.mistral.ai/v1", probe="openai_models", examples=("mistral-large-latest",)),
    Provider("deepseek", "DeepSeek", "deepseek", ("api_key", "api_key_env"), env="DEEPSEEK_API_KEY",
             base_url="https://api.deepseek.com", probe="openai_models", examples=("deepseek-chat",)),
    Provider("azure", "Azure OpenAI", "azure", ("api_key", "api_key_env"), env="AZURE_API_KEY",
             needs_base_url=True, help="Base URL: your Azure resource endpoint. Set api_version under params.",
             examples=("<deployment name>",)),
    Provider("bedrock", "Amazon Bedrock", "bedrock", ("none",),
             help="Uses the AWS credentials of the server (AWS_ACCESS_KEY_ID / AWS_PROFILE, AWS_REGION_NAME).",
             examples=("anthropic.claude-opus-5-5",)),
    Provider("openai_compatible", "OpenAI-compatible server", "openai", ("api_key", "api_key_env", "none"),
             probe="openai_models", needs_base_url=True,
             help="Any server with an OpenAI-style /v1 API (vLLM, LM Studio, a gateway, …).",
             examples=("<model id>",)),
    # agent harnesses (see hani2.harness): API keys only; every built-in tool off; isolated config
    Provider("claude-code", "Claude Code (Agent SDK)", "hani2_harness", ("api_key", "api_key_env"), env="ANTHROPIC_API_KEY",
             probe="harness", harness="claude-code", sources=_HARNESS_SOURCES["claude-code"],
             help="Runs Claude through the Claude Agent SDK (pip install 'hani2[harness]') and its claude CLI, "
                  "signed in with an Anthropic API key from the Claude Console only. Used only for the judge "
                  "and the console's Test.",
             no_subscription="Anthropic does not permit third-party applications to offer claude.ai login or "
                             "to route requests through Claude plan credentials; developers must use an API key.",
             examples=("claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5")),
    Provider("codex", "Codex CLI", "hani2_harness", ("api_key", "api_key_env"), env="OPENAI_API_KEY",
             probe="harness", harness="codex", sources=_HARNESS_SOURCES["codex"],
             help="Runs OpenAI models through the installed codex CLI (codex exec, no tools), signed in with an "
                  "OpenAI API key only. Used only for the judge and the console's Test.",
             no_subscription=f"ChatGPT plan sign-in is {NOT_OFFERED}. Use an API key.",
             examples=("gpt-5.5",)),
    Provider("pi", "pi", "hani2_harness", ("api_key", "api_key_env", "none"), probe="harness", harness="pi",
             sources=_HARNESS_SOURCES["pi"],
             help="Runs a model through the installed pi CLI (RPC mode) with one API-key provider (choose it "
                  "as 'Calls') or a local Ollama server.",
             no_subscription="pi's OAuth sign-ins to personal plans (Claude, ChatGPT, Copilot, …) are not used: "
                             "pi runs with an empty agent folder and one API key.",
             examples=("claude-haiku-5-5", "gpt-5-mini", "qwen3:4b-instruct")),
    Provider("litellm", "Other litellm provider", "", ("api_key", "api_key_env", "none"),
             help="Any provider litellm supports: give litellm's provider name (e.g. together_ai, xai, "
                  "fireworks_ai, cohere, vertex_ai).", examples=("<model id>",)),
]}

#: providers people write in a ``provider:model`` list that are named differently here
ALIASES = {"claude": "anthropic", "ollama.com": "ollama_cloud", "ollama-cloud": "ollama_cloud",
           "copilot": "github_copilot", "github-copilot": "github_copilot", "chatgpt": "openai",
           "google": "gemini", "vllm": "openai_compatible", "openai-compatible": "openai_compatible",
           "claude_code": "claude-code", "claude-agent-sdk": "claude-code", "codex-cli": "codex", "pi-agent": "pi"}


def get(provider_id: str) -> Provider | None:
    pid = (provider_id or "").strip().lower()
    return PROVIDERS.get(ALIASES.get(pid, pid))


def known(provider_id: str) -> bool:
    return get(provider_id) is not None


def table() -> list[dict[str, Any]]:
    """Every provider with its sign-in methods (featured first, those not offered last)."""
    order = list(PROVIDERS)
    return [p.to_dict() for p in sorted(PROVIDERS.values(),
                                        key=lambda p: (not p.offered, bool(p.harness), not p.featured, order.index(p.id)))]
