#!/bin/sh
# MAKER-Rebuild — instalador para Linux e macOS (POSIX sh).
#
#   curl -fsSL https://raw.githubusercontent.com/KMC1525/MAKER-Rebuild/main/install.sh | sh
#   sh install.sh [opções]
#
# Modos:
#   auto   (padrão) tenta o executável pronto da última release; se não houver, instala via Python
#   exe    baixa o executável autônomo (não precisa de Python)
#   python cria um ambiente virtual isolado e instala o pacote (precisa de Python 3.9+)
#
# Opções:
#   --exe | --python        força o modo
#   --prefix DIR            raiz da instalação (padrão: $HOME/.local) → binário em DIR/bin
#   --version X.Y.Z         versão da release (padrão: latest)
#   --ref REF               branch/tag para o modo python quando não há checkout local (padrão: main)
#   --from-local            instala a partir da pasta deste script (checkout do repositório)
#   --uninstall             remove o que este instalador criou
#   --dry-run               só mostra o que faria
#   -h, --help
set -eu

REPO="${MAKER_REBUILD_REPO:-KMC1525/MAKER-Rebuild}"
MODE="${MAKER_REBUILD_MODE:-auto}"
PREFIX="${MAKER_REBUILD_PREFIX:-$HOME/.local}"
VERSION="${MAKER_REBUILD_VERSION:-latest}"
REF="${MAKER_REBUILD_REF:-main}"
FROM_LOCAL=0
UNINSTALL=0
DRY=0

say()  { printf '\033[36m•\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✔\033[0m %s\n' "$*"; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✖\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY" = 1 ]; then printf '  [dry-run] %s\n' "$*"; else "$@"; fi; }

usage() { sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'; exit 0; }

while [ $# -gt 0 ]; do
  case "$1" in
    --exe) MODE=exe ;;
    --python) MODE=python ;;
    --prefix) [ $# -ge 2 ] || die "--prefix exige um valor"; PREFIX="$2"; shift ;;
    --version) [ $# -ge 2 ] || die "--version exige um valor"; VERSION="$2"; shift ;;
    --ref) [ $# -ge 2 ] || die "--ref exige um valor"; REF="$2"; shift ;;
    --from-local) FROM_LOCAL=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --dry-run) DRY=1 ;;
    -h|--help) usage ;;
    *) die "opção desconhecida: $1 (veja --help)" ;;
  esac
  shift
done

case "$MODE" in auto|exe|python) ;; *) die "modo inválido: $MODE" ;; esac

BIN_DIR="$PREFIX/bin"
DATA_DIR="${MAKER_REBUILD_DATA:-$HOME/.local/share/maker-rebuild}"
TARGET="$BIN_DIR/maker-rebuild"

# ------------------------------------------------------------------ desinstalar
if [ "$UNINSTALL" = 1 ]; then
  say "removendo $TARGET e $DATA_DIR"
  run rm -f "$TARGET"
  run rm -rf "$DATA_DIR"
  ok "MAKER-Rebuild removido (a configuração em ~/.config/maker-rebuild e o cache em ~/.cache/maker-rebuild foram mantidos)"
  exit 0
fi

# ------------------------------------------------------------------ plataforma
OS_RAW="$(uname -s)"
case "$OS_RAW" in
  Linux)  OS=linux ;;
  Darwin) OS=macos ;;
  *) die "sistema não suportado por este script: $OS_RAW (no Windows use install.ps1 / install.bat)" ;;
esac
ARCH_RAW="$(uname -m)"
case "$ARCH_RAW" in
  x86_64|amd64) ARCH=x86_64 ;;
  arm64|aarch64) ARCH=arm64 ;;
  *) ARCH="" ;;
esac

have() { command -v "$1" >/dev/null 2>&1; }

fetch() { # fetch URL DEST
  if have curl; then curl -fsSL "$1" -o "$2"
  elif have wget; then wget -q "$1" -O "$2"
  else die "preciso de curl ou wget para baixar arquivos"; fi
}

exists() { # exists URL → 0 se o arquivo existe (HEAD)
  if have curl; then curl -fsSLI "$1" >/dev/null 2>&1
  elif have wget; then wget -q --spider "$1" 2>/dev/null
  else return 1; fi
}

sha_of() {
  if have sha256sum; then sha256sum "$1" | cut -d' ' -f1
  elif have shasum; then shasum -a 256 "$1" | cut -d' ' -f1
  else echo ""; fi
}

release_url() { # release_url ARQUIVO   (MAKER_REBUILD_BASE_URL permite usar um espelho/servidor interno)
  if [ -n "${MAKER_REBUILD_BASE_URL:-}" ]; then echo "$MAKER_REBUILD_BASE_URL/$1"
  elif [ "$VERSION" = latest ]; then echo "https://github.com/$REPO/releases/latest/download/$1"
  else echo "https://github.com/$REPO/releases/download/v${VERSION#v}/$1"; fi
}

