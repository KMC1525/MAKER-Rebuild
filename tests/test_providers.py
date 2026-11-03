"""Provedores contra um servidor HTTP falso que imita os protocolos reais (streaming SSE/NDJSON)."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from maker_rebuild.config import Config
from maker_rebuild.providers import LLMError, LLMRequest, make_provider

STATE = {"seen": [], "fail_once": None, "hits": 0}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="text/event-stream", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            self._send(200, json.dumps({"models": [{"name": "qwen:7b"}]}), "application/json")
        elif self.path.startswith("/v1/models") or self.path.startswith("/models"):
            self._send(200, json.dumps({"data": [{"id": "m1"}, {"id": "m2"}]}), "application/json")
        else:
            self._send(404, "nope", "text/plain")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        STATE["seen"].append({"path": self.path, "headers": dict(self.headers), "body": body})
        STATE["hits"] += 1
        fail = STATE["fail_once"]
        if fail and STATE["hits"] == 1:
            code, text, extra = fail
            return self._send(code, text, "application/json", extra)
        p = self.path
        if p == "/v1/messages":
            ev = [{"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
                  {"type": "content_block_delta", "delta": {"type": "text_delta", "text": '{"a":'}},
                  {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " 1}"}},
                  {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 3}}]
            self._send(200, "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in ev))
        elif p.endswith("/chat/completions"):
            ev = [{"choices": [{"delta": {"content": "Ol"}}]}, {"choices": [{"delta": {"content": "á"}, "finish_reason": "stop"}]}]
            self._send(200, "".join(f"data: {json.dumps(e)}\n\n" for e in ev) + "data: [DONE]\n\n")
        elif ":streamGenerateContent" in p:
            ev = [{"candidates": [{"content": {"parts": [{"text": "gem"}]}}]},
                  {"candidates": [{"content": {"parts": [{"text": "ini"}]}, "finishReason": "STOP"}]}]
            self._send(200, "".join(f"data: {json.dumps(e)}\n\n" for e in ev))
        elif p == "/api/chat":
            lines = [{"message": {"content": "o"}, "done": False}, {"message": {"content": "lá"}, "done": False}, {"done": True, "done_reason": "stop"}]
            self._send(200, "\n".join(json.dumps(x) for x in lines) + "\n", "application/x-ndjson")
        else:
            self._send(404, "nope", "text/plain")


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture(autouse=True)
def reset():
    STATE.update(seen=[], fail_once=None, hits=0)


REQ = LLMRequest(system="sys", messages=[{"role": "user", "content": "oi"}], max_tokens=100, temperature=0.2, json_mode=True)


def test_anthropic(server, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-test")
    chunks = []
    p = make_provider(Config(provider="claude", base_url=server))
    out = p.complete(REQ, chunks.append)
    assert out.text == '{"a": 1}' and chunks == ['{"a":', " 1}"] and out.usage.get("output_tokens") == 3
    seen = STATE["seen"][0]
    hdr = {k.lower(): v for k, v in seen["headers"].items()}
    assert hdr["x-api-key"] == "k-test" and hdr["anthropic-version"]
    assert seen["body"]["system"] == "sys" and seen["body"]["stream"] is True and seen["body"]["model"].startswith("claude")


def test_anthropic_missing_key(server, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MAKER_REBUILD_API_KEY", raising=False)
    with pytest.raises(LLMError, match="ANTHROPIC_API_KEY"):
        make_provider(Config(provider="anthropic", base_url=server)).complete(REQ)


def test_anthropic_retries_without_temperature(server, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    STATE["fail_once"] = (400, '{"error":"temperature is deprecated for this model"}', None)
    out = make_provider(Config(provider="anthropic", base_url=server)).complete(REQ)
    assert out.text and "temperature" not in STATE["seen"][1]["body"] and "temperature" in STATE["seen"][0]["body"]


def test_openai_and_param_fallback(server, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    STATE["fail_once"] = (400, '{"error":{"message":"Unsupported value: temperature does not support 0.2"}}', None)
    out = make_provider(Config(provider="openai", base_url=server)).complete(REQ)
    assert out.text == "Olá"
    assert "temperature" not in STATE["seen"][1]["body"]
    body = STATE["seen"][1]["body"]
    assert body["messages"][0] == {"role": "system", "content": "sys"} and "max_tokens" in body     # URL não-oficial → max_tokens
    assert {k.lower(): v for k, v in STATE["seen"][0]["headers"].items()}["authorization"] == "Bearer k"


def test_local_openai_compat_needs_no_key_and_uses_max_tokens(server):
    out = make_provider(Config(provider="llamacpp", base_url=server)).complete(REQ)
    assert out.text == "Olá" and "max_tokens" in STATE["seen"][0]["body"] and "authorization" not in {k.lower() for k in STATE["seen"][0]["headers"]}


def test_gemini(server, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g-key")
    out = make_provider(Config(provider="gemini", base_url=server, model="gemini-test")).complete(REQ)
    assert out.text == "gemini"
    s = STATE["seen"][0]
    assert "gemini-test:streamGenerateContent" in s["path"] and {k.lower(): v for k, v in s["headers"].items()}["x-goog-api-key"] == "g-key"
    assert s["body"]["systemInstruction"]["parts"][0]["text"] == "sys" and s["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_ollama_and_model_listing(server):
    p = make_provider(Config(provider="ollama", base_url=server, extras={"num_ctx": 8192}))
    assert p.complete(REQ).text == "olá" and p.list_models() == ["qwen:7b"]
    b = STATE["seen"][0]["body"]
    assert b["options"]["num_ctx"] == 8192 and b["format"] == "json" and b["model"]
    assert p.kind == "local"


def test_retry_on_429(server, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    STATE["fail_once"] = (429, '{"error":"rate"}', {"Retry-After": "0.01"})
    assert make_provider(Config(provider="openai", base_url=server)).complete(REQ).text == "Olá" and STATE["hits"] == 2


def test_connection_refused_has_actionable_message():
    cfg = Config(provider="ollama", base_url="http://127.0.0.1:9")
    with pytest.raises(LLMError, match="Ollama está rodando"):
        make_provider(cfg).complete(REQ)


def test_unknown_provider():
    with pytest.raises(LLMError):
        make_provider(Config(provider="inexistente"))
