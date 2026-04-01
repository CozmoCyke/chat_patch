#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'EOF'
Usage:
  chat_patch dry        [--cwd DIR] [--no-git-check]
  chat_patch apply      [--cwd DIR] [--no-git-check]
  chat_patch git-check  [--cwd DIR]
  chat_patch help

Le patch unified diff est lu depuis stdin.

Exemples:
  chat_patch dry <<'PATCH'
  --- a/SynCheck.cpp
  +++ b/SynCheck.cpp
  @@
  -err_handler.SyntaxError(99,"Instrucción no válida.");
  +err_handler.SyntaxError(99,LocalizationManager::Instance().Translate("Instruccion no valida."));
  PATCH

  chat_patch apply --cwd ~/src/ppp/pseint <<'PATCH'
  ...
  PATCH
EOF
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  dry)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/chat_patch_v3.py" --mode dry "$@"
    ;;
  apply)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/chat_patch_v3.py" --mode apply "$@"
    ;;
  git-check)
    exec "$PYTHON_BIN" "$SCRIPT_DIR/chat_patch_v3.py" --mode git-check "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Commande inconnue: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac