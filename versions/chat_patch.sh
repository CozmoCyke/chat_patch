#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_PY="$SCRIPT_DIR/chat_patch_v474_phase7.py"

usage() {
  cat <<'EOF'
Usage:
  chat_patch extract-strings <target>
  chat_patch pseint-patcher <batchfile>
  chat_patch pseint-find "chaine"
  chat_patch pseint-replace "chaine"
  chat_patch lang-find "cle"
  chat_patch lang-upsert <lang> "cle" "valeur"
  chat_patch lang-fix <lang> "cle"
  chat_patch lang-find-broken [lang]
  chat_patch lang-audit [lang]
  chat_patch lang-fix-broken <lang>
  chat_patch lang-check-key "cle-ou-message"
  chat_patch apply
  chat_patch help

Commandes:
  pseint-find        cherche une chaîne dans les fichiers du projet PSeInt
  pseint-replace     prépare une preview de remplacement pour les patterns C++ reconnus
  pseint-upsert     prépare une preview de remplacement pour les patterns C++ reconnus et repare ou ne fais rien si correct
  
  lang-find          cherche une clé dans les fichiers lang/*.txt
  lang-upsert        met à jour ou ajoute une entrée dans un fichier de langue
  lang-fix           fusionne les variantes d'une clé et supprime les doublons
  lang-find-broken   détecte les entrées suspectes (mojibake, placeholders, caractères cassés)
  lang-audit         produit un audit global des fichiers de langue
  lang-fix-broken    supprime ou répare automatiquement les entrées cassées
  lang-check-key     relie le moteur C++ aux fichiers de langue et propose les actions adaptées
  apply              applique la dernière preview préparée
  help               affiche cette aide

Exemples:
  chat_patch extract-strings wxPSeInt/mxMainWindow.cpp
  chat_patch pseint-patcher extract_strings_ALL_EN.txt

  chat_patch pseint-find "Instrucción no válida."
  chat_patch pseint-replace "Instrucción no válida."

  chat_patch lang-find "Instruccion no valida."
  chat_patch lang-upsert en "Instruccion no valida." "Invalid instruction."
  chat_patch lang-fix en "Instruccion no valida."

  chat_patch lang-find-broken
  chat_patch lang-find-broken en
  chat_patch lang-audit
  chat_patch lang-audit en
  chat_patch lang-fix-broken en

  chat_patch lang-check-key "Instrucción no válida."

  chat_patch apply
EOF
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  extract-strings)
    exec "$PYTHON_BIN" "$SCRIPT_PY" extract-strings "$@"
    ;;
  pseint-patcher)
    exec "$PYTHON_BIN" "$SCRIPT_PY" pseint-patcher "$@"
    ;;
  pseint-find)
    exec "$PYTHON_BIN" "$SCRIPT_PY" pseint-find "$@"
    ;;
  pseint-replace)
    exec "$PYTHON_BIN" "$SCRIPT_PY" pseint-replace "$@"
    ;;
  pseint-upsert)
    exec "$PYTHON_BIN" "$SCRIPT_PY" pseint-upsert "$@"
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
  lang-fix-broken)
    exec "$PYTHON_BIN" "$SCRIPT_PY" lang-fix-broken "$@"
    ;;
  lang-check-key)
    exec "$PYTHON_BIN" "$SCRIPT_PY" lang-check-key "$@"
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
