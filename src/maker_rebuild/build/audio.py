"""Conversão opcional de áudio (WMA/MIDI → OGG) usando ffmpeg / fluidsynth, se instalados."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional


def convert(data: bytes, ext: str) -> Optional[bytes]:
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / f"in{ext}", Path(td) / "out.ogg"
        src.write_bytes(data)
        try:
            if ext in (".mid", ".midi"):
                sf = os.environ.get("MAKER_REBUILD_SOUNDFONT")
                if shutil.which("fluidsynth") and sf and Path(sf).exists():
                    wav = Path(td) / "out.wav"
                    subprocess.run(["fluidsynth", "-ni", sf, str(src), "-F", str(wav), "-r", "44100"], check=True,
                                   capture_output=True, timeout=120)
                    src = wav
                else:
                    return None
            if not shutil.which("ffmpeg"):
                return None
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:a", "libvorbis", str(dst)],
                           check=True, capture_output=True, timeout=180)
            return dst.read_bytes()
        except (subprocess.SubprocessError, OSError):
            return None
