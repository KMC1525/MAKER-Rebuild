"""Chat Completions (OpenAI, OpenRouter, LM Studio, llama.cpp, vLLM e qualquer servidor compatível)."""
from __future__ import annotations

from typing import List

from .base import Completion, ChunkCb, LLMError, LLMRequest, Provider
from .http import HttpFailure, get_json, post_stream, sse_events


class OpenAICompatProvider(Provider):
    name = "openai"

    def _headers(self):
        h = {}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        if "openrouter" in self.base_url:
            h["X-Title"] = "MAKER-Rebuild"
        return h

    def complete(self, req: LLMRequest, on_chunk: ChunkCb = None) -> Completion:
        if self.kind == "frontier":
            self.need_key()
        hosted_openai = "api.openai.com" in self.base_url
        payload = {"model": req.model or self.model, "stream": True, "temperature": req.temperature,
                   "messages": [{"role": "system", "content": req.system}] + req.messages}
        payload["max_completion_tokens" if hosted_openai else "max_tokens"] = req.max_tokens
        if req.json_mode and hosted_openai:
            payload["response_format"] = {"type": "json_object"}
        out: List[str] = []
        stop = ""
        for attempt in range(3):
            try:
                for ev in sse_events(post_stream(f"{self.base_url}/chat/completions", self._headers(), payload, self.timeout,
                                                 hint="O servidor local está rodando e com um modelo carregado?")):
                    if "error" in ev:
                        raise LLMError(f"{self.name}: {ev['error']}")
                    for ch in ev.get("choices") or []:
                        txt = (ch.get("delta") or {}).get("content")
                        if txt:
                            out.append(txt)
                            on_chunk and on_chunk(txt)
                        stop = ch.get("finish_reason") or stop
                break
            except HttpFailure as e:
                body = e.body.lower()
                if e.status == 400 and attempt < 2:      # parâmetros que alguns modelos/servidores rejeitam
                    if "temperature" in body and "temperature" in payload:
                        payload.pop("temperature"); out.clear(); continue
                    if "max_completion_tokens" in body and "max_completion_tokens" in payload:
                        payload["max_tokens"] = payload.pop("max_completion_tokens"); out.clear(); continue
                    if "max_tokens" in body and "max_tokens" in payload:
                        payload["max_completion_tokens"] = payload.pop("max_tokens"); out.clear(); continue
                    if "response_format" in body and "response_format" in payload:
                        payload.pop("response_format"); out.clear(); continue
                raise
        return Completion("".join(out), "length" if stop == "length" else ("blocked" if stop == "content_filter" else "stop"))

    def list_models(self) -> List[str]:
        try:
            data = get_json(f"{self.base_url}/models", self._headers())
            return [m["id"] for m in data.get("data", [])]
        except LLMError:
            return []
