"""Resumo compacto do jogo para o contexto do LLM (respeita um orçamento de caracteres)."""
from __future__ import annotations

from typing import Any, Dict, List

from ..build import commands as cmdmod


def _names(arr: Any, limit: int, extra=None) -> str:
    out = []
    for e in (arr or [])[:limit + 1]:
        if e:
            out.append(f"{e['id']}:{e.get('name', '')}" + (f"({extra(e)})" if extra else ""))
    more = len([e for e in (arr or []) if e]) - limit
    return ", ".join(out) + (f" … +{more}" if more > 0 else "")


def first_text(m: Dict[str, Any], ev: Dict[str, Any]) -> str:
    for pg in ev.get("pages") or []:
        for c in pg.get("list") or []:
            if c.get("code") == 401 and c.get("parameters"):
                return str(c["parameters"][0])[:70]
    return ""


def map_ascii(m: Dict[str, Any], max_w: int = 40, max_h: int = 24) -> str:
    """Mini-visão do mapa: '#' bloqueado por tile alto em z1/z2 (heurística), '.' vazio, letras = eventos."""
    w, h = m["width"], m["height"]
    if w > max_w or h > max_h:
        return ""
    rows = []
    evpos = {(e["x"], e["y"]): chr(65 + (e["id"] - 1) % 26) for e in (m.get("events") or []) if e}
    for y in range(h):
        row = ""
        for x in range(w):
            if (x, y) in evpos:
                row += evpos[(x, y)]
                continue
            upper = any(m["data"][(z * h + y) * w + x] for z in (1, 2, 3))
            row += "#" if upper else "."
        rows.append(row)
    return "\n".join(rows)


def digest(game: Any, budget: int = 40000, notes: List[str] | None = None, detail_maps: List[int] | None = None) -> str:
    db, maps = game.db, game.maps
    s = db.get("system") or {}
    lines: List[str] = [f"JOGO: {game.title} | engine original: {game.engine} | tela {game.screen_w}x{game.screen_h} | tile {game.tile_size}px"]
    lines.append(f"Mapa inicial: {s.get('startMapId')} ({s.get('startX')},{s.get('startY')}) | grupo inicial: {s.get('partyMembers')} | moeda: {s.get('currencyUnit')}")
    for kind, lim in (("actors", 12), ("classes", 12), ("skills", 40), ("items", 60), ("weapons", 40), ("armors", 40), ("enemies", 40),
                      ("states", 20), ("commonEvents", 30)):
        arr = db.get(kind)
        if arr and any(arr):
            lines.append(f"{kind.upper()}: {_names(arr, lim)}")
    sw = [f"{i}:{n}" for i, n in enumerate(s.get('switches') or []) if n][:60]
    vr = [f"{i}:{n}" for i, n in enumerate(s.get('variables') or []) if n][:60]
    if sw:
        lines.append("SWITCHES: " + ", ".join(sw))
    if vr:
        lines.append("VARIABLES: " + ", ".join(vr))
    ts = [f"{t['id']}:{t.get('name')}[{', '.join(n for n in t.get('tilesetNames', []) if n)}]" for t in (db.get('tilesets') or []) if t]
    lines.append("TILESETS: " + "; ".join(ts[:8]))
    idx = getattr(game, "config", {}).get("assetIndex") or {}
    for cat in ("characters", "faces", "enemies", "pictures", "bgm", "se", "parallaxes"):
        if idx.get(cat):
            names = sorted(v["n"] for v in idx[cat].values())
            lines.append(f"ASSETS {cat}: " + ", ".join(names[:50]) + (f" … +{len(names) - 50}" if len(names) > 50 else ""))
    lines.append("MAPAS:")
    infos = {i["id"]: i for i in (db.get("mapInfos") or []) if i}
    for mid in sorted(maps):
        m = maps[mid]
        evs = [e for e in (m.get("events") or []) if e]
        head = f"  #{mid} {infos.get(mid, {}).get('name') or m.get('name', '')} ({m['width']}x{m['height']}, tileset {m['tilesetId']}, {len(evs)} eventos)"
        lines.append(head)
        for e in evs[:8]:
            lines.append(f"     ev{e['id']} '{e.get('name')}' @({e['x']},{e['y']}) {first_text(m, e)!r}")
        if len("\n".join(lines)) > budget * 0.7:
            lines.append("  … (mapas restantes omitidos)")
            break
    for mid in detail_maps or []:
        if mid in maps:
            art = map_ascii(maps[mid])
            if art:
                lines.append(f"VISÃO DO MAPA {mid} ('#' = tile em camada alta, letras = eventos A=ev1,B=ev2…):\n{art}")
    if getattr(game, "plugins", None):
        lines.append("PLUGINS: " + ", ".join(str(p.get("name")) for p in game.plugins[:30]))
    for n in notes or []:
        lines.append("DOCUMENTO DO AUTOR:\n" + n)
    text = "\n".join(lines)
    return text[:budget] + ("\n… (contexto truncado)" if len(text) > budget else "")


def cmd_cheatsheet() -> str:
    return ", ".join(f"{k}={v}" for k, v in cmdmod.CODE_NAMES.items())
