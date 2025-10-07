from __future__ import annotations

import sys
from pathlib import Path

# Heuristic set of characters typical for UTF-8↔cp1251 mojibake
# Common artifacts: 'Ð', 'Ñ', 'Р', 'С', '�', and cp1252 quotes/dashes.
SUSPICIOUS_CHARS = set("ÐÑРС�â€™”“•—‹›�")


def looks_mojibake(text: str) -> bool:
    count = sum(1 for ch in text if ch in SUSPICIOUS_CHARS)
    return count >= 3


def try_fix(text: str) -> str:
    # Typical fix for UTF-8 bytes mis-decoded as cp1251 -> now in Unicode
    # Encode back to cp1251 bytes, then decode as UTF-8
    try:
        fixed = text.encode("cp1251", errors="ignore").decode("utf-8", errors="ignore")
        return fixed if fixed else text
    except Exception:
        return text


def main(root: str) -> int:
    root_path = Path(root)
    changed = 0
    for path in root_path.rglob("*.py"):
        if any(part in {".venv", ".git", "__pycache__"} for part in path.parts):
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not looks_mojibake(original):
            continue
        fixed = try_fix(original)

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

