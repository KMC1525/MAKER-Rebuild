"""Provedores de LLM: frontier (Anthropic, OpenAI, Gemini, OpenRouter) e locais (Ollama, LM Studio, llama.cpp, vLLM)."""
from __future__ import annotations

from ..config import ALIASES, PROVIDERS, Config
from .anthropic import AnthropicProvider
from .base import Completion, LLMError, LLMRequest, Provider
from .gemini import GeminiProvider
from .mock import MockProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider

_BY_PROTOCOL = {"anthropic": AnthropicProvider, "openai": OpenAICompatProvider, "gemini": GeminiProvider,
                "ollama": OllamaProvider, "mock": MockProvider}


def make_provider(cfg: Config) -> Provider:
    name = ALIASES.get(cfg.provider, cfg.provider)
    if name not in PROVIDERS:
        raise LLMError(f"provedor desconhecido: {cfg.provider} (use: {', '.join(PROVIDERS)})")
    spec = cfg.resolved()
    cls = _BY_PROTOCOL[spec["protocol"]]
    p = cls(spec, cfg.api_key(), cfg.timeout, cfg.extras)
    p.name = name
    p.kind = spec["kind"]
    return p


__all__ = ["make_provider", "Provider", "LLMError", "LLMRequest", "Completion", "PROVIDERS"]
