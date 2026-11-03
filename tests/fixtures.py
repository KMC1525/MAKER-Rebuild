"""Fixtures de teste: reaproveita o projeto de demo MV e gera projetos VX Ace via um dumper de Ruby Marshal."""
from __future__ import annotations

import struct
import wave
import zlib
from pathlib import Path
from typing import Any, Dict, List

from maker_rebuild.demo import (Img, _cmd, _page, a2_sheet, b_sheet, char_sheet, make_map, make_mv_project,  # noqa: F401
                                wav_bytes)


# ================================================================ Ruby Marshal (dumper) + projeto VX Ace
class RObj:
    def __init__(self, cls: str, **iv: Any):
        self.cls, self.iv = cls, iv


class RTable:
    def __init__(self, xs: int, ys: int = 1, zs: int = 1, data=None):
        self.xs, self.ys, self.zs = xs, ys, zs
        self.data = list(data) if data is not None else [0] * (xs * ys * zs)


def _w_long(n: int) -> bytes:
    if n == 0:
        return b"\x00"
    if 0 < n < 123:
        return bytes([n + 5])
    if -124 < n < 0:
        return bytes([(n - 5) & 0xFF])
    buf = []
    x = n
    for i in range(1, 5):
        buf.append(x & 0xFF)
        x >>= 8
        if x == 0:
            return bytes([i]) + bytes(buf)
        if x == -1:
            return bytes([(-i) & 0xFF]) + bytes(buf)
    raise ValueError(n)


def marshal_dump(obj: Any) -> bytes:
    syms: Dict[str, int] = {}
    out = bytearray(b"\x04\x08")

    def sym(s: str) -> None:
        if s in syms:
            out.extend(b";" + _w_long(syms[s]))
        else:
            syms[s] = len(syms)
            b = s.encode()
            out.extend(b":" + _w_long(len(b)) + b)

    def w(o: Any) -> None:
        if o is None:
            out.extend(b"0")
        elif o is True:
            out.extend(b"T")
        elif o is False:
            out.extend(b"F")
        elif isinstance(o, int):
            out.extend(b"i" + _w_long(o))
        elif isinstance(o, float):
            out.extend(b"f" + _w_long(len(repr(o))) + repr(o).encode())
        elif isinstance(o, str):
            b = o.encode()
            out.extend(b'I"' + _w_long(len(b)) + b + _w_long(1))
            sym("E")
            out.extend(b"T")
        elif isinstance(o, bytes):
            out.extend(b'"' + _w_long(len(o)) + o)
        elif isinstance(o, (list, tuple)):
            out.extend(b"[" + _w_long(len(o)))
            for x in o:
                w(x)
        elif isinstance(o, dict):
            out.extend(b"{" + _w_long(len(o)))
            for k, v in o.items():
                w(k)
                w(v)
        elif isinstance(o, RTable):
            raw = struct.pack("<5i", 3 if o.zs > 1 else (2 if o.ys > 1 else 1), o.xs, o.ys, o.zs, len(o.data)) + struct.pack(f"<{len(o.data)}h", *o.data)
            out.extend(b"u")
            sym("Table")
            out.extend(_w_long(len(raw)) + raw)
        elif isinstance(o, RObj):
            out.extend(b"o")
            sym(o.cls)
            out.extend(_w_long(len(o.iv)))
            for k, v in o.iv.items():
                sym("@" + k)
                w(v)
        else:
            raise TypeError(type(o))

    w(obj)
    return bytes(out)


def _rb_cmd(code: int, indent: int, *params):
    return RObj("RPG::EventCommand", code=code, indent=indent, parameters=list(params))


def _rb_page(cmds, *, char="", idx=0, trigger=0, cond=None):
    c = dict(switch1_valid=False, switch2_valid=False, variable_valid=False, self_switch_valid=False, item_valid=False, actor_valid=False,
             switch1_id=1, switch2_id=1, variable_id=1, variable_value=0, self_switch_ch="A", item_id=1, actor_id=1)
    c.update(cond or {})
    return RObj("RPG::Event::Page", condition=RObj("RPG::Event::Page::Condition", **c),
                graphic=RObj("RPG::Event::Page::Graphic", tile_id=0, character_name=char, character_index=idx, direction=2, pattern=1),
                move_type=0, move_speed=3, move_frequency=3,
                move_route=RObj("RPG::MoveRoute", repeat=True, skippable=False, list=[RObj("RPG::MoveCommand", code=0, parameters=[])]),
                walk_anime=True, step_anime=False, direction_fix=False, through=False, priority_type=1, trigger=trigger,
                list=list(cmds) + [_rb_cmd(0, 0)])


