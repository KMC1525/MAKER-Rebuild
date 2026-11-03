"""Carregamento de projetos RPG Maker para um modelo intermediário (IR) comum.

O IR segue a nomenclatura do RPG Maker MV/MZ (``Actors.json`` etc.). Projetos
VX Ace são convertidos quase 1:1 (os formatos são parentes diretos); XP, VX e
2000/2003 são importados em modo *best effort* — veja ``Project.support``.
"""
from __future__ import annotations

import configparser
import json
import re
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .assets import AssetEntry, classify
from .engines import lcf, rubymarshal as rm
from .engines.crypt import ENCRYPTED_EXT, decrypt, is_encrypted, parse_key, recover_png_key
from .engines.vfs import VFS, safe_extract

ENGINE_LABELS = {
    "rm2k": "RPG Maker 2000", "rm2k3": "RPG Maker 2003", "xp": "RPG Maker XP", "vx": "RPG Maker VX",
    "vxace": "RPG Maker VX Ace", "mv": "RPG Maker MV", "mz": "RPG Maker MZ",
}
# fidelidade esperada da conversão determinística
SUPPORT = {
    "mv": "completo", "mz": "completo", "vxace": "alto (mesmo modelo de dados do MV)",
    "vx": "experimental (banco de dados parcial; tiles/eventos básicos)",
    "xp": "experimental (banco de dados parcial; autotiles simplificados)",
    "rm2k": "experimental (mapas + assets; lógica via IA)", "rm2k3": "experimental (mapas + assets; lógica via IA)",
}
SCREEN = {  # (largura, altura, tamanho do tile)
    "mv": (816, 624, 48), "mz": (816, 624, 48), "vxace": (544, 416, 32), "vx": (544, 416, 32),
    "xp": (640, 480, 32), "rm2k": (320, 240, 16), "rm2k3": (320, 240, 16),
}
DB_FILES = ["Actors", "Classes", "Skills", "Items", "Weapons", "Armors", "Enemies", "Troops", "States",
            "Animations", "Tilesets", "CommonEvents"]
DB_KEYS = {n: n[0].lower() + n[1:] for n in DB_FILES}
RB_EXT = {"xp": ".rxdata", "vx": ".rvdata", "vxace": ".rvdata2"}


class ProjectError(Exception):
    pass


@dataclass
class Project:
    root: Path
    engine: str
    title: str = "Game"
    db: Dict[str, Any] = field(default_factory=dict)
    maps: Dict[int, dict] = field(default_factory=dict)
    assets: List[AssetEntry] = field(default_factory=list)
    plugins: List[dict] = field(default_factory=list)
    plugin_sources: Dict[str, str] = field(default_factory=dict)
    scripts: List[dict] = field(default_factory=list)       # scripts Ruby (XP/VX/VXA)
    fonts: Dict[str, bytes] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)          # docs extras fornecidos (GDD, roteiro...)
    screen_w: int = 816
    screen_h: int = 624
    tile_size: int = 48

    @property
    def label(self) -> str:
        return ENGINE_LABELS.get(self.engine, self.engine)

    @property
    def support(self) -> str:
        return SUPPORT.get(self.engine, "desconhecido")


# ---------------------------------------------------------------------------
# detecção
# ---------------------------------------------------------------------------

def _ci(d: Path, name: str) -> Optional[Path]:
    if not d.is_dir():
        return None
    low = name.lower()
    for p in d.iterdir():
        if p.name.lower() == low:
            return p
    return None


def _has_any(d: Path, names: List[str]) -> bool:
    return any(_ci(d, n) for n in names)


def detect_root(path: Path) -> tuple:
    """Procura (raiz_do_projeto, engine). Aceita a pasta do jogo, ``www/`` ou uma pasta acima."""
    path = Path(path)
    cands = [path]
    for sub in ("www",):
        c = _ci(path, sub)
        if c:
            cands.append(c)
    if path.is_dir():
        cands += [p for p in sorted(path.iterdir()) if p.is_dir()][:20]
        for p in list(cands):
            c = _ci(p, "www")
            if c:
                cands.append(c)
    for d in cands:
        eng = _engine_of(d)
        if eng:
            return d, eng
    raise ProjectError(f"nenhum projeto RPG Maker reconhecido em: {path}")


