import json
import zipfile
from pathlib import Path

from maker_rebuild.build import commands as cmdmod, datajs
from maker_rebuild.build.builder import RUNTIME_DIR, build_game, slugify
from maker_rebuild.build.builtgame import BuiltGame, open_built_game
from maker_rebuild.build.validate import validate_game
from maker_rebuild.build.zipper import make_zip
from maker_rebuild.project import open_project


def test_structure_matches_spec(built):
    r = built.root
    for rel in ("Game.html", "code/html", "code/css", "code/js", "assets/sprites", "assets/background", "assets/ui-ux",
                "assets/music", "assets/sfx", "code/js/data/db.js", "code/js/data/config.js", "code/js/data/maps/map-1.js"):
        assert (r / rel).exists(), rel
    assert (r / "assets/sprites/characters/Actor1.png").read_bytes().startswith(b"\x89PNG")
    assert (r / "assets/background/tilesets/World_A2.png").exists() and (r / "assets/music/bgm/Theme1.wav").exists()
    html = (r / "Game.html").read_text()
    assert "code/js/mr-core.js" in html and html.index("data/db.js") < html.index("MR.boot()")


def test_validate_ok_and_roundtrip_data(built):
    rep = validate_game(built)
    assert rep["ok"], rep["errors"]
    assert rep["commands"]["coverage"] == 100.0
    g2 = BuiltGame(built.root)
    assert g2.db["system"]["gameTitle"] == "Test Quest" and set(g2.maps) == {1, 2}


def test_validate_detects_problems(built):
    built.maps[1]["events"][2]["pages"][0]["list"][0]["parameters"][1] = 99     # teletransporte p/ mapa inexistente
    built.maps[1]["events"][1]["pages"][0]["image"]["characterName"] = "Nope"
    built.db["system"]["startMapId"] = 42
    rep = validate_game(built, check_syntax=False)
    assert not rep["ok"]
    txt = " ".join(rep["errors"] + rep["warnings"])
    assert "mapa inexistente 99" in txt and "mapa inicial 42" in txt and "characters/Nope" in str(rep["missing_where"])


def test_unsupported_command_is_reported(built):
    built.maps[1]["events"][1]["pages"][0]["list"].insert(0, {"code": 339, "indent": 0, "parameters": []})
    rep = validate_game(built, check_syntax=False)
    assert 339 in rep["commands"]["unsupported"] and any("339" in w for w in rep["warnings"])


def test_asset_index_prefers_ogg_and_survives_rescan(built):
    idx = built.rescan_assets()
    assert idx["characters"]["actor1"] == {"n": "Actor1", "e": ".png"}
    (built.root / "assets/sprites/characters/Novo.png").write_bytes(b"\x89PNG")
    assert "novo" in built.rescan_assets()["characters"]


def test_zip_layout_and_reopen(built, tmp_path):
    z = make_zip(built.root, tmp_path / "x.zip")
    names = zipfile.ZipFile(z).namelist()
    assert all(n.startswith("test-quest/") for n in names) and "test-quest/Game.html" in names
    assert open_built_game(str(z), tmp_path / "re").title == "Test Quest"
    z2 = make_zip(built.root, tmp_path / "y.zip")
    assert z.read_bytes() == z2.read_bytes()            # determinístico


def test_vxace_build_normalizes_commands(tmp_path, vxa_src):
    p = open_project(str(vxa_src))
    g = BuiltGame(build_game(p, tmp_path / "o"))
    lst = g.maps[1]["events"][1]["pages"][0]["list"]
    ch = next(c for c in lst if c["code"] == 102)
    assert ch["parameters"][1] == 1 and len(ch["parameters"]) == 5     # VXA cancel_type 2 ("escolha #2") → índice 1
    assert [c["code"] for c in lst if c["code"] in (355, 655)] and all(c.get("lang") == "ruby" for c in lst if c["code"] in (355, 655))
    rep = validate_game(g, check_syntax=False)
    assert rep["commands"]["ruby_scripts"] == 2          # dois comandos 355 (um deles seguido de 655)
    assert any(".mid" in u or "Old" in u for u in json.loads((g.root / "code/rebuild-manifest.json").read_text())["audioUnplayable"])


def test_datajs_roundtrip_and_script_escape():
    obj = {"t": "</script><b>", "u": " "}
    assert datajs.loads(datajs.dumps("MR.data.x", obj)) == obj
    assert "</script" not in datajs.dumps("MR.data.x", obj)


def test_slugify():
    assert slugify("Ação & Aventura!!") == "acao-aventura" and slugify("日本") == "game"


def test_runtime_supported_matches_python_table():
    sup = cmdmod.runtime_supported(RUNTIME_DIR / "js")
    for code in (101, 102, 111, 122, 201, 205, 301, 302, 355, 356, 357):
        assert code in sup
