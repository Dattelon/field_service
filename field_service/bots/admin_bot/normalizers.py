from __future__ import annotations

import re
from typing import Iterable, Mapping, MutableMapping

from field_service.db import OrderCategory
from field_service.db.models import OrderStatus

__all__ = ["normalize_category", "normalize_status"]


def _simplify_token(raw: str) -> str:
    """Return an uppercase token without spaces/underscores/hyphens."""
    normalized = raw.strip()
    if not normalized:
        return ""
    normalized = normalized.replace("ё", "е").replace("Ё", "Е")
    normalized = re.sub(r"[\s_\-]+", "", normalized)
    return normalized.upper()


def _build_category_map() -> Mapping[str, OrderCategory]:
    aliases: MutableMapping[str, OrderCategory] = {}
    alias_pairs: Iterable[tuple[str, OrderCategory]] = (
        (OrderCategory.ELECTRICS.value, OrderCategory.ELECTRICS),
        ("electrics", OrderCategory.ELECTRICS),
        ("elec", OrderCategory.ELECTRICS),
        ("электрика", OrderCategory.ELECTRICS),
        ("электр", OrderCategory.ELECTRICS),
        (OrderCategory.PLUMBING.value, OrderCategory.PLUMBING),
        ("plumbing", OrderCategory.PLUMBING),
        ("plumb", OrderCategory.PLUMBING),
        ("сантехника", OrderCategory.PLUMBING),
        ("сантех", OrderCategory.PLUMBING),
        (OrderCategory.APPLIANCES.value, OrderCategory.APPLIANCES),
        ("appliances", OrderCategory.APPLIANCES),
        ("appli", OrderCategory.APPLIANCES),
        ("бытовая техника", OrderCategory.APPLIANCES),
        ("техника", OrderCategory.APPLIANCES),
        (OrderCategory.WINDOWS.value, OrderCategory.WINDOWS),
        ("windows", OrderCategory.WINDOWS),
        ("окна", OrderCategory.WINDOWS),
        (OrderCategory.HANDYMAN.value, OrderCategory.HANDYMAN),
        ("handyman", OrderCategory.HANDYMAN),
        ("handy", OrderCategory.HANDYMAN),
        ("универсал", OrderCategory.HANDYMAN),
        ("furn", OrderCategory.HANDYMAN),
        ("furniture", OrderCategory.HANDYMAN),
        (OrderCategory.ROADSIDE.value, OrderCategory.ROADSIDE),
        ("roadside", OrderCategory.ROADSIDE),
        ("autohelp", OrderCategory.ROADSIDE),
        ("auto_help", OrderCategory.ROADSIDE),
        ("автопомощь", OrderCategory.ROADSIDE),
    )
    for alias, category in alias_pairs:
        simplified = _simplify_token(alias)
        if simplified:
            aliases.setdefault(simplified, category)
    for category in OrderCategory:
        aliases.setdefault(_simplify_token(category.value), category)
    return aliases


_CATEGORY_MAP = _build_category_map()

LEGACY_STATUS_ALIASES: Mapping[str, OrderStatus] = {
    "DISTRIBUTION": OrderStatus.SEARCHING,
    "SCHEDULED": OrderStatus.EN_ROUTE,
    "INPROGRESS": OrderStatus.WORKING,
    "IN_PROGRESS": OrderStatus.WORKING,
    "DONE": OrderStatus.PAYMENT,
}


def normalize_category(
    value: OrderCategory | str | None,
    *,
    default: OrderCategory | None = None,
) -> OrderCategory | None:
    if value is None:
        return default
    if isinstance(value, OrderCategory):
        return value
    raw = str(value).strip()
    if not raw:
        return default
    try:
        return OrderCategory(raw)
    except ValueError:
        pass
    try:
        return OrderCategory(raw.upper())
    except ValueError:
        pass
    simplified = _simplify_token(raw)
    category = _CATEGORY_MAP.get(simplified)
    if category:
        return category
    return default


def normalize_status(
    value: OrderStatus | str | None,
    *,
    default: OrderStatus | None = None,
) -> OrderStatus | None:
    if value is None:
        return default
    if isinstance(value, OrderStatus):
        return value
    raw = str(value).strip()
    if not raw:
        return default
    upper = raw.upper()
    alias = LEGACY_STATUS_ALIASES.get(upper)
    if alias:
        return alias
    try:
        return OrderStatus(upper)
    except ValueError:
        pass
    try:
        return OrderStatus(raw)
    except ValueError:
        return default
