"""Contrato comum dos provedores de LLM."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


class LLMError(Exception):
    """Falha ao falar com o provedor (rede, autenticação, política, resposta inválida)."""


@dataclass
class LLMRequest:
    system: str
    messages: List[Dict[str, str]]
    max_tokens: int = 16000
    temperature: float = 0.4
    json_mode: bool = False
    task: str = ""
    model: Optional[str] = None


@dataclass
class Completion:
    text: str
    stop_reason: str = ""          # "stop" | "length" | "blocked" | ""
    usage: Dict[str, int] = field(default_factory=dict)


ChunkCb = Optional[Callable[[str], None]]


class Provider:
    name = "base"
    kind = "frontier"      # frontier | local | mock

    def __init__(self, spec: dict, api_key: Optional[str], timeout: int = 900, extras: Optional[dict] = None):
        self.spec = spec
        self.model = spec["model"]
        self.base_url = spec["base_url"].rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.extras = extras or {}

    def complete(self, req: LLMRequest, on_chunk: ChunkCb = None) -> Completion:  # pragma: no cover - abstract
        raise NotImplementedError

    def list_models(self) -> List[str]:
        return []

    def need_key(self) -> None:
        if not self.api_key:
            envs = " ou ".join(self.spec.get("key_env", [])) or "MAKER_REBUILD_API_KEY"
            raise LLMError(f"chave de API ausente para '{self.name}': defina a variável de ambiente {envs}")
