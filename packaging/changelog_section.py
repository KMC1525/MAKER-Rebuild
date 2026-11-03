#!/usr/bin/env python3
"""Imprime a seção de uma versão do CHANGELOG.md (usada nas notas de release): changelog_section.py v0.2.0"""
from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def section(version: str, text: str) -> str:
    v = version.lstrip("v")
    m = re.search(rf"^## \[{re.escape(v)}\][^\n]*\n(.*?)(?=^## \[|^\[[^\]]+\]: |\Z)", text, re.S | re.M)
    if not m:
        raise SystemExit(f"versão {v} não encontrada em CHANGELOG.md")
    return m.group(1).strip() + "\n"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("uso: changelog_section.py vX.Y.Z")
    sys.stdout.write(section(sys.argv[1], CHANGELOG.read_text(encoding="utf-8")))
