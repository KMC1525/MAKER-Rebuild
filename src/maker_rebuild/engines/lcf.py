"""Leitor mínimo do formato LCF (RPG Maker 2000/2003): mapas .lmu.

Suporte *experimental*: lê dimensões, chipset e camadas de tiles. Eventos e
banco de dados do 2000/2003 não são decodificados — a lógica desses jogos é
reconstruída com auxílio da IA a partir do inventário de assets e mapas.
"""
from __future__ import annotations

import struct
from typing import Dict, Optional, Tuple


def ber(b: bytes, pos: int) -> Tuple[int, int]:
    v = 0
    while True:
        c = b[pos]
        pos += 1
        v = (v << 7) | (c & 0x7F)
        if not c & 0x80:
            return v, pos


def chunks(b: bytes, pos: int = 0, end: Optional[int] = None) -> Dict[int, bytes]:
    end = len(b) if end is None else end
    out: Dict[int, bytes] = {}
    while pos < end:
        cid, pos = ber(b, pos)
        if cid == 0:
            break
        ln, pos = ber(b, pos)
        out[cid] = b[pos:pos + ln]
        pos += ln
    return out


def read_map(data: bytes) -> Optional[dict]:
    try:
        n, pos = ber(data, 0)
        if data[pos:pos + n] != b"LcfMapUnit":
            return None
        ch = chunks(data, pos + n)
        w = ber(ch[2], 0)[0]
        h = ber(ch[3], 0)[0]
        res = {"width": w, "height": h, "chipsetId": ber(ch[1], 0)[0] if 1 in ch else 1,
               "parallax": ch.get(0x1F, b"").decode("cp932", "replace")}
        for key, cid in (("lower", 0x47), ("upper", 0x48)):
            raw = ch.get(cid, b"")
            if len(raw) == w * h * 2:
                res[key] = list(struct.unpack(f"<{w * h}H", raw))
        return res
    except (IndexError, struct.error, ValueError):
        return None
