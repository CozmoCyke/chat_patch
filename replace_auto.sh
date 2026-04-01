replace_auto() {
    python3 - "$@" <<'PY'
import sys
import re
import difflib
from pathlib import Path

# =========================
# Helpers
# =========================

def read_text_latin1(path: Path) -> str:
    return path.read_text(encoding="latin-1", errors="replace")

def write_text_latin1(path: Path, text: str) -> None:
    path.write_text(text, encoding="latin-1", errors="replace")

def escape_cpp_string(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', r'\"')

def normalize_aggressive(s: str) -> str:
    repairs = {
        "Ã¡": "a", "Ã©": "e", "Ã­": "i", "Ã³": "o", "Ãº": "u",
        "Ã": "A", "Ã": "E", "Ã": "I", "Ã": "O", "Ã": "U",
        "Ã±": "n", "Ã": "N",
        "Ã¼": "u", "Ã": "U",
        "â": "'", "â": '"', "â": '"',
        "â": "-", "â": "-",
        "Â¿": "", "Â¡": "",
        "Â": "",
        "�": "",
    }
    for a, b in repairs.items():
        s = s.replace(a, b)

    trans = str.maketrans({
        'á':'a','à':'a','â':'a','ä':'a','ã':'a','å':'a',
        'Á':'A','À':'A','Â':'A','Ä':'A','Ã':'A','Å':'A',
        'é':'e','è':'e','ê':'e','ë':'e',
        'É':'E','È':'E','Ê':'E','Ë':'E',
        'í':'i','ì':'i','î':'i','ï':'i',
        'Í':'I','Ì':'I','Î':'I','Ï':'I',
        'ó':'o','ò':'o','ô':'o','ö':'o','õ':'o',
        'Ó':'O','Ò':'O','Ô':'O','Ö':'O','Õ':'O',
        'ú':'u','ù':'u','û':'u','ü':'u',
        'Ú':'U','Ù':'U','Û':'U','Ü':'U',
        'ñ':'n','Ñ':'N',
        'ç':'c','Ç':'C',
    })
    s = s.translate(trans)
    s = re.sub(r'[^\x20-\x7E]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def iter_cpp_files():
    for p in Path(".").glob("*.cpp"):
        if p.is_file():
            yield p

def line_matches_target(line: str, target_raw: str, target_norm: str) -> bool:
    return target_raw in line or target_norm in normalize_aggressive(line)

def detect_replaceable_string(line: str):
    # Catégorie 1 : err_handler.SyntaxError(..., "...")
    m = re.search(r'err_handler\.SyntaxError\s*\(\s*[^,\n]+,\s*"([^"]+)"\s*\)', line)
    if m and 'LocalizationManager::Instance().Translate(' not in line:
        return ("Catégorie 1", m.group(1), line)

    # Catégorie 2 : err_handler.ExecutionError / CompileTimeWarning / Warning(..., "...")
    m = re.search(r'err_handler\.(ExecutionError|CompileTimeWarning|Warning)\s*\(\s*[^,\n]+,\s*"([^"]+)"\s*\)', line)
    if m and 'LocalizationManager::Instance().Translate(' not in line:
        return ("Catégorie 2", m.group(2), line)

    # Catégorie 3 : MkErrorMsg("...", ...)
    m = re.search(r'MkErrorMsg\s*\(\s*"([^"]+)"\s*,', line)
    if m and 'LocalizationManager::Instance().Translate(' not in line:
        return ("Catégorie 3", m.group(1), line)

    return None

def patch_line(line: str, target_raw: str, target_norm: str):
    def same(s: str) -> bool:
        return s == target_raw or normalize_aggressive(s) == target_norm

    # Catégorie 1
    m = re.search(r'(err_handler\.SyntaxError\s*\(\s*[^,\n]+,\s*)"([^"]*)(")', line)
    if m and same(m.group(2)) and 'LocalizationManager::Instance().Translate(' not in line:
        key = normalize_aggressive(m.group(2))
        new = line[:m.start()] + m.group(1) + f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")' + line[m.end(3):]
        return ("Catégorie 1", key, new)

    # Catégorie 2
    m = re.search(r'((?:err_handler\.(?:ExecutionError|CompileTimeWarning|Warning)\s*\(\s*[^,\n]+,\s*))"([^"]*)(")', line)
    if m and same(m.group(2)) and 'LocalizationManager::Instance().Translate(' not in line:
        key = normalize_aggressive(m.group(2))
        new = line[:m.start()] + m.group(1) + f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")' + line[m.end(3):]
        return ("Catégorie 2", key, new)

    # Catégorie 3
    m = re.search(r'(MkErrorMsg\s*\(\s*)"([^"]*)(")', line)
    if m and same(m.group(2)) and 'LocalizationManager::Instance().Translate(' not in line:
        key = normalize_aggressive(m.group(2))
        new = line[:m.start()] + m.group(1) + f'LocalizationManager::Instance().Translate("{escape_cpp_string(key)}")' + line[m.end(3):]
        return ("Catégorie 3", key, new)

    return None

def ask_confirmation():
    try:
        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tty_in, \
             open("/dev/tty", "w", encoding="utf-8", errors="replace") as tty_out:
            tty_out.write("Voulez-vous appliquer le patch ? [y/N] ")
            tty_out.flush()
            ans = tty_in.readline().strip()
            return ans.lower() in ("y", "yes", "o", "oui")
    except Exception:
        return False

def usage():
    print("Usage:")
    print("  replace_auto --list")
    print('  replace_auto --find "chaine"')
    print('  replace_auto --replace "chaine"')

# =========================
# Command parsing
# =========================

argv = sys.argv[1:]
if not argv:
    usage()
    sys.exit(1)

cmd = argv[0]

# =========================
# --list
# =========================

if cmd == "--list":
    found_any = False
    seen = set()

    for file in iter_cpp_files():
        text = read_text_latin1(file)
        for lineno, line in enumerate(text.splitlines(), 1):
            info = detect_replaceable_string(line)
            if not info:
                continue
            category, raw, _ = info
            key = (category, normalize_aggressive(raw), file.name, lineno)
            if key in seen:
                continue
            seen.add(key)
            found_any = True
            print(f"[{category}] {file}:{lineno}")
            print(f"  brut : {raw}")
            print(f"  cle  : {normalize_aggressive(raw)}")
            print()

    if not found_any:
        print("Aucune chaîne remplaçable trouvée.")
    sys.exit(0)

# =========================
# --find
# =========================

if cmd == "--find":
    if len(argv) < 2:
        usage()
        sys.exit(1)

    raw = " ".join(argv[1:])
    norm = normalize_aggressive(raw)
    found = False

    for file in iter_cpp_files():
        text = read_text_latin1(file)
        hits = []
        for lineno, line in enumerate(text.splitlines(), 1):
            if line_matches_target(line, raw, norm):
                hits.append((lineno, line))
        if hits:
            found = True
            print(f"=== {file} ===")
            for lineno, line in hits[:20]:
                print(f"{lineno}: {line}")
            if len(hits) > 20:
                print(f"... {len(hits)-20} autre(s) occurrence(s)")
            print()

    if not found:
        print("Aucun fichier .cpp ne contient cette chaîne.")
    sys.exit(0)

# =========================
# --replace
# =========================

if cmd == "--replace":
    if len(argv) < 2:
        usage()
        sys.exit(1)

    raw = " ".join(argv[1:])
    norm = normalize_aggressive(raw)

    patches = []
    for file in iter_cpp_files():
        old_text = read_text_latin1(file)
        lines = old_text.splitlines()
        new_lines = lines[:]
        local_hits = []

        for i, line in enumerate(lines):
            patched = patch_line(line, raw, norm)
            if patched:
                category, key, new_line = patched
                local_hits.append((i+1, category, line, new_line, key))
                new_lines[i] = new_line

        if local_hits:
            new_text = "\n".join(new_lines)
            if old_text.endswith("\n"):
                new_text += "\n"
            patches.append((file, old_text, new_text, local_hits))

    if not patches:
        print("Aucune catégorie reconnue pour cette chaîne.")
        sys.exit(2)

    total = sum(len(h[3:4]) or 1 for _, _, _, h in patches)
    # better explicit total:
    total = sum(len(local_hits) for _, _, _, local_hits in patches)

    print(f"Chaîne demandée : {raw}")
    print(f"Clé normalisée  : {norm}")
    print(f"Fichiers touchés: {len(patches)}")
    print(f"Occurrences     : {total}")
    print()

    for file, old_text, new_text, local_hits in patches:
        print(f"=== {file} ===")
        print(f"Catégorie(s) trouvée(s) : {', '.join(sorted(set(h[1] for h in local_hits)))}")
        for lineno, category, old_line, new_line, key in local_hits[:10]:
            print(f"[{category}] ligne {lineno}")
            print(f"  - {old_line}")
            print(f"  + {new_line}")
            print(f"  clé: {key}")
            print()
        diff = difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=str(file),
            tofile=str(file) + " (patched)",
            lineterm=""
        )
        for line in diff:
            print(line)
        print()

    if ask_confirmation():
        for file, _, new_text, _ in patches:
            write_text_latin1(file, new_text)
        print("[PATCH APPLIQUÉ]")
    else:
        print("[ANNULÉ]")

    sys.exit(0)

usage()
sys.exit(1)
PY
}