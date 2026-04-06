#!/usr/bin/env bash
set -euo pipefail

PPP_DIR="${PPP_DIR:-$HOME/src/ppp}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VERSIONS_DIR="$HOME/dev/chat_patch/versions"
BIN_DIR="$HOME/bin"
DEV_LAUNCHER="$HOME/dev/chat_patch/chat_patch.sh"
SCRIPT_PY="chat_patch_v475_phase7.py"

usage() {
  cat <<'EOF'
Usage:
  chat_patch --version
  chat_patch --update_version <472|474|475>

  chat_patch extract-strings <target>
  chat_patch pseint-patcher <batchfile>

  chat_patch pseint-find "chaine"
  chat_patch pseint-replace "chaine"
  chat_patch pseint-upsert <lang> "cle" "valeur"

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
  --version          affiche la version Python actuellement ciblée
  --update_version   change la version active dans le launcher, le recopie dans ~/bin/chat_patch
                     et copie aussi le bon fichier .py dans ~/bin

  extract-strings    extrait les chaînes candidates espagnoles d'un fichier source
  pseint-patcher     applique interactivement un batch enrichi de patchs de localisation

  pseint-find        cherche une chaîne dans les fichiers du projet PSeInt
  pseint-replace     prépare une preview de remplacement pour les patterns C++ reconnus
  pseint-upsert      prépare une preview de remplacement pour les patterns C++ reconnus et repare ou ne fais rien si correct

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
  chat_patch --version
  chat_patch --update_version 472
  chat_patch --update_version 474

  chat_patch extract-strings wxPSeInt/mxMainWindow.cpp
  chat_patch pseint-patcher extract_strings_ALL_EN.txt

  chat_patch pseint-find "Instrucción no válida."
  chat_patch pseint-replace "Instrucción no válida."
  chat_patch pseint-upsert en "Instrucción no válida." "Invalid instruction."

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

extract_version() {
  local file="$1"
  if [[ "$file" =~ chat_patch_v([0-9]+)_phase([0-9]+)\.py ]]; then
    echo "v${BASH_REMATCH[1]} phase ${BASH_REMATCH[2]}"
  else
    echo "unknown"
  fi
}

show_version() {
  echo "SCRIPT_DIR   : $SCRIPT_DIR"
  echo "VERSIONS_DIR : $VERSIONS_DIR"
  echo "BIN_DIR      : $BIN_DIR"
  echo "PPP_DIR      : $PPP_DIR"
  echo "SCRIPT_PY    : $SCRIPT_PY"
  echo "Resolved     : $(extract_version "$SCRIPT_PY")"
  echo "Archive file : $VERSIONS_DIR/$SCRIPT_PY"
  echo "Active file  : $BIN_DIR/$SCRIPT_PY"
}

update_version() {
  local requested="${1:-}"
  local new_py=""

  case "$requested" in
    472) new_py="chat_patch_v472_phase7.py" ;;
    474) new_py="chat_patch_v474_phase7.py" ;;
	475) new_py="chat_patch_v475_phase7.py" ;;
    *)
      echo "ERROR: version non supportée: $requested" >&2
      echo "Versions supportées: 472, 474 ou 475" >&2
      exit 1
      ;;
  esac

  local target_py="$VERSIONS_DIR/$new_py"
  if [[ ! -f "$target_py" ]]; then
    echo "ERROR: fichier archive introuvable: $target_py" >&2
    exit 1
  fi

  if [[ ! -f "$DEV_LAUNCHER" ]]; then
    echo "ERROR: launcher source introuvable: $DEV_LAUNCHER" >&2
    exit 1
  fi

  python3 - "$DEV_LAUNCHER" "$new_py" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1]).resolve()
new_py = sys.argv[2]
text = path.read_text(encoding="utf-8")

pattern = r'^SCRIPT_PY="[^"]+"$'
replacement = f'SCRIPT_PY="{new_py}"'

new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
if count != 1:
    print("ERROR: impossible de trouver la ligne SCRIPT_PY= dans le launcher", file=sys.stderr)
    sys.exit(1)

path.write_text(new_text, encoding="utf-8")
PY

  mkdir -p "$BIN_DIR"
  cp "$DEV_LAUNCHER" "$BIN_DIR/chat_patch"
  chmod +x "$BIN_DIR/chat_patch"
  cp "$target_py" "$BIN_DIR/"

  echo "OK: version active -> $new_py"
  echo "OK: launcher installé -> $BIN_DIR/chat_patch"
  echo "OK: fichier Python copié -> $BIN_DIR/$new_py"
}

run_python() {
  local target_py="$BIN_DIR/$SCRIPT_PY"
  if [[ ! -f "$target_py" ]]; then
    echo "ERROR: fichier Python introuvable: $target_py" >&2
    echo "Astuce: lance 'chat_patch --update_version 472' ou 'chat_patch --update_version 474' ou 'chat_patch --update_version 475' " >&2
    exit 1
  fi

  if [[ ! -d "$PPP_DIR" ]]; then
    echo "ERROR: répertoire projet introuvable: $PPP_DIR" >&2
    exit 1
  fi

  cd "$PPP_DIR"
  exec "$PYTHON_BIN" "$target_py" "$@"
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  --version)
    show_version
    ;;
  --update_version)
    update_version "${1:-}"
    ;;
  extract-strings)
    run_python extract-strings "$@"
    ;;
  pseint-patcher)
    run_python pseint-patcher "$@"
    ;;
  pseint-find)
    run_python pseint-find "$@"
    ;;
  pseint-replace)
    run_python pseint-replace "$@"
    ;;
  pseint-upsert)
    run_python pseint-upsert "$@"
    ;;
  lang-find)
    run_python lang-find "$@"
    ;;
  lang-upsert)
    run_python lang-upsert "$@"
    ;;
  lang-fix)
    run_python lang-fix "$@"
    ;;
  lang-find-broken)
    run_python lang-find-broken "$@"
    ;;
  lang-audit)
    run_python lang-audit "$@"
    ;;
  lang-fix-broken)
    run_python lang-fix-broken "$@"
    ;;
  lang-check-key)
    run_python lang-check-key "$@"
    ;;
  apply)
    run_python apply "$@"
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