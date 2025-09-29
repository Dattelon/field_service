from __future__ import annotations

import sys
from pathlib import Path

# Heuristic set of characters typical for UTF-8cp1251 mojibake
SUSPICIOUS_CHARS = set("℁")


def looks_mojibake(text: str) -> bool:
    count = sum(1 for ch in text if ch in SUSPICIOUS_CHARS)
    return count >= 3


def try_fix(text: str) -> str:
    try:
        fixed = text.encode("cp1251", errors="ignore").decode("utf-8", errors="ignore")
        return fixed if fixed else text
    except Exception:
        return text


def main(root: str) -> int:
    root_path = Path(root)
    changed = 0
    for path in root_path.rglob("*.py"):
        if ".venv" in path.parts or ".git" in path.parts:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not looks_mojibake(original):
            continue
        fixed = try_fix(original)
        # Accept only if mojibake density decreased (to avoid damaging good files)
        def density(s: str) -> int:
            return sum(1 for ch in s if ch in SUSPICIOUS_CHARS)

        if density(fixed) < density(original):
            path.write_text(fixed, encoding="utf-8", newline="\n")
            changed += 1
            print(f"fixed: {path}")
    print(f"done, files changed={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))

