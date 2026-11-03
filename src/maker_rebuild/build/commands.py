"""Comandos de evento: normalização XP/VX/VXA → convenção MV e tabela de suporte do runtime."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

# Fallback caso o runtime não esteja acessível; a lista real é lida de mr-interpreter.js
# (``supported_codes``) e o teste tests/test_runtime.py garante a consistência.
IMPLICIT = {0, 108, 401, 402, 403, 404, 405, 408, 411, 412, 413, 601, 602, 603, 604, 605, 655,
            # puramente visuais / sem efeito de lógica: ignorados em silêncio pelo runtime
            138, 137, 139, 140, 202, 206, 212, 216, 217, 233, 234, 236, 251, 261, 283}

CODE_NAMES = {
    101: "Mostrar texto", 102: "Mostrar escolhas", 103: "Entrada numérica", 104: "Escolher item", 105: "Texto rolante",
    108: "Comentário", 111: "Condição", 112: "Laço", 113: "Quebrar laço", 115: "Sair do evento", 116: "Apagar evento",
    117: "Evento comum", 118: "Rótulo", 119: "Ir para rótulo", 121: "Interruptor", 122: "Variável", 123: "Interruptor local",
    124: "Cronômetro", 125: "Dinheiro", 126: "Itens", 127: "Armas", 128: "Armaduras", 129: "Grupo", 201: "Teletransportar",
    202: "Definir veículo", 203: "Posicionar evento", 204: "Rolar mapa", 205: "Rota de movimento", 206: "Embarcar/desembarcar",
    211: "Transparência", 212: "Animação", 213: "Balão", 214: "Apagar evento", 216: "Seguidores", 217: "Reunir seguidores",
    221: "Fade out", 222: "Fade in", 223: "Tonalidade", 224: "Flash", 225: "Tremor", 230: "Esperar", 231: "Mostrar imagem",
    232: "Mover imagem", 233: "Girar imagem", 234: "Tonalidade da imagem", 235: "Apagar imagem", 236: "Clima",
    241: "BGM", 242: "Fade BGM", 243: "Salvar BGM", 244: "Retomar BGM", 245: "BGS", 246: "Fade BGS", 249: "ME", 250: "SE",
    251: "Parar SE", 261: "Vídeo", 281: "Nome do mapa", 282: "Tileset", 283: "Fundo de batalha", 284: "Parallax",
    285: "Info do local", 301: "Batalha", 302: "Loja", 303: "Entrada de nome", 311: "HP", 312: "MP", 313: "Estado",
    314: "Recuperar tudo", 315: "EXP", 316: "Nível", 317: "Parâmetro", 318: "Habilidade", 319: "Equipamento",
    320: "Nome", 321: "Classe", 322: "Gráfico do ator", 324: "Apelido", 325: "Perfil", 331: "HP do inimigo",
    339: "Forçar ação", 340: "Abortar batalha", 351: "Menu", 352: "Salvar", 353: "Game Over", 354: "Título",
    355: "Script", 356: "Comando de plugin", 357: "Comando de plugin (MZ)",
}


def runtime_supported(runtime_dir: Path) -> set:
    """Lê os códigos tratados por ``H[NNN] =`` em mr-interpreter.js."""
    src = (Path(runtime_dir) / "mr-interpreter.js").read_text(encoding="utf-8")
    codes = {int(m.group(1)) for m in re.finditer(r"^\s*H\[(\d+)\]\s*=", src, re.M)}
    codes |= {int(m.group(1)) for m in re.finditer(r"H\[(\d+)\]\s*=\s*H\[", src)}
    return codes | IMPLICIT


def _fix_102(p: List[Any]) -> List[Any]:
    # VX/VXA: [choices, cancel] (0=não, 1..n=escolha, n+1=ramo) → MV: [choices, cancel, default, pos, bg]
    ch = p[0] if p else []
    ct = p[1] if len(p) > 1 else 0
    mv = -1 if ct == 0 else (-2 if ct > len(ch) else ct - 1)
    return [ch, mv, 0, 2, 0]


def normalize_list(cmds: List[Dict[str, Any]], engine: str) -> List[Dict[str, Any]]:
    """Converte (e devolve) uma lista de comandos para a convenção MV. Idempotente para MV/MZ."""
    if engine not in ("xp", "vx", "vxace") or not cmds:
        return cmds
    out: List[Dict[str, Any]] = []
    for c in cmds:
        code, p = c.get("code"), c.get("parameters") or []
        if code == 102:
            c["parameters"] = _fix_102(p)
        elif code == 104 and len(p) == 1:
            c["parameters"] = [p[0], 2]
        elif code in (355, 655):
            c["lang"] = "ruby"
        elif engine == "xp" and code == 101:
            out.append({"code": 101, "indent": c.get("indent", 0), "parameters": ["", 0, 0, 2]})
            out.append({"code": 401, "indent": c.get("indent", 0), "parameters": [p[0] if p else ""]})
            continue
        elif engine == "xp" and code == 201 and len(p) == 5:
            c["parameters"] = list(p) + [0]
        out.append(c)
    return out


def iter_lists(db: Dict[str, Any], maps: Dict[Any, dict]) -> Iterator[Tuple[str, Dict[str, Any], str]]:
    """Itera ``(origem, contêiner, chave)``: ``container[chave]`` é a lista de comandos."""
    for m_id, m in maps.items():
        for ev in m.get("events") or []:
            if not ev:
                continue
            for i, pg in enumerate(ev.get("pages") or []):
                yield f"map{m_id}/ev{ev.get('id')}/p{i + 1}", pg, "list"
    for ce in db.get("commonEvents") or []:
        if ce:
            yield f"common{ce.get('id')}", ce, "list"
    for t in db.get("troops") or []:
        if t:
            for i, pg in enumerate(t.get("pages") or []):
                yield f"troop{t.get('id')}/p{i + 1}", pg, "list"


def iter_commands(db: Dict[str, Any], maps: Dict[Any, dict]) -> Iterator[Tuple[str, Dict[str, Any]]]:
    for origin, cont, key in iter_lists(db, maps):
        for c in cont.get(key) or []:
            yield origin, c


def normalize_project(db: Dict[str, Any], maps: Dict[Any, dict], engine: str) -> None:
    if engine not in ("xp", "vx", "vxace"):
        return
    for _origin, cont, key in list(iter_lists(db, maps)):
        cont[key] = normalize_list(cont.get(key) or [], engine)
