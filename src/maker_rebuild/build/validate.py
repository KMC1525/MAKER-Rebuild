"""Revisão determinística do jogo entregue: estrutura, assets, referências cruzadas, comandos e sintaxe JS."""
from __future__ import annotations

import shutil
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Set, Tuple

from . import commands as cmdmod
from .builder import RUNTIME_DIR
from .builtgame import BuiltGame

REQUIRED = ["Game.html", "code/html", "code/css", "code/js", "assets/sprites", "assets/background", "assets/ui-ux",
            "assets/music", "assets/sfx"]


def _bgm(o: Any) -> str:
    return (o or {}).get("name", "") if isinstance(o, dict) else ""


def asset_refs(db: Dict[str, Any], maps: Dict[int, dict], engine: str = "mv") -> Iterator[Tuple[Tuple[str, ...], str, str]]:
    """Gera ((categorias aceitas), nome, origem) para tudo que o jogo referencia."""
    for a in db.get("actors") or []:
        if a:
            yield ("characters",), a.get("characterName", ""), f"ator {a['id']}"
            yield ("faces",), a.get("faceName", ""), f"ator {a['id']}"
    for e in db.get("enemies") or []:
        if e:
            yield ("enemies", "sv_enemies"), e.get("battlerName", ""), f"inimigo {e['id']}"
    for t in db.get("tilesets") or []:
        if t:
            for i, n in enumerate(t.get("tilesetNames") or []):
                yield (("autotiles",) if engine == "xp" and i else ("tilesets",)), n, f"tileset {t['id']}"
    s = db.get("system") or {}
    yield ("titles1",), s.get("title1Name", ""), "sistema"
    yield ("titles2",), s.get("title2Name", ""), "sistema"
    for k in ("titleBgm", "battleBgm"):
        yield ("bgm",), _bgm(s.get(k)), "sistema"
    for k in ("gameoverMe", "victoryMe", "defeatMe"):
        yield ("me",), _bgm(s.get(k)), "sistema"
    for mid, m in maps.items():
        o = f"mapa {mid}"
        yield ("bgm",), _bgm(m.get("bgm")), o
        yield ("bgs",), _bgm(m.get("bgs")), o
        yield ("parallaxes",), m.get("parallaxName", ""), o
        yield ("battlebacks1",), m.get("battleback1Name", ""), o
        yield ("battlebacks2",), m.get("battleback2Name", ""), o
        for ev in m.get("events") or []:
            if not ev:
                continue
            for pg in ev.get("pages") or []:
                yield ("characters",), (pg.get("image") or {}).get("characterName", ""), f"mapa {mid} ev {ev['id']}"
    for origin, cont, key in cmdmod.iter_lists(db, maps):
        for c in cont.get(key) or []:
            code, p = c.get("code"), c.get("parameters") or []
            try:
                if code == 101:
                    yield ("faces",), p[0], origin
                elif code == 231:
                    yield ("pictures",), p[1], origin
                elif code in (241, 132, 140):
                    yield ("bgm",), _bgm(p[0]), origin
                elif code == 245:
                    yield ("bgs",), _bgm(p[0]), origin
                elif code in (249, 133, 139):
                    yield ("me",), _bgm(p[0]), origin
                elif code == 250:
                    yield ("se",), _bgm(p[0]), origin
                elif code == 322:
                    yield ("characters",), p[1], origin
                    yield ("faces",), p[3], origin
                elif code == 284:
                    yield ("parallaxes",), p[0], origin
                elif code == 205:
                    for rc in (p[1] or {}).get("list", []):
                        if rc.get("code") == 41:
                            yield ("characters",), rc["parameters"][0], origin
                        elif rc.get("code") == 44:
                            yield ("se",), _bgm(rc["parameters"][0]), origin
            except (IndexError, TypeError, AttributeError, KeyError):
                continue


def command_stats(db: Dict[str, Any], maps: Dict[int, dict], supported: Set[int]) -> Dict[str, Any]:
    cnt: Counter = Counter()
    ruby = js = 0
    plugin_cmds: Counter = Counter()
    where: Dict[int, str] = {}
    for origin, c in cmdmod.iter_commands(db, maps):
        code = c.get("code")
        cnt[code] += 1
        if code not in supported and code not in where:
            where[code] = origin
        if code == 355:
            if c.get("lang") == "ruby":
                ruby += 1
            else:
                js += 1
        elif code == 356:
            plugin_cmds[str((c.get("parameters") or [""])[0]).split(" ")[0]] += 1
        elif code == 357:
            p = c.get("parameters") or []
            plugin_cmds[f"{p[0]}.{p[1]}" if len(p) > 1 else str(p)] += 1
    unsup = {k: v for k, v in cnt.items() if k not in supported}
    total = sum(cnt.values()) or 1
    return {
        "total": sum(cnt.values()), "distinct": len(cnt), "counts": dict(cnt),
        "unsupported": unsup, "unsupportedFirstSeen": where, "ruby_scripts": ruby, "js_scripts": js,
        "plugin_commands": dict(plugin_cmds),
        "coverage": round(100.0 * (total - sum(unsup.values())) / total, 1),
    }


