"""Arrastar e soltar: interpreta o que o terminal cola quando você solta arquivos/pastas na janela.

Cada terminal cola de um jeito:
  macOS Terminal   /Users/ana/Meu\\ Jogo.zip                     (espaços e parênteses com barra)
  GNOME/Konsole    '/home/ana/Meu Jogo.zip'  ou  file:///home/ana/Meu%20Jogo.zip
  cmd.exe          "C:\\Users\\ana\\Meu Jogo.zip"
  PowerShell       & 'C:\\Users\\ana\\Meu Jogo.zip'
Também vale soltar vários itens de uma vez (ex.: o .zip do jogo + o roteiro .md) e caminhos com espaços sem aspas.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import unquote, urlparse

DOC_EXT = {".txt", ".md", ".csv", ".tsv", ".json", ".yaml", ".yml", ".html", ".htm"}
_WIN_PATH = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


def _tokenize(text: str) -> List[str]:
    """Divide em itens respeitando aspas; barra invertida só escapa em caminhos estilo POSIX."""
    posix_escapes = not _WIN_PATH.search(text.replace('"', "").replace("'", "").lstrip("& ").strip())
    out: List[str] = []
    cur: List[str] = []
    quote = ""
    i, has = 0, False
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = ""
            else:
                cur.append(ch)
        elif ch in "\"'":
            quote, has = ch, True
        elif ch == "\\" and posix_escapes and i + 1 < len(text):
            cur.append(text[i + 1])
            has = True
            i += 1
        elif ch.isspace():
            if cur or has:
                out.append("".join(cur))
            cur, has = [], False
        else:
            cur.append(ch)
            has = True
        i += 1
    if cur or has:
        out.append("".join(cur))
    return out


def _from_token(tok: str) -> str:
    tok = tok.strip()
    if tok.lower().startswith("file:"):
        u = urlparse(tok)
        p = unquote(u.path)
        if u.netloc and u.netloc != "localhost":          # file://servidor/pasta (UNC)
            return f"//{u.netloc}{p}"
        if re.match(r"^/[A-Za-z]:", p):                    # file:///C:/Users/...
            p = p[1:]
        return p
    return tok


def clean_path(text: str) -> str:
    """Normaliza UM caminho colado (aspas, escapes, file://, ~). Não exige que exista."""
    toks = [t for t in _tokenize(text.strip()) if t != "&"]
    raw = _from_token(" ".join(toks) if toks else text.strip())
    return str(Path(raw).expanduser()) if raw.startswith("~") else raw


def path_arg(text: str) -> str:
    """Para usar como ``type=`` do argparse: aceita o caminho como veio do arrastar-e-soltar."""
    return clean_path(text)


def parse_dropped(text: str) -> List[Tuple[Path, bool]]:
    """Interpreta tudo que foi colado → [(caminho, existe)]. Junta pedaços para formar caminhos com espaço sem aspas."""
    toks = [_from_token(t) for t in _tokenize(text.strip()) if t != "&"]
    toks = [str(Path(t).expanduser()) if t.startswith("~") else t for t in toks]
    out: List[Tuple[Path, bool]] = []
    i = 0
    while i < len(toks):
        for j in range(len(toks), i, -1):                  # prefere o maior trecho que existe
            cand = " ".join(toks[i:j])
            if Path(cand).exists():
                out.append((Path(cand), True))
                i = j
                break
        else:
            out.append((Path(toks[i]), False))
            i += 1
    return out


def looks_like_path(text: str) -> bool:
    """A linha digitada parece um caminho solto (e não uma frase/pedido)? Todos os itens precisam existir."""
    t = text.strip()
    if not t:
        return False
    items = parse_dropped(t)
    return bool(items) and all(ok for _p, ok in items)


@dataclass
class Dropped:
    path: Path
    kind: str            # built | project | docs | folder | unknown
    engine: str = ""     # mv, mz, vxace, ... (quando conhecido)
    detail: str = ""


def _peek_zip(p: Path) -> Tuple[str, str]:
    """Classifica um .zip olhando só a lista de nomes (sem extrair)."""
    try:
        with zipfile.ZipFile(p) as z:
            names = [n.replace("\\", "/") for n in z.namelist()]
    except (zipfile.BadZipFile, OSError):
        return "unknown", "zip inválido ou corrompido"
    low = [n.lower() for n in names]
    if any(n.endswith("code/js/data/db.js") for n in low) and any(n.endswith("game.html") for n in low):
        return "built", "jogo já recompilado pelo MAKER-Rebuild"

    def has(sfx: str) -> bool:
        return any(n.endswith(sfx) for n in low)

    if has("data/system.json"):
        mz = any("rmmz_" in n for n in low) or has(".rmmzproject") or any(n.endswith((".png_", ".ogg_", ".m4a_")) for n in low)
        return "project", "mz" if mz else "mv"
    if has("data/system.rvdata2") or has(".rgss3a") or has(".rvproj2"):
        return "project", "vxace"
    if has("data/system.rvdata") or has(".rgss2a") or has(".rvproj"):
        return "project", "vx"
    if has("data/system.rxdata") or has(".rgssad") or has(".rxproj"):
        return "project", "xp"
    if has("rpg_rt.ldb") or has("rpg_rt.exe"):
        return "project", "rm2k"
    return "unknown", "não reconheci nenhum projeto RPG Maker dentro do zip"


def classify(p: Path) -> Dropped:
    p = Path(p)
    if not p.exists():
        return Dropped(p, "unknown", detail="não existe")
    if p.is_dir():
        from .build.builtgame import is_built_game
        if is_built_game(p):
            return Dropped(p, "built", detail="jogo já recompilado pelo MAKER-Rebuild")
        from .project import ProjectError, detect_root
        try:
            _root, eng = detect_root(p)
            return Dropped(p, "project", eng)
        except ProjectError:
            return Dropped(p, "folder", detail="pasta sem projeto RPG Maker reconhecido")
    ext = p.suffix.lower()
    if ext == ".zip":
        kind, d = _peek_zip(p)
        return Dropped(p, kind, d if kind == "project" else "", d if kind != "project" else "")
    if ext in DOC_EXT:
        return Dropped(p, "docs", detail="documento (GDD/roteiro/fichas) — será usado como contexto da IA")
    return Dropped(p, "unknown", detail=f"tipo '{ext or 'sem extensão'}' não suportado (use .zip, pasta ou .txt/.md/.csv/.json)")


def classify_all(text: str) -> Tuple[List[Dropped], List[Path]]:
    """Texto colado → (itens reconhecidos, caminhos inexistentes)."""
    found, missing = [], []
    for path, ok in parse_dropped(text):
        (found if ok else missing).append(classify(path) if ok else path)
    return found, missing


def pick_main(items: List[Dropped]) -> Optional[Dropped]:
    """O item principal (jogo/projeto) entre vários soltos; o último vence se houver mais de um."""
    mains = [d for d in items if d.kind in ("built", "project")]
    return mains[-1] if mains else None