def _engine_of(d: Path) -> Optional[str]:
    data = _ci(d, "data")
    if data and _ci(data, "System.json"):
        js = _ci(d, "js")
        if (js and (any(js.glob("rmmz_*.js")) or any(js.glob("rmmz*")))) or _has_any(d, ["Game.rmmzproject"]):
            return "mz"
        if (js and any(js.glob("rpg_*.js"))) or _has_any(d, ["Game.rpgproject"]):
            return "mv"
        try:
            sysj = json.loads(_ci(data, "System.json").read_text(encoding="utf-8-sig"))
            return "mz" if "advanced" in sysj else "mv"
        except (OSError, ValueError):
            return "mv"
    for eng, sysfile, arch in (("vxace", "System.rvdata2", "Game.rgss3a"), ("vx", "System.rvdata", "Game.rgss2a"),
                               ("xp", "System.rxdata", "Game.rgssad")):
        if (data and _ci(data, sysfile)) or _ci(d, arch) or _has_any(d, [f"*{arch}"]):
            return eng
    # arquivos .rgss*a com outro nome (ex.: Game.rgss3a renomeado)
    for p in d.glob("*") if d.is_dir() else []:
        n = p.name.lower()
        if n.endswith(".rgss3a"):
            return "vxace"
        if n.endswith(".rgss2a"):
            return "vx"
        if n.endswith(".rgssad"):
            return "xp"
    if _ci(d, "RPG_RT.ldb") or _ci(d, "RPG_RT.exe") and _ci(d, "RPG_RT.lmt"):
        return "rm2k3" if any((_ci(d, x) for x in ("BattleCharSet", "BattleWeapon", "Battle2"))) else "rm2k"
    return None


# ---------------------------------------------------------------------------
# carga
# ---------------------------------------------------------------------------

def open_project(src: str, workdir: Optional[Path] = None) -> Project:
    """Abre pasta ou .zip e devolve o :class:`Project`."""
    p = Path(src).expanduser()
    if not p.exists():
        raise ProjectError(f"caminho não encontrado: {p}")
    tmp = None
    if p.is_file():
        if p.suffix.lower() != ".zip":
            raise ProjectError("informe a pasta do projeto ou um arquivo .zip")
        tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="maker-rebuild-"))
        tmp.mkdir(parents=True, exist_ok=True)
        safe_extract(p, tmp)
        p = tmp
    root, engine = detect_root(p)
    loader = {"mv": _load_mvmz, "mz": _load_mvmz, "vxace": _load_rgss, "vx": _load_rgss, "xp": _load_rgss,
              "rm2k": _load_lcf, "rm2k3": _load_lcf}[engine]
    proj = Project(root=root, engine=engine)
    proj.screen_w, proj.screen_h, proj.tile_size = SCREEN[engine]
    loader(proj)
    proj.notes += _collect_notes(root)
    return proj


def _collect_notes(root: Path) -> List[str]:
    out = []
    for pat in ("*.txt", "*.md"):
        for f in sorted(root.glob(pat))[:5]:
            try:
                t = f.read_text(encoding="utf-8", errors="replace")[:4000]
                if len(t.strip()) > 30 and f.name.lower() not in ("readme.txt", "license.txt"):
                    out.append(f"[{f.name}]\n{t}")
            except OSError:
                pass
    return out


def _jload(vfs: VFS, rel: str) -> Any:
    return json.loads(vfs.read(rel).decode("utf-8-sig"))


