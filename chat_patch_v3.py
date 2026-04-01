#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class HunkLine:
    kind: str  # ' ', '+', '-'
    text: str


@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: List[HunkLine]


@dataclass
class FilePatch:
    old_path: str
    new_path: str
    hunks: List[Hunk]


HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? "
    r"\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--mode", choices=["dry", "apply", "git-check"], required=True)
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--no-git-check", action="store_true")
    parser.add_argument("-h", "--help", action="help")
    return parser.parse_args()


def strip_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def parse_unified_diff(diff_text: str) -> List[FilePatch]:
    lines = diff_text.splitlines()
    i = 0
    patches: List[FilePatch] = []

    while i < len(lines):
        if not lines[i].startswith("--- "):
            i += 1
            continue

        old_path = lines[i][4:].strip()
        i += 1
        if i >= len(lines) or not lines[i].startswith("+++ "):
            raise ValueError("Patch invalide: ligne +++ manquante.")
        new_path = lines[i][4:].strip()
        i += 1

        hunks: List[Hunk] = []
        while i < len(lines) and lines[i].startswith("@@ "):
            m = HUNK_RE.match(lines[i])
            if not m:
                raise ValueError(f"En-tête de hunk invalide: {lines[i]}")
            old_start = int(m.group("old_start"))
            old_count = int(m.group("old_count") or "1")
            new_start = int(m.group("new_start"))
            new_count = int(m.group("new_count") or "1")
            i += 1

            hunk_lines: List[HunkLine] = []
            while i < len(lines):
                line = lines[i]
                if line.startswith("--- ") or line.startswith("@@ "):
                    break
                if line.startswith("\\ No newline at end of file"):
                    i += 1
                    continue
                if not line:
                    raise ValueError("Ligne vide invalide dans un hunk.")
                prefix = line[0]
                if prefix not in (" ", "+", "-"):
                    raise ValueError(f"Ligne de hunk invalide: {line}")
                hunk_lines.append(HunkLine(prefix, line[1:]))
                i += 1

            hunks.append(Hunk(old_start, old_count, new_start, new_count, hunk_lines))

        patches.append(FilePatch(old_path, new_path, hunks))

    if not patches:
        raise ValueError("Aucun patch trouvé sur stdin.")
    return patches


def read_text(path: Path) -> str:
    return path.read_text(encoding="latin-1", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="latin-1", errors="replace")


def check_git_available(cwd: Path) -> bool:
    try:
        subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except Exception:
        return False


def git_check(cwd: Path) -> int:
    if not check_git_available(cwd):
        eprint("[WARN] Pas dans un dépôt git ou git indisponible.")
        return 1

    print("[OK] Dépôt git détecté.")
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    ).stdout

    print(f"Branche : {branch or '(inconnue)'}")
    print("Statut :")
    print(status if status.strip() else "(working tree propre)")
    return 0


def apply_hunk_to_lines(file_lines: List[str], hunk: Hunk, file_path: Path) -> List[str]:
    idx = hunk.old_start - 1
    out: List[str] = []
    out.extend(file_lines[:idx])

    cursor = idx
    for hl in hunk.lines:
        if hl.kind == " ":
            if cursor >= len(file_lines) or file_lines[cursor] != hl.text:
                found = file_lines[cursor] if cursor < len(file_lines) else "<EOF>"
                raise ValueError(
                    f"Contexte non trouvé dans {file_path} à la ligne {cursor+1}: "
                    f"attendu={hl.text!r}, trouvé={found!r}"
                )
            out.append(file_lines[cursor])
            cursor += 1
        elif hl.kind == "-":
            if cursor >= len(file_lines) or file_lines[cursor] != hl.text:
                found = file_lines[cursor] if cursor < len(file_lines) else "<EOF>"
                raise ValueError(
                    f"Ligne à supprimer non trouvée dans {file_path} à la ligne {cursor+1}: "
                    f"attendu={hl.text!r}, trouvé={found!r}"
                )
            cursor += 1
        elif hl.kind == "+":
            out.append(hl.text)

    out.extend(file_lines[cursor:])
    return out


def render_preview(path: Path, patch: FilePatch) -> None:
    print(f"=== {path} ===")
    for h in patch.hunks:
        print(f"@@ -{h.old_start},{h.old_count} +{h.new_start},{h.new_count} @@")
        for line in h.lines:
            print(f"{line.kind}{line.text}")
    print()


def apply_patch(patches: List[FilePatch], cwd: Path, do_apply: bool) -> int:
    for fp in patches:
        rel = strip_prefix(fp.new_path if fp.new_path != "/dev/null" else fp.old_path)
        target = cwd / rel
        if not target.exists():
            raise FileNotFoundError(f"Fichier introuvable: {target}")

        render_preview(target, fp)

    if not do_apply:
        print("[DRY RUN] Aucun fichier modifié.")
        return 0

    for fp in patches:
        rel = strip_prefix(fp.new_path if fp.new_path != "/dev/null" else fp.old_path)
        target = cwd / rel
        text = read_text(target)
        lines = text.splitlines()
        ends_with_nl = text.endswith("\n")

        for hunk in fp.hunks:
            lines = apply_hunk_to_lines(lines, hunk, target)

        new_text = "\n".join(lines) + ("\n" if ends_with_nl else "")
        write_text(target, new_text)
        print(f"[PATCH APPLIQUÉ] {target}")

    return 0


def ask_confirm() -> bool:
    try:
        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tty_in, \
             open("/dev/tty", "w", encoding="utf-8", errors="replace") as tty_out:
            tty_out.write("Voulez-vous appliquer le patch ? [y/N] ")
            tty_out.flush()
            ans = tty_in.readline().strip().lower()
            return ans in {"y", "yes", "o", "oui"}
    except Exception:
        return False


def main() -> int:
    args = parse_args()
    cwd = Path(args.cwd).resolve()

    if args.mode == "git-check":
        return git_check(cwd)

    if not cwd.exists():
        eprint(f"Répertoire introuvable: {cwd}")
        return 1

    if not args.no_git_check and check_git_available(cwd):
        print("[OK] Dépôt git détecté.")
    elif not args.no_git_check:
        print("[WARN] Pas de dépôt git détecté.")

    diff_text = sys.stdin.read()
    if not diff_text.strip():
        eprint("Aucun patch reçu sur stdin.")
        return 1

    try:
        patches = parse_unified_diff(diff_text)
    except Exception as exc:
        eprint(f"Erreur de parsing du patch: {exc}")
        return 1

    if args.mode == "dry":
        try:
            return apply_patch(patches, cwd, do_apply=False)
        except Exception as exc:
            eprint(f"Erreur: {exc}")
            return 1

    if args.mode == "apply":
        try:
            apply_patch(patches, cwd, do_apply=False)
            if not ask_confirm():
                print("[ANNULÉ]")
                return 0
            return apply_patch(patches, cwd, do_apply=True)
        except Exception as exc:
            eprint(f"Erreur: {exc}")
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())