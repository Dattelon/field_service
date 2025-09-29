from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from field_service.db import OrderCategory

from .services_db import AutoAssignResult

@dataclass(slots=True)
class StubStaffUser:
    id: int
    tg_id: int
    role: str
    is_active: bool
    city_ids: frozenset[int]


class StubStaffService:
    async def get_by_tg_id(self, tg_id: int) -> Optional[StubStaffUser]:
        return None


class StubOrdersService:
    async def list_queue(
        self,
        *,
        city_ids: Optional[Iterable[int]],
        page: int,
        page_size: int,
        status_filter: Optional[object] = None,
        category: Optional[OrderCategory] = None,
        master_id: Optional[int] = None,
        timeslot_date: Optional[object] = None,
    ) -> tuple[list[object], bool]:
        return [], False

    async def list_cities(
        self, *, query: Optional[str] = None, limit: int = 20
    ) -> list[object]:
        return []

    async def get_city(self, city_id: int) -> Optional[object]:
        return None

    async def list_districts(
        self, city_id: int, *, page: int, page_size: int
    ) -> tuple[list[object], bool]:
        return [], False

    async def get_district(self, district_id: int) -> Optional[object]:
        return None

    async def search_streets(
        self, city_id: int, query: str, *, limit: int = 10
    ) -> list[object]:
        return []

    async def get_street(self, street_id: int) -> Optional[object]:
        return None

    async def create_order(self, data) -> int:
        return 0

    async def get_card(self, order_id: int, *, city_ids: Optional[Iterable[int]] = None) -> Optional[object]:
        return None

    async def return_to_search(self, order_id: int, by_staff_id: int) -> bool:
        return False

    async def cancel(self, order_id: int, reason: str, by_staff_id: int) -> bool:
        return False

    async def assign_master(
        self, order_id: int, master_id: int, by_staff_id: int
    ) -> bool:
        return False


class StubDistributionService:
    async def assign_auto(self, order_id: int, by_staff_id: int) -> tuple[bool, AutoAssignResult]:
        return False, AutoAssignResult("service is not configured", code="not_configured")


class StubFinanceService:
    async def list_commissions(
        self,
        segment: str,
        *,
        page: int,
        page_size: int,
        city_ids: Optional[Iterable[int]],
    ) -> tuple[list[str], bool]:
        return [], False

    async def get_commission_detail(self, commission_id: int) -> Optional[object]:
        return None

    async def approve(self, commission_id: int, by_staff_id: int) -> bool:
        return False

    async def reject(self, commission_id: int, reason: str, by_staff_id: int) -> bool:
        return False

    async def block_master_for_overdue(self, master_id: int, by_staff_id: int) -> bool:
        return False


class StubSettingsService:
    async def get_owner_pay_requisites(self, *, staff_id: int | None = None) -> dict[str, object]:
        return {}

    async def update_owner_pay_requisites(self, staff_id: int, payload: dict[str, object]) -> None:
        return None

    async def get_owner_pay_snapshot(self) -> dict[str, object]:
        return {}

    async def update_owner_pay_snapshot(self, **payload: object) -> None:
        return None

    async def get_channel_settings(self) -> dict[str, Optional[int]]:
        return {"alerts_channel_id": None, "logs_channel_id": None, "reports_channel_id": None}

    async def get_values(self, keys: Sequence[str]) -> dict[str, tuple[str, str]]:
        return {}

    async def set_value(self, key: str, value: object, *, value_type: str = "STR") -> None:
        return None
