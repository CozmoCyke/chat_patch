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

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = Path.cwd()

def find_repo_root() -> Path:
    here = Path.cwd().resolve()
    candidates = [here] + list(here.parents)
    for p in candidates:
        if (p / "lang").is_dir() and (p / "pseint").is_dir():
            return p
    return here

REPO_ROOT = find_repo_root()

LANG_FILES = {
    "en": REPO_ROOT / "lang" / "en.txt",
    "fr": REPO_ROOT / "lang" / "fr.txt",
    "es": REPO_ROOT / "lang" / "es.txt",
}


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
    print('  chat_patch pseint-find "chaine"')
    print('  chat_patch pseint-replace "chaine"')
    print("  chat_patch apply")
    print('  chat_patch lang-find "cle"')
    print('  chat_patch lang-upsert <lang> "cle" "valeur"')
    print('  chat_patch lang-fix <lang> "cle"')
    print('  chat_patch lang-find-broken [lang]')
    print('  chat_patch lang-audit [lang]')


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


def parse_lang_line(line: str):
    if "=" not in line:
        return None
    k, v = line.split("=", 1)
    return k, v


def load_lang_entries(path: Path):
    text, enc = read_text_auto(path)
    lines = text.splitlines()
    entries = []

    for i, line in enumerate(lines, 1):
        parsed = parse_lang_line(line)
        if parsed is None:
            continue
        key, value = parsed
        entries.append({
            "line": i,
            "raw": line,
            "key": key,
            "value": value,
            "norm_key": normalize_aggressive(key),
        })

    return text, enc, lines, entries


def find_lang_hits(query: str):
    norm = normalize_aggressive(query)
    hits = []

    for lang, path in LANG_FILES.items():
        if not path.exists():
            continue

        _text, _enc, _lines, entries = load_lang_entries(path)
        for entry in entries:
            if entry["key"] == query or entry["norm_key"] == norm:
                hits.append({
                    "lang": lang,
                    "file": str(path),
                    "line": entry["line"],
                    "key": entry["key"],
                    "value": entry["value"],
                    "norm_key": entry["norm_key"],
                })

    return hits


def upsert_lang_entry(path: Path, key: str, value: str):
    text, enc, lines, entries = load_lang_entries(path)
    norm = normalize_aggressive(key)

    replaced = False
    new_lines = lines[:]
    touched_line = None
    old_line = None
    new_line = None

    for entry in entries:
        if entry["key"] == key or entry["norm_key"] == norm:
            idx = entry["line"] - 1
            old_line = new_lines[idx]
            new_lines[idx] = f"{key}={value}"
            new_line = new_lines[idx]
            touched_line = entry["line"]
            replaced = True
            break

    if not replaced:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(f"{key}={value}")
        touched_line = len(new_lines)
        old_line = None
        new_line = new_lines[-1]

    new_text = "\n".join(new_lines)
    if text.endswith("\n"):
        new_text += "\n"

    return {
        "encoding": enc,
        "old_text": text,
        "new_text": new_text,
        "line": touched_line,
        "old_line": old_line,
        "new_line": new_line,
    }


def choose_best_lang_value(entries: list[dict]) -> str:
    """
    Heuristique simple :
    - éviter les valeurs vides
    - éviter les valeurs manifestement placeholder (XXXX...)
    - préférer une valeur différente de la clé
    - sinon garder la première
    """
    if not entries:
        return ""

    def score(entry: dict) -> tuple:
        value = entry["value"].strip()
        key = entry["key"].strip()

        is_empty = (value == "")
        is_placeholder = bool(re.fullmatch(r"X+", value))
        same_as_key_norm = normalize_aggressive(value) == normalize_aggressive(key)

        return (
            1 if is_empty else 0,
            1 if is_placeholder else 0,
            1 if same_as_key_norm else 0,
            len(value) == 0,
        )

    best = sorted(entries, key=score)[0]
    return best["value"]


