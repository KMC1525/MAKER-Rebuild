"""Configuração persistente + variáveis de ambiente.

Chaves de API NUNCA são gravadas em disco: use variáveis de ambiente.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional

# nome → (tipo, url base, modelo padrão, variável de ambiente da chave)
PROVIDERS: Dict[str, Dict[str, Any]] = {
    "anthropic":  {"kind": "frontier", "protocol": "anthropic", "base_url": "https://api.anthropic.com",
                   "model": "claude-sonnet-5-5", "key_env": ["ANTHROPIC_API_KEY"]},
    "openai":     {"kind": "frontier", "protocol": "openai", "base_url": "https://api.openai.com/v1",
                   "model": "gpt-4.1", "key_env": ["OPENAI_API_KEY"]},
    "gemini":     {"kind": "frontier", "protocol": "gemini", "base_url": "https://generativelanguage.googleapis.com",
                   "model": "gemini-2.5-pro", "key_env": ["GEMINI_API_KEY", "GOOGLE_API_KEY"]},
    "openrouter": {"kind": "frontier", "protocol": "openai", "base_url": "https://openrouter.ai/api/v1",
                   "model": "anthropic/claude-sonnet-4.5", "key_env": ["OPENROUTER_API_KEY"]},
    "ollama":     {"kind": "local", "protocol": "ollama", "base_url": "http://localhost:11434",
                   "model": "qwen2.5-coder:14b", "key_env": []},
    "lmstudio":   {"kind": "local", "protocol": "openai", "base_url": "http://localhost:1234/v1",
                   "model": "local-model", "key_env": ["LMSTUDIO_API_KEY"]},
    "llamacpp":   {"kind": "local", "protocol": "openai", "base_url": "http://localhost:8080/v1",
                   "model": "local-model", "key_env": []},
    "vllm":       {"kind": "local", "protocol": "openai", "base_url": "http://localhost:8000/v1",
                   "model": "local-model", "key_env": ["VLLM_API_KEY"]},
    "openai-compat": {"kind": "local", "protocol": "openai", "base_url": "http://localhost:8080/v1",
                      "model": "local-model", "key_env": ["OPENAI_COMPAT_API_KEY"]},
    "mock":       {"kind": "mock", "protocol": "mock", "base_url": "", "model": "mock-1", "key_env": []},
}
ALIASES = {"claude": "anthropic", "gpt": "openai", "google": "gemini", "local": "ollama",
           "lm-studio": "lmstudio", "llama.cpp": "llamacpp", "offline": "mock"}


def config_dir() -> Path:
    base = os.environ.get("MAKER_REBUILD_HOME")
    if base:
        return Path(base)
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "maker-rebuild"


@dataclass
class Config:
    provider: str = "anthropic"
    model: str = ""
    base_url: str = ""
    temperature: float = 0.4
    max_tokens: int = 16000
    timeout: int = 900
    context_chars: int = 60000      # orçamento de contexto enviado por chamada (chars)
    language: str = "pt-BR"         # idioma das mensagens/relatórios da IA
    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def provider_name(self) -> str:
        return ALIASES.get(self.provider, self.provider)

    def resolved(self) -> Dict[str, Any]:
        spec = dict(PROVIDERS.get(self.provider_name, PROVIDERS["openai-compat"]))
        if self.model:
            spec["model"] = self.model
        if self.base_url:
            spec["base_url"] = self.base_url.rstrip("/")
        return spec

    def api_key(self) -> Optional[str]:
        spec = PROVIDERS.get(self.provider_name, {})
        for env in spec.get("key_env", []):
            if os.environ.get(env):
                return os.environ[env]
        return os.environ.get("MAKER_REBUILD_API_KEY")


def load_config() -> Config:
    cfg = Config()
    path = config_dir() / "config.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for k, v in data.items():
                if hasattr(cfg, k):
                    setattr(cfg, k, v)
        except (OSError, ValueError):
            pass
    cfg.provider = os.environ.get("MAKER_REBUILD_PROVIDER", cfg.provider)
    cfg.model = os.environ.get("MAKER_REBUILD_MODEL", cfg.model)
    cfg.base_url = os.environ.get("MAKER_REBUILD_BASE_URL", cfg.base_url)
    return cfg


def save_config(cfg: Config) -> Path:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / "config.json"
    data = asdict(cfg)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
