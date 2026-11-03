"""Monta a pasta do jogo entregue:

    game-x/
      Game.html
      code/{html,css,js}/            (js/ contém o runtime, data/, ext/ e plugins/)
      assets/{sprites,background,ui-ux,music,sfx}/
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import shutil
import unicodedata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .. import __version__
from ..assets import AUDIO_CATS, TARGET_DIRS, UNPLAYABLE_AUDIO, AssetEntry
from ..project import Project
from . import commands as cmdmod
from . import datajs
from .i18n import ui_strings

RUNTIME_DIR = Path(__file__).resolve().parent.parent / "runtime"
RUNTIME_JS = ["mr-core.js", "mr-ui.js", "mr-map.js", "mr-interpreter.js", "mr-battle.js", "mr-scenes.js", "mr-main.js"]
AUDIO_PREF = [".ogg", ".m4a", ".mp3", ".wav", ".flac", ".aac"]
IMAGE_PREF = [".png", ".webp", ".jpg", ".jpeg", ".gif", ".bmp", ".svg"]


def slugify(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-").lower()
    return t or "game"


def _pref_key(ext: str, order: List[str]) -> int:
    return order.index(ext) if ext in order else len(order)


def render(tpl: str, **kw: str) -> str:
    for k, v in kw.items():
        tpl = tpl.replace("{{" + k + "}}", v)
    return tpl


def script_tags(game_dir: Path) -> str:
    """Ordem de carga: runtime → config → banco de dados → módulos ext/ → plugins/ portados."""
    tags = [f"code/js/{n}" for n in RUNTIME_JS[:-1]]
    tags += ["code/js/data/config.js", "code/js/data/db.js"]
    for sub in ("ext", "plugins"):
        d = Path(game_dir) / "code" / "js" / sub
        if d.is_dir():
            tags += [f"code/js/{sub}/{p.name}" for p in sorted(d.glob("*.js"))]
    tags.append(f"code/js/{RUNTIME_JS[-1]}")
    return "\n".join(f'<script src="{t}"></script>' for t in tags)


def write_html(game_dir: Path, title: str, lang: str = "pt-BR") -> None:
    tpl = (RUNTIME_DIR / "html" / "game.html.tpl").read_text(encoding="utf-8")
    html = render(tpl, LANG=lang, TITLE=_esc(title), VERSION=__version__, SCRIPTS=script_tags(game_dir))
    (Path(game_dir) / "Game.html").write_text(html, encoding="utf-8")


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def copy_runtime(game_dir: Path) -> None:
    gd = Path(game_dir)
    (gd / "code" / "js").mkdir(parents=True, exist_ok=True)
    for n in RUNTIME_JS:
        shutil.copyfile(RUNTIME_DIR / "js" / n, gd / "code" / "js" / n)
    (gd / "code" / "css").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNTIME_DIR / "css" / "game.css", gd / "code" / "css" / "game.css")
    theme = gd / "code" / "css" / "theme.css"
    if not theme.exists():  # arquivo do usuário/IA: nunca sobrescrever
        shutil.copyfile(RUNTIME_DIR / "css" / "theme.css", theme)
    (gd / "code" / "html").mkdir(parents=True, exist_ok=True)


def build_asset_index(entries: List[AssetEntry]) -> Dict[str, Dict[str, Dict[str, str]]]:
    index: Dict[str, Dict[str, Dict[str, str]]] = {}
    best: Dict[tuple, int] = {}
    for a in entries:
        if a.ext in UNPLAYABLE_AUDIO or a.ext == ".wma":
            continue
        order = AUDIO_PREF if a.category in AUDIO_CATS else IMAGE_PREF
        k = (a.category, a.name.lower())
        rank = _pref_key(a.ext, order)
        if k in best and best[k] <= rank:
            continue
        best[k] = rank
        index.setdefault(a.category, {})[a.name.lower()] = {"n": a.name, "e": a.ext}
    return index


def write_assets(proj: Project, game_dir: Path, progress: Optional[Callable[[int, int, str], None]] = None,
                 convert_audio: bool = False) -> Dict[str, Any]:
    stats = {"files": 0, "bytes": 0, "errors": [], "unplayable": [], "by_category": {}}
    total = len(proj.assets)
    kept: List[AssetEntry] = []
    for i, a in enumerate(proj.assets, 1):
        try:
            data = a.reader()
        except Exception as e:  # noqa: BLE001
            stats["errors"].append(f"{a.origin}: {e}")
            continue
        entry = a
        if a.category in AUDIO_CATS and (a.ext in UNPLAYABLE_AUDIO):
            stats["unplayable"].append(a.origin)
            if convert_audio:
                from .audio import convert
                res = convert(data, a.ext)
                if res:
                    data, entry = res, AssetEntry(a.category, a.name, ".ogg", a.reader, a.origin)
        dest = Path(game_dir) / entry.rel_target
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        kept.append(entry)
        stats["files"] += 1
        stats["bytes"] += len(data)
        stats["by_category"][a.category] = stats["by_category"].get(a.category, 0) + 1
        if progress:
            progress(i, total, a.category)
    proj_assets = kept
    stats["index"] = build_asset_index(proj_assets)
    # fontes
    fonts = []
    for name, data in proj.fonts.items():
        dest = Path(game_dir) / TARGET_DIRS["fonts"] / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        fonts.append(name)
    stats["fonts"] = fonts
    return stats


def font_css(fonts: List[str]) -> str:
    if not fonts:
        return ""
    pick = next((f for f in fonts if "mplus" in f.lower() or "game" in f.lower()), fonts[0])
    return ('@font-face { font-family: "GameFont"; src: url("../../assets/ui-ux/fonts/%s"); }\n' % pick.replace('"', ""))


def game_config(proj: Project, slug: str, index: dict, fonts: List[str], lang: str, ui_lang: str) -> Dict[str, Any]:
    cfg = {
        "title": proj.title, "engine": proj.engine, "tileSize": proj.tile_size,
        "screen": {"w": proj.screen_w, "h": proj.screen_h},
        "paths": {k: v for k, v in TARGET_DIRS.items()},
        "assetIndex": index, "fonts": fonts, "windowskin": "Window",
        "pixelated": proj.tile_size <= 32, "mapScriptDir": "code/js/data/maps", "saveKey": slug,
        "lang": lang, "ui": ui_strings(ui_lang), "extraMenu": [],
        "generator": {"name": "MAKER-Rebuild", "version": __version__},
    }
    return cfg


def write_data(proj: Project, game_dir: Path, cfg: Dict[str, Any]) -> None:
    gd = Path(game_dir)
    d = gd / "code" / "js" / "data"
    datajs.write(d / "config.js", "MR.config", cfg, "config")
    db = {k: v for k, v in proj.db.items()}
    datajs.write(d / "db.js", "MR.data.db", db, "database")
    mdir = d / "maps"
    if mdir.exists():
        shutil.rmtree(mdir)
    for mid, m in proj.maps.items():
        datajs.write(mdir / f"map-{mid}.js", f"MR.data.maps[{int(mid)}]", m, f"map {mid}")


def write_sources(proj: Project, game_dir: Path) -> Dict[str, int]:
    """Preserva plugins MV/MZ e scripts Ruby originais (referência para o porte via IA)."""
    gd = Path(game_dir)
    out = {"plugins": 0, "ruby": 0}
    if proj.plugins:
        pdir = gd / "code" / "js" / "plugins" / "_original"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "plugins.json").write_text(json.dumps(proj.plugins, ensure_ascii=False, indent=1), encoding="utf-8")
        for name, src in proj.plugin_sources.items():
            (pdir / f"{slugify(name)}.js.txt").write_text(src, encoding="utf-8")
            out["plugins"] += 1
    if proj.scripts:
        sdir = gd / "code" / "js" / "scripts-ruby"
        sdir.mkdir(parents=True, exist_ok=True)
        for i, s in enumerate(proj.scripts, 1):
            (sdir / f"{i:03d}-{slugify(s['name'])}.rb.txt").write_text(s["source"], encoding="utf-8")
            out["ruby"] += 1
    return out


def write_about(proj: Project, game_dir: Path, stats: Dict[str, Any], lang: str) -> None:
    tpl = (RUNTIME_DIR / "html" / "about.html.tpl").read_text(encoding="utf-8")
    html = render(tpl, LANG=lang, TITLE=_esc(proj.title), VERSION=__version__, ENGINE=proj.label,
                  DATE=_dt.datetime.now().strftime("%Y-%m-%d %H:%M"), MAPS=str(len(proj.maps)),
                  ASSETS=str(stats.get("files", 0)))
    (Path(game_dir) / "code" / "html" / "about.html").write_text(html, encoding="utf-8")


def write_manifest(game_dir: Path, proj: Project, stats: Dict[str, Any], extra: Optional[dict] = None) -> None:
    man = {
        "generator": {"name": "MAKER-Rebuild", "version": __version__},
        "createdAt": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "source": {"engine": proj.engine, "label": proj.label, "title": proj.title, "support": proj.support},
        "stats": {"maps": len(proj.maps), "assets": stats.get("files", 0), "bytes": stats.get("bytes", 0),
                  "byCategory": stats.get("by_category", {})},
        "warnings": proj.warnings, "history": [],
    }
    path = Path(game_dir) / "code" / "rebuild-manifest.json"
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            man["history"] = old.get("history", [])
        except ValueError:
            pass
    if extra:
        man.update(extra)
    path.write_text(json.dumps(man, ensure_ascii=False, indent=2), encoding="utf-8")


def build_game(proj: Project, out_root: Path, name: Optional[str] = None, *, lang: str = "pt-BR", ui_lang: str = "pt-BR",
               progress: Optional[Callable[[int, int, str], None]] = None, convert_audio: bool = False,
               extra_manifest: Optional[dict] = None) -> Path:
    """Gera ``out_root/<name>/`` e devolve o caminho."""
    slug = name or slugify(proj.title)
    gd = Path(out_root) / slug
    if gd.exists():
        shutil.rmtree(gd)
    for sub in ("code/html", "code/css", "code/js", "assets/sprites", "assets/background", "assets/ui-ux", "assets/music", "assets/sfx"):
        (gd / sub).mkdir(parents=True, exist_ok=True)
    cmdmod.normalize_project(proj.db, proj.maps, proj.engine)
    copy_runtime(gd)
    stats = write_assets(proj, gd, progress, convert_audio)
    (gd / "code" / "css" / "fonts.css").write_text(font_css(stats["fonts"]), encoding="utf-8")
    cfg = game_config(proj, slug, stats["index"], stats["fonts"], lang, ui_lang)
    write_data(proj, gd, cfg)
    src = write_sources(proj, gd)
    write_html(gd, proj.title, lang)
    write_about(proj, gd, stats, lang)
    extra = dict(extra_manifest or {})
    extra["sources"] = src
    extra["audioUnplayable"] = stats["unplayable"][:200]
    extra["assetErrors"] = stats["errors"][:200]
    write_manifest(gd, proj, stats, extra)
    proj.warnings += [f"asset ignorado: {e}" for e in stats["errors"][:20]]
    if stats["unplayable"]:
        proj.warnings.append(f"{len(stats['unplayable'])} arquivo(s) de áudio MIDI/WMA copiados mas não tocáveis no navegador "
                             f"(use --convert-audio ou converta para .ogg).")
    return gd


def tree_hash(game_dir: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(Path(game_dir).rglob("*")):
        if p.is_file() and "assets" not in p.parts:
            h.update(p.relative_to(game_dir).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()[:16]
