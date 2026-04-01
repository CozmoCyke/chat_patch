#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import os
import re
import subprocess
import sys
import tempfile
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


@dataclass
class ApplyResult:
    file_path: Path
    old_text: str
    new_text: str
    changed: bool


HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(Exception):
    pass


def strip_prefix(path: str) -> str:
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def read_stdin_patch() -> str:
    data = sys.stdin.read()
    if not data.strip():
        raise PatchError("Aucun patch reçu sur stdin.")
    return data


def parse_patch(text: str) -> List[FilePatch]:
    lines = text.splitlines()
    patches: List[FilePatch] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line.startswith("--- "):
            i += 1
            continue

        old_path = line[4:].strip()
        i += 1
        if i >= len(lines) or not lines[i].startswith("+++ "):
            raise PatchError("Patch invalide: ligne '+++' manquante.")
        new_path = lines[i][4:].strip()
        i += 1

        hunks: List[Hunk] = []
        while i < len(lines) and lines[i].startswith("@@ "):
            m = HUNK_RE.match(lines[i])
            if not m:
                raise PatchError(f"En-tête de hunk invalide: {lines[i]}")
            old_start = int(m.group(1))
            old_count = int(m.group(2) or "1")
            new_start = int(m.group(3))
            new_count = int(m.group(4) or "1")
            i += 1

            hunk_lines: List[HunkLine] = []
            while i < len(lines):
                l = lines[i]
                if l.startswith("@@ ") or l.startswith("--- "):
                    break
                if l.startswith("\\ No newline at end of file"):
                    i += 1
                    continue
                if not l or l[0] not in {" ", "+", "-"}:
                    raise PatchError(f"Ligne de hunk invalide: {l!r}")
                hunk_lines.append(HunkLine(l[0], l[1:]))
                i += 1

            hunks.append(Hunk(old_start, old_count, new_start, new_count, hunk_lines))

        patches.append(FilePatch(old_path, new_path, hunks))

    if not patches:
        raise PatchError("Aucun fichier patché détecté.")
    return patches


LATIN1_EXTS = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".txt", ".ini", ".hlp", ".html", ".md"}


def choose_encoding(path: Path) -> str:
    return "latin-1" if path.suffix.lower() in LATIN1_EXTS else "utf-8"


def read_text(path: Path) -> str:
    enc = choose_encoding(path)
    try:
        return path.read_text(encoding=enc, errors="strict")
    except UnicodeDecodeError:
        if enc != "latin-1":
            return path.read_text(encoding="latin-1", errors="replace")
        raise


def write_text(path: Path, text: str) -> None:
    enc = choose_encoding(path)
    path.write_text(text, encoding=enc, errors="replace")


def apply_file_patch(root: Path, patch: FilePatch) -> ApplyResult:
    rel_path = strip_prefix(patch.new_path if patch.new_path != "/dev/null" else patch.old_path)
    file_path = root / rel_path

    if not file_path.exists():
        raise PatchError(f"Fichier introuvable: {file_path}")

    old_text = read_text(file_path)
    old_lines = old_text.splitlines()
    new_lines: List[str] = []
    src_index = 0

    for hunk in patch.hunks:
        target_index = hunk.old_start - 1
        if target_index < src_index:
            raise PatchError(f"Hunks chevauchants dans {file_path}")

        new_lines.extend(old_lines[src_index:target_index])
        src_index = target_index

        for hl in hunk.lines:
            if hl.kind == " ":
                if src_index >= len(old_lines) or old_lines[src_index] != hl.text:
                    got = old_lines[src_index] if src_index < len(old_lines) else "<EOF>"
                    raise PatchError(
                        f"Contexte non trouvé dans {file_path} à la ligne {src_index + 1}:\n"
                        f"  attendu: {hl.text!r}\n"
                        f"  obtenu : {got!r}"
                    )
                new_lines.append(old_lines[src_index])
                src_index += 1
            elif hl.kind == "-":
                if src_index >= len(old_lines) or old_lines[src_index] != hl.text:
                    got = old_lines[src_index] if src_index < len(old_lines) else "<EOF>"
                    raise PatchError(
                        f"Suppression impossible dans {file_path} à la ligne {src_index + 1}:\n"
                        f"  attendu: {hl.text!r}\n"
                        f"  obtenu : {got!r}"
                    )
                src_index += 1
            elif hl.kind == "+":
                new_lines.append(hl.text)
            else:
                raise PatchError(f"Type de ligne inconnu: {hl.kind}")

    new_lines.extend(old_lines[src_index:])
    new_text = "\n".join(new_lines)
    if old_text.endswith("\n"):
        new_text += "\n"

    return ApplyResult(
        file_path=file_path,
        old_text=old_text,
        new_text=new_text,
        changed=(old_text != new_text),
    )