def make_vxace_project(root: Path, *, archived: bool = False, title: str = "VXA Quest") -> Path:
    """Projeto VX Ace mínimo: 1 mapa, 1 NPC com texto+escolhas+script Ruby, tilesets A2/B de 32px."""
    from maker_rebuild.engines import rgssad
    root = Path(root)
    (root / "Data").mkdir(parents=True, exist_ok=True)
    ts = 32
    files: Dict[str, bytes] = {}

    def put(rel: str, data: bytes) -> None:
        files[rel] = data

    put("Graphics/Tilesets/World_A2.png", a2_sheet(ts, [(70, 170, 70), (150, 110, 60)]).png())
    put("Graphics/Tilesets/World_B.png", b_sheet(ts).png())
    put("Graphics/Characters/Actor1.png", char_sheet(ts).png())
    put("Graphics/System/Window.png", Img(128, 128).rect(0, 0, 64, 64, (20, 24, 60)).rect(64, 0, 64, 64, (230, 235, 255)).png())
    put("Graphics/System/IconSet.png", Img(384, 384).rect(0, 0, 24, 24, (200, 40, 40)).png())
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000); w.writeframes(b"\x00\x00" * 400)
    put("Audio/BGM/Theme1.wav", buf.getvalue())
    put("Audio/BGM/Old.mid", b"MThd\x00\x00\x00\x06\x00\x00\x00\x01\x00\x60")

    bgm = lambda n="": RObj("RPG::BGM", name=n, volume=90, pitch=100)  # noqa: E731
    w_, h_ = 12, 9
    data = RTable(w_, h_, 4)
    for y in range(h_):
        for x in range(w_):
            data.data[(0 * h_ + y) * w_ + x] = 2816
    for x in range(w_):
        data.data[(1 * h_ + 0) * w_ + x] = 1
    data.data[3 * w_ * h_ + 5 * w_ + 5] = (7 << 8) | 0b0101     # região 7 + sombra
    npc = RObj("RPG::Event", id=1, name="NPC", x=5, y=3, pages=[_rb_page([
        _rb_cmd(101, 0, "", 0, 0, 2), _rb_cmd(401, 0, "Olá, viajante!"),
        _rb_cmd(102, 0, ["Sim", "Não"], 2), _rb_cmd(402, 0, 0, "Sim"), _rb_cmd(121, 1, 1, 1, 0), _rb_cmd(0, 1),
        _rb_cmd(402, 0, 1, "Não"), _rb_cmd(0, 1), _rb_cmd(404, 0),
        _rb_cmd(355, 0, "$game_variables[2] += 1"), _rb_cmd(655, 0, "$game_switches[3] = true"),
        _rb_cmd(355, 0, "SceneManager.call(Scene_Custom)"),
        ], char="Actor1", idx=1)])
    gmap = RObj("RPG::Map", display_name="Campo", tileset_id=1, width=w_, height=h_, scroll_type=0, specify_battleback=False,
                battleback1_name="", battleback2_name="", bgm=bgm("Theme1"), bgs=bgm(), autoplay_bgm=True, autoplay_bgs=False,
                disable_dashing=False, encounter_list=[], encounter_step=30, parallax_name="", parallax_loop_x=False,
                parallax_loop_y=False, parallax_sx=0, parallax_sy=0, parallax_show=True, note="", data=data, events={1: npc})
    flags = RTable(8192, 1, 1, [0] * 8192)
    flags.data[1] = 0x0F
    tilesets = [None, RObj("RPG::Tileset", id=1, mode=1, name="World", tileset_names=["", "World_A2", "", "", "", "World_B", "", "", ""],
                           flags=flags, note="")]
    params = RTable(8, 100, 1, [0] * 800)
    for lv in range(100):
        for p in range(8):
            params.data[p + 8 * lv] = (60 if p < 2 else 8) + lv * 3
    system = RObj("RPG::System", game_title=title, start_map_id=1, start_x=2, start_y=2, party_members=[1], switches=["", "S1", "S2", "S3"],
                  variables=["", "V1", "V2"], title1_name="", title2_name="", title_bgm=bgm("Theme1"), battle_bgm=bgm(),
                  gameover_me=bgm(), sounds=[RObj("RPG::SE", name="", volume=80, pitch=100)] * 24, currency_unit="G",
                  terms=RObj("RPG::System::Terms", basic=["Level"] * 8, params=["MHP", "MMP", "ATK", "DEF", "MAT", "MDF", "AGI", "LUK"],
                             etypes=["Weapon"], commands=["Fight", "Escape", "Attack", "Guard", "Item", "Skill", "Equip", "Status", "Save", "Game End"]))
    db = {
        "System": system,
        "Actors": [None, RObj("RPG::Actor", id=1, name="Eric", nickname="", class_id=1, initial_level=1, max_level=99, character_name="Actor1",
                              character_index=0, face_name="", face_index=0, equips=[0, 0, 0, 0, 0], description="", features=[], note="")],
        "Classes": [None, RObj("RPG::Class", id=1, name="Hero", exp_params=[30, 20, 30, 30], params=params, learnings=[], features=[], note="")],
        "Skills": [None], "Items": [None], "Weapons": [None], "Armors": [None], "Enemies": [None], "Troops": [None], "States": [None],
        "Animations": [None], "Tilesets": tilesets,
        "CommonEvents": [None],
        "MapInfos": {1: RObj("RPG::MapInfo", name="Campo", parent_id=0, order=1, expanded=False, scroll_x=0, scroll_y=0)},
        "Map001": gmap,
    }
    for name, obj in db.items():
        put(f"Data/{name}.rvdata2", marshal_dump(obj))
    import zlib as _z
    scripts = [[1, "Game_Actor", _z.compress(b"class Game_Actor; end")],
               [2, "MeuSistema", _z.compress(("# sistema custom\n" + "class Scene_Custom\n  def main; end\nend\n" * 6).encode())]]
    put("Data/Scripts.rvdata2", marshal_dump([[a, b.encode(), c] for a, b, c in scripts]))
    (root / "Game.ini").write_text("[Game]\nRTP=RPGVXAce\nLibrary=System\\RGSS301.dll\nScripts=Data\\Scripts.rvdata2\nTitle=VXA Quest\n", encoding="utf-8")
    (root / "Game.rvproj2").write_text("RPGVXAce 1.02", encoding="utf-8")
    if archived:
        rgssad.write_v3(files, root / "Game.rgss3a")
    else:
        for rel, data in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        (root / "Data").mkdir(exist_ok=True)
    if archived:
        (root / "Data").rmdir() if not any((root / "Data").iterdir()) else None
    return root


