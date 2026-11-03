"""Arrastar e soltar: caminhos colados pelo terminal, classificação de zips e continuação do fluxo no shell."""
import io
import zipfile
from pathlib import Path

import pytest

from fixtures import make_mv_project, make_vxace_project, make_rm2k_project
from maker_rebuild import dropin
from maker_rebuild.cli import main
from maker_rebuild.config import Config
from maker_rebuild.shell import Shell


def zip_dir(src: Path, dst: Path, top: str = "") -> Path:
    with zipfile.ZipFile(dst, "w") as z:
        for f in sorted(src.rglob("*")):
            if f.is_file():
                z.write(f, (Path(top) / f.relative_to(src)).as_posix() if top else f.relative_to(src).as_posix())
    return dst


@pytest.fixture()
def spaced(tmp_path):
    d = tmp_path / "Meu Jogo (v2)"
    d.mkdir()
    z = d / "a b.zip"
    z.write_bytes(b"x")
    doc = tmp_path / "roteiro final.md"
    doc.write_text("# Roteiro\nO herói parte em uma jornada.")
    return z, doc


# ------------------------------------------------------------------ parse do que o terminal cola
def _esc(p: Path) -> str:   # macOS Terminal
    return "".join("\\" + c if c in " ()&'" else c for c in str(p))


@pytest.mark.parametrize("fmt", [
    lambda p: _esc(p),                                   # macOS: espaços/parênteses escapados
    lambda p: f"'{p}'",                                  # GNOME Terminal
    lambda p: f'"{p}"  ',                                # cmd.exe (com espaço sobrando)
    lambda p: f"& '{p}'",                                # PowerShell
    lambda p: Path(p).as_uri(),                          # file:///... com %20
    lambda p: str(p),                                    # sem aspas, com espaços
])
def test_parse_each_terminal_style(spaced, fmt):
    z, _ = spaced
    assert dropin.parse_dropped(fmt(z)) == [(z, True)]


def test_parse_multiple_items_and_missing(spaced, tmp_path):
    z, doc = spaced
    got = dropin.parse_dropped(f"'{z}' {_esc(doc)} {tmp_path}/nao-existe.zip")
    assert got[:2] == [(z, True), (doc, True)] and got[2][1] is False


def test_windows_style_paths_keep_backslashes():
    assert dropin._tokenize(r'"C:\Users\ana\Meu Jogo.zip" C:\x\y.md') == [r"C:\Users\ana\Meu Jogo.zip", r"C:\x\y.md"]
    assert dropin.clean_path("file:///C:/Users/ana/a%20b.zip") == "C:/Users/ana/a b.zip"
    assert dropin.clean_path('& "C:\\Games\\RPG (old)\\game.zip"') == "C:\\Games\\RPG (old)\\game.zip"


def test_clean_path_expands_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert dropin.clean_path("~/jogo.zip") == str(tmp_path / "jogo.zip")


def test_looks_like_path_vs_sentence(spaced):
    z, _ = spaced
    assert dropin.looks_like_path(f"'{z}'") and not dropin.looks_like_path("adicione uma dungeon de gelo") and not dropin.looks_like_path("")


# ------------------------------------------------------------------ classificação (sem extrair)
def test_classify_zips_and_folders(tmp_path, mv_src, vxa_src, built):
    mv_zip = zip_dir(mv_src, tmp_path / "mv.zip")
    assert (dropin.classify(mv_zip).kind, dropin.classify(mv_zip).engine) == ("project", "mv")
    www = make_mv_project(tmp_path / "w", www=True)
    assert dropin.classify(zip_dir(tmp_path / "w", tmp_path / "w.zip", top="Game")).engine == "mv"
    mz = make_mv_project(tmp_path / "mz", mz=True)
    assert dropin.classify(zip_dir(mz, tmp_path / "mz.zip")).engine == "mz"
    assert dropin.classify(zip_dir(vxa_src, tmp_path / "vxa.zip")).engine == "vxace"
    assert dropin.classify(zip_dir(make_rm2k_project(tmp_path / "k"), tmp_path / "k.zip")).engine == "rm2k"
    bz = zip_dir(built.root, tmp_path / "built.zip", top=built.root.name)
    assert dropin.classify(bz).kind == "built" and dropin.classify(built.root).kind == "built"
    empty = tmp_path / "vazia"
    empty.mkdir()
    assert dropin.classify(mv_src).kind == "project" and dropin.classify(empty).kind == "folder"


def test_classify_docs_unknown_and_corrupt(tmp_path):
    (tmp_path / "g.md").write_text("x")
    (tmp_path / "x.exe").write_bytes(b"MZ")
    (tmp_path / "bad.zip").write_bytes(b"not a zip")
    (tmp_path / "other.zip").write_bytes(b"")
    with zipfile.ZipFile(tmp_path / "other.zip", "w") as z:
        z.writestr("readme.txt", "oi")
    assert dropin.classify(tmp_path / "g.md").kind == "docs"
    assert dropin.classify(tmp_path / "x.exe").kind == "unknown"
    assert "corrompido" in dropin.classify(tmp_path / "bad.zip").detail
    assert "não reconheci" in dropin.classify(tmp_path / "other.zip").detail
    assert dropin.classify(tmp_path / "nada").kind == "unknown"


# ------------------------------------------------------------------ shell: soltar → menu → continuar
def test_shell_drop_zip_shows_menu_and_runs_option(tmp_path, mv_src, capsys):
    z = zip_dir(mv_src, tmp_path / "Meu Jogo.zip")
    sh = Shell(Config(provider="mock"))
    sh.out = str(tmp_path / "out")
    assert sh.handle(f"'{z}'") is True                       # arrastou o zip
    out = capsys.readouterr().out
    assert "projeto original (mv)" in out and "Próximo passo" in out and "Recompilar fielmente" in out
    assert sh.kind == "project" and sh.path == str(z) and len(sh.menu) == 4
    sh.handle("2")                                           # recompilar
    assert (tmp_path / "out" / "test-quest.zip").exists()
    out = capsys.readouterr().out
    assert "Validar o jogo" in out and "Expandir" in out     # fluxo continua com o menu do jogo pronto
    assert sh.kind == "built" and sh.source == str(z)


