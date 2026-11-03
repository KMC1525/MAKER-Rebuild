"""MR-PATCH v1: valida e aplica o patch devolvido pela IA ao jogo (BuiltGame ou Project).

Princípios: nunca confiar na saída do LLM — tudo é validado (formas, ids, limites, caminhos, JS) antes de gravar;
erros fatais abortam o patch inteiro (nada é aplicado pela metade); problemas leves viram avisos.
"""
from __future__ import annotations

import copy
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

from ..build import commands as cmdmod
from ..build.png import placeholder
from .eventdsl import Compiler, DSLError, check_list, cmd

DB_KINDS = ["actors", "classes", "skills", "items", "weapons", "armors", "enemies", "troops", "states", "commonEvents"]
_DMG = {"type": 0, "elementId": 0, "formula": "0", "variance": 20, "critical": False}
DEFAULTS: Dict[str, Dict[str, Any]] = {
    "items": {"name": "Item", "iconIndex": 0, "description": "", "itypeId": 1, "price": 0, "consumable": True, "scope": 7,
              "occasion": 0, "speed": 0, "successRate": 100, "repeats": 1, "tpGain": 0, "hitType": 0, "animationId": 0,
              "damage": _DMG, "effects": [], "note": ""},
    "weapons": {"name": "Arma", "iconIndex": 0, "description": "", "price": 0, "wtypeId": 1, "etypeId": 1, "params": [0] * 8,
                "animationId": 0, "traits": [], "note": ""},
    "armors": {"name": "Armadura", "iconIndex": 0, "description": "", "price": 0, "atypeId": 1, "etypeId": 2, "params": [0] * 8,
               "traits": [], "note": ""},
    "skills": {"name": "Habilidade", "iconIndex": 0, "description": "", "stypeId": 1, "scope": 1, "occasion": 1, "mpCost": 0,
               "tpCost": 0, "tpGain": 0, "speed": 0, "successRate": 100, "repeats": 1, "hitType": 0, "animationId": 0,
               "damage": _DMG, "effects": [], "message1": "", "message2": "", "requiredWtypeId1": 0, "requiredWtypeId2": 0, "note": ""},
    "enemies": {"name": "Inimigo", "battlerName": "", "params": [100, 0, 10, 10, 10, 10, 10, 10], "exp": 0, "gold": 0,
                "dropItems": [], "actions": [{"skillId": 1, "rating": 5, "conditionType": 0, "conditionParam1": 0, "conditionParam2": 0}],
                "traits": [], "note": ""},
    "troops": {"name": "Tropa", "members": [], "pages": []},
    "states": {"name": "Estado", "iconIndex": 0, "restriction": 0, "priority": 50, "traits": [], "note": "", "message1": "",
               "message2": "", "message3": "", "message4": ""},
    "actors": {"name": "Ator", "nickname": "", "classId": 1, "initialLevel": 1, "maxLevel": 99, "characterName": "",
               "characterIndex": 0, "faceName": "", "faceIndex": 0, "battlerName": "", "equips": [0, 0, 0, 0, 0],
               "profile": "", "traits": [], "note": ""},
    "classes": {"name": "Classe", "expParams": [30, 20, 30, 30], "learnings": [], "traits": [], "note": ""},
    "commonEvents": {"name": "Evento comum", "trigger": 0, "switchId": 1},
}
TRIGGERS = {"action": 0, "touch": 1, "event-touch": 2, "auto": 3, "parallel": 4}
PRIORITY = {"below": 0, "same": 1, "above": 2}
MOVE = {"fixed": 0, "random": 1, "approach": 2, "custom": 3}
FILE_RULES = [
    (re.compile(r"^code/js/ext/[\w\-. ]+\.js$"), "js"), (re.compile(r"^code/js/plugins/[\w\-. ]+\.js$"), "js"),
    (re.compile(r"^code/css/theme\.css$"), "css"), (re.compile(r"^code/html/[\w\-. ]+\.html$"), "html"),
]
TOP_KEYS = {"summary", "system", "db", "maps", "files", "assets", "notes"}


class PatchError(Exception):
    pass


@dataclass
class ApplyResult:
    summary: str = ""
    added: Dict[str, int] = field(default_factory=dict)
    updated: Dict[str, int] = field(default_factory=dict)
    files: List[str] = field(default_factory=list)
    assets_todo: List[dict] = field(default_factory=list)
    placeholders: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    refs: Dict[str, Any] = field(default_factory=dict)


