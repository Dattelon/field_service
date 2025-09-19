from __future__ import annotations

from sqlalchemy import bindparam
from sqlalchemy.dialects import postgresql


def enum_param(name: str, value, enum_name: str):
    """
    Create a typed bind parameter for a PostgreSQL ENUM.

    Avoids driver inferring VARCHAR and causing enum comparison errors.
    """
    return bindparam(name, value, type_=postgresql.ENUM(name=enum_name, create_type=False))


def commission_status_param(name: str, value):
    return enum_param(name, value, "commission_status")


def staff_role_param(name: str, value):
    return enum_param(name, value, "staff_role")


def order_status_param(name: str, value):
    return enum_param(name, value, "order_status")
