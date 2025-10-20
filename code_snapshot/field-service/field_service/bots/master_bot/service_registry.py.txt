from __future__ import annotations

from typing import Any

_SERVICES: dict[str, Any] = {}


def register_service(key: str, service: Any) -> None:
    _SERVICES[key] = service


def register_services(mapping: dict[str, Any]) -> None:
    _SERVICES.update(mapping)


def get_service(key: str) -> Any | None:
    return _SERVICES.get(key)