def fix_lang_entries(path: Path, canonical_key: str):
    text, enc, lines, entries = load_lang_entries(path)
    norm = normalize_aggressive(canonical_key)

    matched = [e for e in entries if e["key"] == canonical_key or e["norm_key"] == norm]

    if not matched:
        return {
            "changed": False,
            "reason": "not_found",
            "encoding": enc,
            "old_text": text,
            "new_text": text,
            "removed_lines": [],
            "kept_line": None,
            "new_line": None,
            "matched": [],
        }

    kept_value = choose_best_lang_value(matched)
    new_entry_line = f"{canonical_key}={kept_value}"

    matched_line_numbers = {e["line"] for e in matched}
    removed_lines = []
    new_lines = []
    inserted = False
    kept_line = None

    for i, line in enumerate(lines, 1):
        if i not in matched_line_numbers:
            new_lines.append(line)
            continue

        if not inserted:
            new_lines.append(new_entry_line)
            inserted = True
            kept_line = len(new_lines)
        else:
            removed_lines.append({
                "line": i,
                "raw": line,
            })

    if not inserted:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(new_entry_line)
        kept_line = len(new_lines)

    new_text = "\n".join(new_lines)
    if text.endswith("\n"):
        new_text += "\n"

    changed = (new_text != text)

    return {
        "changed": changed,
        "reason": "ok",
        "encoding": enc,
        "old_text": text,
        "new_text": new_text,
        "removed_lines": removed_lines,
        "kept_line": kept_line,
        "new_line": new_entry_line,
        "matched": matched,
    }


def iter_lang_targets(lang=None):
    if lang is None:
        for code, path in LANG_FILES.items():
            if path.exists():
                yield code, path
        return

    if lang not in LANG_FILES:
        raise ValueError(f"Langue inconnue : {lang}")

    path = LANG_FILES[lang]
    if path.exists():
        yield lang, path


def is_placeholder_value(value: str) -> bool:
    v = value.strip()
    if not v:
        return False
    return bool(
        re.fullmatch(r"[XxYyZz?*!#_= -]{5,}", v)
        or re.fullmatch(r"(TODO|TBD|FIXME|XXX+|YYY+)", v, flags=re.IGNORECASE)
    )


def mojibake_score(text: str) -> int:
    patterns = [
        "Ã", "Â", "â", "ð", "�",
    ]
    score = 0
    for p in patterns:
        score += text.count(p)
    return score


def is_broken_lang_entry(entry: dict):
    reasons = []

    raw = entry["raw"]
    key = entry["key"]
    value = entry["value"]

    if "�" in raw or "�" in key or "�" in value:
        reasons.append("replacement-char")

    if mojibake_score(raw) > 0:
        reasons.append("mojibake")

    if is_placeholder_value(value):
        reasons.append("placeholder-value")

    return (len(reasons) > 0, reasons)


def find_broken_lang_entries(lang=None):
    results = []

    for code, path in iter_lang_targets(lang):
        _text, _enc, _lines, entries = load_lang_entries(path)
        for entry in entries:
            broken, reasons = is_broken_lang_entry(entry)
            if broken:
                results.append({
                    "lang": code,
                    "file": str(path),
                    "line": entry["line"],
                    "key": entry["key"],
                    "value": entry["value"],
                    "raw": entry["raw"],
                    "reasons": reasons,
                    "norm_key": entry["norm_key"],
                })

    return results


def audit_lang_file(path: Path):
    text, enc, lines, entries = load_lang_entries(path)

    exact_duplicates = {}
    norm_collisions = {}
    broken_entries = []

    seen_exact = {}
    seen_norm = {}

    for entry in entries:
        raw_key = entry["key"]
        norm_key = entry["norm_key"]

        seen_exact.setdefault(raw_key, []).append(entry)
        seen_norm.setdefault(norm_key, []).append(entry)

        broken, reasons = is_broken_lang_entry(entry)
        if broken:
            broken_entries.append({
                **entry,
                "reasons": reasons,
            })

    for key, items in seen_exact.items():
        if len(items) > 1:
            exact_duplicates[key] = items

    for key, items in seen_norm.items():
        distinct_raw_keys = {e["key"] for e in items}
        if len(items) > 1 and len(distinct_raw_keys) >= 1:
            norm_collisions[key] = items

    return {
        "encoding": enc,
        "line_count": len(lines),
        "entry_count": len(entries),
        "broken_entries": broken_entries,
        "exact_duplicates": exact_duplicates,
        "norm_collisions": norm_collisions,
    }


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


def cmd_pseint_find(query: str) -> int:
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


def cmd_pseint_replace(query: str) -> int:
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
        "mode": "replace_pseint",
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


def cmd_lang_find(query: str) -> int:
    hits = find_lang_hits(query)

    print(f"Clé demandée : {query}")
    print(f"Clé normalisée: {normalize_aggressive(query)}")
    print()

    if not hits:
        print("Aucune entrée trouvée dans lang/*.txt")
        return 2

    for h in hits:
        print(f"=== {h['file']} ===")
        print(f"[{h['lang']}] ligne {h['line']}")
        print(f"  clé   : {h['key']}")
        print(f"  valeur: {h['value']}")
        print(f"  norm  : {h['norm_key']}")
        print()

    return 0


