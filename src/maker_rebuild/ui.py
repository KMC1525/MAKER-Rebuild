"""Utilidades de terminal: cores ANSI, spinner, barras de progresso e perguntas."""
from __future__ import annotations

import itertools
import os
import sys
import threading
import time
from typing import Iterable, Optional, Sequence

if os.name == "nt":  # habilita sequências ANSI no console do Windows 10+
    os.system("")

_USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None and os.environ.get("TERM") != "dumb"

CODES = {
    "reset": "0", "bold": "1", "dim": "2", "red": "31", "green": "32", "yellow": "33",
    "blue": "34", "magenta": "35", "cyan": "36", "gray": "90",
}


def set_color(enabled: bool) -> None:
    global _USE_COLOR
    _USE_COLOR = enabled


def c(text: str, *styles: str) -> str:
    if not _USE_COLOR or not styles:
        return text
    seq = ";".join(CODES[s] for s in styles)
    return f"\033[{seq}m{text}\033[0m"


BANNER = r"""
  __  __   _   _  _____ ___     ___      _      _ _    _
 |  \/  | /_\ | |/ / __| _ \___| _ \___ | |__ _(_) |__| |
 | |\/| |/ _ \| ' <| _||   /___|   / -_)| '_ \ | | / _` |
 |_|  |_/_/ \_\_|\_\___|_|_\   |_|_\___||_.__/_|_|_\__,_|
"""


def banner(version: str) -> str:
    return c(BANNER.rstrip("\n"), "cyan", "bold") + "\n" + c(
        f"  RPG Maker 2000 → MZ  ⇒  HTML + CSS + JS   ·   v{version}", "gray")


def info(msg: str) -> None:
    print(f"{c('•', 'cyan')} {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"{c('✔', 'green')} {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"{c('!', 'yellow')} {msg}", file=sys.stderr, flush=True)


def err(msg: str) -> None:
    print(f"{c('✖', 'red')} {msg}", file=sys.stderr, flush=True)


def step(n: int, total: int, msg: str) -> None:
    print(f"{c(f'[{n}/{total}]', 'magenta', 'bold')} {c(msg, 'bold')}", flush=True)


def heading(msg: str) -> None:
    print("\n" + c(msg, "bold", "cyan"))
    print(c("─" * max(8, len(msg)), "gray"))


def kv(rows: Iterable[tuple], indent: int = 2) -> None:
    rows = list(rows)
    if not rows:
        return
    w = max(len(str(k)) for k, _ in rows)
    for k, v in rows:
        print(" " * indent + c(str(k).ljust(w), "gray") + "  " + str(v))


def table(headers: Sequence[str], rows: Sequence[Sequence], indent: int = 2) -> None:
    rows = [[str(x) for x in r] for r in rows]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]
    pad = " " * indent
    print(pad + c("  ".join(h.ljust(w) for h, w in zip(headers, widths)), "bold"))
    for r in rows:
        print(pad + "  ".join(x.ljust(w) for x, w in zip(r, widths)))


class Spinner:
    """Spinner de uma linha, thread-safe; vira no-op quando stdout não é TTY."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, label: str = ""):
        self.label = label
        self.extra = ""
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._tty = sys.stderr.isatty()
        self._t0 = 0.0

    def update(self, extra: str) -> None:
        self.extra = extra

    def _run(self) -> None:
        for fr in itertools.cycle(self.FRAMES):
            if self._stop.is_set():
                break
            el = time.time() - self._t0
            sys.stderr.write(f"\r{c(fr, 'cyan')} {self.label} {c(self.extra, 'gray')} {c(f'{el:0.0f}s', 'gray')}\033[K")
            sys.stderr.flush()
            time.sleep(0.09)

    def __enter__(self) -> "Spinner":
        self._t0 = time.time()
        if self._tty:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join()
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()


def progress(i: int, n: int, label: str = "") -> None:
    if not sys.stderr.isatty():
        return
    width = 28
    done = int(width * i / max(n, 1))
    bar = "█" * done + "░" * (width - done)
    sys.stderr.write(f"\r  {c(bar, 'cyan')} {i}/{n} {label}\033[K")
    if i >= n:
        sys.stderr.write("\r\033[K")
    sys.stderr.flush()


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        ans = input(f"{c('?', 'magenta')} {question}{suffix}: ").strip()
    except EOFError:
        return default
    return ans or default


def confirm(question: str, default: bool = True) -> bool:
    if not is_interactive():
        return default
    d = "S/n" if default else "s/N"
    ans = ask(f"{question} ({d})").lower()
    if not ans:
        return default
    return ans[0] in "sy"
