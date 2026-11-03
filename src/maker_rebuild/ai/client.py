"""Cliente de IA de alto nível: system prompt do projeto, cache em disco, spinner, JSON com reparo."""
from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import ui
from ..config import Config
from ..providers import LLMError, LLMRequest, Provider, make_provider
from . import prompts
from .jsonio import extract_json


class AIOutputError(Exception):
    """O modelo respondeu, mas a saída não pôde ser usada (JSON inválido/truncado)."""


def cache_dir() -> Path:
    base = os.environ.get("MAKER_REBUILD_CACHE") or os.path.join(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")), "maker-rebuild")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


class AIClient:
    def __init__(self, cfg: Config, provider: Optional[Provider] = None, use_cache: bool = True, quiet: bool = False):
        self.cfg = cfg
        self.provider = provider or make_provider(cfg)
        self.use_cache = use_cache
        self.quiet = quiet
        self.calls = 0
        self.cache_hits = 0
        self.chars_out = 0
        self._lock = threading.Lock()

    @property
    def label(self) -> str:
        return f"{self.provider.name}/{self.provider.model}"

    # ----------------------------------------------------------------- baixo nível
    def _key(self, system: str, user: str, task: str, temperature: float) -> str:
        h = hashlib.sha256(json.dumps([self.provider.name, self.provider.model, system, user, task, temperature],
                                      ensure_ascii=False).encode()).hexdigest()
        return h

    def complete(self, task: str, user: str, *, extra_system: str = "", with_api: bool = False, json_mode: bool = True,
                 max_tokens: Optional[int] = None, temperature: Optional[float] = None, cache: bool = False,
                 messages: Optional[List[Dict[str, str]]] = None, desc: str = "") -> str:
        system = prompts.system_prompt(extra_system, with_api, self.cfg.language)
        temp = self.cfg.temperature if temperature is None else temperature
        key = self._key(system, user if not messages else json.dumps(messages, ensure_ascii=False), task, temp)
        path = cache_dir() / f"{key}.json" if (cache and self.use_cache) else None
        if path and path.exists():
            try:
                self.cache_hits += 1
                return json.loads(path.read_text(encoding="utf-8"))["text"]
            except (OSError, ValueError, KeyError):
                pass
        req = LLMRequest(system=system, messages=messages or [{"role": "user", "content": user}],
                         max_tokens=max_tokens or self.cfg.max_tokens, temperature=temp, json_mode=json_mode, task=task)
        total = {"n": 0}

        def on_chunk(t: str) -> None:
            total["n"] += len(t)

        label = desc or task
        if self.quiet:
            comp = self.provider.complete(req, on_chunk)
        else:
            with ui.Spinner(f"{label} ({self.label})") as sp:
                def cb(t: str) -> None:
                    on_chunk(t)
                    sp.update(f"{total['n']} chars")
                comp = self.provider.complete(req, cb)
        with self._lock:
            self.calls += 1
            self.chars_out += len(comp.text)
        if comp.stop_reason == "blocked":
            raise LLMError("o provedor bloqueou/recusou a resposta (política do provedor). "
                           "Para conteúdo sem filtros use um modelo local: `--provider ollama`.")
        self.last_stop = comp.stop_reason
        if path and comp.text.strip() and comp.stop_reason != "length":
            try:
                path.write_text(json.dumps({"text": comp.text}, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        return comp.text

    # ----------------------------------------------------------------- JSON
    def ask_json(self, task: str, user: str, *, repair: int = 1, **kw: Any) -> Any:
        text = self.complete(task, user, json_mode=True, **kw)
        truncated = getattr(self, "last_stop", "") == "length"
        for attempt in range(repair + 1):
            try:
                return extract_json(text)
            except ValueError as e:
                if attempt >= repair:
                    hint = " (resposta cortada por limite de tokens — reduza o escopo/lote ou aumente --max-tokens)" if truncated else ""
                    raise AIOutputError(f"{e}{hint}") from None
                fix = (f"Sua resposta anterior não era JSON válido ({e}). Responda novamente APENAS com o JSON corrigido e completo, "
                       f"sem markdown.")
                text = self.complete(task, "", json_mode=True, cache=False, desc=f"{task} (reparo)",
                                     messages=[{"role": "user", "content": user}, {"role": "assistant", "content": text[:20000]},
                                               {"role": "user", "content": fix}],
                                     **{k: v for k, v in kw.items() if k in ("extra_system", "with_api", "max_tokens", "temperature")})
                truncated = getattr(self, "last_stop", "") == "length"
        raise AIOutputError("falha inesperada ao obter JSON")  # pragma: no cover
