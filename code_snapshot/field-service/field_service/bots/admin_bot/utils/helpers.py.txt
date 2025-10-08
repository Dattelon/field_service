from __future__ import annotations

from typing import Any

from ..infrastructure.registry import get_service as registry_get


def get_service(bot: Any, key: str, *, required: bool = True) -> Any:
    services = getattr(bot, "_services", None)
    svc = None
    if isinstance(services, dict):
        svc = services.get(key)
    if svc is None:
        svc = registry_get(key)
    if not svc and required:
        raise RuntimeError(f"Service '{key}' is not configured on bot instance")
    return svc
