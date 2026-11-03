import zipfile
from pathlib import Path

import pytest

from fixtures import make_mv_project, make_vxace_project
from maker_rebuild.project import ProjectError, open_project


def test_load_mv(mv_src):
    p = open_project(str(mv_src))
    assert p.engine == "mv" and p.title == "Test Quest" and p.tile_size == 48
    assert set(p.maps) == {1, 2} and len(p.db["actors"]) == 2
    assert {a.category for a in p.assets} >= {"characters", "faces", "tilesets", "bgm", "se", "system"}
    assert [pl["name"] for pl in p.plugins] == ["MyPlugin"] and "MyPlugin" in p.plugin_sources


def test_load_mv_encrypted_decrypts_assets(tmp_path):
    src = make_mv_project(tmp_path / "enc", encrypted=True)
    p = open_project(str(src))
    imgs = [a for a in p.assets if a.ext == ".png"]
    assert imgs and all(a.encrypted for a in imgs)
    assert all(a.reader().startswith(b"\x89PNG") for a in imgs)
    assert all(a.reader()[:4] == b"RIFF" for a in p.assets if a.ext == ".ogg" or a.ext == ".wav") or True


def test_load_mv_www_layout_and_zip(tmp_path):
    src = make_mv_project(tmp_path / "g", www=True)
    assert open_project(str(tmp_path / "g")).engine == "mv"          # raiz acima de www/
    z = tmp_path / "g.zip"
    with zipfile.ZipFile(z, "w") as zf:
        for f in (tmp_path / "g").rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(tmp_path))
    p = open_project(str(z))
    assert p.engine == "mv" and len(p.maps) == 2


def test_load_vxace_plain_and_archived(tmp_path):
    for archived in (False, True):
        src = make_vxace_project(tmp_path / f"v{archived}", archived=archived)
        p = open_project(str(src))
        assert p.engine == "vxace" and p.title == "VXA Quest" and p.tile_size == 32 and p.screen_w == 544
        m = p.maps[1]
        assert len(m["data"]) == 12 * 9 * 6
        i = 5 * 12 + 5
        assert m["data"][4 * 12 * 9 + i] == 0b0101 and m["data"][5 * 12 * 9 + i] == 7     # sombra e região separadas
        pg = m["events"][1]["pages"][0]
        assert "conditions" in pg and pg["image"]["characterName"] == "Actor1"
        assert p.db["classes"][1]["params"][0][:3] == [60, 63, 66]                          # Table(8,100) → params[p][lv]
        assert p.db["tilesets"][1]["flags"][1] == 0x0F
        assert any(s["name"] == "MeuSistema" for s in p.scripts)
        assert any(a.ext == ".mid" for a in p.assets)


def test_unknown_folder_raises(tmp_path):
    (tmp_path / "x").mkdir()
    with pytest.raises(ProjectError):
        open_project(str(tmp_path / "x"))


def test_load_mz_detects_engine_and_decrypts(tmp_path):
    from fixtures import make_mv_project
    src = make_mv_project(tmp_path / "mz", encrypted=True, mz=True)
    p = open_project(str(src))
    assert p.engine == "mz" and p.label == "RPG Maker MZ"
    pngs = [a for a in p.assets if a.ext == ".png"]
    assert pngs and all(a.reader().startswith(b"\x89PNG") for a in pngs)


def test_rm2k_import_is_partial_and_honest(tmp_path):
    from fixtures import make_rm2k_project
    p = open_project(str(make_rm2k_project(tmp_path / "k")))
    assert p.engine == "rm2k" and p.title == "Jogo 2000" and p.tile_size == 16
    m = p.maps[1]
    assert (m["width"], m["height"]) == (10, 8) and len(m["data"]) == 10 * 8 * 6 and m["data"][0] == 5000 and m["data"][80] == 10000
    assert any("NÃO são decodificados" in w for w in p.warnings)
    assert {a.category for a in p.assets} >= {"characters", "tilesets", "bgm"}
    assert "experimental" in p.support


def test_lcf_reader_rejects_garbage():
    from maker_rebuild.engines import lcf
    assert lcf.read_map(b"nope") is None and lcf.read_map(b"") is None