def test_shell_continues_from_built_game_without_destroying_it(tmp_path, built, monkeypatch):
    """Expandir a partir de dist/<jogo> com saída em dist/ não pode apagar a pasta de origem."""
    sh = Shell(Config(provider="mock"))
    sh.out = str(built.root.parent)
    sh.handle(f'"{built.root}"')
    assert sh.kind == "built"
    monkeypatch.setattr("maker_rebuild.ui.ask", lambda q, d="": "adicione uma poção e um npc")
    sh.handle("3")
    assert (built.root / "Game.html").exists(), "o jogo de origem foi destruído"
    assert (built.root.parent / "test-quest-expanded").is_dir() and (built.root.parent / "test-quest-expanded.zip").exists()
    assert "Poção Mock" in (built.root.parent / "test-quest-expanded/code/js/data/db.js").read_text(encoding="utf-8")


def test_shell_drop_docs_then_game_and_docs_reach_context(tmp_path, mv_src, spaced, capsys):
    _z, doc = spaced
    sh = Shell(Config(provider="mock"))
    sh.handle(f"{_esc(doc)}")                                # só o roteiro, sem jogo ainda
    out = capsys.readouterr().out
    assert "documento anexado" in out and sh.docs == [str(doc)] and "Solte" in out
    sh.handle(f"'{mv_src}'")
    assert sh.path == str(mv_src) and sh.docs == [str(doc)]
    o = sh.opts()
    assert o.extra_notes and "O herói parte" in o.extra_notes[0]
    sh.handle("/docs clear")
    assert sh.docs == []


def test_shell_drop_game_and_docs_together_and_last_game_wins(tmp_path, mv_src, vxa_src, spaced, capsys):
    _z, doc = spaced
    sh = Shell(Config(provider="mock"))
    sh.handle(f"'{mv_src}' '{vxa_src}' '{doc}'")
    cap = capsys.readouterr()
    assert "vários jogos soltos" in cap.err and sh.path == str(vxa_src) and sh.engine == "vxace" and sh.docs == [str(doc)]


def test_shell_absolute_path_is_not_mistaken_for_a_slash_command(mv_src):
    sh = Shell(Config(provider="mock"))
    assert str(mv_src).startswith("/")
    sh.handle(str(mv_src))
    assert sh.path == str(mv_src)


def test_shell_reports_unknown_and_missing_items(tmp_path, capsys):
    (tmp_path / "x.exe").write_bytes(b"MZ")
    sh = Shell(Config(provider="mock"))
    sh.drop(f"{tmp_path}/x.exe {tmp_path}/nao.zip")
    err = capsys.readouterr().err
    assert "não encontrei" in err and "x.exe" in err and sh.path is None


def test_shell_menu_number_out_of_range(mv_src):
    sh = Shell(Config(provider="mock"))
    sh.handle(f"'{mv_src}'")
    with pytest.raises(RuntimeError, match="1 a 4"):
        sh.handle("9")


def test_shell_open_command_accepts_dropped_syntax(mv_src, capsys):
    sh = Shell(Config(provider="mock"))
    sh.handle(f"/open '{mv_src}'")
    assert sh.path == str(mv_src) and "Próximo passo" in capsys.readouterr().out


# ------------------------------------------------------------------ CLI
def test_cli_shortcut_path_argument_opens_shell_with_game(tmp_path, mv_src, monkeypatch, capsys):
    """`maker-rebuild jogo.zip roteiro.md` (arrastar sobre o .exe/atalho) abre o shell já carregado."""
    import io
    z = zip_dir(mv_src, tmp_path / "jogo.zip")
    doc = tmp_path / "gdd.md"
    doc.write_text("gdd")
    monkeypatch.setattr("sys.stdin", io.StringIO("/status\n/quit\n"))
    assert main([str(z), str(doc)]) == 0
    out = capsys.readouterr().out
    assert "projeto original (mv)" in out and "documento anexado: gdd.md" in out and "Próximo passo" in out


def test_cli_unknown_word_still_errors_like_before(capsys):
    with pytest.raises(SystemExit):
        main(["comando-que-nao-existe"])


def test_cli_accepts_dropped_path_syntax_in_commands(tmp_path, mv_src, capsys):
    import json
    z = zip_dir(mv_src, tmp_path / "Meu Jogo.zip")
    assert main(["analyze", f"'{z}'", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["engine"] == "mv"
    assert main(["analyze", Path(z).as_uri(), "--json"]) == 0


def test_cli_asks_for_missing_path_interactively(tmp_path, mv_src, monkeypatch, capsys):
    import json
    z = zip_dir(mv_src, tmp_path / "jogo.zip")
    monkeypatch.setattr("maker_rebuild.ui.is_interactive", lambda: True)
    monkeypatch.setattr("maker_rebuild.ui.ask", lambda q, d="": f"'{z}'")
    assert main(["analyze", "--json"]) == 0
    out = capsys.readouterr().out
    assert "projeto mv" in out and json.loads(out[out.index("{"):])["engine"] == "mv"


def test_cli_missing_path_non_interactive_fails_clearly(monkeypatch):
    monkeypatch.setattr("maker_rebuild.ui.is_interactive", lambda: False)
    with pytest.raises(SystemExit, match="informe o caminho"):
        main(["analyze"])
