from __future__ import annotations

import sys
from pathlib import Path

SUSPECT_CHARS = set("ÐÑРСâ€™�“)•—‹›")


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

