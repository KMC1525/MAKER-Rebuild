"""Modelo de assets e mapeamento para a árvore padrão ``assets/`` do jogo entregue."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Tuple

# categoria canônica → pasta dentro do jogo entregue
TARGET_DIRS = {
    "characters": "assets/sprites/characters",
    "faces": "assets/sprites/faces",
    "enemies": "assets/sprites/enemies",
    "sv_actors": "assets/sprites/sv_actors",
    "sv_enemies": "assets/sprites/sv_enemies",
    "animations": "assets/sprites/animations",
    "tilesets": "assets/background/tilesets",
    "autotiles": "assets/background/autotiles",
    "parallaxes": "assets/background/parallaxes",
    "battlebacks1": "assets/background/battlebacks1",
    "battlebacks2": "assets/background/battlebacks2",
    "titles1": "assets/background/titles1",
    "titles2": "assets/background/titles2",
    "pictures": "assets/ui-ux/pictures",
    "system": "assets/ui-ux/system",
    "fonts": "assets/ui-ux/fonts",
    "bgm": "assets/music/bgm",
    "me": "assets/music/me",
    "bgs": "assets/music/bgs",
    "se": "assets/sfx",
    "movies": "assets/ui-ux/movies",
}

# pasta original (minúscula) → categoria canônica
FOLDER_ALIASES = {
    "battlers": "enemies", "panoramas": "parallaxes", "fogs": "pictures", "windowskins": "system",
    "icons": "system", "gameovers": "titles2", "titles": "titles1", "transitions": "pictures",
    "battleback": "battlebacks1", "battlebacks": "battlebacks1", "balloons": "system",
}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
AUDIO_EXT = {".ogg", ".m4a", ".mp3", ".wav", ".mid", ".midi", ".wma", ".flac", ".aac"}
UNPLAYABLE_AUDIO = {".mid", ".midi", ".wma"}  # navegadores não tocam sem conversão
AUDIO_CATS = {"bgm", "bgs", "me", "se"}


@dataclass
class AssetEntry:
    category: str
    name: str            # sem extensão, pode conter subpastas ("sub/arquivo")
    ext: str             # extensão final (com ponto, minúscula)
    reader: Callable[[], bytes]
    origin: str          # caminho original (para relatórios)
    encrypted: bool = False

    @property
    def rel_target(self) -> str:
        return f"{TARGET_DIRS[self.category]}/{self.name}{self.ext}"


def classify(rel: str, engine_root_img: Tuple[str, ...], engine_root_audio: Tuple[str, ...]
             ) -> Optional[Tuple[str, str, str]]:
    """``img/characters/Actor1.rpgmvp`` → (categoria, "Actor1", ".rpgmvp")."""
    parts = rel.replace("\\", "/").split("/")
    low = [p.lower() for p in parts]
    if len(parts) < 3 or low[0] not in engine_root_img + engine_root_audio:
        return None
    folder = FOLDER_ALIASES.get(low[1], low[1])
    fname = parts[-1]
    dot = fname.rfind(".")
    if dot <= 0:
        return None
    stem, ext = "/".join(parts[2:-1] + [fname[:dot]]), fname[dot:].lower()
    if low[0] in engine_root_audio:
        folder = {"bgm": "bgm", "bgs": "bgs", "me": "me", "se": "se"}.get(low[1])
        if folder is None:
            return None
    elif folder not in TARGET_DIRS:
        return None
    return folder, stem, ext
