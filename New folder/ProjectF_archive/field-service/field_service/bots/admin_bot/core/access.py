from __future__ import annotations

from typing import Optional

from .dto import StaffRole, StaffUser


def visible_city_ids_for(staff: StaffUser) -> Optional[list[int]]:
    if staff.role is StaffRole.GLOBAL_ADMIN:
        return None
    if not staff.city_ids:
        return []
    return sorted(int(city_id) for city_id in staff.city_ids)


__all__ = ["visible_city_ids_for"]
