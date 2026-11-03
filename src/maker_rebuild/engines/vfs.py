"""Sistema de arquivos virtual: pasta do projeto + arquivo RGSS (.rgssad/.rgss3a)."""
from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Callable, Dict, Iterator, Optional, Tuple

from .rgssad import RGSSArchive


class VFS:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.index: Dict[str, Tuple[str, Callable[[], bytes]]] = {}
        self.archive: Optional[RGSSArchive] = None
        self._walk()

    def _walk(self) -> None:
        for dp, _dn, fns in os.walk(self.root):
            for fn in fns:
                full = Path(dp) / fn
                rel = full.relative_to(self.root).as_posix()
                self.index[rel.lower()] = (rel, (lambda p=full: p.read_bytes()))
        for ext in (".rgss3a", ".rgss2a", ".rgssad"):
            for key, (rel, _r) in list(self.index.items()):
                if key.endswith(ext) and "/" not in key:
                    self.attach(self.root / rel)
                    return

    def attach(self, path: Path) -> None:
        self.archive = RGSSArchive(path)
        for e in self.archive.entries:
            key = e.name.lower()
            if key not in self.index:  # arquivos soltos têm prioridade
                self.index[key] = (e.name, (lambda e=e: self.archive.read(e)))

    def exists(self, rel: str) -> bool:
        return rel.lower() in self.index

    def read(self, rel: str) -> bytes:
        return self.index[rel.lower()][1]()

    def find(self, rel: str) -> Optional[str]:
        e = self.index.get(rel.lower())
        return e[0] if e else None

    def walk(self, prefix: str = "") -> Iterator[Tuple[str, Callable[[], bytes]]]:
        pre = prefix.lower()
        for key, (rel, reader) in self.index.items():
            if key.startswith(pre):
                yield rel, reader


def safe_extract(zip_path: Path, dest: Path) -> None:
    """Extrai .zip evitando path traversal (zip slip)."""
    dest = Path(dest).resolve()
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            name = info.filename
            # nomes sem flag UTF-8 vêm como cp437; tenta recuperar cp932 (jogos japoneses)
            if not info.flag_bits & 0x800:
                try:
                    name = name.encode("cp437").decode("cp932")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            target = (dest / name).resolve()
            if dest != target and dest not in target.parents:
                raise ValueError(f"entrada de zip insegura: {info.filename}")
            if info.is_dir() or name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                while True:
                    buf = src.read(1 << 20)
                    if not buf:
                        break
                    out.write(buf)
