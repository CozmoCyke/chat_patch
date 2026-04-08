#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
import json
import difflib
import shutil
import unicodedata
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

def strip_accents(s: str) -> str:
    normalized = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))

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


def resolve_repo_path(target: str) -> Path:
    path = Path(target)
    if path.is_absolute():
        return path
    return (REPO_ROOT / path).resolve()


def display_repo_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except Exception:
        return str(path)


def sanitize_extract_target_name(path: Path) -> str:
    rel = display_repo_path(path).replace("\\", "/")
    rel = re.sub(r"[^A-Za-z0-9]+", "_", rel)
    rel = re.sub(r"_+", "_", rel).strip("_")
    return rel or "target"


def normalize_localization_key(s: str) -> str:
    s = s.replace("\\t", " ")
    s = s.replace("\\n", " ")
    s = s.replace("\\r", " ")
    s = s.replace("\\f", " ")
    s = s.replace("\\v", " ")
    s = strip_accents(s)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def make_extract_key(source_string: str) -> str:
    return strip_accents(source_string)


def is_hard_technical_string(raw: str) -> bool:
    if not raw:
        return True

    if raw.startswith(("http://", "https://", "ftp://", "www.")):
        return True

    if re.search(r"^[A-Za-z]:[\\/]", raw):
        return True

    if re.search(r"[A-Za-z0-9_.-]+\.[A-Za-z0-9]{1,6}(?:[\\/]|$)", raw):
        return True

    if re.search(r"(?:[A-Za-z0-9_.-]+[\\/]){2,}[A-Za-z0-9_.-]*", raw):
        return True

    if "::" in raw or "->" in raw:
        return True

    if re.search(r"\b(?:TODO|TBD|FIXME|XXX+|DEBUG)\b", raw, re.I):
        return True

    if re.fullmatch(r"ver\d{6,}", raw, re.I):
        return True

    return False


def is_text_like_default_value(raw: str) -> bool:
    raw = raw.strip()
    if not raw or is_hard_technical_string(raw):
        return False

    if re.search(r"\s", raw):
        return True

    if re.search(r"[áéíóúñ¿¡ÁÉÍÓÚÑ]", raw):
        return True

    if re.search(r"[.!?…]", raw):
        return True

    return len(raw) >= 12


def is_whitespace_only_literal(raw: str) -> bool:
    return re.fullmatch(r"(?:\s|\\[nrtfv])+?", raw) is not None


def classify_literal_context(prefix: str) -> str | None:
    stripped = prefix.rstrip()

    if re.search(r"\bSetConfigStr\s*\(\s*$", stripped):
        return "set_key"

    if re.search(r"\bSetConfigStr\s*\([^,\n]*,\s*$", stripped):
        return "set_value"

    if re.search(r"\bGetConfigStr\s*\(\s*$", stripped):
        return "lookup_key"

    if re.search(
        r"\bwx(?:MessageBox|MessageDialog|LogMessage|LogWarning|LogError|LogStatus)\s*\(\s*$",
        stripped,
    ):
        return "ui_message"

    return None


def is_lookup_config_candidate(prefix: str) -> bool:
    return classify_literal_context(prefix) == "lookup_key"