# ------------------------------------------------------------------ modo exe
install_exe() {
  [ -n "$ARCH" ] || { warn "arquitetura sem executável pronto: $ARCH_RAW"; return 1; }
  asset="maker-rebuild-$OS-$ARCH.tar.gz"
  url="$(release_url "$asset")"
  say "procurando executável: $asset"
  if [ "$DRY" = 1 ]; then printf '  [dry-run] baixar %s e instalar em %s\n' "$url" "$TARGET"; return 0; fi
  exists "$url" || { warn "nenhuma release com $asset"; return 1; }
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  fetch "$url" "$tmp/$asset" || return 1
  if fetch "$url.sha256" "$tmp/$asset.sha256" 2>/dev/null; then
    want="$(cut -d' ' -f1 < "$tmp/$asset.sha256")"; got="$(sha_of "$tmp/$asset")"
    if [ -n "$got" ] && [ "$want" != "$got" ]; then die "checksum SHA-256 não confere (esperado $want, obtido $got)"; fi
    [ -n "$got" ] && ok "checksum SHA-256 verificado"
  else
    warn "sem arquivo .sha256 na release — checksum não verificado"
  fi
  tar -xzf "$tmp/$asset" -C "$tmp" maker-rebuild
  mkdir -p "$BIN_DIR"
  install -m 755 "$tmp/maker-rebuild" "$TARGET"
  if [ "$OS" = macos ] && have xattr; then xattr -d com.apple.quarantine "$TARGET" 2>/dev/null || true; fi
  ok "executável instalado em $TARGET"
}

# ------------------------------------------------------------------ modo python
find_python() {
  for c in python3 python; do
    if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then echo "$c"; return 0; fi
  done
  return 1
}

install_python() {
  py="$(find_python)" || die "Python 3.9+ não encontrado. Instale-o (ex.: 'brew install python' no macOS, 'sudo apt install python3 python3-venv' no Debian/Ubuntu) ou use --exe."
  here="$(cd "$(dirname "$0")" 2>/dev/null && pwd || echo .)"
  if [ "$FROM_LOCAL" = 1 ] || { [ -f "$here/pyproject.toml" ] && grep -q 'name = "maker-rebuild"' "$here/pyproject.toml" 2>/dev/null; }; then
    SRC="$here"; say "instalando do checkout local: $SRC"
  else
    SRC="https://github.com/$REPO/archive/$REF.tar.gz"; say "instalando de $SRC"
  fi
  VENV="$DATA_DIR/venv"
  say "criando ambiente virtual em $VENV (Python: $("$py" -c 'import platform;print(platform.python_version())'))"
  if [ "$DRY" = 1 ]; then printf '  [dry-run] %s -m venv %s && pip install %s && ln -sf %s/bin/maker-rebuild %s\n' "$py" "$VENV" "$SRC" "$VENV" "$TARGET"; return 0; fi
  mkdir -p "$DATA_DIR" "$BIN_DIR"
  "$py" -m venv "$VENV" 2>/dev/null || die "não consegui criar o venv (no Debian/Ubuntu: sudo apt install python3-venv)"
  "$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null 2>&1 || true
  "$VENV/bin/python" -m pip install --quiet --upgrade "$SRC" || die "falha no pip install"
  ln -sf "$VENV/bin/maker-rebuild" "$TARGET"
  ok "instalado em $VENV (atalho: $TARGET)"
}

# ------------------------------------------------------------------ execução
say "MAKER-Rebuild · $OS/${ARCH:-$ARCH_RAW} · modo: $MODE · prefixo: $PREFIX"
case "$MODE" in
  exe)    install_exe || die "não foi possível instalar o executável (tente --python)" ;;
  python) install_python ;;
  auto)
    if [ "$FROM_LOCAL" = 1 ]; then install_python
    elif install_exe; then :
    else warn "sem executável pronto; usando o modo Python"; install_python; fi ;;
esac

[ "$DRY" = 1 ] && { ok "dry-run concluído (nada foi alterado)"; exit 0; }

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) warn "$BIN_DIR não está no PATH. Adicione ao seu shell:"
     printf '    echo '"'"'export PATH="%s:$PATH"'"'"' >> ~/.profile   # (ou ~/.zshrc / ~/.bashrc)\n' "$BIN_DIR" ;;
esac
"$TARGET" --version 2>/dev/null && ok "pronto! Experimente:  maker-rebuild demo && maker-rebuild doctor" || warn "instalado, mas '$TARGET --version' falhou"