def default_page() -> Dict[str, Any]:
    return {
        "conditions": {"switch1Valid": False, "switch1Id": 1, "switch2Valid": False, "switch2Id": 1, "variableValid": False,
                       "variableId": 1, "variableValue": 0, "selfSwitchValid": False, "selfSwitchCh": "A", "itemValid": False,
                       "itemId": 1, "actorValid": False, "actorId": 1},
        "image": {"tileId": 0, "characterName": "", "characterIndex": 0, "direction": 2, "pattern": 1},
        "moveType": 0, "moveSpeed": 3, "moveFrequency": 3,
        "moveRoute": {"list": [{"code": 0, "parameters": []}], "repeat": True, "skippable": False, "wait": False},
        "walkAnime": True, "stepAnime": False, "directionFix": False, "through": False, "priorityType": 1, "trigger": 0,
        "list": [cmd(0, 0)],
    }


class Applier:
    def __init__(self, game: Any):
        self.g = game
        self.res = ApplyResult()
        self.refs: Dict[str, Any] = {}
        self.comp = Compiler(self._resolve)
        self.pending_files: List[tuple] = []

    # ------------------------------------------------------------ util
    def _resolve(self, v: Any) -> Any:
        if isinstance(v, str) and v.startswith("@"):
            key = v[1:]
            if key not in self.refs:
                raise PatchError(f"referência desconhecida '{v}' (declare um 'ref' antes de usar)")
            return self.refs[key]
        return v

    def _warn(self, msg: str) -> None:
        self.res.warnings.append(msg)

    def _count(self, bucket: Dict[str, int], key: str, n: int = 1) -> None:
        bucket[key] = bucket.get(key, 0) + n

    # ------------------------------------------------------------ entrada
    def apply(self, patch: Dict[str, Any]) -> ApplyResult:
        if not isinstance(patch, dict):
            raise PatchError("o patch deve ser um objeto JSON")
        for k in patch:
            if k not in TOP_KEYS:
                self._warn(f"chave desconhecida no patch ignorada: {k}")
        self.res.summary = str(patch.get("summary", ""))[:500]
        self.res.notes = [str(n) for n in patch.get("notes", []) or []]
        backup = (copy.deepcopy(self.g.db), copy.deepcopy(self.g.maps))
        try:
            self._system(patch.get("system") or {})
            self._db_add_phase1(patch.get("db") or {})
            self._maps_add_phase1(patch.get("maps") or {})
            self._db_finish(patch.get("db") or {})
            self._maps_finish(patch.get("maps") or {})
            self._files(patch.get("files") or [])
            self._assets(patch.get("assets") or [])
            self._postcheck()
        except (PatchError, DSLError, KeyError, TypeError, ValueError, IndexError) as e:
            self.g.db, self.g.maps = backup
            raise PatchError(f"{type(e).__name__}: {e}") from e
        self._write_files()
        self.res.refs = dict(self.refs)
        return self.res

    # ------------------------------------------------------------ system
    def _system(self, s: Dict[str, Any]) -> None:
        sysd = self.g.db.setdefault("system", {})
        for k, v in (s.get("set") or {}).items():
            sysd[k] = v
        for kind in ("switches", "variables"):
            arr = sysd.setdefault(kind, [""])
            if not arr:
                arr.append("")
            for ent in s.get(kind) or []:
                name = ent if isinstance(ent, str) else ent.get("name", "")
                arr.append(name)
                if isinstance(ent, dict) and ent.get("ref"):
                    self._set_ref(ent["ref"], len(arr) - 1)
                self._count(self.res.added, kind)

    def _set_ref(self, ref: str, val: Any) -> None:
        if ref in self.refs:
            raise PatchError(f"ref duplicado: {ref}")
        self.refs[ref] = val

    # ------------------------------------------------------------ banco de dados
    def _db_list(self, kind: str) -> List[Any]:
        arr = self.g.db.setdefault(kind, [None])
        if not arr:
            arr.append(None)
        return arr

    def _db_add_phase1(self, dbp: Dict[str, Any]) -> None:
        """Aloca ids e cria as entradas (sem compilar eventos, que podem usar @refs de mapas)."""
        for kind, ops in dbp.items():
            if kind not in DB_KINDS:
                self._warn(f"coleção desconhecida em 'db' ignorada: {kind}")
                continue
            arr = self._db_list(kind)
            for ent in ops.get("add") or []:
                if not isinstance(ent, dict):
                    raise PatchError(f"db.{kind}.add: entrada inválida")
                new = copy.deepcopy(DEFAULTS[kind])
                new.update({k: v for k, v in ent.items() if k not in ("ref", "script")})
                new["id"] = len(arr)
                if kind == "classes" and "params" not in new:
                    new["params"] = [[0] + [int(b * (1 + lv * 0.35)) for lv in range(1, 100)] for b in (110, 30, 12, 8, 8, 8, 10, 10)]
                if kind == "commonEvents":
                    new["list"] = new.get("list") or [cmd(0, 0)]
                if ent.get("ref"):
                    self._set_ref(ent["ref"], new["id"])
                new["_script"] = ent.get("script")
                arr.append(new)
                self._count(self.res.added, kind)

    def _db_finish(self, dbp: Dict[str, Any]) -> None:
        for kind, ops in dbp.items():
            if kind not in DB_KINDS:
                continue
            arr = self._db_list(kind)
            for ent in arr:
                if isinstance(ent, dict) and "_script" in ent:
                    sc = ent.pop("_script")
                    if sc:
                        ent["list"] = self.comp.compile(sc, 0) + [cmd(0, 0)]
            for up in ops.get("update") or []:
                i = up.get("id")
                if not isinstance(i, int) or i < 1 or i >= len(arr) or not arr[i]:
                    raise PatchError(f"db.{kind}.update: id inexistente {i}")
                for k, v in (up.get("set") or {}).items():
                    if k == "id":
                        continue
                    if k == "script":
                        arr[i]["list"] = self.comp.compile(v, 0) + [cmd(0, 0)]
                    else:
                        arr[i][k] = v
                self._count(self.res.updated, kind)

    # ------------------------------------------------------------ mapas
    def _new_map_id(self) -> int:
        return max(self.g.maps, default=0) + 1

    def _maps_add_phase1(self, mp: Dict[str, Any]) -> None:
        for ent in mp.get("add") or []:
            w, h = int(ent.get("width", 17)), int(ent.get("height", 13))
            if not (1 <= w <= 256 and 1 <= h <= 256):
                raise PatchError(f"mapa com dimensões inválidas {w}x{h}")
            mid = self._new_map_id()
            if ent.get("ref"):
                self._set_ref(ent["ref"], mid)
            tid = int(ent.get("tilesetId", 1))
            if tid >= len(self.g.db.get("tilesets") or [None]) or not self.g.db["tilesets"][tid]:
                raise PatchError(f"tilesetId inexistente: {tid}")
            m = {"autoplayBgm": bool(ent.get("bgm")), "autoplayBgs": False, "battleback1Name": "", "battleback2Name": "",
                 "bgm": ent.get("bgm") or {"name": "", "pan": 0, "pitch": 100, "volume": 90},
                 "bgs": {"name": "", "pan": 0, "pitch": 100, "volume": 90}, "disableDashing": False,
                 "displayName": ent.get("displayName", ent.get("name", "")), "name": ent.get("name", f"Mapa {mid}"),
                 "encounterList": ent.get("encounterList", []), "encounterStep": 30, "height": h, "note": "",
                 "parallaxLoopX": False, "parallaxLoopY": False, "parallaxName": "", "parallaxShow": True, "parallaxSx": 0,
                 "parallaxSy": 0, "scrollType": 0, "specifyBattleback": False, "tilesetId": tid, "width": w,
                 "data": [0] * (w * h * 6), "events": [None], "id": mid}
            self.g.maps[mid] = m
            self._tiles(m, ent)
            infos = self.g.db.setdefault("mapInfos", [None])
            info = {"id": mid, "name": m["name"], "parentId": int(ent.get("parentId", 0)), "order": mid, "expanded": False}
            while len(infos) < mid:
                infos.append(None)
            if len(infos) > mid:
                infos[mid] = info
            else:
                infos.append(info)
            self._count(self.res.added, "maps")
            ent["_id"] = mid

    def _tiles(self, m: Dict[str, Any], ent: Dict[str, Any]) -> None:
        w, h = m["width"], m["height"]
        for key, val in (ent.get("fill") or {}).items():
            z = int(key.lstrip("z"))
            for i in range(w * h):
                m["data"][z * w * h + i] = int(val)
        for r in ent.get("rects") or []:
            z = int(r.get("z", 0))
            if not 0 <= z <= 5:
                raise PatchError(f"camada z inválida: {z}")
            for y in range(int(r["y"]), min(h, int(r["y"]) + int(r.get("h", 1)))):
                for x in range(int(r["x"]), min(w, int(r["x"]) + int(r.get("w", 1)))):
                    if x >= 0 and y >= 0:
                        m["data"][(z * h + y) * w + x] = int(r["id"])
        for t in ent.get("tiles") or []:
            x, y, z = int(t["x"]), int(t["y"]), int(t.get("z", 0))
            if not (0 <= x < w and 0 <= y < h and 0 <= z <= 5):
                self._warn(f"tile fora do mapa ignorado: {t}")
                continue
            m["data"][(z * h + y) * w + x] = int(t["id"])

    def _maps_finish(self, mp: Dict[str, Any]) -> None:
        for ent in mp.get("add") or []:
            m = self.g.maps[ent["_id"]]
            for ev in ent.get("events") or []:
                self._add_event(m, ev)
        for up in mp.get("update") or []:
            mid = up.get("id")
            if mid not in self.g.maps:
                raise PatchError(f"maps.update: mapa inexistente {mid}")
            m = self.g.maps[mid]
            self._tiles(m, up)
            evs = up.get("events") or {}
            for ev in evs.get("add") or []:
                self._add_event(m, ev)
            for eu in evs.get("update") or []:
                i = eu.get("id")
                if not isinstance(i, int) or i >= len(m["events"]) or not m["events"][i]:
                    raise PatchError(f"mapa {mid}: evento inexistente {i}")
                for k, v in (eu.get("set") or {}).items():
                    if k == "pages":
                        m["events"][i]["pages"] = [self._page(p) for p in v]
                    elif k in ("x", "y", "name"):
                        m["events"][i][k] = v
                self._count(self.res.updated, "events")
            for i in evs.get("remove") or []:
                if isinstance(i, int) and 0 < i < len(m["events"]):
                    m["events"][i] = None
            self._count(self.res.updated, "maps")

    def _add_event(self, m: Dict[str, Any], ev: Dict[str, Any]) -> None:
        x, y = int(ev.get("x", 0)), int(ev.get("y", 0))
        if not (0 <= x < m["width"] and 0 <= y < m["height"]):
            self._warn(f"evento '{ev.get('name')}' fora do mapa ({x},{y}) — ajustado")
            x, y = max(0, min(m["width"] - 1, x)), max(0, min(m["height"] - 1, y))
        i = len(m["events"])
        e = {"id": i, "name": str(ev.get("name", f"EV{i:03d}")), "note": "", "x": x, "y": y,
             "pages": [self._page(p) for p in (ev.get("pages") or [{}])]}
        if ev.get("ref"):
            self._set_ref(ev["ref"], i)
        m["events"].append(e)
        self._count(self.res.added, "events")

    def _page(self, p: Dict[str, Any]) -> Dict[str, Any]:
        pg = default_page()
        if p.get("image"):
            pg["image"].update(p["image"])
        pg["trigger"] = TRIGGERS.get(p["trigger"], 0) if isinstance(p.get("trigger"), str) else int(p.get("trigger", 0))
        pg["priorityType"] = PRIORITY.get(p["priority"], 1) if isinstance(p.get("priority"), str) else int(p.get("priority", 1))
        pg["moveType"] = MOVE.get(p["move"], 0) if isinstance(p.get("move"), str) else int(p.get("move", 0))
        c = p.get("conditions") or {}
        cd = pg["conditions"]
        if "switch" in c:
            cd.update(switch1Valid=True, switch1Id=self._resolve(c["switch"]))
        if "switch2" in c:
            cd.update(switch2Valid=True, switch2Id=self._resolve(c["switch2"]))
        if "variable" in c:
            vid, op, val = c["variable"]
            if op != ">=":
                self._warn("condição de variável só suporta '>=' em páginas de evento — usando >=")
            cd.update(variableValid=True, variableId=self._resolve(vid), variableValue=self._resolve(val))
        if "self" in c:
            cd.update(selfSwitchValid=True, selfSwitchCh=c["self"])
        if "item" in c:
            cd.update(itemValid=True, itemId=self._resolve(c["item"]))
        if "actor" in c:
            cd.update(actorValid=True, actorId=self._resolve(c["actor"]))
        for k in ("moveSpeed", "moveFrequency", "walkAnime", "stepAnime", "directionFix", "through"):
            if k in p:
                pg[k] = p[k]
        if p.get("script") is not None:
            pg["list"] = self.comp.compile(p["script"], 0) + [cmd(0, 0)]
        elif p.get("list"):
            pg["list"] = p["list"]
        errs = check_list(pg["list"])
        if errs:
            raise PatchError("evento inválido: " + "; ".join(errs[:3]))
        return pg

    # ------------------------------------------------------------ arquivos / assets
    def _files(self, files: List[Dict[str, Any]]) -> None:
        for f in files:
            path, content = str(f.get("path", "")), f.get("content")
            norm = str(PurePosixPath(path))
            if path.startswith("/") or ".." in PurePosixPath(norm).parts or "\\" in path:
                raise PatchError(f"caminho de arquivo inseguro: {path}")
            kind = next((k for rx, k in FILE_RULES if rx.match(norm)), None)
            if not kind:
                raise PatchError(f"caminho não permitido: {path} (use code/js/ext/*.js, code/js/plugins/*.js, code/css/theme.css, code/html/*.html)")
            if not isinstance(content, str) or len(content) > 400_000:
                raise PatchError(f"conteúdo inválido ou grande demais em {path}")
            if kind == "js":
                err = _js_syntax(content)
                if err:
                    raise PatchError(f"JS inválido em {path}: {err}")
            self.pending_files.append((norm, content))

    def _write_files(self) -> None:
        for norm, content in self.pending_files:
            dest = Path(self.g.root) / norm
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
            self.res.files.append(norm)

    def _assets(self, assets: List[Dict[str, Any]]) -> None:
        from ..assets import TARGET_DIRS
        for a in assets:
            cat, name = str(a.get("category", "")), str(a.get("name", ""))
            if cat not in TARGET_DIRS or not re.fullmatch(r"[\w\- .$!]+", name):
                self._warn(f"pedido de asset ignorado: {a}")
                continue
            self.res.assets_todo.append({"category": cat, "name": name, "note": a.get("note", "")})
            dest = Path(self.g.root) / TARGET_DIRS[cat] / f"{name}.png"
            if cat in ("bgm", "bgs", "me", "se", "fonts", "movies"):
                continue
            if not dest.exists() and getattr(self.g, "root", None):
                self._pending_placeholders = getattr(self, "_pending_placeholders", [])
                self._pending_placeholders.append((dest, cat, name))

    def _postcheck(self) -> None:
        db, maps = self.g.db, self.g.maps
        commons = {c["id"] for c in db.get("commonEvents") or [] if c}
        for origin, cont, key in cmdmod.iter_lists(db, maps):
            lst = cont.get(key) or []
            for c in lst:
                code, p = c.get("code"), c.get("parameters") or []
                try:
                    if code in (126, 127, 128):
                        coll = {126: "items", 127: "weapons", 128: "armors"}[code]
                        if p[0] >= len(db.get(coll) or []):
                            raise PatchError(f"{origin}: id {p[0]} não existe em db.{coll}")
                    if code == 201 and p[0] == 0 and p[1] not in maps:
                        raise PatchError(f"{origin}: teletransporte para mapa inexistente {p[1]}")
                    if code == 117 and p[0] not in commons:
                        raise PatchError(f"{origin}: evento comum inexistente {p[0]}")
                    if code == 301 and p[0] == 0 and p[1] >= len(db.get("troops") or []):
                        raise PatchError(f"{origin}: tropa inexistente {p[1]}")
                except (IndexError, TypeError):
                    continue

    def finish(self) -> None:
        for dest, cat, name in getattr(self, "_pending_placeholders", []):
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(placeholder(cat, name, getattr(self.g, "tile_size", 48)))
            self.res.placeholders.append(str(dest.relative_to(self.g.root)))


def _js_syntax(code: str) -> Optional[str]:
    node = shutil.which("node")
    if not node:
        return None
    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "m.js"
        f.write_text(code, encoding="utf-8")
        r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
        if r.returncode:
            lines = [ln for ln in r.stderr.splitlines() if ln.strip()]
            return next((ln for ln in lines if "Error" in ln), lines[0] if lines else "erro de sintaxe")
    return None


def apply_patch(game: Any, patch: Dict[str, Any]) -> ApplyResult:
    ap = Applier(game)
    res = ap.apply(patch)
    ap.finish()
    return res