def _load_mvmz(proj: Project) -> None:
    vfs = VFS(proj.root)
    dkey = (vfs.find("data/System.json") or "").rsplit("/", 1)[0] or "data"
    system = _jload(vfs, f"{dkey}/System.json")
    proj.db["system"] = system
    proj.title = system.get("gameTitle") or proj.root.name
    if proj.engine == "mz":
        adv = system.get("advanced", {})
        proj.screen_w = adv.get("screenWidth", 816)
        proj.screen_h = adv.get("screenHeight", 624)
        proj.tile_size = system.get("tileSize", 48)
    for n in DB_FILES:
        rel = vfs.find(f"{dkey}/{n}.json")
        if rel:
            proj.db[DB_KEYS[n]] = _jload(vfs, rel)
        else:
            proj.warnings.append(f"{n}.json ausente")
    infos = _jload(vfs, f"{dkey}/MapInfos.json") if vfs.exists(f"{dkey}/MapInfos.json") else []
    proj.db["mapInfos"] = infos
    for info in infos:
        if not info:
            continue
        rel = vfs.find(f"{dkey}/Map{info['id']:03d}.json")
        if rel:
            m = _jload(vfs, rel)
            m.setdefault("displayName", "")
            m["name"] = info.get("name", "")
            proj.maps[info["id"]] = m
        else:
            proj.warnings.append(f"mapa {info['id']} ({info.get('name')}) sem arquivo")
    # plugins
    pj = vfs.find("js/plugins.js")
    if pj:
        txt = vfs.read(pj).decode("utf-8", "replace")
        try:
            proj.plugins = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
        except ValueError:
            proj.warnings.append("não foi possível interpretar js/plugins.js")
        for pl in proj.plugins:
            rel = vfs.find(f"js/plugins/{pl.get('name')}.js")
            if rel:
                proj.plugin_sources[pl["name"]] = vfs.read(rel).decode("utf-8", "replace")
    # assets (+ descriptografia)
    key = parse_key(system["encryptionKey"]) if system.get("encryptionKey") else None
    for rel, reader in vfs.walk("fonts/"):
        if rel.lower().endswith((".ttf", ".otf", ".woff", ".woff2")):
            proj.fonts[rel.split("/", 1)[1]] = reader()
    _collect_assets(proj, vfs, ("img",), ("audio",), key)


def _collect_assets(proj: Project, vfs: VFS, img_roots, audio_roots, key: Optional[bytes]) -> None:
    key_box = {"key": key}

    def make_reader(reader, enc):
        def read() -> bytes:
            data = reader()
            if enc and is_encrypted(data):
                if key_box["key"] is None:
                    key_box["key"] = recover_png_key(data)
                if key_box["key"] is None:
                    raise ProjectError("asset criptografado sem chave (System.json sem encryptionKey)")
                return decrypt(data, key_box["key"])
            return data
        return read

    for rel, reader in vfs.walk(""):
        got = classify(rel, img_roots, audio_roots)
        if not got:
            continue
        cat, name, ext = got
        enc = ext in ENCRYPTED_EXT
        if enc:
            ext = ENCRYPTED_EXT[ext]
        proj.assets.append(AssetEntry(cat, name, ext, make_reader(reader, enc), rel, enc))
    # se a chave não veio do System.json, tenta recuperá-la de um PNG criptografado
    if key_box["key"] is None:
        for a in proj.assets:
            if a.encrypted and a.ext == ".png":
                try:
                    a.reader()
                    break
                except ProjectError:
                    pass


# --- RGSS (XP / VX / VX Ace) ---------------------------------------------

def _rb(vfs: VFS, rel: str, ext: str) -> Any:
    raw = vfs.read(rel)
    return rm.convert(rm.loads(raw))


def _dict_to_list(d: Any) -> list:
    if isinstance(d, list):
        return d
    if not isinstance(d, dict) or not d:
        return [None]
    n = max(int(k) for k in d) + 1
    out: list = [None] * n
    for k, v in d.items():
        out[int(k)] = v
    return out


def _fix_event_page(pg: dict) -> dict:
    if "condition" in pg:
        pg["conditions"] = pg.pop("condition")
    if "graphic" in pg:
        pg["image"] = pg.pop("graphic")
    if "priorityType" not in pg:
        pg["priorityType"] = 2 if pg.get("alwaysOnTop") else 1
    pg.setdefault("moveSpeed", 3)
    return pg


def _fix_map(m: dict, engine: str, info: Optional[dict]) -> dict:
    w, h = m["width"], m["height"]
    data = list(m.get("data") or [])
    zs = len(data) // (w * h) if w * h else 0
    out = [0] * (w * h * 6)
    size = w * h
    for z in range(min(zs, 3 if engine != "vxace" else 3)):
        out[z * size:(z + 1) * size] = data[z * size:(z + 1) * size]
    if engine == "vxace" and zs >= 4:  # camada 3: sombra (bits 0-3) + região (bits 8+)
        for i in range(size):
            v = data[3 * size + i]
            out[4 * size + i] = v & 0xF
            out[5 * size + i] = (v >> 8) & 0xFF
    m["data"] = out
    evs = _dict_to_list(m.get("events", {}))
    for e in evs:
        if e:
            e["pages"] = [_fix_event_page(p) for p in e.get("pages", [])]
    m["events"] = evs
    m.setdefault("displayName", "")
    m.setdefault("note", "")
    if info:
        m["name"] = info.get("name", "")
    return m


