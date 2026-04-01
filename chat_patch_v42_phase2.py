#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import json
import difflib
import shutil
from pathlib import Path
from datetime import datetime

APP_DIR = Path(".chat_patch")
PREVIEW_DIR = APP_DIR / "preview"
BACKUP_DIR = APP_DIR / "backup"
SESSION_FILE = APP_DIR / "session.json"


def read_text_auto(path: Path):
    raw = path.read_bytes()

    for enc in ("utf-8", "iso-8859-1", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass

    return raw.decode("utf-8", errors="replace"), "utf-8"


def read_text_latin1(path: Path) -> str:
    text, _enc = read_text_auto(path)
    return text


def write_text_auto(path: Path, text: str, enc: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding=enc, errors="replace", newline="\n")


def write_text_latin1(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="latin-1", errors="replace")


def ensure_dirs() -> None:
    APP_DIR.mkdir(exist_ok=True)
    PREVIEW_DIR.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)


def escape_cpp_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', r"\"")


def normalize_aggressive(s: str) -> str:
    repairs = {
        "Ã¡": "a", "Ã©": "e", "Ã­": "i", "Ã³": "o", "Ãº": "u",
        "Ã": "A", "Ã": "E", "Ã": "I", "Ã": "O", "Ã": "U",
        "Ã±": "n", "Ã": "N",
        "Ã¼": "u", "Ã": "U",
        "Ã§": "c", "Ã‡": "C",
        "â": "'",
        "â": '"',
        "â": '"',
        "â": "-",
        "â": "-",
        "Â¿": "",
        "Â¡": "",
        "Â": "",
        "�": "",
    }
    for a, b in repairs.items():
        s = s.replace(a, b)

    trans = str.maketrans({
        'á': 'a', 'à': 'a', 'â': 'a', 'ä': 'a', 'ã': 'a', 'å': 'a',
        'Á': 'A', 'À': 'A', 'Â': 'A', 'Ä': 'A', 'Ã': 'A', 'Å': 'A',
        'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
        'É': 'E', 'È': 'E', 'Ê': 'E', 'Ë': 'E',
        'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
        'Í': 'I', 'Ì': 'I', 'Î': 'I', 'Ï': 'I',
        'ó': 'o', 'ò': 'o', 'ô': 'o', 'ö': 'o', 'õ': 'o',
        'Ó': 'O', 'Ò': 'O', 'Ô': 'O', 'Ö': 'O', 'Õ': 'O',
        'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
        'Ú': 'U', 'Ù': 'U', 'Û': 'U', 'Ü': 'U',
        'ñ': 'n', 'Ñ': 'N',
        'ç': 'c', 'Ç': 'C',
    })
    s = s.translate(trans)
    s = re.sub(r'[^\x20-\x7E]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def iter_cpp_files():
    for p in sorted(Path(".").glob("*.cpp")):
        if p.is_file():
            yield p


def iter_search_files():
    exts = {".cpp", ".h", ".hpp", ".txt", ".ini", ".html", ".htm", ".hlp", ".md"}
    skip_dirs = {
        ".git", ".svn", "__pycache__", "dist", "build", ".idea", ".vscode"
    }

    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue

        if any(part in skip_dirs for part in path.parts):
            continue

        if path.suffix.lower() in exts:
            yield path


def usage() -> None:
    print("Usage:")
    print('  chat_patch find "chaine"')
    print('  chat_patch replace "chaine"')
    print("  chat_patch apply")


def line_matches_target(line: str, target_raw: str, target_norm: str) -> bool:
    return (target_raw in line) or (target_norm in normalize_aggressive(line))


def detect_category_for_line(line: str):
    if 'LocalizationManager::Instance().Translate(' in line:
        return None

    m = re.search(r'err_handler\.SyntaxError\s*\(\s*[^,\n]+,\s*"([^"]+)"\s*\)', line)
    if m:
        return ("Catégorie 1", m.group(1))

    m = re.search(r'err_handler\.(ExecutionError|CompileTimeWarning|Warning)\s*\(\s*[^,\n]+,\s*"([^"]+)"\s*\)', line)
    if m:
        return ("Catégorie 2", m.group(2))

    m = re.search(r'MkErrorMsg\s*\(\s*"([^"]+)"\s*,', line)
    if m:
        return ("Catégorie 3", m.group(1))

    return None


def patch_line(line: str, target_raw: str, target_norm: str):
    def same(s: str) -> bool:
        return s == target_raw or normalize_aggressive(s) == target_norm

    m = re.search(r'(err_handler\.SyntaxError\s*\(\s*[^,\n]+,\s*)"([^"]*)(")', line)
    if m and same(m.group(2)) and 'LocalizationManager::Instance().Translate(' not in line:
        key = normalize_aggressive(m.group(2))
        new_line = (
            line[:m.start()]
            + m.group(1)
            + f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")'
            + line[m.end(3):]
        )
        return ("Catégorie 1", key, new_line)

    m = re.search(r'((?:err_handler\.(?:ExecutionError|CompileTimeWarning|Warning)\s*\(\s*[^,\n]+,\s*))"([^"]*)(")', line)
    if m and same(m.group(2)) and 'LocalizationManager::Instance().Translate(' not in line:
        key = normalize_aggressive(m.group(2))
        new_line = (
            line[:m.start()]
            + m.group(1)
            + f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")'
            + line[m.end(3):]
        )
        return ("Catégorie 2", key, new_line)

    m = re.search(r'(MkErrorMsg\s*\(\s*)"([^"]*)(")', line)
    if m and same(m.group(2)) and 'LocalizationManager::Instance().Translate(' not in line:
        key = normalize_aggressive(m.group(2))
        new_line = (
            line[:m.start()]
            + m.group(1)
            + f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")'
            + line[m.end(3):]
        )
        return ("Catégorie 3", key, new_line)

    return None


def save_session(data: dict) -> None:
    ensure_dirs()
    SESSION_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_session() -> dict:
    if not SESSION_FILE.exists():
        print("Aucune session en attente.")
        sys.exit(1)
    return json.loads(SESSION_FILE.read_text(encoding="utf-8"))


def clear_preview_dir() -> None:
    if PREVIEW_DIR.exists():
        shutil.rmtree(PREVIEW_DIR)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def cmd_find(query: str) -> int:
    norm = normalize_aggressive(query)
    found = False

    print(f"Chaîne demandée : {query}")
    print(f"Clé normalisée  : {norm}")
    print()

    for file in iter_search_files():
        text, _enc = read_text_auto(file)
        hits = []
        for lineno, line in enumerate(text.splitlines(), 1):
            if line_matches_target(line, query, norm):
                cat = detect_category_for_line(line) if file.suffix.lower() in {".cpp", ".h", ".hpp"} else None
                hits.append((lineno, line, cat))

        if hits:
            found = True
            print(f"=== {file} ===")
            for lineno, line, cat in hits[:30]:
                if cat:
                    print(f"[{cat[0]}] ligne {lineno}")
                else:
                    print(f"[texte brut] ligne {lineno}")
                print(f"  {line}")
            if len(hits) > 30:
                print(f"... {len(hits)-30} autre(s) occurrence(s)")
            print()

    if not found:
        print("Aucun fichier texte pertinent ne contient cette chaîne.")
        return 2

    return 0


def cmd_replace(query: str) -> int:
    ensure_dirs()
    clear_preview_dir()

    norm = normalize_aggressive(query)
    patches = []

    for file in iter_search_files():
        old_text, enc = read_text_auto(file)
        lines = old_text.splitlines()
        new_lines = lines[:]
        local_hits = []

        for i, line in enumerate(lines):
            patched = patch_line(line, query, norm)
            if patched:
                category, key, new_line = patched
                local_hits.append({
                    "line": i + 1,
                    "category": category,
                    "old": line,
                    "new": new_line,
                    "key": key,
                })
                new_lines[i] = new_line

        if local_hits:
            new_text = "\n".join(new_lines)
            if old_text.endswith("\n"):
                new_text += "\n"

            rel_file = file
            preview_path = PREVIEW_DIR / rel_file
            write_text_auto(preview_path, new_text, enc)

            patches.append({
                "file": str(rel_file),
                "preview": str(preview_path),
                "encoding": enc,
                "hits": local_hits,
                "old_text": old_text,
                "new_text": new_text,
            })

    if not patches:
        print("Aucune occurrence patchable reconnue pour cette chaîne.")
        return 2

    total_occ = sum(len(p["hits"]) for p in patches)

    print(f"Chaîne demandée : {query}")
    print(f"Clé normalisée  : {norm}")
    print(f"Fichiers touchés: {len(patches)}")
    print(f"Occurrences     : {total_occ}")
    print()

    for patch in patches:
        print(f"=== {patch['file']} ===")
        cats = sorted(set(h["category"] for h in patch["hits"]))
        print(f"Catégorie(s) trouvée(s) : {', '.join(cats)}")
        for h in patch["hits"][:10]:
            print(f"[{h['category']}] ligne {h['line']}")
            print(f"  - {h['old']}")
            print(f"  + {h['new']}")
            print(f"  clé: {h['key']}")
            print()

        diff = difflib.unified_diff(
            patch["old_text"].splitlines(),
            patch["new_text"].splitlines(),
            fromfile=patch["file"],
            tofile=patch["file"] + " (preview)",
            lineterm=""
        )
        for line in diff:
            print(line)
        print()

    session = {
        "created_at": datetime.now().isoformat(),
        "mode": "replace",
        "query": query,
        "normalized_key": norm,
        "pending_apply": True,
        "files": [
            {
                "file": p["file"],
                "preview": p["preview"],
                "encoding": p["encoding"],
                "hits": p["hits"],
            }
            for p in patches
        ],
    }
    save_session(session)

    print(f"[PREVIEW PRÊTE] {PREVIEW_DIR}")
    print("Utilise maintenant : chat_patch apply")
    return 0


def cmd_apply() -> int:
    session = load_session()

    if not session.get("pending_apply"):
        print("Aucune preview en attente.")
        return 1

    files = session.get("files", [])
    if not files:
        print("Session vide.")
        return 1

    print("Fichiers à appliquer :")
    for entry in files:
        print(f" - {entry['file']} ({len(entry.get('hits', []))} occurrence(s))")
    print()

    ans = input("Voulez-vous appliquer le patch ? [y/N] ").strip().lower()
    if ans not in ("y", "yes", "o", "oui"):
        print("[ANNULÉ]")
        return 0

    ensure_dirs()

    for entry in files:
        target = Path(entry["file"])
        preview = Path(entry["preview"])
        enc = entry.get("encoding", "utf-8")

        if not preview.exists():
            print(f"Preview introuvable : {preview}")
            return 1

        if target.exists():
            backup_target = BACKUP_DIR / target
            old_text, old_enc = read_text_auto(target)
            write_text_auto(backup_target, old_text, old_enc)

        preview_text, preview_enc = read_text_auto(preview)
        write_text_auto(target, preview_text, preview_enc or enc)

    session["pending_apply"] = False
    save_session(session)

    print("[PATCH APPLIQUÉ]")
    print(f"[BACKUP] {BACKUP_DIR}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        usage()
        return 1

    cmd = sys.argv[1]

    if cmd == "find":
        if len(sys.argv) < 3:
            usage()
            return 1
        query = " ".join(sys.argv[2:])
        return cmd_find(query)

    if cmd == "replace":
        if len(sys.argv) < 3:
            usage()
            return 1
        query = " ".join(sys.argv[2:])
        return cmd_replace(query)

    if cmd == "apply":
        return cmd_apply()

    usage()
    return 1


if __name__ == "__main__":
    sys.exit(main())