"""Runtime JS: sintaxe e jogabilidade real em Chromium headless (pulado se node/playwright ausentes)."""
import shutil
import subprocess
from pathlib import Path

import pytest

from maker_rebuild.build.builder import RUNTIME_DIR, build_game
from maker_rebuild.cli import main
from maker_rebuild.project import open_project

NODE = shutil.which("node")
E2E = Path(__file__).parent / "e2e"


def _has_playwright() -> bool:
    if not NODE:
        return False
    return subprocess.run([NODE, "-e", "require('playwright')"], capture_output=True).returncode == 0


needs_browser = pytest.mark.skipif(not _has_playwright(), reason="node + playwright não disponíveis")


@pytest.mark.skipif(not NODE, reason="node ausente")
@pytest.mark.parametrize("f", sorted((RUNTIME_DIR / "js").glob("*.js")), ids=lambda p: p.name)
def test_runtime_files_parse(f):
    r = subprocess.run([NODE, "--check", str(f)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def _run(script, *args, timeout=150):
    r = subprocess.run([NODE, str(E2E / script), *map(str, args)], capture_output=True, text=True, timeout=timeout)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


@needs_browser
def test_play_mv_game_end_to_end(built, tmp_path):
    out = _run("play_mv.js", built.root, tmp_path / "shot")
    assert "FAIL" not in out and "verificações OK" in out


@needs_browser
def test_play_mv_encrypted_assets(tmp_path):
    from fixtures import make_mv_project
    gd = build_game(open_project(str(make_mv_project(tmp_path / "enc", encrypted=True))), tmp_path / "o")
    out = _run("play_mv.js", gd)
    assert "FAIL" not in out


@needs_browser
@pytest.mark.parametrize("archived", [False, True])
def test_play_vxace_game(tmp_path, archived):
    from fixtures import make_vxace_project
    gd = build_game(open_project(str(make_vxace_project(tmp_path / "v", archived=archived))), tmp_path / "o")
    out = _run("play_vxace.js", gd, tmp_path / "vx")
    assert "FAIL" not in out


@needs_browser
def test_play_game_expanded_by_ai(built, tmp_path, capsys):
    assert main(["expand", str(built.root), "poção e npc", "--provider", "mock", "-o", str(tmp_path / "x"), "-y", "--no-color"]) == 0
    out = _run("play_expanded.js", tmp_path / "x" / "test-quest")
    assert "FAIL" not in out


@needs_browser
def test_rm2k_game_boots_without_errors(tmp_path):
    """Modo experimental (só tiles): o runtime deve abrir título e mapa sem exceções."""
    from fixtures import make_rm2k_project
    gd = build_game(open_project(str(make_rm2k_project(tmp_path / "k"))), tmp_path / "o")
    script = tmp_path / "boot.js"
    script.write_text("""
const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch(); const p = await b.newPage(); const errs = [];
  p.on('pageerror', (e) => errs.push(e.message)); p.on('console', (m) => m.type() === 'error' && errs.push(m.text()));
  await p.goto('file://%s/Game.html');
  await p.waitForFunction(() => MR.scene() instanceof MR.SceneTitle, null, { timeout: 8000 });
  await p.keyboard.press('Enter');
  await p.waitForFunction(() => MR.scene() instanceof MR.SceneMap && !MR.sceneMap.loading, null, { timeout: 8000 });
  await p.waitForTimeout(400);
  console.log(JSON.stringify({ errs })); await b.close(); process.exit(errs.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
""" % gd)
    r = subprocess.run([NODE, str(script)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout + r.stderr
