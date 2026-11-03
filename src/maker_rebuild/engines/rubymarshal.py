"""Leitor de Ruby ``Marshal`` (formato 4.8) usado por RPG Maker XP/VX/VX Ace.

Não executa nada: apenas reconstrói a árvore de objetos. Objetos Ruby viram
``RObject`` (classe + variáveis de instância); ``Table``, ``Color`` e ``Tone``
viram estruturas simples.
"""
from __future__ import annotations

import struct
from typing import Any, Dict, List


class RSymbol(str):
    pass


class RObject:
    __slots__ = ("cls", "ivars")

    def __init__(self, cls: str):
        self.cls = cls
        self.ivars: Dict[str, Any] = {}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.cls} {list(self.ivars)[:6]}>"


class RUserDef:
    """Objeto serializado com ``_dump`` (ex.: Table, Color, Tone)."""
    __slots__ = ("cls", "data")

    def __init__(self, cls: str, data: bytes):
        self.cls = cls
        self.data = data


class RUserMarshal(RObject):
    __slots__ = ("payload",)


class Table(list):
    """``Table`` do RGSS: lista plana (x varia mais rápido) + dimensões."""
    dims = (1, 1, 1)


class MarshalError(ValueError):
    pass


class Loader:
    def __init__(self, data: bytes, decode: bool = True):
        if data[:2] != b"\x04\x08":
            raise MarshalError("não é um arquivo Marshal 4.8")
        self.decode = decode
        self.d = data
        self.p = 2
        self.syms: List[RSymbol] = []
        self.objs: List[Any] = []

    # --- primitivos --------------------------------------------------
    def _byte(self) -> int:
        b = self.d[self.p]
        self.p += 1
        return b

    def _long(self) -> int:
        c = self._byte()
        if c > 127:
            c -= 256
        if c == 0:
            return 0
        if 4 < c < 128:
            return c - 5
        if -129 < c < -4:
            return c + 5
        n = abs(c)
        raw = self.d[self.p:self.p + n]
        self.p += n
        x = int.from_bytes(raw, "little")
        if c < 0:
            x -= 1 << (8 * n)
        return x

    def _bytes(self) -> bytes:
        n = self._long()
        raw = self.d[self.p:self.p + n]
        self.p += n
        return raw

    def _sym(self) -> RSymbol:
        t = chr(self._byte())
        if t == ":":
            s = RSymbol(self._bytes().decode("utf-8", "replace"))
            self.syms.append(s)
            return s
        if t == ";":
            return self.syms[self._long()]
        raise MarshalError(f"símbolo esperado, veio {t!r} @ {self.p}")

    def _text(self, raw: bytes) -> Any:
        if not self.decode:
            return raw
        for enc in ("utf-8", "cp932"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                continue
        return raw  # binário (ex.: scripts compactados)

    def _reg(self, o: Any) -> int:
        self.objs.append(o)
        return len(self.objs) - 1

    # --- objetos -----------------------------------------------------
    def load(self) -> Any:
        t = chr(self._byte())
        if t == "0":
            return None
        if t == "T":
            return True
        if t == "F":
            return False
        if t == "i":
            return self._long()
        if t == ":":
            self.p -= 1
            return self._sym()
        if t == ";":
            self.p -= 1
            return self._sym()
        if t == "@":
            return self.objs[self._long()]
        if t == "I":
            o = self.load()
            for _ in range(self._long()):
                self._sym()
                self.load()  # encoding ivar (E/encoding) — ignorado
            return o
        if t == '"':
            s = self._text(self._bytes())
            self._reg(s)
            return s
        if t == "f":
            s = self._bytes().decode("ascii", "replace")
            v = {"inf": float("inf"), "-inf": float("-inf"), "nan": float("nan")}.get(s)
            if v is None:
                try:
                    v = float(s.split("\0")[0])
                except ValueError:
                    v = 0.0
            self._reg(v)
            return v
        if t == "l":
            sign = chr(self._byte())
            n = self._long()
            raw = self.d[self.p:self.p + 2 * n]
            self.p += 2 * n
            v = int.from_bytes(raw, "little")
            v = -v if sign == "-" else v
            self._reg(v)
            return v
        if t == "[":
            arr: List[Any] = []
            self._reg(arr)
            for _ in range(self._long()):
                arr.append(self.load())
            return arr
        if t in "{}":
            h: Dict[Any, Any] = {}
            self._reg(h)
            for _ in range(self._long()):
                k = self.load()
                v = self.load()
                if isinstance(k, list):
                    k = tuple(k)
                try:
                    h[k] = v
                except TypeError:
                    h[repr(k)] = v
            if t == "}":
                self.load()  # valor padrão
            return h
        if t == "o":
            name = str(self._sym())
            o = RObject(name)
            self._reg(o)
            for _ in range(self._long()):
                k = str(self._sym())
                o.ivars[k] = self.load()
            return o
        if t == "u":
            name = str(self._sym())
            raw = self._bytes()
            u = RUserDef(name, raw)
            self._reg(u)
            return u
        if t == "U":
            name = str(self._sym())
            o = RUserMarshal(name)
            self._reg(o)
            o.payload = self.load()
            return o
        if t == "S":
            name = str(self._sym())
            o = RObject(name)
            self._reg(o)
            for _ in range(self._long()):
                k = str(self._sym())
                o.ivars["@" + k] = self.load()
            return o
        if t in "cmM":
            s = RSymbol(self._bytes().decode("utf-8", "replace"))
            self._reg(s)
            return s
        if t == "e":
            self._sym()
            return self.load()
        if t == "C":
            self._sym()
            return self.load()
        if t == "/":
            s = self._bytes().decode("utf-8", "replace")
            self._byte()
            self._reg(s)
            return s
        raise MarshalError(f"tipo Marshal desconhecido {t!r} @ {self.p - 1}")


def loads(data: bytes, decode: bool = True) -> Any:
    return Loader(data, decode).load()


# ---------------------------------------------------------------------
# Conversão para estruturas Python/JSON no estilo MV
# ---------------------------------------------------------------------

def camel(name: str) -> str:
    name = name.lstrip("@")
    parts = name.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def decode_table(raw: bytes) -> Table:
    dim, xs, ys, zs, size = struct.unpack_from("<5i", raw, 0)
    t = Table(struct.unpack_from(f"<{size}h", raw, 20))
    t.dims = (xs, ys, zs)
    return t


def convert(o: Any, keep_class: bool = False) -> Any:
    """RObject/Table/Color/Tone → dict/list/escalares JSON-serializáveis."""
    if isinstance(o, RUserDef):
        if o.cls == "Table":
            return decode_table(o.data)
        if o.cls in ("Color", "Tone"):
            try:
                return list(struct.unpack("<4d", o.data))
            except struct.error:
                return []
        return {"__userdef__": o.cls, "hex": o.data.hex()}
    if isinstance(o, RUserMarshal):
        return convert(o.payload, keep_class)
    if isinstance(o, RObject):
        d: Dict[str, Any] = {}
        for k, v in o.ivars.items():
            d[camel(k)] = convert(v, keep_class)
        if keep_class:
            d["__class__"] = o.cls
        return d
    if isinstance(o, list):
        return [convert(x, keep_class) for x in o]
    if isinstance(o, dict):
        return {str(k): convert(v, keep_class) for k, v in o.items()}
    if isinstance(o, bytes):
        return {"__bytes__": len(o)}
    return o
