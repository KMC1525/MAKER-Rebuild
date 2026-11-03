"""Arquivos criptografados .rgssad / .rgss2a (XP/VX, v1) e .rgss3a (VX Ace, v3)."""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List

M32 = 0xFFFFFFFF


@dataclass
class ArchiveEntry:
    name: str
    offset: int
    size: int
    key: int


class RGSSArchive:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.blob = self.path.read_bytes()
        self.entries: List[ArchiveEntry] = []
        self.version = 0
        self._parse()

    def _parse(self) -> None:
        b = self.blob
        if b[:6] not in (b"RGSSAD", b"RGSS3A") or len(b) < 8:
            raise ValueError("cabeçalho RGSSAD inválido")
        self.version = b[7]
        if self.version in (1, 2):
            self._parse_v1()
        elif self.version == 3:
            self._parse_v3()
        else:
            raise ValueError(f"versão de arquivo não suportada: {self.version}")

    def _parse_v1(self) -> None:
        b, pos, key = self.blob, 8, 0xDEADCAFE
        while pos + 4 <= len(b):
            (n,) = struct.unpack_from("<I", b, pos)
            n ^= key
            key = (key * 7 + 3) & M32
            pos += 4
            name = bytearray()
            for i in range(n):
                name.append(b[pos + i] ^ (key & 0xFF))
                key = (key * 7 + 3) & M32
            pos += n
            (size,) = struct.unpack_from("<I", b, pos)
            size ^= key
            key = (key * 7 + 3) & M32
            pos += 4
            self.entries.append(ArchiveEntry(name.decode("utf-8", "replace").replace("\\", "/"), pos, size, key))
            pos += size

    def _parse_v3(self) -> None:
        b = self.blob
        (raw,) = struct.unpack_from("<I", b, 8)
        key = (raw * 9 + 3) & M32
        pos = 12
        while True:
            off, size, fkey, n = struct.unpack_from("<4I", b, pos)
            pos += 16
            off ^= key
            size ^= key
            fkey ^= key
            n ^= key
            if off == 0:
                break
            kb = struct.pack("<I", key)
            name = bytes(b[pos + i] ^ kb[i % 4] for i in range(n))
            pos += n
            self.entries.append(ArchiveEntry(name.decode("utf-8", "replace").replace("\\", "/"), off, size, fkey))

    def read(self, e: ArchiveEntry) -> bytes:
        raw = self.blob[e.offset:e.offset + e.size]
        out = bytearray()
        key = e.key
        for i in range(0, len(raw), 4):
            chunk = raw[i:i + 4]
            kb = struct.pack("<I", key)
            out.extend(c ^ kb[j] for j, c in enumerate(chunk))
            key = (key * 7 + 3) & M32
        return bytes(out)


# --- escrita (usada nos testes e para gerar fixtures) -------------------

def write_v1(files: dict, path: Path) -> None:
    key = 0xDEADCAFE
    out = bytearray(b"RGSSAD\0\x01")
    for name, data in files.items():
        nb = name.replace("/", "\\").encode()
        out += struct.pack("<I", len(nb) ^ key)
        key = (key * 7 + 3) & M32
        for c in nb:
            out.append(c ^ (key & 0xFF))
            key = (key * 7 + 3) & M32
        out += struct.pack("<I", len(data) ^ key)
        key = (key * 7 + 3) & M32
        k2 = key
        for i in range(0, len(data), 4):
            kb = struct.pack("<I", k2)
            out.extend(c ^ kb[j] for j, c in enumerate(data[i:i + 4]))
            k2 = (k2 * 7 + 3) & M32
    Path(path).write_bytes(bytes(out))


def write_v3(files: dict, path: Path, seed: int = 0x1234) -> None:
    key = (seed * 9 + 3) & M32
    header = bytearray(b"RGSS3A\0\x03") + struct.pack("<I", seed)
    entries, body = [], bytearray()
    base = 12 + sum(16 + len(n.encode()) for n in files) + 16
    for name, data in files.items():
        fkey = (0xA5A5 + len(entries)) & M32
        enc, k2 = bytearray(), fkey
        for i in range(0, len(data), 4):
            kb = struct.pack("<I", k2)
            enc.extend(c ^ kb[j] for j, c in enumerate(data[i:i + 4]))
            k2 = (k2 * 7 + 3) & M32
        entries.append((name.replace("/", "\\").encode(), base + len(body), len(data), fkey))
        body += enc
    out = bytearray(header)
    kb = struct.pack("<I", key)
    for nb, off, size, fkey in entries:
        out += struct.pack("<4I", off ^ key, size ^ key, fkey ^ key, len(nb) ^ key)
        out += bytes(c ^ kb[i % 4] for i, c in enumerate(nb))
    out += struct.pack("<4I", 0 ^ key, 0, 0, 0)
    out += body
    Path(path).write_bytes(bytes(out))
