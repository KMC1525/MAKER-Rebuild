import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("MAKER_REBUILD_CACHE", str(ROOT / ".pytest_cache" / "ai-cache"))
os.environ.setdefault("MAKER_REBUILD_HOME", str(ROOT / ".pytest_cache" / "cfg"))

from fixtures import make_mv_project, make_vxace_project  # noqa: E402


@pytest.fixture(scope="session")
def mv_src(tmp_path_factory):
    return make_mv_project(tmp_path_factory.mktemp("mv"))


@pytest.fixture(scope="session")
def vxa_src(tmp_path_factory):
    return make_vxace_project(tmp_path_factory.mktemp("vxa"))


@pytest.fixture()
def built(tmp_path, mv_src):
    """Jogo MV recompilado (BuiltGame), em pasta descartável."""
    from maker_rebuild.build.builder import build_game
    from maker_rebuild.build.builtgame import BuiltGame
    from maker_rebuild.project import open_project
    p = open_project(str(mv_src))
    gd = build_game(p, tmp_path / "out")
    g = BuiltGame(gd)
    g.plugins, g.scripts, g.plugin_sources = p.plugins, p.scripts, p.plugin_sources
    return g
