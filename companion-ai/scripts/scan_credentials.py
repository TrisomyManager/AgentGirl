"""Scan repo for hardcoded COMPANION_VOLC_APP_ID / COMPANION_VOLC_ACCESS_TOKEN.

Usage:
    python scripts/scan_credentials.py          # scan git-tracked + .env* + test fixtures
    python scripts/scan_credentials.py --all    # scan all files (slower)

Exit 0 if clean, exit 1 if any hardcoded credential is found.
Output: file_path:line_number only — no token values printed.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PATTERN = re.compile(r"COMPANION_VOLC_(?:APP_ID|ACCESS_TOKEN)\s*=\s*[^$\s]")


def _git_ls_files() -> List[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
            timeout=10,
        )
        if result.returncode != 0:
            return []
        return [PROJECT_ROOT / line.strip() for line in result.stdout.splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


def _extra_files() -> List[Path]:
    extra: List[Path] = []
    for p in PROJECT_ROOT.glob(".env*"):
        if p.is_file():
            extra.append(p)
    for p in PROJECT_ROOT.rglob("**/tests/**/*.py"):
        if p.is_file():
            extra.append(p)
    for p in PROJECT_ROOT.rglob("**/tests/**/*.json"):
        if p.is_file():
            extra.append(p)
    for p in PROJECT_ROOT.rglob("**/tests/**/*.yaml"):
        if p.is_file():
            extra.append(p)
    for p in PROJECT_ROOT.rglob("**/tests/**/*.yml"):
        if p.is_file():
            extra.append(p)
    for p in PROJECT_ROOT.rglob("**/fixtures/**/*"):
        if p.is_file():
            extra.append(p)
    return extra


def _scan_file(filepath: Path) -> List[str]:
    hits: List[str] = []
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        if PATTERN.search(line):
            hits.append(f"{filepath}:{lineno}")
    return hits


def main() -> int:
    all_hits: List[str] = []
    scanned: set[str] = set()

    for fp in _git_ls_files():
        if not fp.is_file():
            continue
        scanned.add(str(fp))
        all_hits.extend(_scan_file(fp))

    for fp in _extra_files():
        if str(fp) in scanned:
            continue
        if not fp.is_file():
            continue
        all_hits.extend(_scan_file(fp))

    if all_hits:
        for hit in sorted(all_hits):
            print(hit)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
