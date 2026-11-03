"""Projeto de demonstração: um mini-jogo RPG Maker MV sintético (sem arte de terceiros).

Usado por ``maker-rebuild demo`` (para experimentar a ferramenta sem ter um jogo) e pelos testes."""
from __future__ import annotations

import json
import wave
from pathlib import Path
from typing import Any, Dict, List


# ---------------------------------------------------------------- PNG mínimo
from .build.png import Canvas as Img  # noqa: E402


def wav_bytes(path: Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)


def _mix(c, k, other=(0, 0, 0)):
    return tuple(int(c[i] * (1 - k) + other[i] * k) for i in range(3))


# ---------------------------------------------------------------- tilesets (tile = ts px)
def a2_sheet(ts: int, colors: List[tuple]) -> Img:
    """Folha A2 (16x12 tiles): bloco 2x3 por autotile; cada tipo de peça tem um tom diferente."""
    im = Img(ts * 16, ts * 12)
    h = ts // 2
    for k, base in enumerate(colors):
        bx, by = (k % 8) * 2 * ts, (k // 8) * 3 * ts
        for gy in range(6):
            for gx in range(4):
                if gy < 2:                       # peças de canto interno (2x2 em x=2..3)
                    col = _mix(base, .5, (255, 255, 255)) if gx >= 2 else (40, 40, 40)
                else:
                    edge_x = gx in (0, 3)
                    edge_y = gy in (2, 5)
                    col = _mix(base, .6) if edge_x and edge_y else _mix(base, .3) if (edge_x or edge_y) else base
                im.rect(bx + gx * h, by + gy * h, h, h, col)
    return im


def b_sheet(ts: int) -> Img:
    im = Img(ts * 16, ts * 16)
    im.rect(ts, 0, ts, ts, (120, 70, 30))           # id 1 = árvore (marrom)
    im.rect(ts * 2, 0, ts, ts, (150, 150, 160))      # id 2 = muro
    im.rect(ts * 3, 0, ts, ts, (230, 190, 40))       # id 3 = baú (acima do herói quando ☆)
    return im


def char_sheet(ts: int, body=(40, 90, 220)) -> Img:
    """Folha 12x8 tiles... (4 personagens por linha: 3 quadros x 4 direções)."""
    im = Img(ts * 12, ts * 8)
    for ci in range(8):
        cx, cy = (ci % 4) * 3 * ts, (ci // 4) * 4 * ts
        col = tuple((body[i] + ci * 25) % 256 for i in range(3))
        for d in range(4):
            for f in range(3):
                x, y = cx + f * ts, cy + d * ts
                im.rect(x + ts // 4, y + ts // 5, ts // 2, ts * 3 // 5, col)
                im.rect(x + ts // 3, y + ts // 10, ts // 3, ts // 5, (240, 200, 170))
                marks = {0: (ts // 3, ts * 4 // 5), 1: (ts // 4, ts // 2), 2: (ts * 3 // 4 - 3, ts // 2), 3: (ts // 3, ts // 5)}
                mx, my = marks[d]
                im.rect(x + mx, y + my, 4, 4, (255, 255, 255))
    return im


# ---------------------------------------------------------------- projeto MV
def _cmd(code: int, indent: int = 0, *params) -> dict:
    return {"code": code, "indent": indent, "parameters": list(params)}


def _page(list_, *, image=None, trigger=0, priority=1, cond=None, move_type=0) -> dict:
    return {
        "conditions": cond or {"switch1Valid": False, "switch1Id": 1, "switch2Valid": False, "switch2Id": 1,
                               "variableValid": False, "variableId": 1, "variableValue": 0, "selfSwitchValid": False,
                               "selfSwitchCh": "A", "itemValid": False, "itemId": 1, "actorValid": False, "actorId": 1},
        "image": image or {"tileId": 0, "characterName": "", "characterIndex": 0, "direction": 2, "pattern": 1},
        "moveType": move_type, "moveSpeed": 3, "moveFrequency": 3, "moveRoute": {"list": [{"code": 0, "parameters": []}], "repeat": True, "skippable": False, "wait": False},
        "walkAnime": True, "stepAnime": False, "directionFix": False, "through": False, "priorityType": priority,
        "trigger": trigger, "list": list_ + [_cmd(0)],
    }


def make_map(w: int, h: int, events: List[dict]) -> dict:
    data = [0] * (w * h * 6)
    for y in range(h):
        for x in range(w):
            data[(0 * h + y) * w + x] = 2816            # grama (A2 kind 16, shape 0)
    for x in range(w):                                  # borda de árvores
        for y in (0, h - 1):
            data[(1 * h + y) * w + x] = 1
    for y in range(h):
        for x in (0, w - 1):
            data[(1 * h + y) * w + x] = 1
    for y in range(3, 6):                               # lago de terra (A2 kind 17) para testar autotile
        for x in range(9, 13):
            data[(0 * h + y) * w + x] = 2816 + 48
    return {"autoplayBgm": True, "autoplayBgs": False, "battleback1Name": "", "battleback2Name": "", "bgm": {"name": "Theme1", "pan": 0, "pitch": 100, "volume": 90},
            "bgs": {"name": "", "pan": 0, "pitch": 100, "volume": 90}, "disableDashing": False, "displayName": "Vila Inicial",
            "encounterList": [], "encounterStep": 30, "height": h, "note": "", "parallaxLoopX": False, "parallaxLoopY": False,
            "parallaxName": "", "parallaxShow": True, "parallaxSx": 0, "parallaxSy": 0, "scrollType": 0,
            "specifyBattleback": False, "tilesetId": 1, "width": w, "data": data, "events": [None] + events}


def make_mv_project(root: Path, *, encrypted: bool = False, www: bool = False, title: str = "Test Quest", mz: bool = False) -> Path:
    root = Path(root)
    base = root / "www" if www else root
    data, img, audio = base / "data", base / "img", base / "audio"
    for d in (data, img / "tilesets", img / "characters", img / "faces", img / "enemies", img / "system", img / "titles1",
              audio / "bgm", audio / "se"):
        d.mkdir(parents=True, exist_ok=True)
    (base / "js").mkdir(exist_ok=True)
    (base / "js" / ("rmmz_core.js" if mz else "rpg_core.js")).write_text("// stub", encoding="utf-8")
    (base / "js" / "plugins").mkdir(exist_ok=True)
    (base / "js" / "plugins" / "MyPlugin.js").write_text("//=============\n// MyPlugin\n//=============\n(function(){ /* cmd */ })();", encoding="utf-8")
    (base / "js" / "plugins.js").write_text(
        'var $plugins =\n[\n{"name":"MyPlugin","status":true,"description":"demo","parameters":{"x":"1"}}\n];\n', encoding="utf-8")
    key = "d41d8cd98f00b204e9800998ecf8427e"
    ts = 48
    from .engines.crypt import encrypt, parse_key
    k = parse_key(key)

    def put_img(rel: str, im: Img) -> None:
        p = img / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = im.png()
        if encrypted:
            p = p.with_suffix(".png_" if mz else ".rpgmvp")
            raw = encrypt(raw, k)
        p.write_bytes(raw)

    put_img("tilesets/World_A2.png", a2_sheet(ts, [(70, 170, 70), (150, 110, 60)]))
    put_img("tilesets/World_B.png", b_sheet(ts))
    put_img("characters/Actor1.png", char_sheet(ts))
    put_img("characters/People1.png", char_sheet(ts, (180, 60, 60)))
    faces = Img(144 * 4, 144 * 2)
    faces.rect(0, 0, 144, 144, (60, 80, 150)).rect(40, 30, 64, 80, (240, 200, 170))
    put_img("faces/Actor1.png", faces)
    put_img("enemies/Slime.png", Img(120, 100).rect(10, 20, 100, 80, (60, 200, 90)).rect(30, 40, 12, 12, (0, 0, 0)).rect(70, 40, 12, 12, (0, 0, 0)))
    win = Img(192, 192).rect(0, 0, 96, 96, (20, 24, 60)).rect(96, 0, 96, 96, (230, 235, 255)).rect(96 + 4, 4, 88, 88, (0, 0, 0, 0))
    put_img("system/Window.png", win)
    icons = Img(512, 512)
    icons.rect(0, 0, 32, 32, (200, 40, 40)).rect(32, 0, 32, 32, (40, 160, 220))
    put_img("system/IconSet.png", icons)
    for rel in ("bgm/Theme1.wav", "se/Cursor1.wav"):
        p = audio / rel
        wav_bytes(p)
        if encrypted:
            raw = encrypt(p.read_bytes(), k)
            p.unlink()
            p.with_suffix(".ogg_" if mz else ".rpgmvo").write_bytes(raw)

    flags = [0] * 8192
    flags[1] = 0x0F      # árvore bloqueia
    flags[2] = 0x0F      # muro bloqueia
    flags[3] = 0x0F      # baú bloqueia
    tilesets = [None, {"id": 1, "flags": flags, "mode": 1, "name": "World", "note": "",
                       "tilesetNames": ["", "World_A2", "", "", "", "World_B", "", "", ""]}]
    system = {
        "gameTitle": title, "startMapId": 1, "startX": 3, "startY": 3, "partyMembers": [1], "currencyUnit": "G",
        "title1Name": "", "title2Name": "", "titleBgm": {"name": "Theme1", "pan": 0, "pitch": 100, "volume": 90},
        "battleBgm": {"name": "", "pan": 0, "pitch": 100, "volume": 90}, "gameoverMe": {"name": "", "pan": 0, "pitch": 100, "volume": 90},
        "sounds": [{"name": "Cursor1", "pan": 0, "pitch": 100, "volume": 20}] * 24,
        "switches": ["", "Falou com NPC", "Pegou poção"], "variables": ["", "Contador"], "versionId": 1,
        "terms": {"basic": ["Level", "Lv", "HP", "HP", "MP", "MP", "TP", "TP", "EXP", "EXP"], "commands": ["Fight", "Escape", "Attack", "Guard", "Item", "Skill", "Equip", "Status", "Formation", "Save", "Game End"],
                  "params": ["Max HP", "Max MP", "Attack", "Defense", "M.Attack", "M.Defense", "Agility", "Luck"], "messages": {}},
        "optSideView": False, "hasEncryptedImages": encrypted, "hasEncryptedAudio": encrypted,
    }
    if encrypted:
        system["encryptionKey"] = key
    if mz:
        system["advanced"] = {"gameId": 1, "screenWidth": 816, "screenHeight": 624, "uiAreaWidth": 816, "uiAreaHeight": 624, "numberFontFilename": "", "fontSize": 26, "mainFontFilename": "", "faceSize": 144}
        system["tileSize"] = 48
        system["locale"] = "en_US"
    params = [[0] + [int(base_ * (1 + lv * 0.4)) for lv in range(1, 100)] for base_ in (120, 30, 12, 8, 8, 8, 10, 10)]
    db: Dict[str, Any] = {
        "Actors": [None, {"id": 1, "name": "Heroi", "nickname": "", "classId": 1, "initialLevel": 1, "maxLevel": 99, "characterName": "Actor1", "characterIndex": 0,
                          "faceName": "Actor1", "faceIndex": 0, "battlerName": "", "equips": [1, 0, 0, 0, 0], "profile": "Um aventureiro.", "traits": []}],
        "Classes": [None, {"id": 1, "name": "Guerreiro", "expParams": [30, 20, 30, 30], "params": params, "learnings": [{"level": 1, "skillId": 3, "note": ""}], "traits": []}],
        "Skills": [None,
                   {"id": 1, "name": "Attack", "iconIndex": 76, "scope": 1, "mpCost": 0, "successRate": 100, "damage": {"type": 1, "elementId": 0, "formula": "a.atk * 4 - b.def * 2", "variance": 20, "critical": True}, "effects": [], "description": ""},
                   {"id": 2, "name": "Guard", "iconIndex": 81, "scope": 11, "mpCost": 0, "successRate": 100, "damage": {"type": 0, "formula": "0", "variance": 0}, "effects": [], "description": ""},
                   {"id": 3, "name": "Fire", "iconIndex": 64, "scope": 1, "mpCost": 4, "successRate": 100, "damage": {"type": 1, "elementId": 2, "formula": "30 + a.mat * 2 - b.mdf", "variance": 10, "critical": False}, "effects": [], "description": "Bola de fogo"}],
        "Items": [None, {"id": 1, "name": "Potion", "iconIndex": 176, "itypeId": 1, "price": 50, "consumable": True, "scope": 7, "occasion": 0, "description": "Cura 100 HP",
                         "damage": {"type": 0, "formula": "0", "variance": 0}, "effects": [{"code": 11, "dataId": 0, "value1": 0, "value2": 100}]}],
        "Weapons": [None, {"id": 1, "name": "Espada", "iconIndex": 97, "price": 100, "wtypeId": 1, "etypeId": 1, "params": [0, 0, 10, 0, 0, 0, 0, 0], "description": "", "traits": []}],
        "Armors": [None],
        "Enemies": [None, {"id": 1, "name": "Slime", "battlerName": "Slime", "params": [30, 0, 8, 3, 2, 2, 5, 5], "exp": 12, "gold": 8, "dropItems": [{"kind": 1, "dataId": 1, "denominator": 1}],
                           "actions": [{"skillId": 1, "rating": 5, "conditionType": 0, "conditionParam1": 0, "conditionParam2": 0}], "traits": []}],
        "Troops": [None, {"id": 1, "name": "Slime", "members": [{"enemyId": 1, "x": 400, "y": 300, "hidden": False}], "pages": []}],
        "States": [None, {"id": 1, "name": "Death", "iconIndex": 1}],
        "Animations": [None], "Tilesets": tilesets, "CommonEvents": [None],
    }
    for name, val in db.items():
        (data / f"{name}.json").write_text(json.dumps(val), encoding="utf-8")
    (data / "System.json").write_text(json.dumps(system), encoding="utf-8")

    npc = {"id": 1, "name": "NPC", "note": "", "x": 6, "y": 4, "pages": [
        _page([_cmd(101, 0, "Actor1", 0, 0, 2), _cmd(401, 0, "Olá, \\C[2]\\N[1]\\C[0]! Bem-vindo à vila."),
               _cmd(401, 0, "Quer uma poção? (você tem \\V[1] até agora)"),
               _cmd(102, 0, ["Sim", "Não"], 1, 0, 2, 0), _cmd(402, 0, 0, "Sim"),
               _cmd(126, 1, 1, 0, 0, 1), _cmd(121, 1, 2, 2, 0), _cmd(122, 1, 1, 1, 0, 0, 1),
               _cmd(101, 1, "", 0, 0, 2), _cmd(401, 1, "Toma! Cuide-se."), _cmd(0, 1), _cmd(402, 0, 1, "Não"),
               _cmd(101, 1, "", 0, 0, 2), _cmd(401, 1, "Tudo bem então."), _cmd(0, 1), _cmd(404, 0),
               _cmd(121, 0, 1, 1, 0)],
              image={"tileId": 0, "characterName": "People1", "characterIndex": 0, "direction": 2, "pattern": 1})]}
    door = {"id": 2, "name": "Porta", "note": "", "x": 7, "y": 8, "pages": [
        _page([_cmd(201, 0, 0, 2, 3, 3, 2, 0)], trigger=1, priority=0)]}
    monster = {"id": 3, "name": "Slime", "note": "", "x": 4, "y": 6, "pages": [
        _page([_cmd(301, 0, 0, 1, True, False), _cmd(601, 0), _cmd(101, 1, "", 0, 0, 2), _cmd(401, 1, "Venceu!"), _cmd(0, 1),
               _cmd(602, 0), _cmd(0, 1), _cmd(603, 0), _cmd(0, 1), _cmd(604, 0)],
              image={"tileId": 0, "characterName": "People1", "characterIndex": 1, "direction": 2, "pattern": 1})]}
    wanderer = {"id": 4, "name": "Andarilho", "note": "", "x": 10, "y": 8, "pages": [
        _page([_cmd(101, 0, "", 0, 0, 2), _cmd(401, 0, "Só passeando...")],
              image={"tileId": 0, "characterName": "People1", "characterIndex": 2, "direction": 2, "pattern": 1}, move_type=1)]}
    cond_ev = {"id": 5, "name": "Após falar", "note": "", "x": 9, "y": 8, "pages": [
        _page([_cmd(101, 0, "", 0, 0, 2), _cmd(401, 0, "Você já falou com o NPC.")],
              cond={"switch1Valid": True, "switch1Id": 1, "switch2Valid": False, "switch2Id": 1, "variableValid": False, "variableId": 1,
                    "variableValue": 0, "selfSwitchValid": False, "selfSwitchCh": "A", "itemValid": False, "itemId": 1, "actorValid": False, "actorId": 1},
              image={"tileId": 3, "characterName": "", "characterIndex": 0, "direction": 2, "pattern": 0}, priority=0)]}
    m1 = make_map(15, 11, [npc, door, monster, wanderer, cond_ev])
    m2 = make_map(8, 6, [{"id": 1, "name": "Saída", "note": "", "x": 3, "y": 4, "pages": [_page([_cmd(201, 0, 0, 1, 7, 7, 8, 0)], trigger=1, priority=0)]}])
    m2["displayName"] = "Casa"
    infos = [None, {"id": 1, "name": "Vila", "parentId": 0, "order": 1, "expanded": False}, {"id": 2, "name": "Casa", "parentId": 1, "order": 2, "expanded": False}]
    (data / "MapInfos.json").write_text(json.dumps(infos), encoding="utf-8")
    (data / "Map001.json").write_text(json.dumps(m1), encoding="utf-8")
    (data / "Map002.json").write_text(json.dumps(m2), encoding="utf-8")
    (root / ("Game.rmmzproject" if mz else "Game.rpgproject")).write_text("RPGMZ 1.8.0" if mz else "RPGMV 1.6.2", encoding="utf-8")
    return base


