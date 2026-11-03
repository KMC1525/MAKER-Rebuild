"""Google Gemini (generativelanguage API) com streaming SSE."""
from __future__ import annotations

from typing import List

from .base import Completion, ChunkCb, LLMError, LLMRequest, Provider
from .http import get_json, post_stream, sse_events


class GeminiProvider(Provider):
    name = "gemini"

    def _headers(self):
        return {"x-goog-api-key": self.api_key or ""}

    def complete(self, req: LLMRequest, on_chunk: ChunkCb = None) -> Completion:
        self.need_key()
        model = req.model or self.model
        gen = {"temperature": req.temperature, "maxOutputTokens": req.max_tokens}
        if req.json_mode:
            gen["responseMimeType"] = "application/json"
        payload = {"systemInstruction": {"parts": [{"text": req.system}]},
                   "contents": [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                                for m in req.messages],
                   "generationConfig": gen}
        url = f"{self.base_url}/v1beta/models/{model}:streamGenerateContent?alt=sse"
        out: List[str] = []
        stop = "stop"
        for ev in sse_events(post_stream(url, self._headers(), payload, self.timeout)):
            fb = ev.get("promptFeedback") or {}
            if fb.get("blockReason"):
                raise LLMError(f"Gemini bloqueou o prompt ({fb['blockReason']}). A política do provedor se aplica; "
                               f"para conteúdo sem filtros use um modelo local (--provider ollama).")
            for cand in ev.get("candidates") or []:
                for part in (cand.get("content") or {}).get("parts") or []:
                    if part.get("text"):
                        out.append(part["text"])
                        on_chunk and on_chunk(part["text"])
                fr = cand.get("finishReason")
                if fr in ("MAX_TOKENS",):
                    stop = "length"
                elif fr in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"):
                    stop = "blocked"
        return Completion("".join(out), stop)

    def list_models(self) -> List[str]:
        try:
            data = get_json(f"{self.base_url}/v1beta/models?pageSize=100", self._headers())
            return [m["name"].split("/", 1)[-1] for m in data.get("models", [])]
        except LLMError:
            return []