def unquote_if_needed(s: str) -> str:
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def normalize_lang_value_for_compare(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {"'", '"'}:
        v = v[1:-1].strip()
    return v


def lang_values_equivalent(a: str, b: str) -> bool:
    return normalize_lang_value_for_compare(a) == normalize_lang_value_for_compare(b)


SPANISH_CUE_WORDS = {
    "abrir",
    "acerca",
    "actualizar",
    "actualizacion",
    "agregar",
    "ayuda",
    "buscar",
    "cerrar",
    "configurar",
    "copiar",
    "debe",
    "deshacer",
    "editar",
    "ejemplos",
    "eliminar",
    "encontrado",
    "error",
    "errores",
    "escribir",
    "existe",
    "falta",
    "guardar",
    "instruccion",
    "instrucciones",
    "insertar",
    "linea",
    "mensaje",
    "nuevo",
    "opciones",
    "operador",
    "pseudocodigo",
    "reemplazar",
    "rehacer",
    "salir",
    "seleccione",
    "seleccionar",
    "sintaxis",
    "traducir",
    "traduccion",
    "valida",
    "valido",
    "verificar",
}


def is_technical_string(raw: str) -> bool:
    if is_hard_technical_string(raw):
        return True

    if re.fullmatch(r"[A-Za-z0-9_.-]+", raw):
        return True

    return False


def is_already_localized_line(prefix: str) -> bool:
    localizer_markers = (
        "LocalizationManager::Instance().Translate(",
        "Translate(",
        "tr(",
        "_(",
        "wxGetTranslation(",
    )
    return any(marker in prefix for marker in localizer_markers)


def is_likely_spanish_candidate(raw: str, prefix: str = "") -> bool:
    raw = raw.strip()
    if len(raw) < 2:
        return False

    if is_technical_string(raw):
        return False

    if is_already_localized_line(prefix):
        return False

    normalized = normalize_localization_key(raw)
    if not normalized:
        return False

    tokens = normalized.split()
    if not tokens:
        return False

    if any(token in SPANISH_CUE_WORDS for token in tokens):
        return True

    if re.search(r"[áéíóúñ¿¡ÁÉÍÓÚÑ]", raw):
        return True

    if raw.count(" ") >= 1 and len(tokens) >= 2 and len(normalized) >= 8:
        if re.search(r"[.!?…]$", raw):
            return True

    if re.search(r"\b(?:Ctrl|Shift|Alt|F\d{1,2})\b", raw):
        if any(token in SPANISH_CUE_WORDS for token in tokens):
            return True

    return False


def iter_string_literals_with_lines(text: str):
    i = 0
    line = 1
    line_start = 0
    in_block_comment = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if ch == "\n":
            line += 1
            i += 1
            line_start = i
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if ch == "/" and nxt == "/":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue

        if ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue

        if ch != '"':
            i += 1
            continue

        prefix = text[line_start:i]
        start_line = line
        start = i + 1
        j = start
        escaped = False
        literal_line = line
        found = False

        while j < len(text):
            cj = text[j]
            if cj == "\n":
                break
            if escaped:
                escaped = False
                j += 1
                continue
            if cj == "\\":
                escaped = True
                j += 1
                continue
            if cj == '"':
                found = True
                break
            j += 1

        if not found:
            i = j
            continue

        raw_inner = text[start:j]
        yield {
            "source": f'"{raw_inner}"',
            "raw_inner": raw_inner,
            "line": start_line,
            "prefix": prefix,
        }

        i = j + 1


def split_batch_line(line: str):
    parts = line.split("|", 5)
    if len(parts) != 6:
        return None
    source, normalized_key, file_name, line_no, english, status = parts
    return {
        "source": source,
        "normalized_key": normalized_key,
        "file": file_name.strip(),
        "line": line_no.strip(),
        "english": english,
        "status": status.strip().upper(),
    }



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


def extract_strings_from_text(text: str, rel_file: str):
    candidates = []
    seen = set()
    total_literals = 0
    lines = text.splitlines()
    visited_blocks = set()

    def add_candidate(source: str, normalized: str, line_no: int):
        record = (source, normalized, rel_file, line_no)
        if record in seen:
            return
        seen.add(record)
        candidates.append(
            {
                "source": source,
                "normalized_key": normalized,
                "file": rel_file,
                "line": line_no,
            }
        )

    # Some adjacent literal blocks are easier to detect from the raw lines than
    # from the literal scanner alone, so we pre-walk the file for multiline spans.
    for line_idx, line in enumerate(lines):
        if '"' not in line:
            continue
        for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', line):
            source = f'"{m.group(1)}"'
            block_info = classify_string_block(lines, line_idx, source)
            if not block_info["found"] or not block_info["multiline"]:
                continue
            if block_info["wrapper"] == "_ZZ":
                continue

            block_key = (
                block_info["block_start"],
                block_info["block_end"],
                block_info["wrapper"],
            )
            if block_key in visited_blocks:
                continue
            visited_blocks.add(block_key)

            block_fragments = extract_block_fragments(
                lines, block_info["block_start"], block_info["block_end"]
            )
            for fragment in block_fragments:
                if is_whitespace_only_literal(fragment["raw_inner"]):
                    continue
                normalized = fragment["normalized_key"]
                if normalized:
                    add_candidate(fragment["source"], normalized, fragment["line_number"])

    for literal in iter_string_literals_with_lines(text):
        total_literals += 1
        source = literal["source"]
        raw_inner = literal["raw_inner"]
        line_no = literal["line"]
        prefix = literal["prefix"]

        if is_whitespace_only_literal(raw_inner):
            continue

        block_info = None
        line_idx = line_no - 1
        if 0 <= line_idx < len(lines):
            block_info = classify_string_block(lines, line_idx, source)

        if block_info and block_info["found"]:
            if block_info["wrapper"] == "_ZZ":
                continue

            if block_info["multiline"]:
                block_key = (
                    block_info["block_start"],
                    block_info["block_end"],
                    block_info["wrapper"],
                )
                if block_key in visited_blocks:
                    continue
                visited_blocks.add(block_key)

                block_fragments = extract_block_fragments(
                    lines, block_info["block_start"], block_info["block_end"]
                )

                if block_info["wrapper"] == "_Z":
                    for fragment in block_fragments:
                        if is_whitespace_only_literal(fragment["raw_inner"]):
                            continue
                        normalized = fragment["normalized_key"]
                        if normalized:
                            add_candidate(
                                fragment["source"], normalized, fragment["line_number"]
                            )
                    continue

                for fragment in block_fragments:
                    if is_whitespace_only_literal(fragment["raw_inner"]):
                        continue
                    normalized = fragment["normalized_key"]
                    if normalized:
                        add_candidate(fragment["source"], normalized, fragment["line_number"])
                continue

        context = classify_literal_context(prefix)

        if context == "set_key":
            if is_hard_technical_string(raw_inner):
                continue
            normalized = make_extract_key(raw_inner)
            if not normalized:
                continue
            add_candidate(source, normalized, line_no)
            continue

        if context == "lookup_key":
            if is_hard_technical_string(raw_inner):
                continue
            normalized = make_extract_key(raw_inner)
            if not normalized:
                continue
            add_candidate(source, normalized, line_no)
            continue

        if context == "set_value":
            if not is_text_like_default_value(raw_inner):
                continue
            normalized = make_extract_key(raw_inner)
            if not normalized:
                continue
            add_candidate(source, normalized, line_no)
            continue

        if context == "ui_message":
            if is_hard_technical_string(raw_inner):
                continue
            normalized = make_extract_key(raw_inner)
            if not normalized:
                continue
            add_candidate(source, normalized, line_no)
            continue

        if not is_lookup_config_candidate(prefix) and not is_likely_spanish_candidate(
            raw_inner, prefix=prefix
        ):
            continue

        normalized = make_extract_key(raw_inner)
        if not normalized:
            continue

        add_candidate(source, normalized, line_no)

    ignored = total_literals - len(candidates)
    return candidates, total_literals, ignored


def cmd_extract_strings(target: str) -> int:
    target_path = resolve_repo_path(target)
    if not target_path.exists() or not target_path.is_file():
        print(f"Fichier introuvable: {target}")
        return 1

    text, _enc = read_text_auto(target_path)
    rel_file = display_repo_path(target_path)
    candidates, total_literals, ignored = extract_strings_from_text(text, rel_file)

    out_name = f"extract_strings_{sanitize_extract_target_name(target_path)}.txt"
    out_path = Path.cwd() / out_name

    lines = [
        f"{item['source']}|{item['normalized_key']}|{item['file']}|{item['line']}"
        for item in candidates
    ]
    out_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    print(f"Scan terminé: {len(candidates)} candidates, {ignored} ignorées")
    print(f"Sortie: {out_name}")
    return 0


def locate_batch_code_line(lines: list[str], source_literal: str, expected_line: int):
    def line_has_patchable_source(line: str) -> bool:
        stripped = line.lstrip()
        if stripped.startswith(("//", "/*", "*")):
            return False
        return source_literal in line

    if expected_line < 1 or expected_line > len(lines):
        expected_idx = None
    else:
        expected_idx = expected_line - 1

    replacement_hits = []
    if expected_idx is not None and line_has_patchable_source(lines[expected_idx]):
        return expected_idx, "exact"

    if expected_idx is not None:
        start = max(0, expected_idx - 3)
        end = min(len(lines), expected_idx + 4)
        for idx in range(start, end):
            if line_has_patchable_source(lines[idx]):
                replacement_hits.append(idx)

    if len(replacement_hits) == 1:
        return replacement_hits[0], "nearby"

    all_hits = [idx for idx, line in enumerate(lines) if line_has_patchable_source(line)]
    if len(all_hits) == 1:
        return all_hits[0], "unique"

    if expected_idx is not None:
        already = f'LocalizationManager::Instance().Translate("{escape_cpp_string(normalize_localization_key(unquote_if_needed(source_literal)))}")'
        if already in lines[expected_idx]:
            return expected_idx, "already"

    return None, "missing" if not all_hits else "ambiguous"


def build_code_patch_preview(line: str, source_literal: str, normalized_key: str):
    replacement = (
        f'LocalizationManager::Instance().Translate("{escape_cpp_string(normalized_key)}")'
    )
    if replacement in line:
        return line, line, False, "already localized"

    if source_literal not in line:
        return line, line, False, "source not found"

    new_line = line.replace(source_literal, replacement, 1)
    if new_line == line:
        return line, line, False, "no change"

    return line, new_line, True, "patched"


def is_wrapped_by_z(line: str, source_literal: str) -> bool:
    pattern = r'_Z\s*\(\s*' + re.escape(source_literal) + r'\s*\)'
    return re.search(pattern, line) is not None


def build_z_code_patch_preview(line: str, source_literal: str, normalized_key: str):
    if source_literal not in line:
        return line, line, False, "source not found"

    new_line = line.replace(
        source_literal,
        f'"{escape_cpp_string(normalized_key)}"',
        1,
    )
    if new_line == line:
        return line, line, False, "no change"

    return line, new_line, True, "patched _Z"


def skip_ws_and_comments(lines: list[str], line_idx: int, col_idx: int):
    i = line_idx
    j = col_idx
    in_block_comment = False

    while i < len(lines):
        line = lines[i]

        while j < len(line):
            if in_block_comment:
                end = line.find("*/", j)
                if end == -1:
                    break
                j = end + 2
                in_block_comment = False
                continue

            if line.startswith("//", j):
                break

            if line.startswith("/*", j):
                in_block_comment = True
                j += 2
                continue

            if line[j] in " \t\r":
                j += 1
                continue

            return i, j

        i += 1
        j = 0

    return None, None


def classify_string_block(lines: list[str], line_idx: int, source_literal: str):
    def line_has_string_literal(idx: int) -> bool:
        if idx < 0 or idx >= len(lines):
            return False
        line = lines[idx]
        return '"' in line and not line.lstrip().startswith("//")

    def line_continues_string_block(idx: int) -> bool:
        if idx < 0 or idx >= len(lines):
            return False
        line = lines[idx].rstrip()
        if not line or line.lstrip().startswith("//"):
            return False
        return bool(
            re.search(
                r'"(?:[^"\\]|\\.)*"\s*(?://.*)?$',
                line,
            )
        )

    def line_starts_string_literal(idx: int) -> bool:
        if idx < 0 or idx >= len(lines):
            return False
        return bool(re.match(r'^\s*"', lines[idx]))

    line = lines[line_idx]
    start = line.find(source_literal)
    if start < 0:
        return {
            "found": False,
            "wrapper": None,
            "multiline": False,
            "concat": False,
            "supported": False,
            "reason": "source not found",
            "block_start": line_idx,
            "block_end": line_idx,
        }

    block_start = line_idx
    while (
        block_start > 0
        and line_continues_string_block(block_start - 1)
        and line_starts_string_literal(block_start)
    ):
        block_start -= 1

    block_end = line_idx
    while (
        block_end + 1 < len(lines)
        and line_continues_string_block(block_end)
        and line_starts_string_literal(block_end + 1)
    ):
        block_end += 1

    multiline = block_start != block_end
    concat = multiline
    wrapper = None
    for idx in range(block_start, block_end + 1):
        quote_idx = lines[idx].find('"')
        prefix = lines[idx][:quote_idx].rstrip() if quote_idx >= 0 else lines[idx].rstrip()
        if re.search(r'_ZZ\s*\($', prefix):
            wrapper = "_ZZ"
            break
        if wrapper is None and re.search(r'_Z\s*\($', prefix):
            wrapper = "_Z"

    supported = True
    reason = "single literal"

    if wrapper == "_ZZ":
        supported = False
        reason = "_ZZ variant is byte-string conversion, not translate-aware"
    elif multiline:
        supported = False
        if wrapper == "_Z":
            reason = "_Z multiline/concatenated block"
        else:
            reason = "multiline literal block"

    return {
        "found": True,
        "wrapper": wrapper,
        "multiline": multiline,
        "concat": concat,
        "supported": supported,
        "reason": reason,
        "block_start": block_start,
        "block_end": block_end,
    }


def extract_block_fragments(lines: list[str], block_start: int, block_end: int):
    fragments = []
    for idx in range(block_start, block_end + 1):
        line = lines[idx]
        for m in re.finditer(r'"((?:[^"\\]|\\.)*)"', line):
            raw_inner = m.group(1)
            source = f'"{raw_inner}"'
            prefix = line[: m.start()].rstrip()
            fragments.append(
                {
                    "source": source,
                    "raw_inner": raw_inner,
                    "prefix": prefix,
                    "line_index": idx,
                    "line_number": idx + 1,
                    "start_col": m.start(),
                    "end_col": m.end(),
                    "normalized_key": make_extract_key(raw_inner),
                }
            )
    return fragments


def build_multiline_literal_block_preview(
    lines: list[str], block_info: dict, fragments: list[dict]
):
    if not fragments:
        return lines[block_info["block_start"]], lines[block_info["block_start"]], False, "block not parsed"

    replacement_parts = [
        f'LocalizationManager::Instance().Translate("{escape_cpp_string(fragment["normalized_key"])}")'
        for fragment in fragments
        if fragment["normalized_key"]
    ]
    replacement = " + ".join(replacement_parts)

    first = fragments[0]
    last = fragments[-1]
    first_line = lines[first["line_index"]]
    last_line = lines[last["line_index"]]
    prefix = first_line[: first["start_col"]]
    suffix = last_line[last["end_col"] :]
    new_block_line = prefix + replacement + suffix
    old_block_text = "\n".join(lines[block_info["block_start"] : block_info["block_end"] + 1])

    if replacement and replacement in old_block_text:
        return old_block_text, old_block_text, False, "already localized"

    return old_block_text, new_block_line, True, "patched multiline literal block"


def find_block_fragment(fragments: list[dict], source_literal: str, line_index: int):
    for fragment in fragments:
        if fragment["line_index"] == line_index and fragment["source"] == source_literal:
            return fragment
    for fragment in fragments:
        if fragment["source"] == source_literal:
            return fragment
    return None


def preview_lang_upsert(path: Path, key: str, value: str):
    text, enc, lines, entries = load_lang_entries(path)
    norm = normalize_localization_key(key)

    exact_entries = [e for e in entries if e["key"] == key]
    norm_entries = [e for e in entries if e["norm_key"] == norm]
    matching_entries = exact_entries + [
        e for e in norm_entries if e not in exact_entries
    ]

    result = upsert_lang_entry(path, key, value)
    changed = result["new_text"] != result["old_text"]

    same_effective = any(
        lang_values_equivalent(e["value"], value) for e in matching_entries
    )

    if same_effective and matching_entries:
        state = "exact-same" if exact_entries else "normalized-same"
        changed = False
        result["new_text"] = result["old_text"]
        result["new_line"] = result["old_line"]
    elif exact_entries:
        state = "exact-update"
    elif norm_entries:
        state = "normalized-collision"
    else:
        state = "insert"

    return {
        "encoding": enc,
        "old_text": text,
        "new_text": result["new_text"],
        "changed": changed,
        "state": state,
        "exact_entries": exact_entries,
        "norm_entries": norm_entries,
        "matching_entries": matching_entries,
        "same_effective": same_effective,
        "line": result["line"],
        "old_line": result["old_line"],
        "new_line": result["new_line"],
        "key": key,
        "value": value,
        "normalized_key": norm,
    }


def backup_path_for_target(target: Path) -> Path:
    rel = display_repo_path(target)
    rel_path = Path(rel)
    if rel_path.is_absolute():
        rel_path = Path(target.name)
    return BACKUP_DIR / rel_path


def apply_text_file_preview(target: Path, preview_text: str, encoding: str) -> None:
    if target.exists():
        backup_target = backup_path_for_target(target)
        old_text, old_enc = read_text_auto(target)
        write_text_auto(backup_target, old_text, old_enc)
    write_text_auto(target, preview_text, encoding)


def cmd_pseint_patcher(batchfile: str) -> int:
    batch_path = resolve_repo_path(batchfile)
    if not batch_path.exists() or not batch_path.is_file():
        print(f"Fichier batch introuvable: {batchfile}")
        return 1

    text, _enc = read_text_auto(batch_path)
    rows = []
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parsed = split_batch_line(raw_line)
        if parsed is None:
            print(
                "Ligne batch ignorée (format invalide, attendu "
                "source|key|file|line|english|READY; les lignes d'extraction brutes "
                "ne suffisent pas) "
                f"{lineno}: {raw_line}"
            )
            continue
        parsed["batch_line"] = lineno
        rows.append(parsed)

    ready_rows = [row for row in rows if row["status"] == "READY"]

    stats = {
        "ready_read": len(ready_rows),
        "applied": 0,
        "rejected": 0,
        "skipped": 0,
        "skipped_multiline_Z": 0,
        "skipped_ZZ": 0,
        "skipped_multiline_literal": 0,
        "multiline_Z_lang_only": 0,
        "already_localized": 0,
        "en_conflicts": 0,
        "missing": 0,
        "quit": False,
    }
    processed_multiline_literal_blocks = set()
    processed_multiline_literal_rows = set()

    if not ready_rows:
        print("Aucune ligne READY à traiter.")
        print("=== Résumé patch ===")
        print("Lignes READY lues        : 0")
        print("Patches appliqués        : 0")
        print("Skips total              : 0")
        print("  - multiline _Z         : 0")
        print("  - _ZZ                  : 0")
        print("  - multiline literal    : 0")
        print("multiline_Z_lang_only    : 0")
        print("Already localized        : 0")
        print("Rejets utilisateur       : 0")
        print("Conflits en.txt          : 0")
        print("Occurrences introuvables : 0")
        print("Arrêt anticipé           : non")
        return 0

    for row in ready_rows:
        if row["batch_line"] in processed_multiline_literal_rows:
            continue

        source_field = row["source"]
        source_literal = source_field if source_field.startswith('"') else f'"{source_field}"'
        source_inner = unquote_if_needed(source_field)
        normalized_key = row["normalized_key"] or normalize_localization_key(source_inner)
        file_path = resolve_repo_path(row["file"])
        line_no = int(row["line"]) if row["line"].isdigit() else -1
        english = row["english"]

        if not file_path.exists() or not file_path.is_file():
            print(f"\n=== {row['file']} ===")
            print(f"Ligne batch : {row['batch_line']}")
            print("Fichier cible introuvable, ligne ignorée.")
            stats["missing"] += 1
            continue

        code_text, code_enc = read_text_auto(file_path)
        code_lines = code_text.splitlines()
        idx, status = locate_batch_code_line(code_lines, source_literal, line_no)

        if idx is None:
            print(f"\n=== {display_repo_path(file_path)} ===")
            print(f"Ligne batch : {row['batch_line']}")
            print(f"Source      : {source_literal}")
            print(f"État code    : {status}")
            print("Occurrence introuvable, ligne ignorée.")
            stats["missing"] += 1
            continue

        old_line = code_lines[idx]
        block_info = classify_string_block(code_lines, idx, source_literal)

        lang_target = LANG_FILES.get("en")
        if lang_target is None or not lang_target.exists():
            print("Fichier lang/en.txt introuvable.")
            return 1

        # Multiline _Z stays code-frozen here; we still audit the fragment key in en.txt.
        if block_info["wrapper"] == "_Z" and block_info["multiline"]:
            fragments = extract_block_fragments(
                code_lines, block_info["block_start"], block_info["block_end"]
            )
            fragment = find_block_fragment(fragments, source_literal, idx)

            if fragment is None:
                print(f"\n=== SKIP: multiline _Z block ===")
                print(f"Fichier : {display_repo_path(file_path)}")
                print(f"Ligne   : {idx + 1}")
                print(f"Type    : {block_info['reason']}")
                print(f"Source  : {source_inner}")
                print("Action  : skip")
                print()
                stats["skipped"] += 1
                continue

            fragment_key = fragment["normalized_key"] or normalized_key
            lang_preview = preview_lang_upsert(lang_target, fragment_key, english)
            stats["multiline_Z_lang_only"] += 1
            if lang_preview["state"] == "normalized-collision":
                stats["en_conflicts"] += 1

            skip_label = (
                "SKIP: multiline _Z block (translations already present)"
                if not lang_preview["changed"]
                else "SKIP: multiline _Z block (code unchanged, en.txt entries pending)"
            )

            print(f"\n=== {skip_label} ===")
            print(f"Fichier : {display_repo_path(file_path)}")
            print(f"Ligne   : {fragment['line_number']}")
            print("Code    : unchanged")
            print()
            print("=== Patch langue en.txt ===")
            print(f"Clé source      : {fragment['raw_inner']}")
            print(f"Clé normalisée  : {fragment_key}")
            print(f"Entrée existante: {'oui' if lang_preview['matching_entries'] else 'non'}")
            if lang_preview["matching_entries"]:
                current_values = ", ".join(
                    repr(entry["value"]) for entry in lang_preview["matching_entries"]
                )
                print(f"Valeur actuelle : {current_values}")
            if lang_preview["norm_entries"] and not lang_preview["exact_entries"]:
                current_norms = ", ".join(
                    f"{entry['key']}={entry['value']}" for entry in lang_preview["norm_entries"]
                )
                print(f"Collision norm. : {current_norms}")
            print(f"Valeur proposée : {english}")
            if not lang_preview["changed"]:
                print("État           : aucune entrée manquante")
            elif lang_preview["state"] == "normalized-collision":
                print("État           : collision normalisée possible")
            elif lang_preview["state"] == "normalized-same":
                print("État           : entrée normalisée déjà équivalente")
            elif lang_preview["state"] == "exact-update":
                print("État           : mise à jour d'une entrée existante")
            else:
                print("État           : ajout d'une entrée")
            print()

            if not lang_preview["changed"]:
                stats["already_localized"] += 1
                print("Aucun changement à appliquer, ligne ignorée.")
                continue

            # Les choix ici sont intentionnellement non persistants.
            # Un skip/reject s'applique seulement à cette exécution; la batch
            # est relue à chaque run pour recalculer l'état actuel.
            while True:
                try:
                    action = input(
                        "Action ? [y]es / [n]o / [s]kip / [e]dit english / [q]uit "
                    ).strip().lower()
                except EOFError:
                    action = "q"

                if action == "e":
                    try:
                        edited = input(f"Nouvelle traduction anglaise [{english}]: ").strip()
                    except EOFError:
                        edited = ""
                    if edited:
                        english = edited
                        lang_preview = preview_lang_upsert(lang_target, fragment_key, english)
                        if lang_preview["state"] == "normalized-collision":
                            stats["en_conflicts"] += 1
                        print()
                        print("Traduction anglaise mise à jour.")
                        print(f"Valeur proposée : {english}")
                        print()
                    continue

                if action in {"s", "skip"}:
                    stats["skipped"] += 1
                    break

                if action in {"n", "no"}:
                    stats["rejected"] += 1
                    break

                if action in {"q", "quit"}:
                    stats["quit"] = True
                    break

                if action in {"y", "yes", "o", "oui"}:
                    if lang_preview["changed"]:
                        apply_text_file_preview(
                            lang_target, lang_preview["new_text"], lang_preview["encoding"]
                        )

                    stats["applied"] += 1
                    break

                print("Réponse attendue: y, n, s, e ou q.")

        if stats["quit"]:
            break

            continue

        if block_info["multiline"] and block_info["wrapper"] is None:
            block_key = (file_path, block_info["block_start"], block_info["block_end"])
            if block_key in processed_multiline_literal_blocks:
                continue
            processed_multiline_literal_blocks.add(block_key)

            block_fragments = extract_block_fragments(
                code_lines, block_info["block_start"], block_info["block_end"]
            )
            block_rows = []
            row_by_line = {}
            for candidate in ready_rows:
                if candidate["batch_line"] in processed_multiline_literal_rows:
                    continue
                if candidate["file"] != row["file"]:
                    continue
                candidate_line = int(candidate["line"]) if candidate["line"].isdigit() else -1
                if candidate_line > 0:
                    row_by_line.setdefault(candidate_line, []).append(candidate)

            for fragment in block_fragments:
                fragment_line = fragment["line_number"]
                matched_row = None
                for candidate in row_by_line.get(fragment_line, []):
                    candidate_source = (
                        candidate["source"]
                        if candidate["source"].startswith('"')
                        else f'"{candidate["source"]}"'
                    )
                    if unquote_if_needed(candidate_source) == fragment["raw_inner"]:
                        matched_row = candidate
                        break
                if matched_row is None:
                    continue
                block_rows.append(
                    {
                        "row": matched_row,
                        "fragment": fragment,
                    }
                )

            block_rows.sort(key=lambda item: item["fragment"]["line_index"])
            if not block_rows:
                continue

            for item in block_rows:
                processed_multiline_literal_rows.add(item["row"]["batch_line"])

            fragment_entries = []
            for item in block_rows:
                fragment = item["fragment"]
                fragment_preview = preview_lang_upsert(
                    lang_target,
                    fragment["normalized_key"],
                    item["row"]["english"],
                )
                if fragment_preview["state"] == "normalized-collision":
                    stats["en_conflicts"] += 1
                fragment_entries.append(
                    {
                        "row": item["row"],
                        "fragment": fragment,
                        "preview": fragment_preview,
                    }
                )

            old_block_text, new_block_line, code_changed, code_note = (
                build_multiline_literal_block_preview(
                    code_lines, block_info, block_fragments
                )
            )
            block_source = "".join(fragment["raw_inner"] for fragment in block_fragments)
            block_has_changes = code_changed or any(
                entry["preview"]["changed"] for entry in fragment_entries
            )

            print(f"\n=== Patch code multiline literal block ===")
            print(f"Fichier : {display_repo_path(file_path)}")
            print(
                f"Ligne   : {block_info['block_start'] + 1}-{block_info['block_end'] + 1}"
            )
            print()
            print("AVANT :")
            print(old_block_text)
            print()
            print("APRÈS :")
            print(new_block_line)
            print(f"État   : {code_note}")
            print()

            print("=== Patch langue en.txt ===")
            print(f"Clé source      : {block_source}")
            print(f"Fragments       : {len(fragment_entries)}")
            for idx_entry, entry in enumerate(fragment_entries, 1):
                preview = entry["preview"]
                fragment = entry["fragment"]
                print(f"- Fragment {idx_entry}/{len(fragment_entries)}")
                print(f"  Clé source      : {fragment['raw_inner']}")
                print(f"  Clé normalisée  : {fragment['normalized_key']}")
                print(
                    f"  Entrée existante: {'oui' if preview['matching_entries'] else 'non'}"
                )
                print(f"  Valeur proposée : {entry['row']['english']}")
                if not preview["changed"]:
                    print("  État           : aucun changement nécessaire")
                elif preview["state"] == "normalized-collision":
                    print("  État           : collision normalisée possible")
                elif preview["state"] == "normalized-same":
                    print("  État           : entrée normalisée déjà équivalente")
                elif preview["state"] == "exact-update":
                    print("  État           : mise à jour d'une entrée existante")
                else:
                    print("  État           : ajout d'une entrée")
            print()

            if not block_has_changes:
                print("Aucun changement à appliquer, bloc ignoré.")
                stats["skipped"] += 1
                continue

            # Les choix ici sont intentionnellement non persistants.
            # Un skip/reject s'applique seulement à cette exécution; la batch
            # est relue à chaque run pour recalculer l'état actuel.
            while True:
                try:
                    action = input(
                        "Action ? [y]es / [n]o / [s]kip / [e]dit english / [q]uit "
                    ).strip().lower()
                except EOFError:
                    action = "q"

                if action == "e":
                    try:
                        edited = input(
                            "Nouvelle traduction anglaise pour le premier fragment [vide = conserver]: "
                        ).strip()
                    except EOFError:
                        edited = ""
                    if edited and fragment_entries:
                        fragment_entries[0]["row"]["english"] = edited
                        fragment_entries[0]["preview"] = preview_lang_upsert(
                            lang_target,
                            fragment_entries[0]["fragment"]["normalized_key"],
                            edited,
                        )
                        if fragment_entries[0]["preview"]["state"] == "normalized-collision":
                            stats["en_conflicts"] += 1
                        print()
                        print("Traduction anglaise mise à jour.")
                        print(f"Valeur proposée : {edited}")
                        print()
                    continue

                if action in {"s", "skip"}:
                    stats["skipped"] += 1
                    break

                if action in {"n", "no"}:
                    stats["rejected"] += 1
                    break

                if action in {"q", "quit"}:
                    stats["quit"] = True
                    break

                if action in {"y", "yes", "o", "oui"}:
                    if code_changed:
                        new_code_lines = (
                            code_lines[: block_info["block_start"]]
                            + [new_block_line]
                            + code_lines[block_info["block_end"] + 1 :]
                        )
                        new_code_text = "\n".join(new_code_lines)
                        if code_text.endswith("\n"):
                            new_code_text += "\n"
                        apply_text_file_preview(file_path, new_code_text, code_enc)

                    for entry in fragment_entries:
                        fragment = entry["fragment"]
                        row_english = entry["row"]["english"]
                        fragment_preview = preview_lang_upsert(
                            lang_target, fragment["normalized_key"], row_english
                        )
                        if fragment_preview["state"] == "normalized-collision":
                            stats["en_conflicts"] += 1
                        if fragment_preview["changed"]:
                            apply_text_file_preview(
                                lang_target,
                                fragment_preview["new_text"],
                                fragment_preview["encoding"],
                            )

                    stats["applied"] += 1
                    break

                print("Réponse attendue: y, n, s, e ou q.")

            if stats["quit"]:
                break

            continue

        lang_preview = preview_lang_upsert(lang_target, normalized_key, english)

        if not block_info["supported"]:
            if block_info["wrapper"] == "_Z":
                skip_label = "SKIP: multiline _Z block"
                stats["skipped_multiline_Z"] += 1
            elif block_info["wrapper"] == "_ZZ":
                skip_label = "SKIP: _ZZ helper (non-translatable)"
                stats["skipped_ZZ"] += 1
            else:
                skip_label = "SKIP: multiline literal block"
                stats["skipped_multiline_literal"] += 1

            print(f"\n=== {skip_label} ===")
            print(f"Fichier : {display_repo_path(file_path)}")
            print(f"Ligne   : {idx + 1}")
            print(f"Type    : {block_info['reason']}")
            print(f"Source  : {source_inner}")
            print("Action  : skip")
            print()
            stats["skipped"] += 1
            continue

        source_is_z = block_info["wrapper"] == "_Z"
        if source_is_z:
            if lang_preview["changed"]:
                new_line, after_line, code_changed, code_note = build_z_code_patch_preview(
                    old_line, source_literal, normalized_key
                )
            else:
                new_line, after_line, code_changed, code_note = (
                    old_line,
                    old_line,
                    False,
                    "already localized (_Z)",
                )
                stats["already_localized"] += 1
        else:
            new_line, after_line, code_changed, code_note = build_code_patch_preview(
                old_line, source_literal, normalized_key
            )

        if lang_preview["state"] == "normalized-collision":
            stats["en_conflicts"] += 1

        print(f"\n=== Patch code source ===")
        print(f"Fichier : {display_repo_path(file_path)}")
        print(f"Ligne   : {idx + 1}")
        print()
        print("AVANT :")
        print(old_line)
        print()
        print("APRÈS :")
        print(after_line)
        print(f"État   : {code_note}")
        print()

        print("=== Patch langue en.txt ===")
        print(f"Clé source      : {source_inner}")
        print(f"Clé normalisée  : {normalized_key}")
        print(f"Entrée existante: {'oui' if lang_preview['matching_entries'] else 'non'}")
        if lang_preview["matching_entries"]:
            current_values = ", ".join(
                repr(entry["value"]) for entry in lang_preview["matching_entries"]
            )
            print(f"Valeur actuelle : {current_values}")
        if lang_preview["norm_entries"] and not lang_preview["exact_entries"]:
            current_norms = ", ".join(
                f"{entry['key']}={entry['value']}" for entry in lang_preview["norm_entries"]
            )
            print(f"Collision norm. : {current_norms}")
        print(f"Valeur proposée : {english}")
        if not lang_preview["changed"]:
            print("État           : aucun changement nécessaire")
        elif lang_preview["state"] == "normalized-collision":
            print("État           : collision normalisée possible")
        elif lang_preview["state"] == "normalized-same":
            print("État           : entrée normalisée déjà équivalente")
        elif lang_preview["state"] == "exact-update":
            print("État           : mise à jour d'une entrée existante")
        else:
            print("État           : ajout d'une entrée")
        print()

        if not code_changed and not lang_preview["changed"] and code_note.startswith("already localized"):
            stats["already_localized"] += 1

        if not code_changed and not lang_preview["changed"]:
            print("Aucun changement à appliquer, ligne ignorée.")
            stats["skipped"] += 1
            continue

        # Les choix ici sont intentionnellement non persistants.
        # Un skip/reject s'applique seulement à cette exécution; la batch
        # est relue à chaque run pour recalculer l'état actuel.
        while True:
            try:
                action = input("Action ? [y]es / [n]o / [s]kip / [e]dit english / [q]uit ").strip().lower()
            except EOFError:
                action = "q"

            if action == "e":
                try:
                    edited = input(f"Nouvelle traduction anglaise [{english}]: ").strip()
                except EOFError:
                    edited = ""
                if edited:
                    english = edited
                    lang_preview = preview_lang_upsert(lang_target, normalized_key, english)
                    if lang_preview["state"] == "normalized-collision":
                        stats["en_conflicts"] += 1
                    print()
                    print("Traduction anglaise mise à jour.")
                    print(f"Valeur proposée : {english}")
                    print()
                continue

            if action in {"s", "skip"}:
                stats["skipped"] += 1
                break

            if action in {"n", "no"}:
                stats["rejected"] += 1
                break

            if action in {"q", "quit"}:
                stats["quit"] = True
                break

            if action in {"y", "yes", "o", "oui"}:
                if code_changed:
                    code_lines[idx] = after_line
                    new_code_text = "\n".join(code_lines)
                    if code_text.endswith("\n"):
                        new_code_text += "\n"
                    apply_text_file_preview(file_path, new_code_text, code_enc)

                if lang_preview["changed"]:
                    apply_text_file_preview(lang_target, lang_preview["new_text"], lang_preview["encoding"])

                stats["applied"] += 1
                break

            print("Réponse attendue: y, n, s, e ou q.")

        if stats["quit"]:
            break

    print()
    print("=== Résumé patch ===")
    print(f"Lignes READY lues        : {stats['ready_read']}")
    print(f"Patches appliqués        : {stats['applied']}")
    print(f"Skips total              : {stats['skipped']}")
    print(f"  - multiline _Z         : {stats['skipped_multiline_Z']}")
    print(f"  - _ZZ                  : {stats['skipped_ZZ']}")
    print(f"  - multiline literal    : {stats['skipped_multiline_literal']}")
    print(f"multiline_Z_lang_only    : {stats['multiline_Z_lang_only']}")
    print(f"Already localized        : {stats['already_localized']}")
    print(f"Rejets utilisateur       : {stats['rejected']}") 
    print(f"Conflits en.txt          : {stats['en_conflicts']}")
    print(f"Occurrences introuvables : {stats['missing']}")
    print(f"Arrêt anticipé           : {'oui' if stats['quit'] else 'non'}")
    return 0


def usage() -> None:
    print("Usage:")
    print('  chat_patch extract-strings <target>')
    print('  chat_patch pseint-patcher <batchfile>')
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

    if cmd == "extract-strings":
        if len(sys.argv) < 3:
            usage()
            return 1
        target = " ".join(sys.argv[2:])
        return cmd_extract_strings(target)

    if cmd == "pseint-patcher":
        if len(sys.argv) < 3:
            usage()
            return 1
        batchfile = " ".join(sys.argv[2:])
        return cmd_pseint_patcher(batchfile)

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
