"""Textos da interface própria do runtime (menus, batalha, título). Os textos do *jogo* vêm do banco de dados dele."""
from __future__ import annotations

from typing import Dict

STRINGS: Dict[str, Dict[str, str]] = {
    "pt-BR": {
        "newGame": "Novo Jogo", "continue": "Continuar", "loading": "Carregando…", "credit": "Recompilado com MAKER-Rebuild",
        "attack": "Atacar", "skill": "Habilidade", "guard": "Defender", "item": "Item", "escape": "Fugir",
        "appeared": "{0} apareceu!", "battle": "Batalha!", "defends": "{0} defende.", "fled": "Fugiu com sucesso!",
        "fleeFail": "Não conseguiu fugir!", "attacks": "{0} ataca!", "usedItem": "{0} usou {1}!", "usesSkill": "{0} usa {1}!",
        "miss": "Errou!", "takes": "{0} sofre {1} de {2}.", "recovers": "{0} recupera {1} de {2}.", "defeated": "{0} foi derrotado!",
        "victory": "Vitória!", "gains": "{0} EXP e {1} {2} obtidos!", "wiped": "Todos foram derrotados...",
        "levelUp": "{0} subiu para o nível {1}!", "learned": "{0} aprendeu {1}!", "got": "{0} obtido!",
        "items": "Itens", "skills": "Habilidades", "equip": "Equipar", "status": "Status", "save": "Salvar", "quit": "Encerrar",
        "empty": "(vazio)", "time": "Tempo", "slot": "Arquivo {0}", "emptySlot": "(vazio)", "buy": "Comprar", "sell": "Vender",
        "exit": "Sair", "money": "Dinheiro", "gameOver": "GAME OVER", "namePrompt": "Nome do personagem:",
        "mhp": "HP máx.", "mmp": "MP máx.", "atk": "Ataque", "def": "Defesa", "mat": "At. mágico", "mdf": "Def. mágica",
        "agi": "Agilidade", "luk": "Sorte", "level": "Nv", "exp": "EXP",
    },
    "en": {
        "newGame": "New Game", "continue": "Continue", "loading": "Loading…", "credit": "Rebuilt with MAKER-Rebuild",
        "attack": "Attack", "skill": "Skill", "guard": "Guard", "item": "Item", "escape": "Escape",
        "appeared": "{0} appeared!", "battle": "Battle!", "defends": "{0} guards.", "fled": "Got away safely!",
        "fleeFail": "Couldn't escape!", "attacks": "{0} attacks!", "usedItem": "{0} used {1}!", "usesSkill": "{0} uses {1}!",
        "miss": "Missed!", "takes": "{0} takes {1} {2} damage.", "recovers": "{0} recovers {1} {2}.", "defeated": "{0} was defeated!",
        "victory": "Victory!", "gains": "Gained {0} EXP and {1} {2}!", "wiped": "The party was wiped out...",
        "levelUp": "{0} reached level {1}!", "learned": "{0} learned {1}!", "got": "Found {0}!",
        "items": "Items", "skills": "Skills", "equip": "Equip", "status": "Status", "save": "Save", "quit": "Quit",
        "empty": "(empty)", "time": "Time", "slot": "File {0}", "emptySlot": "(empty)", "buy": "Buy", "sell": "Sell",
        "exit": "Exit", "money": "Money", "gameOver": "GAME OVER", "namePrompt": "Character name:",
        "mhp": "Max HP", "mmp": "Max MP", "atk": "Attack", "def": "Defense", "mat": "M. Attack", "mdf": "M. Defense",
        "agi": "Agility", "luk": "Luck", "level": "Lv", "exp": "EXP",
    },
    "es": {
        "newGame": "Nuevo juego", "continue": "Continuar", "loading": "Cargando…", "credit": "Reconstruido con MAKER-Rebuild",
        "attack": "Atacar", "skill": "Habilidad", "guard": "Defender", "item": "Objeto", "escape": "Huir",
        "appeared": "¡{0} apareció!", "battle": "¡Batalla!", "defends": "{0} se defiende.", "fled": "¡Escapaste con éxito!",
        "fleeFail": "¡No pudo huir!", "attacks": "¡{0} ataca!", "usedItem": "¡{0} usó {1}!", "usesSkill": "¡{0} usa {1}!",
        "miss": "¡Falló!", "takes": "{0} sufre {1} de {2}.", "recovers": "{0} recupera {1} de {2}.", "defeated": "¡{0} fue derrotado!",
        "victory": "¡Victoria!", "gains": "¡{0} EXP y {1} {2} obtenidos!", "wiped": "El grupo fue derrotado...",
        "levelUp": "¡{0} subió al nivel {1}!", "learned": "¡{0} aprendió {1}!", "got": "¡{0} obtenido!",
        "items": "Objetos", "skills": "Habilidades", "equip": "Equipar", "status": "Estado", "save": "Guardar", "quit": "Salir",
        "empty": "(vacío)", "time": "Tiempo", "slot": "Archivo {0}", "emptySlot": "(vacío)", "buy": "Comprar", "sell": "Vender",
        "exit": "Salir", "money": "Dinero", "gameOver": "GAME OVER", "namePrompt": "Nombre del personaje:",
        "mhp": "PV máx.", "mmp": "PM máx.", "atk": "Ataque", "def": "Defensa", "mat": "At. mágico", "mdf": "Def. mágica",
        "agi": "Agilidad", "luk": "Suerte", "level": "Nv", "exp": "EXP",
    },
}


def ui_strings(lang: str) -> Dict[str, str]:
    base = dict(STRINGS["en"])
    key = lang if lang in STRINGS else next((k for k in STRINGS if k.split("-")[0] == lang.split("-")[0]), "en")
    base.update(STRINGS[key])
    return base
