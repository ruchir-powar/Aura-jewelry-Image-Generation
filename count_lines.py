#!/usr/bin/env python3
"""
count_lines.py — total lines of code in a directory.

Usage:
  python count_lines.py [path] [--ext .py --ext .js ...] [--all] [--show]
                        [--max-size 2000000] [--exclude node_modules --exclude .git]

Defaults:
  • Counts only common code files by extension (see DEFAULT_EXTS below).
  • Skips vendor/cache dirs (.git, node_modules, venv, __pycache__, etc).
  • Treats files > 2MB as non-source (skip) to avoid huge blobs.
  • UTF-8 read with errors='ignore' (so weird encodings don't crash it).
"""

import argparse
import os
from pathlib import Path

DEFAULT_EXTS = {
    ".py", ".ipynb",
    ".js", ".jsx", ".ts", ".tsx",
    ".html", ".htm", ".css", ".scss", ".sass",
    ".json", ".yml", ".yaml", ".toml", ".ini",
    ".md", ".rst",
    ".c", ".h", ".hpp", ".hh", ".cc", ".cpp", ".cxx",
    ".java", ".kt", ".kts",
    ".go", ".rs", ".rb", ".php", ".swift", ".m", ".mm",
    ".sh", ".bash", ".zsh", ".ps1", ".psm1", ".bat", ".cmd",
    ".sql",
}

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", ".pnpm-store",
    ".venv", "venv", "env",
    "__pycache__", ".mypy_cache", ".pytest_cache",
    ".idea", ".vscode", ".DS_Store",
    "build", "dist", ".next", ".nuxt", ".cache", ".parcel-cache",
    ".terraform", "target", "out", "coverage",
}

def is_probably_text(path: Path, probe_bytes: int = 2048) -> bool:
    """Heuristic: treat as text if no NUL bytes in the first chunk."""
    try:
        with path.open("rb") as f:
            chunk = f.read(probe_bytes)
        return b"\x00" not in chunk
    except Exception:
        return False

def count_file_lines(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0

def walk_and_count(root: Path, *, use_all_text: bool, exts: set[str],
                   exclude_dirs: set[str], max_size: int, show: bool):
    total = 0
    per_file = []

    for dirpath, dirnames, filenames in os.walk(root):
        # prune excluded dirs in-place for efficiency
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs and not d.startswith(".git")]
        for name in filenames:
            p = Path(dirpath) / name
            # skip hidden files by default if in excluded dirs list only; otherwise include
            if not p.is_file():
                continue
            try:
                size = p.stat().st_size
            except Exception:
                continue
            if max_size and size > max_size:
                continue

            ext_ok = True
            if use_all_text:
                ext_ok = is_probably_text(p)
            else:
                ext_ok = p.suffix.lower() in exts

            if not ext_ok:
                continue

            n = count_file_lines(p)
            if n:
                total += n
                if show:
                    per_file.append((str(p.relative_to(root)), n))

    return total, sorted(per_file, key=lambda x: x[0].lower())

def main():
    ap = argparse.ArgumentParser(description="Count total lines of code in a directory.")
    ap.add_argument("path", nargs="?", default=".", help="Root directory (default: current).")
    ap.add_argument("--ext", action="append", default=[],
                    help="Extra/extensions to include (e.g., --ext .py --ext .js).")
    ap.add_argument("--all", dest="all_text", action="store_true",
                    help="Count ALL probable text files (ignore extensions).")
    ap.add_argument("--exclude", action="append", default=[],
                    help="Directory names to exclude (repeatable).")
    ap.add_argument("--max-size", type=int, default=2_000_000,
                    help="Max file size in bytes to scan (default: 2,000,000).")
    ap.add_argument("--show", action="store_true",
                    help="Print per-file counts.")
    args = ap.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Path not found: {root}")
        raise SystemExit(1)

    exts = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in args.ext}
    if not args.all_text:
        exts = DEFAULT_EXTS.union(exts)

    exclude_dirs = DEFAULT_EXCLUDE_DIRS.union(set(args.exclude or []))

    total, per_file = walk_and_count(
        root, use_all_text=args.all_text, exts=exts,
        exclude_dirs=exclude_dirs, max_size=args.max_size, show=args.show
    )

    if args.show and per_file:
        width = max(len(p) for p, _ in per_file)
        for p, n in per_file:
            print(f"{p.ljust(width)}  {n:>8}")

    print(f"\nTotal lines: {total}")

if __name__ == "__main__":
    main()
