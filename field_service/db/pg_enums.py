from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import bindparam
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import BindParameter


def enum_param(name: str, value: Any, enum_name: str) -> BindParameter[Any]:
    """Create a typed bind parameter for a PostgreSQL ENUM."""
    return bindparam(
        name,
        value,
        type_=postgresql.ENUM(name=enum_name, create_type=False),
    )


def commission_status_param(name: str, value: Any) -> BindParameter[Any]:
    return enum_param(name, value, "commission_status")


def staff_role_param(name: str, value: Any) -> BindParameter[Any]:
    return enum_param(name, value, "staff_role")


def order_status_param(name: str, value: Any) -> BindParameter[Any]:
    return enum_param(name, value, "order_status")


class OrderCategory(StrEnum):
    ELECTRICS = "ELECTRICS"
    PLUMBING = "PLUMBING"
    APPLIANCES = "APPLIANCES"
    WINDOWS = "WINDOWS"
    HANDYMAN = "HANDYMAN"
    ROADSIDE = "ROADSIDE"