def _fix_tileset(ts: dict, engine: str) -> dict:
    if engine == "xp":
        pas, pri = ts.get("passages") or [], ts.get("priorities") or []
        flags = []
        for i in range(max(len(pas), len(pri))):
            base = i - i % 48 if i < 384 else i
            f = (pas[base] if base < len(pas) else 0) & 0x0F
            if (pri[base] if base < len(pri) else 0) > 0:
                f |= 0x10
            flags.append(f)
        ts["flags"] = flags
        ts["mode"] = "xp"
        ts["tilesetNames"] = [ts.get("tilesetName", "")] + list(ts.get("autotileNames", []))
    else:
        ts["flags"] = list(ts.get("flags") or [])
        ts["mode"] = ts.get("mode", 1)
    return ts


def _fix_classes(classes: list) -> list:
    for c in classes:
        if not c:
            continue
        p = c.get("params")
        if isinstance(p, list) and p and not isinstance(p[0], list):
            # Table(8, 100): índice = param + 8 * nível
            c["params"] = [[p[k + 8 * lv] if k + 8 * lv < len(p) else 0 for lv in range(100)] for k in range(8)]
    return classes


def _read_scripts(vfs: VFS, ext: str) -> List[dict]:
    rel = vfs.find(f"data/Scripts{ext}")
    if not rel:
        return []
    out = []
    try:
        for ent in rm.loads(vfs.read(rel), decode=False):
            _id, name, blob = ent[0], ent[1], ent[2]
            src = zlib.decompress(blob)
            try:
                text = src.decode("utf-8")
            except UnicodeDecodeError:
                text = src.decode("cp932", "replace")
            nm = name.decode("utf-8", "replace") if isinstance(name, bytes) else str(name)
            if text.strip():
                out.append({"name": nm, "source": text})
    except Exception as e:  # noqa: BLE001 - scripts são opcionais
        out.append({"name": "<erro>", "source": f"# falha ao ler Scripts: {e}"})
    return out


def _ini_title(vfs: VFS, section: str, key: str, filename: str = "Game.ini") -> Optional[str]:
    rel = vfs.find(filename)
    if not rel:
        return None
    raw = vfs.read(rel)
    for enc in ("utf-8-sig", "cp932", "latin-1"):
        try:
            cp = configparser.ConfigParser(interpolation=None)
            cp.read_string(raw.decode(enc))
            return cp.get(section, key)
        except Exception:  # noqa: BLE001
            continue
    return None


def _load_rgss(proj: Project) -> None:
    vfs = VFS(proj.root)
    eng, ext = proj.engine, RB_EXT[proj.engine]
    if vfs.archive:
        proj.notes.append(f"Assets e dados lidos do arquivo criptografado (RGSS v{vfs.archive.version}).")
    sysrel = vfs.find(f"data/System{ext}")
    if not sysrel:
        raise ProjectError(f"Data/System{ext} não encontrado")
    system = _rb(vfs, sysrel, ext)
    proj.db["system"] = system
    proj.title = (system.get("gameTitle") or _ini_title(vfs, "Game", "Title") or proj.root.name)
    for n in DB_FILES:
        rel = vfs.find(f"data/{n}{ext}")
        if not rel:
            proj.warnings.append(f"{n}{ext} ausente")
            continue
        try:
            val = _rb(vfs, rel, ext)
        except Exception as e:  # noqa: BLE001
            proj.warnings.append(f"falha ao ler {n}{ext}: {e}")
            continue
        if n == "Tilesets":
            val = [(_fix_tileset(t, eng) if t else None) for t in val]
        if n == "Classes":
            val = _fix_classes(val)
        proj.db[DB_KEYS[n]] = val
    infos_raw = _rb(vfs, vfs.find(f"data/MapInfos{ext}"), ext) if vfs.find(f"data/MapInfos{ext}") else {}
    infos: list = [None]
    for k in sorted(infos_raw, key=int):
        v = infos_raw[k]
        infos.append({"id": int(k), "name": v.get("name", ""), "parentId": v.get("parentId", 0),
                      "order": v.get("order", int(k)), "expanded": v.get("expanded", False)})
    proj.db["mapInfos"] = infos
    for info in infos[1:]:
        rel = vfs.find(f"data/Map{info['id']:03d}{ext}")
        if not rel:
            proj.warnings.append(f"mapa {info['id']} sem arquivo")
            continue
        try:
            proj.maps[info["id"]] = _fix_map(_rb(vfs, rel, ext), eng, info)
        except Exception as e:  # noqa: BLE001
            proj.warnings.append(f"falha ao ler mapa {info['id']}: {e}")
    proj.scripts = _read_scripts(vfs, ext)
    if proj.scripts:
        proj.notes.append(f"{len(proj.scripts)} scripts Ruby encontrados — lógica custom precisa de port para JS.")
    # sistema: converter para o formato MV mínimo usado pelo runtime
    system.setdefault("partyMembers", system.get("partyMembers", []))
    _collect_assets(proj, vfs, ("graphics",), ("audio",), None)
    if eng != "vxace":
        proj.warnings.append(f"{proj.label}: conversão experimental — revise o resultado.")


