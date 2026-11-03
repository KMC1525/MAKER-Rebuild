"""HTTP mínimo (urllib) com streaming de linhas, retries e mensagens de erro úteis."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterator, Optional

from .base import LLMError

RETRY_STATUS = {408, 429, 500, 502, 503, 504, 529}


def post_stream(url: str, headers: Dict[str, str], payload: Dict[str, Any], timeout: int, retries: int = 3,
                hint: str = "") -> Iterator[str]:
    """POST JSON e devolve as linhas da resposta (SSE/NDJSON) conforme chegam."""
    body = json.dumps(payload).encode("utf-8")
    hdr = {"Content-Type": "application/json", "User-Agent": "maker-rebuild", **headers}
    last: Optional[Exception] = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=hdr, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")[:2000]
            if e.code in RETRY_STATUS and attempt < retries:
                wait = float(e.headers.get("Retry-After", 0) or 0) or min(30, 2 ** (attempt + 1))
                time.sleep(wait)
                last = LLMError(f"HTTP {e.code}: {text}")
                continue
            raise HttpFailure(e.code, text) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            last = e
            refused = isinstance(getattr(e, "reason", e), ConnectionRefusedError) or isinstance(e, ConnectionRefusedError)
            if attempt < retries and not refused:      # servidor local desligado não é falha transitória
                time.sleep(min(20, 2 ** (attempt + 1)))
                continue
            raise LLMError(f"não foi possível conectar a {url}: {getattr(e, 'reason', e)}. {hint}".strip()) from None
        with resp:
            for raw in resp:
                yield raw.decode("utf-8", "replace").rstrip("\r\n")
        return
    raise LLMError(str(last))


class HttpFailure(LLMError):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status
        self.body = body


def get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 10) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "maker-rebuild", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except (urllib.error.URLError, ValueError, OSError) as e:
        raise LLMError(f"GET {url} falhou: {getattr(e, 'reason', e)}") from None


def sse_events(lines: Iterator[str]) -> Iterator[Dict[str, Any]]:
    """Extrai objetos JSON das linhas ``data:`` de um stream SSE (ignora ``[DONE]``)."""
    for line in lines:
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            yield json.loads(data)
        except ValueError:
            continue


def ndjson(lines: Iterator[str]) -> Iterator[Dict[str, Any]]:
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue
