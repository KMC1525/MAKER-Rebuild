import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from fixtures import RObj, RTable, marshal_dump
from maker_rebuild.engines import rgssad, rubymarshal as rm
from maker_rebuild.engines.crypt import decrypt, encrypt, parse_key, recover_png_key
from maker_rebuild.engines.vfs import safe_extract


def test_marshal_roundtrip_with_python_dumper():
    obj = {1: RObj("RPG::Foo", name="Héroi 日本", class_id=3, flag=True, arr=[1, -1, 300, -70000, 2 ** 31, None],
                   tbl=RTable(2, 2, 1, [0, 1, -5, 7]))}
    out = rm.convert(rm.loads(marshal_dump(obj)))
    foo = out["1"]
    assert foo["name"] == "Héroi 日本" and foo["classId"] == 3 and foo["flag"] is True
    assert foo["arr"] == [1, -1, 300, -70000, 2 ** 31, None]
    assert list(foo["tbl"]) == [0, 1, -5, 7] and foo["tbl"].dims == (2, 2, 1)


@pytest.mark.skipif(not shutil.which("ruby"), reason="ruby não instalado")
def test_marshal_against_real_ruby(tmp_path):
    rb = tmp_path / "g.rb"
    rb.write_text('''
class Table; def initialize(x); @x=x; @d=Array.new(x,0); @d[1]=-5; end
  def _dump(lv); [1, @x, 1, 1, @d.size].pack("l<5") + @d.pack("s<*"); end; def self._load(s); s; end; end
module RPG; class Foo; def initialize; @name="Ação"; @n=[1,-1,300,2**40,1.5,nil,:a,:a]; @t=Table.new(3); @s="x"; @a=@s; @b=@s; end; end; end
File.binwrite(ARGV[0], Marshal.dump({1=>RPG::Foo.new}))
''')
    out = tmp_path / "a.bin"
    subprocess.run(["ruby", str(rb), str(out)], check=True)
    foo = rm.convert(rm.loads(out.read_bytes()))["1"]
    assert foo["name"] == "Ação" and foo["n"][:4] == [1, -1, 300, 2 ** 40] and list(foo["t"]) == [0, -5, 0]
    assert foo["a"] == foo["b"] == "x"          # objetos compartilhados (@ links)


def test_marshal_rejects_garbage():
    with pytest.raises(rm.MarshalError):
        rm.loads(b"not marshal")


@pytest.mark.parametrize("writer,ver", [(rgssad.write_v1, 1), (rgssad.write_v3, 3)])
def test_rgssad_roundtrip(tmp_path, writer, ver):
    files = {"Data/System.rvdata2": b"abc" * 100, "Graphics/Characters/Ação.png": bytes(range(256)) * 3, "Audio/BGM/x.ogg": b"\x00"}
    f = tmp_path / "Game.rgss"
    writer(files, f)
    a = rgssad.RGSSArchive(f)
    assert a.version == ver
    got = {e.name: a.read(e) for e in a.entries}
    assert got == files


def test_mv_crypt_roundtrip_and_key_recovery():
    from fixtures import Img
    png = Img(40, 40).rect(0, 0, 20, 20, (1, 2, 3)).png()
    key = parse_key("d41d8cd98f00b204e9800998ecf8427e")
    enc = encrypt(png, key)
    assert enc != png and decrypt(enc, key) == png
    assert recover_png_key(enc) == key


def test_safe_extract_blocks_zip_slip(tmp_path):
    import zipfile
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../evil.txt", "x")
    with pytest.raises(ValueError):
        safe_extract(z, tmp_path / "dest")
    assert not (tmp_path / "evil.txt").exists()