# ================================================================ RPG Maker 2000/2003 (LCF) mínimo
def _ber(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


def make_rm2k_project(root: Path, *, w: int = 10, h: int = 8, title: str = "Jogo 2000") -> Path:
    root = Path(root)
    for d in ("CharSet", "ChipSet", "Music", "Sound", "Title", "FaceSet"):
        (root / d).mkdir(parents=True, exist_ok=True)
    (root / "RPG_RT.ldb").write_bytes(b"\x0bLcfDataBase\x00")
    (root / "RPG_RT.lmt").write_bytes(b"\x0bLcfMapTree\x00")
    (root / "RPG_RT.exe").write_bytes(b"MZ")
    (root / "RPG_RT.ini").write_text(f"[RPG_RT]\nGameTitle={title}\n", encoding="utf-8")

    def chunk(cid: int, data: bytes) -> bytes:
        return _ber(cid) + _ber(len(data)) + data

    lower = struct.pack(f"<{w * h}H", *[(5000 + (i % 7)) for i in range(w * h)])
    upper = struct.pack(f"<{w * h}H", *([10000] * (w * h)))
    body = (_ber(10) + b"LcfMapUnit" + chunk(1, _ber(1)) + chunk(2, _ber(w)) + chunk(3, _ber(h)) + chunk(0x47, lower) + chunk(0x48, upper) + _ber(0))
    (root / "Map0001.lmu").write_bytes(body)
    (root / "CharSet" / "Hero.png").write_bytes(Img(72, 128, (10, 10, 10, 255)).png())
    (root / "ChipSet" / "Basis.png").write_bytes(Img(480, 256, (50, 90, 50, 255)).png())
    wav_bytes(root / "Music" / "Town.wav")
    (root / "Music" / "Old.mid").write_bytes(b"MThd")
    return root
