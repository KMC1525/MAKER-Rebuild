"""Descriptografia de assets do MV (.rpgmvp/.rpgmvm/.rpgmvo) e MZ (.png_/.m4a_/.ogg_)."""
from __future__ import annotations

from typing import Optional

HEADER_LEN = 16
MV_SIG = b"RPGMV\0\0\0"
PNG_MAGIC = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52])

ENCRYPTED_EXT = {
    ".rpgmvp": ".png", ".rpgmvm": ".m4a", ".rpgmvo": ".ogg",
    ".rpgmzp": ".png", ".rpgmzm": ".m4a", ".rpgmzo": ".ogg",
    ".png_": ".png", ".m4a_": ".m4a", ".ogg_": ".ogg",
}


def parse_key(hex_key: str) -> bytes:
    hex_key = hex_key.strip()
    return bytes(int(hex_key[i:i + 2], 16) for i in range(0, len(hex_key) - 1, 2))


def is_encrypted(data: bytes) -> bool:
    return data[:8] == MV_SIG


def decrypt(data: bytes, key: bytes) -> bytes:
    """Remove o cabeçalho falso (16 B) e aplica XOR nos 16 primeiros bytes reais."""
    if not is_encrypted(data):
        return data
    body = bytearray(data[HEADER_LEN:])
    for i in range(min(HEADER_LEN, len(body), len(key))):
        body[i] ^= key[i]
    return bytes(body)


def recover_png_key(data: bytes) -> Optional[bytes]:
    """Recupera a chave a partir de um PNG criptografado (cabeçalho PNG é conhecido)."""
    if not is_encrypted(data) or len(data) < HEADER_LEN * 2:
        return None
    enc = data[HEADER_LEN:HEADER_LEN * 2]
    return bytes(a ^ b for a, b in zip(enc, PNG_MAGIC))


def encrypt(data: bytes, key: bytes) -> bytes:
    """Usado nos testes para gerar fixtures."""
    head = bytearray(data[:HEADER_LEN])
    for i in range(len(head)):
        head[i] ^= key[i]
    return MV_SIG + b"\x00\x03\x01\x00\x00\x00\x00\x00" + bytes(head) + data[HEADER_LEN:]
