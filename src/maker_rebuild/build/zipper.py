"""Empacotamento final: <jogo>.zip contendo a pasta game-x/ (ordem determinística)."""
from __future__ import annotations

import zipfile
from pathlib import Path

EXCLUDE_DIRS = {".maker-rebuild", "__pycache__", ".git"}
FIXED_DATE = (2026, 1, 1, 0, 0, 0)


def make_zip(game_dir: Path, out_zip: Path) -> Path:
    game_dir, out_zip = Path(game_dir), Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    if out_zip.exists():
        out_zip.unlink()
    top = game_dir.name
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(game_dir.rglob("*")):
            rel = p.relative_to(game_dir)
            if any(part in EXCLUDE_DIRS for part in rel.parts) or not p.is_file():
                continue
            info = zipfile.ZipInfo(f"{top}/{rel.as_posix()}", FIXED_DATE)
            info.compress_type = zipfile.ZIP_STORED if p.suffix.lower() in (".png", ".ogg", ".m4a", ".jpg") else zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.flag_bits |= 0x800  # nomes UTF-8
            z.writestr(info, p.read_bytes())
    return out_zip
