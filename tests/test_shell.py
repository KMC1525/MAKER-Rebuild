from pathlib import Path

from maker_rebuild.config import Config
from maker_rebuild.shell import Shell


def test_shell_commands_flow(capsys, mv_src, tmp_path):
    sh = Shell(Config(provider="mock"))
    sh.out = str(tmp_path / "o")
    assert sh.dispatch("open", str(mv_src)) is True
    sh.dispatch("analyze", "")
    sh.dispatch("recompile", "")
    assert sh.last_game and (sh.last_game / "Game.html").exists()
    sh.dispatch("expand", "uma poção e um npc")
    assert "Poção Mock" in (sh.last_game / "code/js/data/db.js").read_text(encoding="utf-8")
    sh.dispatch("provider", "ollama qwen:7b")
    assert sh.cfg.provider_name == "ollama" and sh.cfg.model == "qwen:7b"
    assert sh.dispatch("quit", "") is False


def test_shell_requires_open_project():
    import pytest
    with pytest.raises(RuntimeError, match="nenhum projeto"):
        Shell(Config(provider="mock")).dispatch("analyze", "")
