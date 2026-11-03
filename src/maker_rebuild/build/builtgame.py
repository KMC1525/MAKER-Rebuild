"""Jogo já recompilado (pasta ou .zip no formato game-x/): leitura, edição e regravação."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..assets import AUDIO_CATS, IMAGE_EXT, TARGET_DIRS, UNPLAYABLE_AUDIO
from ..engines.vfs import safe_extract
from . import datajs
from .builder import AUDIO_PREF, IMAGE_PREF, _pref_key, write_html

_MAP_RE = re.compile(r"map-(\d+)\.js$")


class BuiltGameError(Exception):
    pass


def is_built_game(path: Path) -> bool:
    p = Path(path)
    if p.is_file():
        return False
    return (p / "Game.html").exists() and (p / "code" / "js" / "data" / "db.js").exists()


def find_game_root(base: Path) -> Optional[Path]:
    base = Path(base)
    if is_built_game(base):
        return base
    for sub in sorted(p for p in base.iterdir() if p.is_dir()):
        if is_built_game(sub):
            return sub
    return None


class BuiltGame:
    """Interface equivalente a :class:`maker_rebuild.project.Project` para os fluxos de IA."""

    def __init__(self, root: Path):
        self.root = Path(root)
        d = self.root / "code" / "js" / "data"
        self.config: Dict[str, Any] = datajs.read(d / "config.js")
        self.db: Dict[str, Any] = datajs.read(d / "db.js")
        self.maps: Dict[int, dict] = {}
        for f in sorted((d / "maps").glob("map-*.js")):
            m = _MAP_RE.search(f.name)
            if m:
                self.maps[int(m.group(1))] = datajs.read(f)
        self.warnings: List[str] = []
        self.scripts: List[dict] = []
        self.plugin_sources: Dict[str, str] = {}
        self._load_sources()

    # --- Propriedades compatíveis com Project
    @property
    def engine(self) -> str:
        return self.config.get("engine", "mv")

    @property
    def title(self) -> str:
        return self.config.get("title", self.root.name)

    @title.setter
    def title(self, v: str) -> None:
        self.config["title"] = v

    @property
    def tile_size(self) -> int:
        return self.config.get("tileSize", 48)

    @property
    def screen_w(self) -> int:
        return self.config["screen"]["w"]

    @property
    def screen_h(self) -> int:
        return self.config["screen"]["h"]

    def _load_sources(self) -> None:
        sdir = self.root / "code" / "js" / "scripts-ruby"
        if sdir.is_dir():
            for f in sorted(sdir.glob("*.rb.txt")):
                self.scripts.append({"name": f.name, "source": f.read_text(encoding="utf-8", errors="replace")})
        pdir = self.root / "code" / "js" / "plugins" / "_original"
        if pdir.is_dir():
            for f in sorted(pdir.glob("*.js.txt")):
                self.plugin_sources[f.name[:-7]] = f.read_text(encoding="utf-8", errors="replace")

    # --- persistência
    def rescan_assets(self) -> Dict[str, Any]:
        """Reconstrói ``config.assetIndex`` a partir do conteúdo real de ``assets/``."""
        index: Dict[str, Dict[str, Dict[str, str]]] = {}
        for cat, rel in TARGET_DIRS.items():
            base = self.root / rel
            if not base.is_dir() or cat == "fonts" or cat == "movies":
                continue
            order = AUDIO_PREF if cat in AUDIO_CATS else IMAGE_PREF
            best: Dict[str, int] = {}
            for f in sorted(base.rglob("*")):
                if not f.is_file():
                    continue
                ext = f.suffix.lower()
                if ext in UNPLAYABLE_AUDIO or (cat not in AUDIO_CATS and ext not in IMAGE_EXT):
                    continue
                name = f.relative_to(base).with_suffix("").as_posix()
                rank = _pref_key(ext, order)
                if name.lower() in best and best[name.lower()] <= rank:
                    continue
                best[name.lower()] = rank
                index.setdefault(cat, {})[name.lower()] = {"n": name, "e": ext}
        self.config["assetIndex"] = index
        return index

    def save(self) -> None:
        d = self.root / "code" / "js" / "data"
        self.rescan_assets()
        datajs.write(d / "config.js", "MR.config", self.config, "config")
        datajs.write(d / "db.js", "MR.data.db", self.db, "database")
        mdir = d / "maps"
        mdir.mkdir(parents=True, exist_ok=True)
        for old in mdir.glob("map-*.js"):
            m = _MAP_RE.search(old.name)
            if m and int(m.group(1)) not in self.maps:
                old.unlink()
        for mid, m in self.maps.items():
            datajs.write(mdir / f"map-{int(mid)}.js", f"MR.data.maps[{int(mid)}]", m, f"map {mid}")
        write_html(self.root, self.title, self.config.get("lang", "pt-BR"))

    def log_history(self, entry: Dict[str, Any]) -> None:
        path = self.root / "code" / "rebuild-manifest.json"
        man: Dict[str, Any] = {}
        if path.exists():
            try:
                man = json.loads(path.read_text(encoding="utf-8"))
            except ValueError:
                man = {}
        man.setdefault("history", []).append(entry)
        path.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")


def open_built_game(src: str, workdir: Optional[Path] = None) -> BuiltGame:
    """Abre pasta ou .zip de um jogo recompilado. Zips são extraídos em ``workdir`` (ou temporário)."""
    p = Path(src).expanduser()
    if not p.exists():
        raise BuiltGameError(f"caminho não encontrado: {p}")
    if p.is_file():
        if p.suffix.lower() != ".zip":
            raise BuiltGameError("informe a pasta do jogo ou um arquivo .zip")
        wd = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="maker-rebuild-game-"))
        wd.mkdir(parents=True, exist_ok=True)
        safe_extract(p, wd)
        root = find_game_root(wd)
    else:
        root = find_game_root(p)
    if root is None:
        raise BuiltGameError("não parece um jogo gerado pelo MAKER-Rebuild (faltam Game.html e code/js/data/db.js)")
    return BuiltGame(root)


def copy_game(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst
