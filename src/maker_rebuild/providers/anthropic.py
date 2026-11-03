"""API Messages da Anthropic (Claude), com streaming."""
from __future__ import annotations

from typing import List

from .base import Completion, ChunkCb, LLMError, LLMRequest, Provider
from .http import HttpFailure, get_json, post_stream, sse_events


class AnthropicProvider(Provider):
    name = "anthropic"

    def _headers(self):
        return {"x-api-key": self.api_key or "", "anthropic-version": "2023-06-01"}

    def complete(self, req: LLMRequest, on_chunk: ChunkCb = None) -> Completion:
        self.need_key()
        payload = {"model": req.model or self.model, "max_tokens": req.max_tokens, "system": req.system,
                   "messages": req.messages, "temperature": req.temperature, "stream": True}
        out: List[str] = []
        stop = ""
        usage = {}
        for attempt in range(2):
            try:
                for ev in sse_events(post_stream(f"{self.base_url}/v1/messages", self._headers(), payload, self.timeout)):
                    t = ev.get("type")
                    if t == "content_block_delta":
                        txt = (ev.get("delta") or {}).get("text")
                        if txt:
                            out.append(txt)
                            on_chunk and on_chunk(txt)
                    elif t == "message_delta":
                        stop = (ev.get("delta") or {}).get("stop_reason") or stop
                        usage.update(ev.get("usage") or {})
                    elif t == "message_start":
                        usage.update(((ev.get("message") or {}).get("usage")) or {})
                    elif t == "error":
                        raise LLMError(f"Anthropic: {ev.get('error')}")
                break
            except HttpFailure as e:
                # alguns modelos rejeitam `temperature`; tenta de novo sem ela
                if e.status == 400 and "temperature" in e.body and "temperature" in payload and attempt == 0:
                    payload.pop("temperature")
                    out.clear()
                    continue
                raise
        return Completion("".join(out), {"max_tokens": "length", "refusal": "blocked"}.get(stop, "stop"), usage)

    def list_models(self) -> List[str]:
        try:
            data = get_json(f"{self.base_url}/v1/models", self._headers())
            return [m["id"] for m in data.get("data", [])]
        except LLMError:
            return []
