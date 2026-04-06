#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import json
import difflib
import shutil
from pathlib import Path
from datetime import datetime


def find_repo_root() -> Path:
    here = Path.cwd().resolve()
    candidates = [here] + list(here.parents)
    for p in candidates:
        if (p / "lang").is_dir() and (p / "pseint").is_dir():
            return p
    return here


REPO_ROOT = find_repo_root()

APP_DIR = REPO_ROOT / ".chat_patch"
PREVIEW_DIR = APP_DIR / "preview"
BACKUP_DIR = APP_DIR / "backup"
SESSION_FILE = APP_DIR / "session.json"

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_REPO_ROOT = Path.cwd()


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
    APP_DIR.mkdir(parents=True, exist_ok=True)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def escape_cpp_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', r"\"")
    
def escape_lang_string(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')    

def normalize_translate_key(s: str) -> str:
    s = s.lower()
    s = strip_accents(s)
    # réduit seulement les espaces internes, pas ceux de bord
    m1 = re.match(r'^\s*', s)
    m2 = re.search(r'\s*$', s)
    lead = m1.group(0) if m1 else ""
    trail = m2.group(0) if m2 else ""
    core = s[len(lead): len(s) - len(trail) if trail else len(s)]
    core = re.sub(r'\s+', ' ', core)
    return lead + core + trail
    
def normalize_aggressive(s: str) -> str:
    repairs = {
        "Ã¡": "a",
        "Ã©": "e",
        "Ã­": "i",
        "Ã³": "o",
        "Ãº": "u",
        "Ã": "A",
        "Ã": "E",
        "Ã": "I",
        "Ã": "O",
        "Ã": "U",
        "Ã±": "n",
        "Ã": "N",
        "Ã¼": "u",
        "Ã": "U",
        "Ã§": "c",
        "Ã‡": "C",
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

    trans = str.maketrans(
        {
            "á": "a",
            "à": "a",
            "â": "a",
            "ä": "a",
            "ã": "a",
            "å": "a",
            "Á": "A",
            "À": "A",
            "Â": "A",
            "Ä": "A",
            "Ã": "A",
            "Å": "A",
            "é": "e",
            "è": "e",
            "ê": "e",
            "ë": "e",
            "É": "E",
            "È": "E",
            "Ê": "E",
            "Ë": "E",
            "í": "i",
            "ì": "i",
            "î": "i",
            "ï": "i",
            "Í": "I",
            "Ì": "I",
            "Î": "I",
            "Ï": "I",
            "ó": "o",
            "ò": "o",
            "ô": "o",
            "ö": "o",
            "õ": "o",
            "Ó": "O",
            "Ò": "O",
            "Ô": "O",
            "Ö": "O",
            "Õ": "O",
            "ú": "u",
            "ù": "u",
            "û": "u",
            "ü": "u",
            "Ú": "U",
            "Ù": "U",
            "Û": "U",
            "Ü": "U",
            "ñ": "n",
            "Ñ": "N",
            "ç": "c",
            "Ç": "C",
        }
    )
    s = s.translate(trans)
    s = re.sub(r"[^\x20-\x7E]", "", s)
    #s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\s+", " ", s).rstrip("\r\n")
    return s


def iter_cpp_files():
    for p in sorted(Path(".").glob("*.cpp")):
        if p.is_file():
            yield p


def iter_search_files():
    exts = {".cpp", ".h", ".hpp", ".txt", ".ini", ".html", ".htm", ".hlp", ".md"}
    skip_dirs = {
        ".git",
        ".svn",
        "__pycache__",
        "dist",
        "build",
        ".idea",
        ".vscode",
        ".chat_patch",
    }

    for path in REPO_ROOT.rglob("*"):
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
    print('  chat_patch pseint-upsert "chaine"')

    print("  chat_patch apply")
    print('  chat_patch lang-find "cle"')
    print('  chat_patch lang-upsert <lang> "cle" "valeur"')
    print('  chat_patch lang-fix <lang> "cle"')
    print("  chat_patch lang-find-broken [lang]")
    print("  chat_patch lang-audit [lang]")
    print("  chat_patch lang-fix-broken <lang>")
    print('  chat_patch lang-check-key "cle-ou-message"')


def line_matches_target(line: str, target_raw: str, target_norm: str) -> bool:
    return (target_raw in line) or (target_norm in normalize_aggressive(line))


def detect_category_for_line(line: str):
    m = re.search(r'err_handler\.SyntaxError\s*\(\s*[^,\n]+,\s*"([^"]+)"\s*\)', line)
    if m:
        return ("Catégorie 1", m.group(1))

    m = re.search(
        r'err_handler\.(ExecutionError|CompileTimeWarning|Warning)\s*\(\s*[^,\n]+,\s*"([^"]+)"\s*\)',
        line,
    )
    if m:
        return ("Catégorie 2", m.group(2))

    m = re.search(r'MkErrorMsg\s*\(\s*"([^"]+)"\s*,', line)
    if m:
        return ("Catégorie 3", m.group(1))

    m = re.search(r'show_user_info\s*\(\s*"([^"]+)"\s*\)', line)
    if m:
        return ("Catégorie 4", m.group(1))

    # Catégorie 5 : concaténation avec <<
    if "<<" in line and ('"' in line or "LocalizationManager::Instance().Translate(" in line):
        return ("Catégorie 5", None)

    # Catégorie 5 bis : show_user_info multi-arguments
    # Version simple et robuste, même si les arguments contiennent Translate(...)
    if "show_user_info(" in line and line.count(",") >= 2:
        return ("Catégorie 5", None)

    return None

def make_translate_expr(key: str, spacebefore: bool = False, spaceafter: bool = False) -> str:
    expr = f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")'
    if spacebefore:
        expr = '" " + ' + expr
    if spaceafter:
        expr = expr + ' + " "'
    return expr
    
def strip_edge_spaces_with_flags(s: str):
    has_before = s.startswith(" ")
    has_after = s.endswith(" ")
    core = s
    if has_before:
        core = core[1:]
    if has_after and core:
        core = core[:-1]
    return core, has_before, has_after    

#def patch_line(line: str, target_raw: str, target_norm: str):
def patch_line(
    line: str,
    target_raw: str,
    target_norm: str,
    spacebefore: bool = False,
    spaceafter: bool = False,
    ):   
    def same(s: str) -> bool:
        return s == target_raw or normalize_aggressive(s) == target_norm

    def canon_translate_replacement(prefix: str, raw_key: str, suffix: str):
        key = normalize_aggressive(raw_key)
        new_line = (
            prefix
            + f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")'
            + suffix
        )
        return key, new_line

    # Catégorie 1b : err_handler.SyntaxError(..., Translate("clé non canonique"))

    m = re.search(
        r'(err_handler\.SyntaxError\s*\(\s*[^,\n]+,\s*LocalizationManager::Instance\(\)\.Translate\(")([^"]*)("\)\s*\))',
        line,
    )
    if m and normalize_aggressive(m.group(2)) == target_norm:
        key = normalize_aggressive(m.group(2))
        if m.group(2) != key:
            new_line = (
                line[: m.start()]
                + m.group(1)
                + escape_cpp_string(key)
                + m.group(3)
                + line[m.end() :]
            )
            return ("Catégorie 1B", key, new_line)

    m = re.search(
        r'(err_handler\.SyntaxError\s*\(\s*[^,\n]+,\s*LocalizationManager::Instance\(\)\.Translate\(")([^"]*)(")',
        line,
    )
    if m:
        raw_key = m.group(2)
        norm_key = normalize_aggressive(raw_key)
        if norm_key == target_norm and raw_key != norm_key:
            new_line = (
                line[: m.start()]
                + m.group(1)
                + escape_cpp_string(norm_key)
                + line[m.end(2) :]
            )
            return ("Catégorie 1A", norm_key, new_line)

    # Catégorie 2a : brut -> Translate(clef canonique)
    m = re.search(
        r'((?:err_handler\.(?:ExecutionError|CompileTimeWarning|Warning)\s*\(\s*[^,\n]+,\s*))"([^"]*)(")',
        line,
    )
    if (
        m
        and same(m.group(2))
        and "LocalizationManager::Instance().Translate(" not in line
    ):
        key, new_line = canon_translate_replacement(
            line[: m.start()] + m.group(1), m.group(2), line[m.end(3) :]
        )
        return ("Catégorie 2A", key, new_line)

    # Catégorie 2b : Translate(clef non canonique) -> Translate(clef canonique)
    m = re.search(
        r'((?:err_handler\.(?:ExecutionError|CompileTimeWarning|Warning)\s*\(\s*[^,\n]+,\s*LocalizationManager::Instance\(\)\.Translate\("))([^"]*)("\)\s*\))',
        line,
    )
    if m and normalize_aggressive(m.group(2)) == target_norm:
        key = normalize_aggressive(m.group(2))
        if m.group(2) != key:
            new_line = (
                line[: m.start()]
                + m.group(1)
                + escape_cpp_string(key)
                + m.group(3)
                + line[m.end() :]
            )
            return ("Catégorie 2B", key, new_line)

    # Catégorie 3a : MkErrorMsg("...", ...) -> MkErrorMsg(Translate("clef"), ...)
    m = re.search(r'(MkErrorMsg\s*\(\s*)"([^"]*)(")', line)
    if (
        m
        and same(m.group(2))
        and "LocalizationManager::Instance().Translate(" not in line
    ):
        key, new_line = canon_translate_replacement(
            line[: m.start()] + m.group(1), m.group(2), line[m.end(3) :]
        )
        return ("Catégorie 3A", key, new_line)

    # Catégorie 3b : MkErrorMsg(Translate("clé non canonique"), ...)
    m = re.search(
        r'(MkErrorMsg\s*\(\s*LocalizationManager::Instance\(\)\.Translate\(")([^"]*)("\)\s*,)',
        line,
    )
    if m and normalize_aggressive(m.group(2)) == target_norm:
        key = normalize_aggressive(m.group(2))
        if m.group(2) != key:
            new_line = (
                line[: m.start()]
                + m.group(1)
                + escape_cpp_string(key)
                + m.group(3)
                + line[m.end() :]
            )
            return ("Catégorie 3B", key, new_line)

    # Catégorie 4a : show_user_info("...") -> show_user_info(Translate("clef"))
    m = re.search(r'(show_user_info\s*\(\s*)"([^"]*)("\s*\))', line)
    if (
        m
        and same(m.group(2))
        and "LocalizationManager::Instance().Translate(" not in line
    ):
        key = normalize_aggressive(m.group(2))
        new_line = (
            line[: m.start()]
            + m.group(1)
            + f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")'
            + line[m.end(2) + 1 :]
        )
        return ("Catégorie 4A", key, new_line)

    # Catégorie 4b : show_user_info(Translate("clef non canonique")) -> clef canonique
    m = re.search(
        r'(show_user_info\s*\(\s*LocalizationManager::Instance\(\)\.Translate\(")([^"]*)(")',
        line,
    )
    if m:
        raw_key = m.group(2)
        norm_key = normalize_aggressive(raw_key)
        if norm_key == target_norm and raw_key != norm_key:
            new_line = (
                line[: m.start()]
                + m.group(1)
                + escape_cpp_string(norm_key)
                + line[m.end(2) :]
            )
            return ("Catégorie 4B", norm_key, new_line)
            
    # Catégorie 5 : lignes avec plusieurs morceaux texte + variables
    # Exemples:
    #   ExeInfo<<"*** Se encontraron "<<errores<<" errores. ***";
    #   show_user_info("*** Se encontraron ",errores," errores. ***");
    #
    # On remplace uniquement le littéral ciblé par Translate("clé canonique"),
    # sans toucher aux variables ni au reste de la ligne.
    for m in re.finditer(r'"([^"]*)"', line):
        raw_piece = m.group(1)
        if same(raw_piece):
            prefix = line[: m.start()]
            if re.search(r'LocalizationManager::Instance\(\)\.Translate\(\s*$', prefix):
                continue

            key, auto_before, auto_after = strip_edge_spaces_with_flags(raw_piece)

            # sécurité : si après retrait il ne reste rien, ne pas patcher
            if not key:
                return None

            new_expr = make_translate_expr(
                key,
                spacebefore=auto_before,
                spaceafter=auto_after,
            )

            new_line = line[: m.start()] + new_expr + line[m.end() :]
            return ("Catégorie 5", key, new_line)   
    return None


def parse_lang_line(line: str):
    if "=" not in line:
        return None
    k, v = line.split("=", 1)
    k = k.rstrip("\r\n")
    v = v.rstrip("\r\n")
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
        entries.append(
            {
                "line": i,
                "raw": line,
                "key": key,
                "value": value,
                "norm_key": normalize_aggressive(key),
            }
        )

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
                hits.append(
                    {
                        "lang": lang,
                        "file": str(path),
                        "line": entry["line"],
                        "key": entry["key"],
                        "value": entry["value"],
                        "norm_key": entry["norm_key"],
                    }
                )

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
    if not entries:
        return ""

    def score(entry: dict) -> tuple:
        value = entry["value"].strip()
        key = entry["key"].strip()

        is_empty = value == ""
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
            removed_lines.append(
                {
                    "line": i,
                    "raw": line,
                }
            )

    if not inserted:
        if new_lines and new_lines[-1].strip() != "":
            new_lines.append("")
        new_lines.append(new_entry_line)
        kept_line = len(new_lines)

    new_text = "\n".join(new_lines)
    if text.endswith("\n"):
        new_text += "\n"

    changed = new_text != text

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
        "Ã",
        "Â",
        "â",
        "ð",
        "�",
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
                results.append(
                    {
                        "lang": code,
                        "file": str(path),
                        "line": entry["line"],
                        "key": entry["key"],
                        "value": entry["value"],
                        "raw": entry["raw"],
                        "reasons": reasons,
                        "norm_key": entry["norm_key"],
                    }
                )

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
            broken_entries.append(
                {
                    **entry,
                    "reasons": reasons,
                }
            )

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


def fix_broken_lang_entries(path: Path):
    text, enc, lines, entries = load_lang_entries(path)

    new_lines = []
    removed = []
    repaired = []

    for entry in entries:
        broken, reasons = is_broken_lang_entry(entry)

        if not broken:
            new_lines.append(entry["raw"])
            continue

        raw = entry["raw"]

        if "placeholder-value" in reasons and "mojibake" in reasons:
            removed.append(
                {
                    "line": entry["line"],
                    "raw": raw,
                    "reasons": reasons,
                }
            )
            continue

        if "mojibake" in reasons:
            clean_key = normalize_aggressive(entry["key"])
            clean_value = normalize_aggressive(entry["value"])

            if clean_key and clean_value:
                new_line = f"{clean_key}={clean_value}"
                new_lines.append(new_line)
                repaired.append(
                    {
                        "line": entry["line"],
                        "old": raw,
                        "new": new_line,
                        "reasons": reasons,
                    }
                )
                continue

        if "placeholder-value" in reasons:
            new_line = f"{entry['key']}="
            new_lines.append(new_line)
            repaired.append(
                {
                    "line": entry["line"],
                    "old": raw,
                    "new": new_line,
                    "reasons": reasons,
                }
            )
            continue

        new_lines.append(raw)

    new_text = "\n".join(new_lines)
    if text.endswith("\n"):
        new_text += "\n"

    changed = new_text != text

    return {
        "changed": changed,
        "encoding": enc,
        "old_text": text,
        "new_text": new_text,
        "removed": removed,
        "repaired": repaired,
    }


def get_lang_entries_for_key(lang: str, key: str):
    if lang not in LANG_FILES:
        return []

    path = LANG_FILES[lang]
    if not path.exists():
        return []

    _text, _enc, _lines, entries = load_lang_entries(path)
    norm = normalize_aggressive(key)
    return [e for e in entries if e["key"] == key or e["norm_key"] == norm]


def classify_lang_key_state(lang: str, key: str):
    entries = get_lang_entries_for_key(lang, key)

    if not entries:
        return {
            "state": "missing",
            "entries": [],
            "broken": [],
        }

    broken_entries = []
    for e in entries:
        broken, reasons = is_broken_lang_entry(e)
        if broken:
            broken_entries.append({**e, "reasons": reasons})

    if broken_entries and len(entries) == 1:
        return {
            "state": "broken",
            "entries": entries,
            "broken": broken_entries,
        }

    if len(entries) > 1:
        return {
            "state": "duplicate",
            "entries": entries,
            "broken": broken_entries,
        }

    return {
        "state": "ok",
        "entries": entries,
        "broken": broken_entries,
    }


def save_session(data: dict) -> None:
    ensure_dirs()
    SESSION_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_session() -> dict:
    if not SESSION_FILE.exists():
        print("Aucune session en attente.")
        sys.exit(1)
    return json.loads(SESSION_FILE.read_text(encoding="utf-8"))


def clear_preview_dir() -> None:
    if PREVIEW_DIR.exists():
        shutil.rmtree(PREVIEW_DIR)
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

def cmd_lang_upsert_if_key_exists(lang: str, source_text: str, translated_text: str) -> bool:
    # Vérifie d'abord si la clé existe déjà dans le code
    key_found = False
    needle = f'LocalizationManager::Instance().Translate("{escape_cpp_string(source_text)}")'

    for file in iter_search_files():
        text, _enc = read_text_auto(file)
        if needle in text:
            key_found = True
            break

    if not key_found:
        return False

    lang_file = Path("lang") / f"{lang}.txt"
    if not lang_file.exists():
        print(f"Fichier langue introuvable: {lang_file}")
        return False

    old_text, enc = read_text_auto(lang_file)
    lines = old_text.splitlines()

    quoted_key = f'"{escape_lang_string(source_text)}"'
    quoted_val = f'"{escape_lang_string(translated_text)}"'
    new_entry = f"{quoted_key}={quoted_val}"

    replaced = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(quoted_key + "="):
            new_lines.append(new_entry)
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        new_lines.append(new_entry)

    new_text = "\n".join(new_lines)
    if old_text.endswith("\n"):
        new_text += "\n"

    preview_path = PREVIEW_DIR / lang_file
    write_text_auto(preview_path, new_text, enc)

    session = {
        "created_at": datetime.now().isoformat(),
        "mode": "upsert_lang_only",
        "lang": lang,
        "source_text": source_text,
        "translated_text": translated_text,
        "pending_apply": True,
        "files": [
            {
                "file": str(lang_file),
                "preview": str(preview_path),
                "encoding": enc,
                "hits": [
                    {
                        "line": None,
                        "category": "Lang",
                        "old": None,
                        "new": new_entry,
                        "key": source_text,
                    }
                ],
            }
        ],
    }
    save_session(session)

    print(f"Langue        : {lang}")
    print(f"Clé exacte    : {source_text!r}")
    print(f"Traduction    : {translated_text!r}")
    print(f"[PREVIEW PRÊTE] {preview_path}")
    print("Utilise maintenant : chat_patch apply")
    return True

def make_translate_expr(key: str, spacebefore: bool = False, spaceafter: bool = False) -> str:
    expr = f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")'
    if spacebefore:
        expr = '" " + ' + expr
    if spaceafter:
        expr = expr + ' + " "'
    return expr

def cmd_pseint_find(query: str) -> int:
    norm = normalize_aggressive(query)
    found = False

    #print(f"Chaîne demandée : {query}")
    #print(f"Clé normalisée  : {norm}")
    print(f"Chaîne demandée : {query!r}")
    print(f"Clé normalisée  : {norm!r}")
    print()

    for file in iter_search_files():
        text, _enc = read_text_auto(file)
        hits = []
        for lineno, line in enumerate(text.splitlines(), 1):
            if line_matches_target(line, query, norm):
                cat = (
                    detect_category_for_line(line)
                    if file.suffix.lower() in {".cpp", ".h", ".hpp"}
                    else None
                )
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
    return cmd_pseint_upsert(query)


def cmd_pseint_upsert(
    lang: str,
    source_text: str,
    translated_text: str,
    spacebefore: bool = False,
    spaceafter: bool = False,
) -> int:
    ensure_dirs()
    clear_preview_dir()

    norm = normalize_aggressive(source_text)
    patches = []
    already_localized_hits = []

    exact_translate_needle = (
        f'LocalizationManager::Instance().Translate("{escape_cpp_string(source_text)}")'
    )

    for file in iter_search_files():
        old_text, enc = read_text_auto(file)
        lines = old_text.splitlines()
        new_lines = lines[:]
        local_hits = []
        local_already = []

        for i, line in enumerate(lines):
            # 1) Détection informative : déjà localisé tel quel
            if exact_translate_needle in line:
                local_already.append(
                    {
                        "line": i + 1,
                        "category": "Déjà localisé",
                        "old": line,
                        "key": source_text,
                    }
                )

            # 2) Tentative normale de patch
            patched = patch_line(
                line,
                source_text,
                norm,
                spacebefore=spacebefore,
                spaceafter=spaceafter,
            )
            if patched:
                category, key, new_line = patched
                if new_line != line:
                    local_hits.append(
                        {
                            "line": i + 1,
                            "category": category,
                            "old": line,
                            "new": new_line,
                            "key": key,
                        }
                    )
                    new_lines[i] = new_line

        if local_hits:
            new_text = "\n".join(new_lines)
            if old_text.endswith("\n"):
                new_text += "\n"

            rel_file = file
            preview_path = PREVIEW_DIR / rel_file
            write_text_auto(preview_path, new_text, enc)

            patches.append(
                {
                    "file": str(rel_file),
                    "preview": str(preview_path),
                    "encoding": enc,
                    "hits": local_hits,
                    "old_text": old_text,
                    "new_text": new_text,
                }
            )

        if local_already:
            already_localized_hits.append(
                {
                    "file": str(file),
                    "hits": local_already,
                }
            )

    # Cas 1 : rien à patcher, mais déjà localisé
    if not patches and already_localized_hits:
        total_already = sum(len(p["hits"]) for p in already_localized_hits)

        print(f"Langue          : {lang}")
        print(f"Chaîne source   : {source_text!r}")
        print(f"Traduction      : {translated_text!r}")
        print(f"Clé normalisée  : {norm!r}")
        print("Statut          : déjà localisée dans le code")
        print(f"Occurrences     : {total_already}")
        print()

        for item in already_localized_hits:
            print(f"=== {item['file']} ===")
            for h in item["hits"][:30]:
                print(f"[{h['category']}] ligne {h['line']}")
                print(f"  {h['old']}")
            if len(item["hits"]) > 30:
                print(f"... {len(item['hits']) - 30} autre(s) occurrence(s)")
            print()

        print("Aucun patch C++ à générer : la chaîne est déjà passée par Translate(...).")
        return 0

    # Cas 2 : rien du tout
    if not patches:
        print("Aucune occurrence upsertable reconnue pour cette chaîne.")
        return 2

    total_occ = sum(len(p["hits"]) for p in patches)

    print(f"Langue          : {lang}")
    print(f"Chaîne source   : {source_text!r}")
    print(f"Traduction      : {translated_text!r}")
    print(f"Clé normalisée  : {norm!r}")
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
            lineterm="",
        )
        for line in diff:
            print(line)
        print()

    session = {
        "created_at": datetime.now().isoformat(),
        "mode": "upsert_pseint",
        "lang": lang,
        "source_text": source_text,
        "translated_text": translated_text,
        "normalized_key": norm,
        "spacebefore": spacebefore,
        "spaceafter": spaceafter,
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

    print(f"Clé demandée : {query!r}")
    print(f"Clé normalisée: {normalize_aggressive(query)!r}")
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

    diff = list(
        difflib.unified_diff(
            result["old_text"].splitlines(),
            result["new_text"].splitlines(),
            fromfile=str(target),
            tofile=str(target) + " (preview)",
            lineterm="",
        )
    )

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

    diff = list(
        difflib.unified_diff(
            result["old_text"].splitlines(),
            result["new_text"].splitlines(),
            fromfile=str(target),
            tofile=str(target) + " (preview)",
            lineterm="",
        )
    )

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
                ]
                + [
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
                desc = "; ".join(
                    f"l.{i['line']} {i['key']}={i['value']}" for i in items[:4]
                )
                print(f"  - {key} -> {desc}")
            if len(report["norm_collisions"]) > 20:
                print(f"  ... {len(report['norm_collisions']) - 20} autre(s)")
            print()

    print("=== RÉSUMÉ GLOBAL ===")
    print(f"Entrées suspectes     : {total_broken}")
    print(f"Doublons exacts       : {total_exact_dup}")
    print(f"Collisions normalisées: {total_norm_collisions}")

    return 0


def cmd_lang_fix_broken(lang: str) -> int:
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

    result = fix_broken_lang_entries(target)

    if not result["changed"]:
        print("Aucune correction nécessaire.")
        return 0

    preview_path = PREVIEW_DIR / target
    write_text_auto(preview_path, result["new_text"], result["encoding"])

    diff = list(
        difflib.unified_diff(
            result["old_text"].splitlines(),
            result["new_text"].splitlines(),
            fromfile=str(target),
            tofile=str(target) + " (preview)",
            lineterm="",
        )
    )

    print(f"=== {target} ===")

    if result["removed"]:
        print("Lignes supprimées :")
        for e in result["removed"]:
            print(f"  - ligne {e['line']}: {e['raw']} [{', '.join(e['reasons'])}]")
        print()

    if result["repaired"]:
        print("Lignes réparées :")
        for e in result["repaired"]:
            print(f"  - ligne {e['line']}")
            print(f"    old: {e['old']}")
            print(f"    new: {e['new']}")
        print()

    for line in diff:
        print(line)
    print()

    hits = []
    for e in result["removed"]:
        hits.append(
            {
                "line": e["line"],
                "category": "Lang fix broken removed",
                "old": e["raw"],
                "new": None,
                "key": None,
            }
        )

    for e in result["repaired"]:
        hits.append(
            {
                "line": e["line"],
                "category": "Lang fix broken repaired",
                "old": e["old"],
                "new": e["new"],
                "key": None,
            }
        )

    session = {
        "created_at": datetime.now().isoformat(),
        "mode": "lang-fix-broken",
        "pending_apply": True,
        "files": [
            {
                "file": str(target),
                "preview": str(preview_path),
                "encoding": result["encoding"],
                "hits": hits,
            }
        ],
    }

    save_session(session)

    print(f"[PREVIEW PRÊTE] {PREVIEW_DIR}")
    print("Utilise maintenant : chat_patch apply")

    return 0


def cmd_lang_check_key(query: str) -> int:
    canonical_key = normalize_aggressive(query)

    print("=== KEY CHECK ===")
    print(f"Chaîne source : {query}")
    print(f"Clé canonique : {canonical_key}")
    print()

    print("C++:")
    cpp_hits = []
    for file in iter_search_files():
        if file.suffix.lower() not in {".cpp", ".h", ".hpp"}:
            continue
        text, _enc = read_text_auto(file)
        for lineno, line in enumerate(text.splitlines(), 1):
            if line_matches_target(line, query, canonical_key):
                cat = detect_category_for_line(line)
                cpp_hits.append((file, lineno, line, cat))

    if cpp_hits:
        for file, lineno, line, cat in cpp_hits[:20]:
            if cat:
                label = cat[0]
            elif "LocalizationManager::Instance().Translate(" in line:
                label = "déjà localisé"
            else:
                label = "texte brut"

            print(f"  - {file}:{lineno} [{label}]")
            print(f"    {line.strip()}")

            mkey = re.search(
                r'LocalizationManager::Instance\(\)\.Translate\("([^"]*)"\)', line
            )
            if mkey:
                cpp_key = mkey.group(1)
                cpp_norm = normalize_aggressive(cpp_key)
                status = "oui" if cpp_key == canonical_key else "non"
                print(f"    clé C++ : {cpp_key}")
                print(f"    clé norm: {cpp_norm}")
                print(f"    canonique ? {status}")
    else:
        print("  - aucune occurrence C++ trouvée")
    print()

    print("Langues:")
    for lang in sorted(LANG_FILES):
        info = classify_lang_key_state(lang, canonical_key)
        state = info["state"]
        print(f"  [{lang}] {state}")

        for e in info["entries"][:10]:
            print(f"       - {e['key']}={e['value']}")

        if state == "missing":
            print(
                f'       suggestion: chat_patch lang-upsert {lang} "{canonical_key}" "<TRADUCTION>"'
            )
        elif state == "duplicate":
            print(f'       suggestion: chat_patch lang-fix {lang} "{canonical_key}"')
            if info["broken"]:
                print(f"       suggestion: chat_patch lang-fix-broken {lang}")
        elif state == "broken":
            print(f"       suggestion: chat_patch lang-fix-broken {lang}")

        print()

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
        return cmd_pseint_upsert(query)

    if cmd == "pseint-upsert":
        if len(sys.argv) < 5:
            usage()
            return 1

        args = sys.argv[2:]

        spacebefore = False
        spaceafter = False

        if args[0] == "spacebefore":
            spacebefore = True
            args = args[1:]

        if len(args) < 3:
            usage()
            return 1

        lang = args[0]
        args = args[1:]

        if args[0] == "spaceafter":
            spaceafter = True
            args = args[1:]

        if len(args) < 2:
            usage()
            return 1

        source_text = args[0]
        translated_text = " ".join(args[1:])

        return cmd_pseint_upsert(
            lang,
            source_text,
            translated_text,
            spacebefore=spacebefore,
            spaceafter=spaceafter,
        )

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

    if cmd == "lang-fix-broken":
        if len(sys.argv) < 3:
            usage()
            return 1
        return cmd_lang_fix_broken(sys.argv[2])

    if cmd == "lang-check-key":
        if len(sys.argv) < 3:
            usage()
            return 1
        query = " ".join(sys.argv[2:])
        return cmd_lang_check_key(query)

    if cmd == "apply":
        return cmd_apply()

    usage()
    return 1


if __name__ == "__main__":
    sys.exit(main())
