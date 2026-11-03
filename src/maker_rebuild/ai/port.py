"""Porte de scripts para o runtime: Ruby (XP/VX/VXA) → JS e plugins MV/MZ → módulos ext/.

1) Um tradutor determinístico conservador resolve os one-liners comuns (switches, variáveis, ouro, itens...).
2) O restante vai para a IA em lotes; todo JS devolvido passa por ``node --check`` antes de ser aceito.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..build import commands as cmdmod
from ..build.builder import slugify
from . import prompts
from .client import AIClient, AIOutputError
from .patch import _js_syntax

DEFAULT_SCRIPT = re.compile(r"^(Game_|Scene_|Window_|Sprite|Spriteset_|Cache|DataManager|BattleManager|SoundManager|SceneManager|Vocab|"
                            r"RPG|Main|Interpreter|Input|Tilemap|Plane|Module|Basic|▼|Materials|Game Objects|Sprites|Windows|Scenes|"
                            r"Main Process|Bitmap|Color|Font|Graphics|Audio|Rect|Table|Tone|Viewport|Window$)", re.I)

# --- tradutor determinístico ------------------------------------------------------------------
_NUM = r"(\d+)"
_EXPR = r"([\w\s\+\-\*/%\(\)\.\[\]\$']+)"


def _expr(e: str) -> Optional[str]:
    """Traduz uma expressão aritmética simples com leituras de variáveis/switches."""
    e = e.strip().rstrip(";")
    e = re.sub(r"\$game_variables\[(\d+)\]", r"$gameVariables.value(\1)", e)
    e = re.sub(r"\$game_switches\[(\d+)\]", r"$gameSwitches.value(\1)", e)
    e = re.sub(r"\$game_party\.gold\b", "$gameParty.gold()", e)
    e = re.sub(r"\brand\((\d+)\)", r"Math.floor(Math.random()*\1)", e)
    e = e.replace("true", "true").replace("false", "false")
    if re.search(r"[A-Za-z_]", re.sub(r"\$game(Variables|Switches|Party)\.(value|gold)|Math\.(floor|random)|true|false", "", e)):
        return None
    return e


def port_line(line: str) -> Optional[str]:
    s = line.strip()
    if not s or s.startswith("#"):
        return "" if not s else "// " + s[1:].strip()
    m = re.fullmatch(r"\$game_switches\[(\d+)\]\s*=\s*(true|false)", s)
    if m:
        return f"$gameSwitches.setValue({m.group(1)}, {m.group(2)});"
    m = re.fullmatch(r"\$game_variables\[(\d+)\]\s*([\+\-\*/%]?)=\s*(.+)", s)
    if m:
        ex = _expr(m.group(3))
        if ex is None:
            return None
        vid, op = m.group(1), m.group(2)
        cur = f"$gameVariables.value({vid})"
        return f"$gameVariables.setValue({vid}, {cur} {op} ({ex}));" if op else f"$gameVariables.setValue({vid}, {ex});"
    m = re.fullmatch(r"\$game_party\.(gain|lose)_gold\((.+)\)", s)
    if m:
        ex = _expr(m.group(2))
        return None if ex is None else f"$gameParty.{m.group(1)}Gold({ex});"
    m = re.fullmatch(r"\$game_party\.(gain|lose)_item\(\$data_(items|weapons|armors)\[(\d+)\],\s*(\d+)\)", s)
    if m:
        sign = "" if m.group(1) == "gain" else "-"
        coll = {"items": "$dataItems", "weapons": "$dataWeapons", "armors": "$dataArmors"}[m.group(2)]
        return f"$gameParty.gainItem({coll}[{m.group(3)}], {sign}{m.group(4)});"
    m = re.fullmatch(r"\$game_party\.add_actor\((\d+)\)", s)
    if m:
        return f"$gameParty.addActor({m.group(1)});"
    m = re.fullmatch(r"\$game_party\.remove_actor\((\d+)\)", s)
    if m:
        return f"$gameParty.removeActor({m.group(1)});"
    m = re.fullmatch(r'\$game_self_switches\[\[@map_id,\s*@event_id,\s*"([A-D])"\]\]\s*=\s*(true|false)', s)
    if m:
        return f'$gameSelfSwitches.setValue([$gameMap.mapId(), this._eventId, "{m.group(1)}"], {m.group(2)});'
    m = re.fullmatch(r"\$game_player\.reserve_transfer\((.+)\)", s)
    return None


def port_ruby_simple(src: str) -> Optional[str]:
    out = []
    for ln in src.split("\n"):
        r = port_line(ln)
        if r is None:
            return None
        if r:
            out.append(r)
    return "\n".join(out)


# --- agrupamento de comandos 355/655 ----------------------------------------------------------

def script_groups(game: Any) -> List[Tuple[str, List[Dict[str, Any]], str]]:
    """[(origem, [comandos 355,655...], texto)] dos scripts Ruby ainda não portados."""
    groups = []
    for origin, cont, key in cmdmod.iter_lists(game.db, game.maps):
        lst = cont.get(key) or []
        i = 0
        while i < len(lst):
            if lst[i].get("code") == 355 and lst[i].get("lang") == "ruby":
                j = i + 1
                while j < len(lst) and lst[j].get("code") == 655:
                    j += 1
                cmds = lst[i:j]
                text = "\n".join(str(c["parameters"][0]) for c in cmds if c.get("parameters"))
                groups.append((origin, cmds, text))
                i = j
            else:
                i += 1
    return groups


def _replace_with_js(cmds: List[Dict[str, Any]], js: str) -> None:
    lines = js.split("\n") or [""]
    indent = cmds[0].get("indent", 0)
    cmds[0]["parameters"] = [lines[0]]
    cmds[0].pop("lang", None)
    # reaproveita os objetos existentes; sobras viram 655 vazios (mantém índices da lista estáveis)
    for k, c in enumerate(cmds[1:], 1):
        c["parameters"] = [lines[k] if k < len(lines) else ""]
        c["code"] = 655
        c.pop("lang", None)
    if len(lines) > len(cmds):
        extra = "\n".join(lines[len(cmds):])
        cmds[-1]["parameters"] = [cmds[-1]["parameters"][0] + "\n" + extra]  # linhas extras ficam na última (executadas juntas)
    _ = indent


@dataclass
class PortReport:
    ruby_groups: int = 0
    deterministic: int = 0
    ai: int = 0
    failed: List[str] = field(default_factory=list)
    modules: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def port_event_scripts(ai: Optional[AIClient], game: Any, rep: PortReport) -> None:
    groups = script_groups(game)
    rep.ruby_groups = len(groups)
    pending: Dict[str, List[Tuple[List[Dict[str, Any]], str]]] = {}
    for _origin, cmds, text in groups:
        js = port_ruby_simple(text)
        if js is not None and (_js_syntax("(function(){" + js + "\n})") is None):
            _replace_with_js(cmds, js)
            rep.deterministic += 1
        else:
            pending.setdefault(text, []).append((cmds, text))
    if not pending:
        return
    if ai is None:
        rep.warnings.append(f"{len(pending)} script(s) Ruby distintos precisam de IA para o porte (use --provider)")
        return
    texts = list(pending)
    for start in range(0, len(texts), 12):
        chunk = texts[start:start + 12]
        payload = json.dumps([{"id": f"s{start + i}", "ruby": t} for i, t in enumerate(chunk)], ensure_ascii=False)
        try:
            data = ai.ask_json("port", "Porte cada script Ruby (RPG Maker VX Ace/VX/XP, chamado por um comando de evento) para JS do runtime.\n"
                               "Use somente a API de compatibilidade ($gameVariables, $gameSwitches, $gameParty, $gamePlayer, $gameMap, "
                               "$gameMessage, $dataItems...). `this._eventId` é o id do evento atual.\n"
                               'Saída: {"ports":[{"id":"s0","js":"...","notes":"..."}]}\nENTRADA:\n' + payload,
                               extra_system=prompts.PORT_TASK, with_api=True, cache=True, desc=f"portando {len(chunk)} scripts Ruby",
                               temperature=0.2)
        except AIOutputError as e:
            rep.warnings.append(f"lote de scripts falhou: {e}")
            continue
        for p in (data.get("ports") if isinstance(data, dict) else data) or []:
            idx = int(str(p.get("id", "s-1"))[1:]) - start if str(p.get("id", "")).startswith("s") else -1
            if not 0 <= idx < len(chunk) or not isinstance(p.get("js"), str):
                continue
            js = p["js"]
            err = _js_syntax("(function(){" + js + "\n})")
            if err:
                rep.failed.append(f"{chunk[idx][:40]!r}: {err}")
                continue
            for cmds, _t in pending[chunk[idx]]:
                _replace_with_js(cmds, js)
            rep.ai += 1


def port_modules(ai: Optional[AIClient], game: Any, rep: PortReport) -> None:
    """Plugins MV/MZ e scripts Ruby customizados → ``code/js/ext/port-*.js`` (revisão humana recomendada)."""
    items: List[Tuple[str, str, str]] = []   # (nome, tipo, fonte)
    for name, src in (getattr(game, "plugin_sources", {}) or {}).items():
        items.append((name, "plugin MV/MZ", src))
    for s in getattr(game, "scripts", []) or []:
        nm = s["name"]
        base = re.sub(r"^\d+-|\.rb\.txt$", "", nm)
        if not DEFAULT_SCRIPT.match(base.replace("-", "_")) and len(s["source"]) > 80:
            items.append((base, "script Ruby customizado", s["source"]))
    if not items:
        return
    if ai is None:
        rep.warnings.append(f"{len(items)} plugin(s)/script(s) customizados sem port (requer IA)")
        return
    out_dir = Path(game.root) / "code" / "js" / "ext"
    ported = list(game.config.setdefault("ports", []))
    for name, kind, src in items:
        slug = slugify(name)
        dest = out_dir / f"port-{slug}.js"
        user = (f"Porte este {kind} chamado '{name}' para um módulo JS do MAKER-Rebuild.\n"
                'Saída JSON: {"js": "código completo do módulo", "commands": ["nomes de comandos de plugin/eventos que ele atende"], '
                '"limitations": ["o que não foi possível reproduzir"], "notes": "..."}\n'
                "O módulo deve se registrar via MR.ext (hooks, commands, pluginCommands) e não depender de rpg_*.js/rmmz_*.js.\n"
                f"=== CÓDIGO ORIGINAL ===\n{src[:30000]}")
        try:
            data = ai.ask_json("port", user, extra_system=prompts.PORT_TASK, with_api=True, cache=True, desc=f"portando {kind} {name}",
                               temperature=0.2)
        except AIOutputError as e:
            rep.warnings.append(f"port de {name} falhou: {e}")
            continue
        js = data.get("js") if isinstance(data, dict) else None
        if not isinstance(js, str) or not js.strip():
            rep.warnings.append(f"port de {name}: resposta sem JS")
            continue
        err = _js_syntax(js)
        if err:
            rep.failed.append(f"{name}: {err}")
            continue
        header = (f"/* Port gerado por IA de: {kind} '{name}' — REVISAR antes de publicar.\n"
                  f" * Limitações: {'; '.join(map(str, data.get('limitations') or [])) or 'n/d'} */\n")
        out_dir.mkdir(parents=True, exist_ok=True)
        dest.write_text(header + js, encoding="utf-8")
        rep.modules.append(dest.name)
        ported += [str(c) for c in (data.get("commands") or [])] + [name]
    game.config["ports"] = sorted(set(ported))


def port_game(ai: Optional[AIClient], game: Any, modules: bool = True) -> PortReport:
    rep = PortReport()
    port_event_scripts(ai, game, rep)
    if modules:
        port_modules(ai, game, rep)
    return rep
