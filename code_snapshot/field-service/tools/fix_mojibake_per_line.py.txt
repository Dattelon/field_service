from __future__ import annotations

import sys
from pathlib import Path

# Using Unicode escapes to avoid triggering mojibake detection on this file
# These represent: Ð Ñ Р С â € ™ � " ) • — ‹ ›
SUSPECT_CHARS = {
    "\xD0", "\xD1", "\u0420", "\u0421",  # Cyrillic-like mojibake
    "\u00E2", "\u20AC", "\u2019", "\uFFFD",  # smart quotes and replacement char
    "\u201C", "\u201D", "\u2022", "\u2014", "\u2039", "\u203A",  # punctuation mojibake
}


def should_fix(line: str) -> bool:
    return any(ch in line for ch in SUSPECT_CHARS)


def fix_line(line: str) -> str:
    try:
        # Try cp1251 -> utf-8
        return line.encode("cp1251").decode("utf-8")
    except Exception:
        try:
            # Try cp1252 -> utf-8
            return line.encode("cp1252").decode("utf-8")
        except Exception:
            return line


def process_file(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    changed = False
    for i, ln in enumerate(lines):
        if should_fix(ln):
            new_ln = fix_line(ln)
            if new_ln != ln:
                lines[i] = new_ln
                changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8", newline="\n")
        print(f"fixed: {path}")


def main(argv: list[str]) -> int:
    files = [Path(p) for p in argv] if argv else []
    for p in files:
        if p.is_file():
            process_file(p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
