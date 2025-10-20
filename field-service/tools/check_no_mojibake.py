#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

# Using Unicode escapes to avoid mojibake detection in this file itself
PATTERNS = [
    re.compile(r"\xD0[^\s]"),  # Ð followed by non-space
    re.compile(r"\xD1[^\s]"),  # Ñ followed by non-space
    re.compile(r"\u0014"),  # control character
]


def has_mojibake(text: str) -> bool:
    return any(pattern.search(text) for pattern in PATTERNS)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    bad_files: list[Path] = []
    for path in repo_root.rglob("*.py"):
        try:
            contents = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            bad_files.append(path)
            continue
        if has_mojibake(contents):
            bad_files.append(path)
    if bad_files:
        for path in bad_files:
            print(path.relative_to(repo_root))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
