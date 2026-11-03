"""Extração tolerante de JSON da resposta de um LLM (cercas ```json, texto antes/depois, vírgulas sobrando)."""
from __future__ import annotations

import json
import re
from typing import Any


def _balanced(text: str, start: int) -> int:
    """Índice do fecho que casa com o abre em ``start`` (respeita strings/escapes), ou -1."""
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_json(text: str) -> Any:
    """Devolve o primeiro valor JSON (objeto/array) encontrado. Levanta ValueError se não houver."""
    if not text or not text.strip():
        raise ValueError("resposta vazia")
    s = text.strip()
    fence = re.search(r"```(?:json|JSON)?\s*\n(.*?)```", s, re.S)
    candidates = [fence.group(1)] if fence else []
    candidates.append(s)
    last_err = None
    for cand in candidates:
        pos = 0
        while True:
            m = re.compile(r"[\[{]").search(cand, pos)
            if not m:
                break
            end = _balanced(cand, m.start())
            if end < 0:
                pos = m.start() + 1
                continue
            chunk = cand[m.start():end + 1]
            for attempt in (chunk, re.sub(r",\s*([}\]])", r"\1", chunk)):
                try:
                    return json.loads(attempt)
                except ValueError as e:
                    last_err = e
            pos = end + 1          # bloco balanceado mas inválido: segue para o próximo candidato
    raise ValueError(f"JSON inválido na resposta: {last_err or 'nenhum objeto encontrado'}")
