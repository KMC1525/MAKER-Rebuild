"""Ollama local (/api/chat) com streaming NDJSON."""
from __future__ import annotations

from typing import List

from .base import Completion, ChunkCb, LLMError, LLMRequest, Provider
from .http import get_json, ndjson, post_stream


class OllamaProvider(Provider):
    name = "ollama"
    kind = "local"

    def complete(self, req: LLMRequest, on_chunk: ChunkCb = None) -> Completion:
        opts = {"temperature": req.temperature, "num_predict": req.max_tokens,
                "num_ctx": int(self.extras.get("num_ctx", 16384))}
        payload = {"model": req.model or self.model, "stream": True, "options": opts,
                   "messages": [{"role": "system", "content": req.system}] + req.messages}
        if req.json_mode:
            payload["format"] = "json"
        out: List[str] = []
        stop = "stop"
        for ev in ndjson(post_stream(f"{self.base_url}/api/chat", {}, payload, self.timeout,
                                     hint="O Ollama está rodando? (`ollama serve`) O modelo foi baixado? (`ollama pull <modelo>`)")):
            if ev.get("error"):
                raise LLMError(f"Ollama: {ev['error']}")
            txt = (ev.get("message") or {}).get("content")
            if txt:
                out.append(txt)
                on_chunk and on_chunk(txt)
            if ev.get("done"):
                stop = "length" if ev.get("done_reason") == "length" else "stop"
        return Completion("".join(out), stop)

    def list_models(self) -> List[str]:
        try:
            return [m["name"] for m in get_json(f"{self.base_url}/api/tags").get("models", [])]
        except LLMError:
            return []
