import json
import zipfile
from pathlib import Path

import pytest

from maker_rebuild.cli import main
from maker_rebuild.build.builtgame import open_built_game


def run(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr()
    return code, out.out, out.err


def test_analyze_json(capsys, mv_src):
    code, out, _ = run(capsys, "analyze", str(mv_src), "--json")
    rep = json.loads(out)
    assert code == 0 and rep["engine"] == "mv" and rep["maps"] == 2 and rep["commands"]["coverage"] == 100.0


def test_recompile_produces_zip_and_valid_game(capsys, mv_src, tmp_path):
    code, out, err = run(capsys, "recompile", str(mv_src), "-o", str(tmp_path / "d"), "--no-color", "-y")
    assert code == 0, err
    z = tmp_path / "d" / "test-quest.zip"
    assert z.exists() and "test-quest/Game.html" in zipfile.ZipFile(z).namelist()
    assert (tmp_path / "d" / "test-quest" / "code" / "validation-report.json").exists()


def test_validate_command(capsys, built):
    code, out, _ = run(capsys, "validate", str(built.root), "--json")
    assert code == 0 and json.loads(out)["ok"]


def test_expand_with_mock_provider_then_validate(capsys, built, tmp_path):
    code, out, err = run(capsys, "expand", str(built.root), "uma poção e um NPC", "--provider", "mock", "-o", str(tmp_path / "x"), "-y", "--no-color")
    assert code == 0, err
    g = open_built_game(str(tmp_path / "x" / "test-quest-expanded.zip"), tmp_path / "unz")
    assert g.db["items"][-1]["name"] == "Poção Mock" and len([e for e in g.maps[1]["events"] if e]) == 6
    assert g.db["items"][-1]["id"] == 2


def test_translate_with_mock_provider(capsys, built, tmp_path):
    code, _, err = run(capsys, "translate", str(built.root), "--to", "en", "--provider", "mock", "-o", str(tmp_path / "t"), "-y", "--no-color")
    assert code == 0, err
    g = open_built_game(str(tmp_path / "t" / "test-quest-en.zip"), tmp_path / "unz")
    assert g.title.startswith("[en]") and g.config["lang"] == "en"


def test_expand_without_key_fails_with_hint(capsys, built, monkeypatch, tmp_path):
    for k in ("ANTHROPIC_API_KEY", "MAKER_REBUILD_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SystemExit) as e:
        main(["expand", str(built.root), "algo", "--provider", "anthropic", "-o", str(tmp_path)])
    assert "ANTHROPIC_API_KEY" in str(e.value) and "ollama" in str(e.value)


def test_expand_requires_request(capsys, built):
    with pytest.raises(SystemExit):
        main(["expand", str(built.root), "--provider", "mock"])


def test_not_a_project_gives_clean_error(capsys, tmp_path):
    (tmp_path / "vazio").mkdir()
    code, _, err = run(capsys, "analyze", str(tmp_path / "vazio"), "--no-color")
    assert code == 2 and "nenhum projeto RPG Maker" in err


def test_providers_and_prompt_commands(capsys):
    code, out, _ = run(capsys, "providers")
    assert code == 0 and "ollama" in out and "anthropic" in out
    code, out, _ = run(capsys, "prompt")
    assert "sem restrições" in out and "Contrato operacional" in out


def test_demo_command_creates_loadable_project(capsys, tmp_path):
    code, out, _ = run(capsys, "demo", str(tmp_path / "d"), "--no-color")
    assert code == 0 and (tmp_path / "d" / "data" / "System.json").exists()
    code, out, _ = run(capsys, "analyze", str(tmp_path / "d"), "--json")
    assert json.loads(out)["title"] == "Demo Quest"


def test_serve_serves_game_over_http(built):
    import threading, time, urllib.request
    from maker_rebuild.cli import main as cli_main
    port = 18765
    t = threading.Thread(target=lambda: cli_main(["serve", str(built.root), "--port", str(port)]), daemon=True)
    t.start()
    for _ in range(50):
        try:
            body = urllib.request.urlopen(f"http://127.0.0.1:{port}/Game.html", timeout=1).read().decode()
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise AssertionError("servidor não subiu")
    assert "MR.boot()" in body
    assert urllib.request.urlopen(f"http://127.0.0.1:{port}/code/js/data/db.js", timeout=2).status == 200


def test_interactive_shell_reads_stdin(monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("/help\n/status\n/quit\n"))
    from maker_rebuild.cli import main as cli_main
    assert cli_main(["shell", "--provider", "mock"]) == 0
    out = capsys.readouterr().out
    assert "/recompile" in out and "mock" in out
