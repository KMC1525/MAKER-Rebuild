#!/usr/bin/env python3
"""Gera o executável autônomo do MAKER-Rebuild (PyInstaller --onefile) e o pacote de release.

    python packaging/build_exe.py                # build + smoke test + pacote em dist-exe/
    python packaging/build_exe.py --no-smoke

Saída: dist-exe/maker-rebuild-<so>-<arch>.(tar.gz|zip) e o .sha256 correspondente.
<so> ∈ {linux, macos, windows}; <arch> ∈ {x86_64, arm64}. É o mesmo nome que os instaladores baixam.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"


def target() -> tuple:
    osname = {"linux": "linux", "darwin": "macos", "win32": "windows"}.get(sys.platform)
    if not osname:
        raise SystemExit(f"plataforma não suportada: {sys.platform}")
    m = platform.machine().lower()
    arch = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}.get(m)
    if not arch:
        raise SystemExit(f"arquitetura não suportada: {m}")
    return osname, arch


def pyinstaller_cmd(out: Path, work: Path) -> list:
    sep = os.pathsep
    pkg = SRC / "maker_rebuild"
    return [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--name", "maker-rebuild",
            "--distpath", str(out), "--workpath", str(work), "--specpath", str(work), "--paths", str(SRC),
            "--collect-submodules", "maker_rebuild",
            "--add-data", f"{pkg / 'runtime'}{sep}maker_rebuild/runtime",
            "--add-data", f"{pkg / 'prompts'}{sep}maker_rebuild/prompts",
            str(ROOT / "packaging" / "entry.py")]


def smoke(exe: Path) -> None:
    """Roda o binário de verdade: versão → demo → recompile → validate (sem rede, sem IA)."""
    def run(*args: str, cwd: Path) -> str:
        r = subprocess.run([str(exe), *args], capture_output=True, text=True, cwd=cwd, timeout=300,
                           env={**os.environ, "NO_COLOR": "1", "MAKER_REBUILD_HOME": str(cwd / "cfg")})
        if r.returncode:
            raise SystemExit(f"smoke test falhou: {' '.join(args)}\n{r.stdout}\n{r.stderr}")
        return r.stdout
    with tempfile.TemporaryDirectory() as td:
        td_p = Path(td)
        print("  →", run("--version", cwd=td_p).strip())
        run("demo", "d", cwd=td_p)
        run("recompile", "d", "-o", "out", "-y", cwd=td_p)
        z = td_p / "out" / "demo-quest.zip"
        if not z.exists():
            raise SystemExit("smoke test: .zip não foi gerado")
        run("validate", "out/demo-quest", cwd=td_p)
        run("expand", "out/demo-quest.zip", "poção", "--provider", "mock", "-o", "out2", "-y", cwd=td_p)
        print("  → demo/recompile/validate/expand(mock) OK")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def package(exe: Path, out: Path, osname: str, arch: str) -> Path:
    base = f"maker-rebuild-{osname}-{arch}"
    extras = [p for p in (ROOT / "LICENSE", ROOT / "README.md", ROOT / "CHANGELOG.md") if p.exists()]
    if osname == "windows":
        archive = out / f"{base}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(exe, exe.name)
            for p in extras:
                z.write(p, p.name)
    else:
        archive = out / f"{base}.tar.gz"
        with tarfile.open(archive, "w:gz") as t:
            t.add(exe, arcname=exe.name)        # preserva o bit de execução
            for p in extras:
                t.add(p, arcname=p.name)
    (out / f"{archive.name}.sha256").write_text(f"{sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return archive


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "dist-exe"))
    ap.add_argument("--no-smoke", action="store_true", help="pula o teste do binário gerado")
    args = ap.parse_args()
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        raise SystemExit("PyInstaller não instalado: pip install pyinstaller   (ou: pip install -e '.[exe]')")
    osname, arch = target()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = ROOT / "build-exe"
    print(f"• construindo maker-rebuild para {osname}/{arch}…")
    subprocess.run(pyinstaller_cmd(out, work), check=True, cwd=ROOT)
    exe = out / ("maker-rebuild.exe" if osname == "windows" else "maker-rebuild")
    if not exe.exists():
        raise SystemExit("PyInstaller não gerou o executável")
    if not args.no_smoke:
        print("• smoke test do binário:")
        smoke(exe)
    archive = package(exe, out, osname, arch)
    shutil.rmtree(work, ignore_errors=True)
    print(f"✔ {archive}  ({archive.stat().st_size / 1e6:.1f} MB)\n  sha256: {(out / (archive.name + '.sha256')).read_text().split()[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