def cmd_lang_upsert(lang: str, key: str, value: str) -> int:
    ensure_dirs()
    clear_preview_dir()

    if lang not in LANG_FILES:
        print(f"Langue inconnue : {lang}")
        print(f"Langues supportées : {', '.join(sorted(LANG_FILES))}")
        return 1

    target = LANG_FILES[lang]
    if not target.exists():
        print(f"Fichier langue introuvable : {target}")
        return 1

    result = upsert_lang_entry(target, key, value)

    preview_path = PREVIEW_DIR / target
    write_text_auto(preview_path, result["new_text"], result["encoding"])

    diff = list(difflib.unified_diff(
        result["old_text"].splitlines(),
        result["new_text"].splitlines(),
        fromfile=str(target),
        tofile=str(target) + " (preview)",
        lineterm=""
    ))

    print(f"=== {target} ===")
    print(f"ligne touchée : {result['line']}")
    if result["old_line"] is not None:
        print(f"  - {result['old_line']}")
    else:
        print("  - [nouvelle entrée]")
    print(f"  + {result['new_line']}")
    print()

    for line in diff:
        print(line)
    print()

    session = {
        "created_at": datetime.now().isoformat(),
        "mode": "lang-upsert",
        "pending_apply": True,
        "files": [
            {
                "file": str(target),
                "preview": str(preview_path),
                "encoding": result["encoding"],
                "hits": [
                    {
                        "line": result["line"],
                        "category": "Lang upsert",
                        "old": result["old_line"],
                        "new": result["new_line"],
                        "key": key,
                    }
                ],
            }
        ],
    }
    save_session(session)

    print(f"[PREVIEW PRÊTE] {PREVIEW_DIR}")
    print("Utilise maintenant : chat_patch apply")
    return 0


def cmd_lang_fix(lang: str, key: str) -> int:
    ensure_dirs()
    clear_preview_dir()

    if lang not in LANG_FILES:
        print(f"Langue inconnue : {lang}")
        print(f"Langues supportées : {', '.join(sorted(LANG_FILES))}")
        return 1

    target = LANG_FILES[lang]
    if not target.exists():
        print(f"Fichier langue introuvable : {target}")
        return 1

    canonical_key = normalize_aggressive(key)
    result = fix_lang_entries(target, canonical_key)

    if result["reason"] == "not_found":
        print(f"Aucune variante trouvée pour : {key}")
        return 2

    preview_path = PREVIEW_DIR / target
    write_text_auto(preview_path, result["new_text"], result["encoding"])

    diff = list(difflib.unified_diff(
        result["old_text"].splitlines(),
        result["new_text"].splitlines(),
        fromfile=str(target),
        tofile=str(target) + " (preview)",
        lineterm=""
    ))

    print(f"=== {target} ===")
    print(f"clé demandée     : {key}")
    print(f"clé canonique    : {canonical_key}")
    print(f"ligne conservée  : {result['kept_line']}")
    print(f"entrée finale    : {result['new_line']}")
    print()

    print("Variantes détectées :")
    for entry in result["matched"]:
        print(f"  - ligne {entry['line']}: {entry['key']}={entry['value']}")
    print()

    if result["removed_lines"]:
        print("Lignes supprimées :")
        for entry in result["removed_lines"]:
            print(f"  - ligne {entry['line']}: {entry['raw']}")
        print()

    for line in diff:
        print(line)
    print()

    session = {
        "created_at": datetime.now().isoformat(),
        "mode": "lang-fix",
        "pending_apply": True,
        "files": [
            {
                "file": str(target),
                "preview": str(preview_path),
                "encoding": result["encoding"],
                "hits": [
                    {
                        "line": result["kept_line"],
                        "category": "Lang fix",
                        "old": None,
                        "new": result["new_line"],
                        "key": canonical_key,
                    }
                ] + [
                    {
                        "line": entry["line"],
                        "category": "Lang fix removed duplicate",
                        "old": entry["raw"],
                        "new": None,
                        "key": canonical_key,
                    }
                    for entry in result["removed_lines"]
                ],
            }
        ],
    }
    save_session(session)

    print(f"[PREVIEW PRÊTE] {PREVIEW_DIR}")
    print("Utilise maintenant : chat_patch apply")
    return 0


