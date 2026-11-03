"""Instaladores (install.sh / install.ps1 / install.bat) e empacotamento do executável."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SH = shutil.which("sh")
posix_only = pytest.mark.skipif(not SH or os.name == "nt", reason="precisa de sh (Linux/macOS)")

sys.path.insert(0, str(ROOT / "packaging"))
import build_exe  # noqa: E402


def _arch() -> str:
    import platform
    return {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(platform.machine().lower(), "")


def _osname() -> str:
    return {"linux": "linux", "darwin": "macos"}.get(sys.platform, "")


@posix_only
def test_install_sh_syntax_and_help():
    assert subprocess.run([SH, "-n", str(ROOT / "install.sh")]).returncode == 0
    r = subprocess.run([SH, str(ROOT / "install.sh"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "--uninstall" in r.stdout and "--prefix" in r.stdout
    assert subprocess.run([SH, str(ROOT / "install.sh"), "--nope"], capture_output=True).returncode != 0


@posix_only
def test_install_sh_dry_run_changes_nothing(tmp_path):
    r = subprocess.run([SH, str(ROOT / "install.sh"), "--dry-run", "--prefix", str(tmp_path / "p")], capture_output=True, text=True,
                       env={**os.environ, "MAKER_REBUILD_BASE_URL": "http://127.0.0.1:1", "MAKER_REBUILD_DATA": str(tmp_path / "d")})
    assert r.returncode == 0 and "dry-run" in r.stdout
    assert not (tmp_path / "p").exists() and not (tmp_path / "d").exists()


@pytest.fixture()
def fake_release(tmp_path):
    """Servidor local com uma 'release' cujo executável é um script (testa download+checksum+extração+instalação)."""
    if not (_osname() and _arch()):
        pytest.skip("plataforma sem asset de release")
    rel = tmp_path / "rel"
    rel.mkdir()
    asset = f"maker-rebuild-{_osname()}-{_arch()}.tar.gz"
    payload = b"#!/bin/sh\necho 'maker-rebuild 9.9.9-fake'\n"
    with tarfile.open(rel / asset, "w:gz") as t:
        info = tarfile.TarInfo("maker-rebuild")
        info.size, info.mode = len(payload), 0o755
        t.addfile(info, io.BytesIO(payload))
    digest = hashlib.sha256((rel / asset).read_bytes()).hexdigest()
    (rel / f"{asset}.sha256").write_text(f"{digest}  {asset}\n")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(rel)))
    srv.RequestHandlerClass.log_message = lambda *a, **k: None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield rel, asset, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _env(tmp_path, url):
    return {**os.environ, "MAKER_REBUILD_BASE_URL": url, "MAKER_REBUILD_DATA": str(tmp_path / "data")}


@posix_only
def test_install_sh_exe_mode_roundtrip(tmp_path, fake_release):
    _rel, _asset, url = fake_release
    prefix = tmp_path / "prefix"
    r = subprocess.run([SH, str(ROOT / "install.sh"), "--exe", "--prefix", str(prefix)], capture_output=True, text=True, env=_env(tmp_path, url))
    assert r.returncode == 0, r.stdout + r.stderr
    exe = prefix / "bin" / "maker-rebuild"
    assert "checksum SHA-256 verificado" in r.stdout and os.access(exe, os.X_OK)
    assert subprocess.run([str(exe)], capture_output=True, text=True).stdout.strip() == "maker-rebuild 9.9.9-fake"
    u = subprocess.run([SH, str(ROOT / "install.sh"), "--uninstall", "--prefix", str(prefix)], capture_output=True, text=True, env=_env(tmp_path, url))
    assert u.returncode == 0 and not exe.exists()


@posix_only
def test_install_sh_rejects_bad_checksum(tmp_path, fake_release):
    rel, asset, url = fake_release
    (rel / f"{asset}.sha256").write_text("0" * 64 + f"  {asset}\n")
    r = subprocess.run([SH, str(ROOT / "install.sh"), "--exe", "--prefix", str(tmp_path / "p")], capture_output=True, text=True, env=_env(tmp_path, url))
    assert r.returncode != 0 and "checksum" in r.stderr and not (tmp_path / "p" / "bin" / "maker-rebuild").exists()


@posix_only
def test_install_sh_auto_falls_back_to_python_when_no_release(tmp_path):
    """Sem release → modo Python a partir do checkout (venv + pip). Precisa de rede para o setuptools; pula se falhar."""
    r = subprocess.run([SH, str(ROOT / "install.sh"), "--prefix", str(tmp_path / "p")], capture_output=True, text=True, timeout=300,
                       env=_env(tmp_path, "http://127.0.0.1:1"))
    if r.returncode != 0 and ("falha no pip" in r.stderr or "venv" in r.stderr):
        pytest.skip("pip/venv indisponível neste ambiente: " + r.stderr[-200:])
    assert r.returncode == 0, r.stdout + r.stderr
    out = subprocess.run([str(tmp_path / "p" / "bin" / "maker-rebuild"), "--version"], capture_output=True, text=True).stdout
    assert out.startswith("maker-rebuild ")


def test_windows_installers_static_checks():
    ps1 = (ROOT / "install.ps1").read_bytes()
    assert ps1.startswith(b"\xef\xbb\xbf"), "install.ps1 precisa de BOM UTF-8 (Windows PowerShell 5.1)"
    text = ps1.decode("utf-8-sig")
    for token in ("param(", "[switch]$Uninstall", "[switch]$DryRun", "Get-FileHash", "maker-rebuild-windows-", "SetEnvironmentVariable", "Expand-Archive"):
        assert token in text, token
    assert text.count("{") == text.count("}") and text.count("(") == text.count(")")
    bat = (ROOT / "install.bat").read_bytes()
    assert b"\r\n" in bat and b"install.ps1" in bat and b"-ExecutionPolicy Bypass" in bat
    assert b"\n" not in bat.replace(b"\r\n", b"")                              # CRLF consistente


def test_gitattributes_keeps_sh_lf():
    ga = (ROOT / ".gitattributes").read_text()
    assert "*.sh  text eol=lf" in ga and "*.bat text eol=crlf" in ga
    assert b"\r" not in (ROOT / "install.sh").read_bytes()


def test_build_exe_target_and_command():
    osname, arch = build_exe.target()
    assert osname in ("linux", "macos", "windows") and arch in ("x86_64", "arm64")
    cmd = build_exe.pyinstaller_cmd(Path("out"), Path("work"))
    assert "--onefile" in cmd and cmd.count("--add-data") == 2
    assert any("runtime" in c and os.pathsep in c for c in cmd) and any("prompts" in c for c in cmd)


def test_build_exe_packaging_names(tmp_path):
    exe = tmp_path / "maker-rebuild"
    exe.write_bytes(b"x")
    a = build_exe.package(exe, tmp_path, "linux", "x86_64")
    assert a.name == "maker-rebuild-linux-x86_64.tar.gz"
    digest = (tmp_path / (a.name + ".sha256")).read_text().split()[0]
    assert digest == hashlib.sha256(a.read_bytes()).hexdigest()
    exe2 = tmp_path / "maker-rebuild.exe"
    exe2.write_bytes(b"x")
    assert build_exe.package(exe2, tmp_path, "windows", "x86_64").name == "maker-rebuild-windows-x86_64.zip"


# ------------------------------------------------------------------ CHANGELOG / versão
def test_changelog_documents_current_version_and_helper_extracts_it():
    import changelog_section
    from maker_rebuild import __version__
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{__version__}]" in text, "atualize o CHANGELOG.md para a versão atual"
    assert "## [Não lançado]" in text
    body = changelog_section.section(f"v{__version__}", text)
    assert body.startswith("### ") and "## [" not in body
    with pytest.raises(SystemExit):
        changelog_section.section("v99.0.0", text)


def test_version_is_consistent_everywhere():
    import re
    from maker_rebuild import __version__
    pyproject = (ROOT / "pyproject.toml").read_text()
    assert re.search(rf'^version = "{re.escape(__version__)}"', pyproject, re.M)
    core = (ROOT / "src/maker_rebuild/runtime/js/mr-core.js").read_text()
    assert f"MR.version = '{__version__}'" in core
