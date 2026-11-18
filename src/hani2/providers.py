"""Language-model providers HANI2 can connect to, and how each one signs in.

Every call goes through `litellm <https://docs.litellm.ai>`_, so any provider litellm
supports can be used (the ``litellm`` provider below takes litellm's own provider name).
The presets here add a default address, the environment variable that usually holds the
key, a cheap availability check and the sign-in methods the provider supports.

Sign-in methods (``auth``):

``api_key``       a key pasted into the admin console (stored only in the settings folder, 0600)
``api_key_env``   the name of an environment variable that holds the key
``subscription``  a sign-in with the provider's own device-code flow (a code shown in the
                  console, confirmed on the provider's site); the token is kept in the settings folder
``none``          nothing (a local server, or credentials from the environment such as AWS)

What was checked for each subscription flow is in :data:`PROVIDERS` (``sources``) and in the
models guide of the documentation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

AUTH_METHODS = ("api_key", "api_key_env", "subscription", "none")


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
    probe: str = "credentials"  # anthropic | openai_models | ollama_tags | gemini | copilot | chatgpt | credentials
    #: where to get a key / how to sign in (shown in the console)
    help: str = ""
    #: the litellm provider used for a ``subscription`` connection (if different)
    subscription_litellm: str = ""
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
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "litellm": self.litellm, "auth": list(self.auth), "env": self.env,
            "base_url": self.base_url, "help": self.help, "no_subscription": self.no_subscription,
            "notes": self.notes, "sources": list(self.sources), "examples": list(self.examples),
            "needs_base_url": self.needs_base_url, "featured": self.featured,
            "subscription": "subscription" in self.auth,
        }


_ANTHROPIC_TERMS = "https://code.claude.com/docs/en/legal-and-compliance"

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
        "openai", "OpenAI", "openai", ("api_key", "api_key_env", "subscription"), env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1", probe="openai_models", featured=True, subscription_litellm="chatgpt",
        help="API key: platform.openai.com/api-keys. Subscription: sign in with a ChatGPT plan "
             "(device code at auth.openai.com/codex/device; enable device code sign-in in your ChatGPT "
             "security settings first).",
        notes="A ChatGPT sign-in calls the Codex backend through litellm's chatgpt provider (models such as "
              "gpt-5.5); usage counts against the plan's Codex allowance. OpenAI recommends API keys for "
              "programmatic and shared use. Experimental: the sign-in follows litellm's source; "
              "calls through it were not tried against the live service.",
        sources=("litellm/llms/chatgpt/authenticator.py (litellm 1.109.1)", "https://learn.chatgpt.com/docs/auth"),
        examples=("gpt-5.5", "gpt-5", "gpt-5-mini"),
    ),
    Provider(
        "ollama_cloud", "Ollama Cloud (ollama.com)", "ollama", ("api_key", "api_key_env"), env="OLLAMA_API_KEY",
        base_url="https://ollama.com", probe="ollama_tags", featured=True,
        help="Create a key at ollama.com/settings/keys.",
        no_subscription="ollama.com accepts API keys; to use an Ollama account sign-in instead, run "
                        "`ollama signin` on the server and use the local Ollama provider with the cloud "
                        "models (names ending in -cloud).",
        sources=("https://docs.ollama.com/api/authentication", "https://docs.ollama.com/cloud"),
        examples=("gpt-oss:120b", "qwen3-coder:480b", "deepseek-v3.1:671b"),
    ),
    Provider(
        "ollama", "Ollama (local server)", "ollama", ("none",), base_url="http://localhost:11434",
        probe="ollama_tags", featured=True,
        help="A local Ollama server. Run `ollama signin` on it to use cloud models through it "
             "(model names ending in -cloud, e.g. gpt-oss:120b-cloud).",
        sources=("https://docs.ollama.com/api/authentication",),
        examples=("qwen3:4b-instruct", "gpt-oss:120b-cloud", "llama3.2"),
    ),
    Provider(
        "github_copilot", "GitHub Copilot", "openai", ("subscription",), base_url="https://api.githubcopilot.com",
        probe="copilot", featured=True,
        help="Sign in with a GitHub account that has a Copilot plan (device code at github.com/login/device).",
        notes="Uses the Copilot device-code sign-in and token exchange that litellm's github_copilot provider "
              "uses; requests go to the Copilot API with the exchanged token. The Copilot token endpoint is "
              "not a documented public API; use it within your Copilot plan's terms. Experimental: the "
              "sign-in follows litellm's source; calls through it were not tried against the live service.",
        no_subscription="",
        sources=("litellm/llms/github_copilot/per_user_auth.py and authenticator.py (litellm 1.109.1)",
                 "https://github.blog/changelog/2026-01-16-github-copilot-now-supports-opencode/"),
        examples=("gpt-5", "claude-sonnet-5-5", "gpt-5-mini"),
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
    Provider("litellm", "Other litellm provider", "", ("api_key", "api_key_env", "none"),
             help="Any provider litellm supports: give litellm's provider name (e.g. together_ai, xai, "
                  "fireworks_ai, cohere, vertex_ai).", examples=("<model id>",)),
]}

#: providers people write in a ``provider:model`` list that are named differently here
ALIASES = {"claude": "anthropic", "ollama.com": "ollama_cloud", "ollama-cloud": "ollama_cloud",
           "copilot": "github_copilot", "github-copilot": "github_copilot", "chatgpt": "openai",
           "google": "gemini", "vllm": "openai_compatible", "openai-compatible": "openai_compatible"}


def get(provider_id: str) -> Provider | None:
    pid = (provider_id or "").strip().lower()
    return PROVIDERS.get(ALIASES.get(pid, pid))


def known(provider_id: str) -> bool:
    return get(provider_id) is not None


def table() -> list[dict[str, Any]]:
    """Every provider with its sign-in methods (featured first)."""
    return [p.to_dict() for p in sorted(PROVIDERS.values(), key=lambda p: (not p.featured, list(PROVIDERS).index(p.id)))]
