"""Mapeamento estrutural do projeto (original ou já recompilado): números, idioma, riscos."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List

from . import ui
from .build import commands as cmdmod
from .build.builder import RUNTIME_DIR
from .build.validate import command_stats

_RANGES = [
    ("ja", re.compile(r"[぀-ヿ一-鿿]")), ("ko", re.compile(r"[가-힯]")),
    ("ru", re.compile(r"[Ѐ-ӿ]")), ("zh", re.compile(r"[㐀-䶿]")),
]
_STOP = {
    "pt": {"que", "não", "uma", "para", "você", "com", "isso", "está", "são", "mais", "ele", "ela", "por", "meu"},
    "en": {"the", "you", "and", "that", "with", "have", "this", "what", "your", "are", "for", "not", "was"},
    "es": {"que", "los", "las", "una", "por", "con", "para", "pero", "esto", "está", "como", "más", "del"},
    "fr": {"les", "des", "est", "pas", "vous", "que", "une", "pour", "dans", "qui", "sur", "avec"},
}


def guess_language(samples: Iterable[str]) -> str:
    text = " ".join(samples)[:20000]
    if not text.strip():
        return "?"
    letters = max(1, sum(ch.isalpha() for ch in text))
    for code, rx in _RANGES:
        if len(rx.findall(text)) / letters > 0.25:
            return code
    words = re.findall(r"[a-záéíóúâêôãõçñàèù]+", text.lower())
    score = {k: sum(w in v for w in words) for k, v in _STOP.items()}
    best = max(score, key=lambda k: score[k])
    return best if score[best] >= 3 else "?"


def dialog_lines(db: Dict[str, Any], maps: Dict[int, dict]) -> List[str]:
    return [str(c["parameters"][0]) for _o, c in cmdmod.iter_commands(db, maps)
            if c.get("code") in (401, 405) and c.get("parameters")]


def analyze(obj: Any) -> Dict[str, Any]:
    """``obj``: Project ou BuiltGame."""
    db, maps = obj.db, obj.maps
    supported = cmdmod.runtime_supported(RUNTIME_DIR / "js")
    st = command_stats(db, maps, supported)
    lines = dialog_lines(db, maps)
    n_ev = n_pages = 0
    per_map = []
    for mid, m in maps.items():
        evs = [e for e in (m.get("events") or []) if e]
        n_ev += len(evs)
        n_pages += sum(len(e.get("pages") or []) for e in evs)
        per_map.append({"id": mid, "name": m.get("displayName") or m.get("name") or "", "w": m.get("width"),
                        "h": m.get("height"), "events": len(evs)})
    per_map.sort(key=lambda x: -x["events"])
    count = lambda k: sum(1 for x in (db.get(k) or []) if x)  # noqa: E731
    rep: Dict[str, Any] = {
        "title": obj.title, "engine": getattr(obj, "engine", "?"),
        "label": getattr(obj, "label", None) or getattr(obj, "engine", "?"),
        "support": getattr(obj, "support", ""),
        "screen": f"{obj.screen_w}x{obj.screen_h}", "tile": obj.tile_size,
        "maps": len(maps), "events": n_ev, "pages": n_pages,
        "database": {k: count(k) for k in ("actors", "classes", "skills", "items", "weapons", "armors", "enemies",
                                           "troops", "states", "commonEvents", "tilesets")},
        "commands": st, "dialogLines": len(lines), "language": guess_language(lines + [
            (a or {}).get("name", "") for a in db.get("items") or []]),
        "topMaps": per_map[:5], "plugins": [], "rubyScripts": len(getattr(obj, "scripts", []) or []), "assets": {},
        "warnings": list(getattr(obj, "warnings", [])), "attention": [],
    }
    assets = getattr(obj, "assets", None)
    if assets is not None:
        c = Counter(a.category for a in assets)
        rep["assets"] = dict(c)
        rep["assetsEncrypted"] = sum(1 for a in assets if a.encrypted)
        rep["audioUnplayable"] = sum(1 for a in assets if a.ext in (".mid", ".midi", ".wma"))
    else:
        rep["assets"] = {k: len(v) for k, v in (obj.config.get("assetIndex") or {}).items()}
    rep["plugins"] = [{"name": p.get("name"), "on": p.get("status")} for p in getattr(obj, "plugins", [])]
    att = rep["attention"]
    if rep["plugins"]:
        on = [p["name"] for p in rep["plugins"] if p["on"]]
        att.append(f"{len(on)} plugin(s) ativo(s) — não rodam no runtime novo; precisam de port (`maker-rebuild port`): "
                   f"{', '.join(on[:6])}{'…' if len(on) > 6 else ''}")
    if rep["rubyScripts"]:
        att.append(f"{rep['rubyScripts']} script(s) Ruby customizados — lógica não portada automaticamente")
    if st["ruby_scripts"]:
        att.append(f"{st['ruby_scripts']} chamada(s) de script Ruby em eventos — precisam de port para JS")
    if st["js_scripts"]:
        att.append(f"{st['js_scripts']} chamada(s) de script JS em eventos — rodam se usarem só a API de compatibilidade")
    if st["unsupported"]:
        att.append("comandos sem suporte no runtime: " + ", ".join(
            f"{k} ({cmdmod.CODE_NAMES.get(k, '?')}) ×{v}" for k, v in sorted(st["unsupported"].items())))
    if rep.get("audioUnplayable"):
        att.append(f"{rep['audioUnplayable']} áudio(s) MIDI/WMA não tocam no navegador — converta para .ogg (`--convert-audio`)")
    if rep.get("assetsEncrypted"):
        att.append(f"{rep['assetsEncrypted']} asset(s) criptografados serão descriptografados na conversão")
    if getattr(obj, "engine", "") in ("xp", "vx", "rm2k", "rm2k3"):
        att.append(f"suporte {rep['support']}")
    return rep


def print_report(rep: Dict[str, Any]) -> None:
    ui.heading(f"{rep['title']}  ·  {rep['label']}")
    ui.kv([
        ("Suporte", rep["support"] or "-"), ("Tela / tile", f"{rep['screen']} / {rep['tile']}px"),
        ("Mapas / eventos", f"{rep['maps']} / {rep['events']} ({rep['pages']} páginas)"),
        ("Idioma provável", rep["language"]), ("Linhas de diálogo", rep["dialogLines"]),
        ("Comandos de evento", f"{rep['commands']['total']} ({rep['commands']['distinct']} tipos) — "
                               f"cobertura do runtime {rep['commands']['coverage']}%"),
    ])
    ui.heading("Banco de dados")
    ui.kv(list(rep["database"].items()))
    if rep["assets"]:
        ui.heading("Assets")
        ui.kv(sorted(rep["assets"].items()))
    if rep["topMaps"]:
        ui.heading("Mapas com mais eventos")
        ui.table(["id", "nome", "tamanho", "eventos"],
                 [[m["id"], m["name"], f"{m['w']}x{m['h']}", m["events"]] for m in rep["topMaps"]])
    if rep["attention"]:
        ui.heading("Pontos de atenção")
        for a in rep["attention"]:
            ui.warn(a)
    for w in rep["warnings"]:
        ui.warn(w)
