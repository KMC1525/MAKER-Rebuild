"""Leitura/escrita dos arquivos de dados do jogo (.js carregáveis via <script>, funcionam em file://)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_PREFIX = re.compile(r"^\s*/\*[^*]*\*/\s*[\w.\[\]]+\s*=\s*", re.S)


def dumps(target: str, obj: Any, note: str = "") -> str:
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    body = body.replace("</script", "<\\/script").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return f"/* maker-rebuild data{': ' + note if note else ''} */\n{target} = {body};\n"


def loads(text: str) -> Any:
    m = _PREFIX.match(text)
    if not m:
        raise ValueError("arquivo de dados em formato inesperado")
    body = text[m.end():].rstrip()
    if body.endswith(";"):
        body = body[:-1]
    return json.loads(body)


def write(path: Path, target: str, obj: Any, note: str = "") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(target, obj, note), encoding="utf-8")


def read(path: Path) -> Any:
    return loads(Path(path).read_text(encoding="utf-8"))