def cmd_lang_find_broken(lang=None) -> int:
    try:
        results = find_broken_lang_entries(lang)
    except ValueError as e:
        print(str(e))
        print(f"Langues supportées : {', '.join(sorted(LANG_FILES))}")
        return 1

    if not results:
        print("Aucune entrée suspecte trouvée dans lang/*.txt")
        return 0

    print("Entrées suspectes détectées :")
    print()

    for r in results:
        print(f"=== {r['file']} ===")
        print(f"[{r['lang']}] ligne {r['line']}")
        print(f"  clé    : {r['key']}")
        print(f"  valeur : {r['value']}")
        print(f"  raisons: {', '.join(r['reasons'])}")
        print()

    print(f"Total: {len(results)} entrée(s) suspecte(s)")
    return 0


def cmd_lang_audit(lang=None) -> int:
    try:
        targets = list(iter_lang_targets(lang))
    except ValueError as e:
        print(str(e))
        print(f"Langues supportées : {', '.join(sorted(LANG_FILES))}")
        return 1

    if not targets:
        print("Aucun fichier de langue trouvé.")
        return 1

    total_broken = 0
    total_exact_dup = 0
    total_norm_collisions = 0

    for code, path in targets:
        report = audit_lang_file(path)

        broken_count = len(report["broken_entries"])
        exact_dup_count = len(report["exact_duplicates"])
        norm_collision_count = len(report["norm_collisions"])

        total_broken += broken_count
        total_exact_dup += exact_dup_count
        total_norm_collisions += norm_collision_count

        print(f"=== {path} ===")
        print(f"langue                : {code}")
        print(f"encodage              : {report['encoding']}")
        print(f"lignes                : {report['line_count']}")
        print(f"entrées               : {report['entry_count']}")
        print(f"entrées suspectes     : {broken_count}")
        print(f"doublons exacts       : {exact_dup_count}")
        print(f"collisions normalisées: {norm_collision_count}")
        print()

        if report["broken_entries"]:
            print("Entrées suspectes :")
            for e in report["broken_entries"][:20]:
                print(f"  - ligne {e['line']}: {e['raw']} [{', '.join(e['reasons'])}]")
            if len(report["broken_entries"]) > 20:
                print(f"  ... {len(report['broken_entries']) - 20} autre(s)")
            print()

        if report["exact_duplicates"]:
            print("Doublons exacts :")
            for key, items in list(report["exact_duplicates"].items())[:20]:
                lines = ", ".join(str(i["line"]) for i in items)
                print(f"  - {key} -> lignes {lines}")
            if len(report["exact_duplicates"]) > 20:
                print(f"  ... {len(report['exact_duplicates']) - 20} autre(s)")
            print()

        if report["norm_collisions"]:
            print("Collisions normalisées :")
            for key, items in list(report["norm_collisions"].items())[:20]:
                desc = "; ".join(f"l.{i['line']} {i['key']}={i['value']}" for i in items[:4])
                print(f"  - {key} -> {desc}")
            if len(report["norm_collisions"]) > 20:
                print(f"  ... {len(report['norm_collisions']) - 20} autre(s)")
            print()

    print("=== RÉSUMÉ GLOBAL ===")
    print(f"Entrées suspectes     : {total_broken}")
    print(f"Doublons exacts       : {total_exact_dup}")
    print(f"Collisions normalisées: {total_norm_collisions}")

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

    if cmd == "pseint-find":
        if len(sys.argv) < 3:
            usage()
            return 1
        query = " ".join(sys.argv[2:])
        return cmd_pseint_find(query)

    if cmd == "pseint-replace":
        if len(sys.argv) < 3:
            usage()
            return 1
        query = " ".join(sys.argv[2:])
        return cmd_pseint_replace(query)

    if cmd == "lang-find":
        if len(sys.argv) < 3:
            usage()
            return 1
        query = " ".join(sys.argv[2:])
        return cmd_lang_find(query)

    if cmd == "lang-upsert":
        if len(sys.argv) < 5:
            usage()
            return 1
        lang = sys.argv[2]
        key = sys.argv[3]
        value = " ".join(sys.argv[4:])
        return cmd_lang_upsert(lang, key, value)

    if cmd == "lang-fix":
        if len(sys.argv) < 4:
            usage()
            return 1
        lang = sys.argv[2]
        key = " ".join(sys.argv[3:])
        return cmd_lang_fix(lang, key)

    if cmd == "lang-find-broken":
        lang = sys.argv[2] if len(sys.argv) >= 3 else None
        return cmd_lang_find_broken(lang)

    if cmd == "lang-audit":
        lang = sys.argv[2] if len(sys.argv) >= 3 else None
        return cmd_lang_audit(lang)

    if cmd == "apply":
        return cmd_apply()

    usage()
    return 1


if __name__ == "__main__":
    sys.exit(main())