# --- 2000 / 2003 ------------------------------------------------------------

def _load_lcf(proj: Project) -> None:
    vfs = VFS(proj.root)
    proj.title = _ini_title(vfs, "RPG_RT", "GameTitle", "RPG_RT.ini") or proj.root.name
    proj.db["system"] = {"gameTitle": proj.title, "startMapId": 1, "startX": 0, "startY": 0,
                         "partyMembers": [], "switches": [], "variables": []}
    infos: list = [None]
    n = 0
    for rel, reader in sorted(vfs.walk("")):
        m = re.fullmatch(r"(?i)map(\d{4})\.lmu", rel)
        if not m:
            continue
        mid = int(m.group(1))
        parsed = lcf.read_map(reader())
        if not parsed:
            proj.warnings.append(f"mapa {rel}: formato LCF não reconhecido")
            continue
        w, h = parsed["width"], parsed["height"]
        data = [0] * (w * h * 6)
        data[0:w * h] = parsed.get("lower", [0] * (w * h))
        data[w * h:2 * w * h] = parsed.get("upper", [0] * (w * h))
        proj.maps[mid] = {"id": mid, "name": f"Map{mid:04d}", "displayName": "", "width": w, "height": h,
                          "tilesetId": parsed.get("chipsetId", 1), "data": data, "events": [None], "note": "",
                          "lcf": True}
        infos.append({"id": mid, "name": f"Map{mid:04d}", "parentId": 0, "order": mid})
        n += 1
    proj.db["mapInfos"] = infos
    if infos[1:]:
        proj.db["system"]["startMapId"] = infos[1]["id"]
    for key in DB_KEYS.values():
        proj.db.setdefault(key, [None])
    proj.db["tilesets"] = [None, {"id": 1, "name": "chipset", "tilesetNames": [], "flags": [], "mode": "lcf"}]
    proj.warnings.append(
        f"{proj.label}: banco de dados e eventos (RPG_RT.ldb/.lmu) NÃO são decodificados; "
        f"{n} mapas importados só com tiles. Use `expand --ai` para reconstruir a lógica a partir do material fornecido.")
    _collect_assets_lcf(proj, vfs)


_LCF_CAT = {"charset": "characters", "faceset": "faces", "monster": "enemies", "picture": "pictures",
            "panorama": "parallaxes", "backdrop": "battlebacks1", "chipset": "tilesets", "system": "system",
            "system2": "system", "title": "titles1", "gameover": "titles2", "battle": "animations",
            "battle2": "animations", "battlecharset": "sv_actors", "battleweapon": "animations",
            "frame": "system", "genericmenu": "system", "music": "bgm", "sound": "se"}


def _collect_assets_lcf(proj: Project, vfs: VFS) -> None:
    """No 2000/2003 a pasta de topo já é a categoria (CharSet/, Music/, ...)."""
    for rel, reader in vfs.walk(""):
        parts = rel.split("/")
        cat = _LCF_CAT.get(parts[0].lower())
        if not cat or len(parts) < 2:
            continue
        fname = parts[-1]
        dot = fname.rfind(".")
        if dot <= 0:
            continue
        name = "/".join(parts[1:-1] + [fname[:dot]])
        proj.assets.append(AssetEntry(cat, name, fname[dot:].lower(), reader, rel))
