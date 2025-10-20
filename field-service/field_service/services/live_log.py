from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

__all__ = ["LiveLogEntry", "push", "snapshot", "clear", "size"]


@dataclass(slots=True)
class LiveLogEntry:
    timestamp: datetime
    source: str
    message: str
    level: str = "INFO"


_BUFFER = deque[LiveLogEntry](maxlen=200)
UTC = timezone.utc


def push(source: str, message: str, *, level: str = "INFO") -> None:
    """Add a log line to the in-memory buffer."""
    entry = LiveLogEntry(
        timestamp=datetime.now(UTC),
        source=source,
        message=message,
        level=level.upper(),
    )
    _BUFFER.append(entry)


def snapshot(limit: int = 50) -> List[LiveLogEntry]:
    """Return up to *limit* recent log entries (most recent last)."""
    if limit <= 0:
        return []
    return list(_BUFFER)[-limit:]


def clear() -> None:
    """Remove all stored entries."""
    _BUFFER.clear()


def size() -> int:
    """Current number of cached log entries."""
    return len(_BUFFER)
