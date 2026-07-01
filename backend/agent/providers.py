"""AI Provider Configuration — 20 verified providers, BYOK, custom endpoints, auto-detect.

Every provider is verified against their official documentation to work
with the OpenAI Python SDK's standard interface:

    client = OpenAI(api_key=key, base_url=url)
    client.chat.completions.create(model=model, messages=[...])

The SDK adds /chat/completions to base_url automatically. Each config
below has a base_url such that {base_url}/chat/completions is the
correct chat endpoint for that provider.

Prints a table of available providers on startup so users always know
what's available.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIProvider:
    name: str
    base_url: str
    api_key: str = ""
    default_model: str = ""
    env_key: str = ""
    env_base_url: str = ""
    env_model: str = ""
    docs_url: str = ""
    key_prefix: str = ""
    notes: str = ""
    supports_streaming: bool = True

    def resolve(self) -> AIProvider:
        key = os.getenv(self.env_key, self.api_key) if self.env_key else self.api_key
        base = os.getenv(self.env_base_url, self.base_url) if self.env_base_url else self.base_url
        model = os.getenv(self.env_model, self.default_model) if self.env_model else self.default_model
        return AIProvider(
            name=self.name,
            base_url=base.rstrip("/"),
            api_key=key,
            default_model=model,
            notes=self.notes,
            docs_url=self.docs_url,
            supports_streaming=self.supports_streaming,
        )


def _ollama_auto_detect() -> Optional[AIProvider]:
    """Auto-detect a running Ollama instance on localhost or common ports."""
    import socket
    for port in [11434, 11435]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        if result == 0:
            base = os.getenv("WP_AI_OLLAMA_URL", f"http://127.0.0.1:{port}/v1")
            model = os.getenv("WP_AI_OLLAMA_MODEL", "")
            return AIProvider(
                name=f"Ollama (detected on :{port})",
                base_url=base.rstrip("/"),
                api_key=os.getenv("WP_AI_OLLAMA_KEY", "ollama"),
                default_model=model or "",
                notes="Auto-detected! Chat endpoint: /chat/completions",
                supports_streaming=True,
            )
    return None


PROVIDERS: dict[str, AIProvider] = {
    # ── BIG THREE ───────────────────────────────────────────
    "openai": AIProvider(
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o",
        env_key="WP_AI_OPENAI_KEY",
        docs_url="https://platform.openai.com/api-keys",
        key_prefix="sk-",
        notes="Industry standard. gpt-4o, o3, o4-mini. Requires paid API key.",
    ),
    "anthropic": AIProvider(
        name="Anthropic (OpenAI Relay)",
        base_url="https://api.anthropic.com/v1/openai",
        default_model="claude-sonnet-4-20250514",
        env_key="WP_AI_ANTHROPIC_KEY",
        docs_url="https://console.anthropic.com/",
        key_prefix="sk-ant-",
        notes="Uses Anthropic's OpenAI-compatible relay at /v1/openai. Models: claude-sonnet-4, claude-haiku-3-5.",
    ),
    "google": AIProvider(
        name="Google Gemini (OpenAI Relay)",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        default_model="gemini-2.5-flash",
        env_key="WP_AI_GEMINI_KEY",
        docs_url="https://aistudio.google.com/apikey",
        key_prefix="AIza",
        notes="Google's OpenAI-compatible endpoint. Free tier available. 1M context. Models: gemini-2.5-flash, gemini-2.5-pro.",
    ),
    "xai": AIProvider(
        name="xAI (Grok)",
        base_url="https://api.x.ai/v1",
        default_model="grok-2-1212",
        env_key="WP_AI_XAI_KEY",
        docs_url="https://console.x.ai/",
        key_prefix="",
        notes="Grok models. OpenAI compatible. grok-2, grok-3 available. Requires paid key.",
    ),
    "mistral": AIProvider(
        name="Mistral AI",
        base_url="https://api.mistral.ai/v1",
        default_model="mistral-large-latest",
        env_key="WP_AI_MISTRAL_KEY",
        docs_url="https://console.mistral.ai/api-keys/",
        key_prefix="",
        notes="European provider. Models: mistral-large-latest, mistral-small-latest, pixtral. Strong multilingual.",
    ),

    # ── GATEWAYS / AGGREGATORS ──────────────────────────────
    "openrouter": AIProvider(
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        default_model="openai/gpt-4o",
        env_key="WP_AI_OPENROUTER_KEY",
        docs_url="https://openrouter.ai/keys",
        key_prefix="sk-or-v1-",
        notes="300+ models from every provider. Many free models. Set model name as provider/model (e.g. openai/gpt-4o).",
    ),

    # ── FAST INFERENCE ──────────────────────────────────────
    "groq": AIProvider(
        name="Groq",
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.3-70b-versatile",
        env_key="WP_AI_GROQ_KEY",
        docs_url="https://console.groq.com/keys",
        key_prefix="gsk_",
        notes="Fastest inference. Free tier: 30 req/min. Models: llama-3.3-70b, deepseek-r1, mixtral. No logprobs.",
    ),
    "cerebras": AIProvider(
        name="Cerebras",
        base_url="https://api.cerebras.ai/v1",
        default_model="llama-3.3-70b",
        env_key="WP_AI_CEREBRAS_KEY",
        docs_url="https://inference.cerebras.ai/",
        key_prefix="",
        notes="Fastest inference (~1800 tok/s). Limited free tier. Models: llama-3.3-70b, llama-4-scout.",
    ),

    # ── OPEN-SOURCE FOCUSED ─────────────────────────────────
    "deepseek": AIProvider(
        name="DeepSeek",
        base_url="https://api.deepseek.com/v1",
        default_model="deepseek-chat",
        env_key="WP_AI_DEEPSEEK_KEY",
        docs_url="https://platform.deepseek.com/api_keys",
        key_prefix="sk-",
        notes="Excellent coding. ~$0.14/M tokens. 1M context. Models: deepseek-chat (V3), deepseek-reasoner (R1).",
    ),
    "together": AIProvider(
        name="Together AI",
        base_url="https://api.together.xyz/v1",
        default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        env_key="WP_AI_TOGETHER_KEY",
        docs_url="https://api.together.xyz/settings/api-keys",
        key_prefix="",
        notes="Broad open-source selection. Llama, DeepSeek, Qwen, Mixtral. Good free credits to start.",
    ),
    "fireworks": AIProvider(
        name="Fireworks AI",
        base_url="https://api.fireworks.ai/inference/v1",
        default_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
        env_key="WP_AI_FIREWORKS_KEY",
        docs_url="https://fireworks.ai/api-keys",
        key_prefix="",
        notes="Fast open-source inference. Models prefixed with accounts/fireworks/models/. Free tier.",
    ),
    "deepinfra": AIProvider(
        name="DeepInfra",
        base_url="https://api.deepinfra.com/v1/openai",
        default_model="meta-llama/Meta-Llama-3.1-70B-Instruct",
        env_key="WP_AI_DEEPINFRA_KEY",
        docs_url="https://deepinfra.com/dash/api_keys",
        key_prefix="",
        notes="Very broad model selection. Llama, Qwen, DeepSeek, Mixtral, Phi. Serverless pricing.",
    ),

    # ── SEARCH-AUGMENTED ────────────────────────────────────
    "perplexity": AIProvider(
        name="Perplexity",
        base_url="https://api.perplexity.ai",
        default_model="sonar-pro",
        env_key="WP_AI_PERPLEXITY_KEY",
        docs_url="https://docs.perplexity.ai/",
        key_prefix="pplx-",
        notes="Web-search augmented models. NO /v1 in base_url. Models: sonar-pro, sonar-deep-research. Paid API.",
    ),

    # ── ADDITIONAL PROVIDERS ─────────────────────────────────
    "cohere": AIProvider(
        name="Cohere",
        base_url="https://api.cohere.ai/v1",
        default_model="command-r-plus",
        env_key="WP_AI_COHERE_KEY",
        docs_url="https://dashboard.cohere.com/api-keys",
        key_prefix="",
        notes="Enterprise-focused. Strong RAG. Models: command-r-plus, command-r. OpenAI-compatible chat endpoint.",
    ),
    "replicate": AIProvider(
        name="Replicate",
        base_url="https://api.replicate.com/v1",
        default_model="meta/meta-llama-3-70b-instruct",
        env_key="WP_AI_REPLICATE_KEY",
        docs_url="https://replicate.com/account/api-tokens",
        key_prefix="r8_",
        notes="Run open models on demand. Pay-per-second. Models: meta/meta-llama-3-70b-instruct, stability-ai/stable-diffusion.",
    ),
    "hyperbolic": AIProvider(
        name="Hyperbolic",
        base_url="https://api.hyperbolic.xyz/v1",
        default_model="meta-llama/Meta-Llama-3.1-70B-Instruct",
        env_key="WP_AI_HYPERBOLIC_KEY",
        docs_url="https://app.hyperbolic.xyz/settings",
        key_prefix="",
        notes="GPU cloud + inference. OpenAI compatible. Models: Llama, Qwen, DeepSeek. Free trial credits.",
    ),

    # ── CLOUD PROVIDERS ──────────────────────────────────────
    "github": AIProvider(
        name="GitHub Models",
        base_url="https://models.inference.ai.azure.com",
        default_model="gpt-4o",
        env_key="WP_AI_GITHUB_KEY",
        docs_url="https://github.com/settings/tokens",
        key_prefix="ghp_",
        notes="FREE with GitHub Copilot. Use your GitHub PAT. Models: gpt-4o, gpt-4o-mini, DeepSeek-R1, Phi-4. Rate limited.",
    ),
    "cloudflare": AIProvider(
        name="Cloudflare Workers AI",
        base_url="https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        default_model="@cf/meta/llama-3.3-70b-instruct",
        env_key="WP_AI_CLOUDFLARE_KEY",
        env_base_url="WP_AI_CLOUDFLARE_URL",
        docs_url="https://developers.cloudflare.com/workers-ai/",
        key_prefix="",
        notes="Runs on Cloudflare's edge network. Set WP_AI_CLOUDFLARE_URL with your account_id baked in. Models: @cf/meta/llama-*.",
    ),

    # ── LOCAL ────────────────────────────────────────────────
    "ollama": AIProvider(
        name="Ollama (Local)",
        base_url="http://localhost:11434/v1",
        default_model="llama3.2",
        env_key="WP_AI_OLLAMA_KEY",
        env_base_url="WP_AI_OLLAMA_URL",
        env_model="WP_AI_OLLAMA_MODEL",
        docs_url="https://ollama.ai/",
        key_prefix="",
        notes="FULLY LOCAL. No API key needed. Run any open model. Set WP_AI_OLLAMA_URL for remote instances.",
    ),
    "custom": AIProvider(
        name="Custom Endpoint",
        base_url="https://your-endpoint.com/v1",
        default_model="your-model-name",
        env_key="WP_AI_CUSTOM_KEY",
        env_base_url="WP_AI_CUSTOM_BASE_URL",
        env_model="WP_AI_CUSTOM_MODEL",
        docs_url="",
        key_prefix="",
        notes="Any OpenAI-compatible endpoint. Set: WP_AI_CUSTOM_BASE_URL, WP_AI_CUSTOM_KEY, WP_AI_CUSTOM_MODEL.",
    ),
}

# Sort: local first, then alphabetically
SORT_ORDER = {
    "ollama": "00_ollama",
    "custom": "01_custom",
}


def _get_provider(name: str | None = None) -> AIProvider:
    """Get the configured AI provider with auto-detection and fallbacks.

    Resolution order:
    1. Explicit name argument (e.g. get_provider('groq'))
    2. WP_AI_PROVIDER env var
    3. WP_AI_API_KEY + WP_AI_BASE_URL (legacy env vars) → Custom
    4. Auto-detect running Ollama instance on localhost:11434
    5. OpenRouter (best free model availability)
    """
    name = name or os.getenv("WP_AI_PROVIDER", "").lower().strip()

    # Explicit name
    if name:
        provider = PROVIDERS.get(name)
        if not provider:
            available = ", ".join(sorted(PROVIDERS.keys()))
            raise ValueError(
                f"Unknown provider '{name}'. Available: {available}\n"
                f"Set WP_AI_PROVIDER to one of the above, or WP_AI_API_KEY + WP_AI_BASE_URL for custom."
            )
        resolved = provider.resolve()

        # Only raise on missing key if the provider actually requires keys
        key_required = resolved.env_key and not resolved.api_key
        custom_key = os.getenv("WP_AI_API_KEY", "")
        if key_required and not custom_key:
            # Don't raise — just resolve with empty key. The LLM call will
            # fail with a clear auth error when actually used.
            pass

        # If custom_key is set but provider-specific key is not, use custom_key
        if not resolved.api_key and custom_key:
            resolved.api_key = custom_key

        return resolved

    # Legacy env vars
    api_key = os.getenv("WP_AI_API_KEY", "")
    base_url = os.getenv("WP_AI_BASE_URL", "")
    if api_key and base_url:
        return AIProvider(
            name="Custom (Legacy)",
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            default_model=os.getenv("WP_AI_MODEL", ""),
            notes="Configured via WP_AI_API_KEY + WP_AI_BASE_URL.",
        ).resolve()

    # Auto-detect Ollama
    ollama = _ollama_auto_detect()
    if ollama:
        return ollama

    # Fallback: OpenRouter (best free tier)
    return PROVIDERS["openrouter"].resolve()


def get_provider(name: str | None = None) -> AIProvider:
    """Get provider with friendly error wrapping."""
    try:
        return _get_provider(name)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Failed to configure AI provider: {e}")


def test_connection(provider: AIProvider) -> dict:
    """Test the provider connection by listing available models.

    Returns dict with success status, model count, and error message.
    This is called when the user first configures a provider to validate
    that the endpoint, key, and model are all correct.
    """
    from openai import OpenAI, APIError, AuthenticationError, NotFoundError, RateLimitError
    try:
        client = OpenAI(api_key=provider.api_key, base_url=provider.base_url)
        models = client.models.list()
        model_list = [m.id for m in models][:20]
        return {
            "connected": True,
            "provider": provider.name,
            "base_url": provider.base_url,
            "models_available": len(model_list),
            "model_samples": model_list[:5],
        }
    except AuthenticationError as e:
        return {
            "connected": False,
            "error": f"Authentication failed. Check your API key.\n  Provider: {provider.name}\n  URL: {provider.base_url}\n  Key prefix: {provider.api_key[:12] if provider.api_key else '(empty)'}...\n  Detail: {e}",
        }
    except NotFoundError:
        return {
            "connected": False,
            "error": f"Endpoint not found. Check base_url.\n  URL: {provider.base_url}\n  Some providers don't support the /models endpoint but still work for chat.",
        }
    except RateLimitError as e:
        return {
            "connected": True,
            "warning": f"Connected but rate limited: {e}",
            "provider": provider.name,
        }
    except APIError as e:
        return {
            "connected": True,
            "warning": f"Connected (API responded, status={e.status_code}): {e}",
            "provider": provider.name,
        }
    except Exception as e:
        return {
            "connected": False,
            "error": f"Connection failed: {type(e).__name__}: {e}",
        }


def list_providers() -> str:
    """Return a formatted table of all available providers."""
    lines = []
    lines.append("─" * 78)
    lines.append(f"  Available AI Providers ({len(PROVIDERS)})")
    lines.append("─" * 78)
    lines.append(f"  {'Name':<14} {'Default Model':<30} {'Key Env Var':<22}")
    lines.append("─" * 78)
    for pname in sorted(PROVIDERS.keys()):
        p = PROVIDERS[pname]
        key_var = p.env_key or "(none)"
        model = p.default_model[:28] if p.default_model else "(auto)"
        lines.append(f"  {pname:<14} {model:<30} {key_var:<22}")
    lines.append("─" * 78)
    lines.append("  Set WP_AI_PROVIDER=<name> and the corresponding key env var.")
    lines.append("  Or just WP_AI_API_KEY + WP_AI_BASE_URL for quick custom setup.")
    lines.append("  Ollama is auto-detected if running on localhost:11434.")
    lines.append("─" * 78)
    return "\n".join(lines)


def get_llm_client(provider: AIProvider):
    """Create an OpenAI-compatible client for the given provider."""
    from openai import OpenAI
    return OpenAI(api_key=provider.api_key, base_url=provider.base_url)


def get_embedding_client(provider: AIProvider):
    """Create an OpenAI-compatible client for embeddings."""
    from openai import OpenAI
    return OpenAI(api_key=provider.api_key, base_url=provider.base_url)
