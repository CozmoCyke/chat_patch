#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_PY="$SCRIPT_DIR/chat_patch_v45_phase5.py"

usage() {
  cat <<'EOF'
Usage:
  chat_patch pseint-find "chaine"
  chat_patch pseint-replace "chaine"
  chat_patch lang-find "cle"
  chat_patch lang-upsert <lang> "cle" "valeur"
  chat_patch lang-fix <lang> "cle"
  chat_patch lang-find-broken [lang]
  chat_patch lang-audit [lang]
  chat_patch apply
  chat_patch help

Commandes:
  pseint-find        cherche une chaîne dans les fichiers du projet PSeInt
  pseint-replace     prépare une preview de remplacement pour les patterns C++ reconnus
  lang-find          cherche une clé dans les fichiers lang/*.txt
  lang-upsert        met à jour ou ajoute une entrée dans un fichier de langue
  lang-fix           fusionne les variantes d'une clé et supprime les doublons
  lang-find-broken   détecte les entrées suspectes (mojibake, placeholders, caractères cassés)
  lang-audit         produit un audit global des fichiers de langue
  apply              applique la dernière preview préparée
  help               affiche cette aide

Exemples:
  chat_patch pseint-find "Instrucción no válida."
  chat_patch pseint-replace "Instrucción no válida."

  chat_patch lang-find "Instruccion no valida."
  chat_patch lang-upsert en "Instruccion no valida." "Invalid instruction."
  chat_patch lang-fix en "Instruccion no valida."

  chat_patch lang-find-broken
  chat_patch lang-find-broken en
  chat_patch lang-audit
  chat_patch lang-audit en

  chat_patch apply
EOF
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  pseint-find)
    exec "$PYTHON_BIN" "$SCRIPT_PY" pseint-find "$@"
    ;;
  pseint-replace)
    exec "$PYTHON_BIN" "$SCRIPT_PY" pseint-replace "$@"
    ;;
  lang-find)
    exec "$PYTHON_BIN" "$SCRIPT_PY" lang-find "$@"
    ;;
  lang-upsert)
    exec "$PYTHON_BIN" "$SCRIPT_PY" lang-upsert "$@"
    ;;
  lang-fix)
    exec "$PYTHON_BIN" "$SCRIPT_PY" lang-fix "$@"
    ;;
  lang-find-broken)
    exec "$PYTHON_BIN" "$SCRIPT_PY" lang-find-broken "$@"
    ;;
  lang-audit)
    exec "$PYTHON_BIN" "$SCRIPT_PY" lang-audit "$@"
    ;;
  apply)
    exec "$PYTHON_BIN" "$SCRIPT_PY" apply "$@"
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