def build_diff(result: ApplyResult) -> str:
    diff = difflib.unified_diff(
        result.old_text.splitlines(),
        result.new_text.splitlines(),
        fromfile=str(result.file_path),
        tofile=str(result.file_path),
        lineterm="",
    )
    return "\n".join(diff)


def ask_confirmation(prompt: str) -> bool:
    try:
        with open("/dev/tty", "r", encoding="utf-8", errors="replace") as tin, \
             open("/dev/tty", "w", encoding="utf-8", errors="replace") as tout:
            tout.write(prompt)
            tout.flush()
            ans = tin.readline().strip().lower()
            return ans in {"y", "yes", "o", "oui"}
    except OSError:
        return False


def format_summary(results: List[ApplyResult]) -> str:
    changed = sum(1 for r in results if r.changed)
    return f"Fichiers analysés: {len(results)} | Fichiers modifiés: {changed}"


def save_backup(result: ApplyResult, suffix: str = ".orig") -> Optional[Path]:
    backup = result.file_path.with_suffix(result.file_path.suffix + suffix)
    if backup.exists():
        return None
    write_text(backup, result.old_text)
    return backup


def run_git_apply(root: Path, patch_text: str, check_only: bool) -> int:
    cmd = ["git", "apply", "--check" if check_only else "--apply", "-"]
    proc = subprocess.run(cmd, input=patch_text.encode("utf-8"), cwd=root)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Applique un diff unifié proposé par IA de façon sûre.")
    parser.add_argument("--root", default=".", help="Racine du projet")
    parser.add_argument("--dry-run", action="store_true", help="Prévisualiser sans écrire")
    parser.add_argument("--yes", action="store_true", help="Appliquer sans confirmation")
    parser.add_argument("--backup", action="store_true", help="Créer un backup .orig avant écriture")
    parser.add_argument("--git-check", action="store_true", help="Valider aussi le patch avec git apply --check")
    parser.add_argument("--git-apply", action="store_true", help="Laisser git apply appliquer le patch")
    args = parser.parse_args()

    root = Path(args.root).resolve()

    try:
        patch_text = read_stdin_patch()
        if args.git_check:
            rc = run_git_apply(root, patch_text, check_only=True)
            if rc != 0:
                raise PatchError("git apply --check a échoué.")

        if args.git_apply:
            if args.dry_run:
                print("[OK] git apply --check réussi.")
                return 0
            if not args.yes and not ask_confirmation("Voulez-vous appliquer le patch via git apply ? [y/N] "):
                print("[ANNULÉ]")
                return 1
            rc = run_git_apply(root, patch_text, check_only=False)
            if rc != 0:
                raise PatchError("git apply a échoué.")
            print("[PATCH APPLIQUÉ via git apply]")
            return 0

        file_patches = parse_patch(patch_text)
        results: List[ApplyResult] = [apply_file_patch(root, fp) for fp in file_patches]

        print(format_summary(results))
        print()
        for res in results:
            print(f"=== {res.file_path} ===")
            diff_text = build_diff(res)
            print(diff_text if diff_text else "(aucune différence)")
            print()

        if args.dry_run:
            print("[DRY-RUN] Aucun fichier modifié.")
            return 0

        if not args.yes:
            if not ask_confirmation("Voulez-vous appliquer le patch ? [y/N] "):
                print("[ANNULÉ]")
                return 1

        for res in results:
            if args.backup:
                backup = save_backup(res)
                if backup:
                    print(f"[BACKUP] {backup}")
            write_text(res.file_path, res.new_text)
            print(f"[PATCH APPLIQUÉ] {res.file_path}")

        return 0

    except PatchError as e:
        print(f"[ERREUR] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
