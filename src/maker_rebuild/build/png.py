"""Gerador de PNG mínimo (sem dependências) — usado para placeholders de assets pedidos pela IA."""
from __future__ import annotations

import struct
import zlib
from typing import Tuple

Color = Tuple[int, int, int]


class Canvas:
    def __init__(self, w: int, h: int, bg=(0, 0, 0, 0)):
        self.w, self.h = w, h
        self.rows = [bytearray(bytes(bg) * w) for _ in range(h)]

    def rect(self, x: int, y: int, w: int, h: int, c) -> "Canvas":
        c = bytes(c if len(c) == 4 else (*c, 255))
        x0, x1 = max(0, x), min(self.w, x + w)
        for yy in range(max(0, y), min(self.h, y + h)):
            if x1 > x0:
                self.rows[yy][x0 * 4:x1 * 4] = c * (x1 - x0)
        return self

    def png(self) -> bytes:
        raw = b"".join(b"\x00" + bytes(r) for r in self.rows)

        def chunk(t: bytes, d: bytes) -> bytes:
            return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def _color_for(name: str) -> Color:
    h = sum(ord(c) * (i + 3) for i, c in enumerate(name))
    return (60 + h * 37 % 160, 60 + h * 91 % 160, 60 + h * 53 % 160)


def placeholder(category: str, name: str, tile: int = 48) -> bytes:
    """PNG de marcação (cor derivada do nome) no formato esperado pela categoria."""
    col = _color_for(name)
    if category == "characters":
        single = name.startswith("$")
        cols, rows = (3, 4) if single else (12, 8)
        cv = Canvas(tile * cols, tile * rows)
        for ci in range(1 if single else 8):
            cx, cy = (0 if single else (ci % 4) * 3 * tile), (0 if single else (ci // 4) * 4 * tile)
            for d in range(4):
                for f in range(3):
                    x, y = cx + f * tile, cy + d * tile
                    cv.rect(x + tile // 4, y + tile // 5, tile // 2, tile * 3 // 5, col)
                    cv.rect(x + tile // 3, y + tile // 10, tile // 3, tile // 5, (240, 200, 170))
        return cv.png()
    if category == "faces":
        s = 144 if tile >= 48 else 96
        cv = Canvas(s * 4, s * 2)
        for i in range(8):
            cv.rect((i % 4) * s + 4, (i // 4) * s + 4, s - 8, s - 8, col)
        return cv.png()
    if category in ("enemies", "sv_enemies"):
        return Canvas(160, 160).rect(10, 20, 140, 130, col).rect(45, 55, 18, 18, (0, 0, 0)).rect(97, 55, 18, 18, (0, 0, 0)).png()
    if category in ("parallaxes", "titles1", "titles2", "battlebacks1", "battlebacks2"):
        return Canvas(816, 624, (*col, 255)).png()
    return Canvas(96, 96).rect(0, 0, 96, 96, col).rect(8, 8, 80, 80, _mix(col)).png()


def _mix(c: Color) -> Color:
    return tuple(min(255, v + 60) for v in c)  # type: ignore[return-value]