def check_js_syntax(game_dir: Path) -> List[str]:
    node = shutil.which("node")
    if not node:
        return []
    errs = []
    files = [p for p in (Path(game_dir) / "code" / "js").glob("*.js")]
    for sub in ("ext", "plugins"):
        files += list((Path(game_dir) / "code" / "js" / sub).glob("*.js"))
    files += [Path(game_dir) / "code" / "js" / "data" / n for n in ("config.js", "db.js")]
    for f in files:
        if not f.exists():
            continue
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        if r.returncode:
            errs.append(f"{f.relative_to(game_dir)}: {r.stderr.strip().splitlines()[0] if r.stderr else 'erro de sintaxe'}")
    return errs


def validate_game(game: BuiltGame, check_syntax: bool = True) -> Dict[str, Any]:
    rep: Dict[str, Any] = {"errors": [], "warnings": [], "info": []}
    root = game.root
    for rel in REQUIRED:
        if not (root / rel).exists():
            rep["errors"].append(f"estrutura: falta {rel}")
    idx = game.config.get("assetIndex", {})
    missing: Dict[str, Set[str]] = defaultdict(set)
    where: Dict[str, str] = {}
    for cats, name, origin in asset_refs(game.db, game.maps, game.engine):
        if not name:
            continue
        if not any(name.lower() in idx.get(c, {}) for c in cats):
            key = f"{cats[0]}/{name}"
            missing[cats[0]].add(name)
            where.setdefault(key, origin)
    for sysimg in ("Window", "IconSet"):
        if sysimg.lower() not in idx.get("system", {}):
            rep["warnings"].append(f"imagem de sistema ausente: system/{sysimg} (a UI usa fallback)")
    rep["missing_assets"] = {k: sorted(v) for k, v in missing.items()}
    n_missing = sum(len(v) for v in missing.values())
    if n_missing:
        rep["warnings"].append(f"{n_missing} asset(s) referenciado(s) não encontrados (veja missing_assets)")
    rep["missing_where"] = where

    # referências cruzadas
    db, maps = game.db, game.maps
    commons = {c["id"] for c in db.get("commonEvents") or [] if c}
    troops = {t["id"] for t in db.get("troops") or [] if t}
    bad: List[str] = []
    for origin, c in cmdmod.iter_commands(db, maps):
        code, p = c.get("code"), c.get("parameters") or []
        if code == 201 and p and p[0] == 0 and p[1] not in maps:
            bad.append(f"{origin}: teletransporte para mapa inexistente {p[1]}")
        elif code == 117 and p and p[0] not in commons:
            bad.append(f"{origin}: evento comum inexistente {p[0]}")
        elif code == 301 and p and p[0] == 0 and p[1] not in troops:
            bad.append(f"{origin}: tropa inexistente {p[1]}")
    for b in bad[:50]:
        rep["errors"].append(b)
    if len(bad) > 50:
        rep["errors"].append(f"... e mais {len(bad) - 50} referências quebradas")
    s = db.get("system") or {}
    if s.get("startMapId") not in maps:
        rep["errors"].append(f"mapa inicial {s.get('startMapId')} não existe")
    actors = db.get("actors") or [None]
    for aid in s.get("partyMembers") or []:
        if not isinstance(aid, int) or aid >= len(actors) or not actors[aid]:
            rep["errors"].append(f"membro inicial {aid} não existe")

    # comandos
    try:
        supported = cmdmod.runtime_supported(RUNTIME_DIR / "js")
    except OSError:
        supported = set(cmdmod.IMPLICIT)
    st = command_stats(db, maps, supported)
    rep["commands"] = st
    for code, n in sorted(st["unsupported"].items()):
        rep["warnings"].append(f"comando {code} ({cmdmod.CODE_NAMES.get(code, '?')}) usado {n}x e não suportado pelo runtime "
                               f"(1º uso: {st['unsupportedFirstSeen'].get(code)})")
    if st["ruby_scripts"]:
        rep["warnings"].append(f"{st['ruby_scripts']} linha(s) de script Ruby ainda não portadas para JS (use `maker-rebuild port`)")
    if st["plugin_commands"]:
        loaded = set(game.config.get("ports", []))
        pend = [k for k in st["plugin_commands"] if k not in loaded]
        if pend:
            rep["warnings"].append(f"{len(pend)} comando(s) de plugin sem port: {', '.join(sorted(pend)[:8])}")
    if check_syntax:
        for e in check_js_syntax(root):
            rep["errors"].append("JS: " + e)
    rep["info"].append(f"{len(maps)} mapas · {st['total']} comandos de evento · cobertura do runtime {st['coverage']}%")
    rep["ok"] = not rep["errors"]
    return rep
