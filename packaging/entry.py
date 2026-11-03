"""Ponto de entrada usado pelo PyInstaller (o pacote é importado como ``maker_rebuild``)."""
import sys

from maker_rebuild.cli import main

if __name__ == "__main__":
    sys.exit(main())
