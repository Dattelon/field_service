from __future__ import annotations

import pytest

from field_service.bots.admin_bot import queue
from field_service.bots.admin_bot.dto import CityRef, StaffRole, StaffUser


class DummyOrdersService:
    def __init__(self, cities: list[CityRef]) -> None:
        self._cities = {city.id: city for city in cities}

    async def list_cities(self, *, query: str | None = None, limit: int = 20):
        return list(self._cities.values())[:limit]

    async def get_city(self, city_id: int):
        return self._cities.get(city_id)


def _staff(role: StaffRole, city_ids: set[int] | frozenset[int]):
    return StaffUser(
        id=1,
        tg_id=1,
        role=role,
        is_active=True,
        city_ids=frozenset(city_ids),
    )


@pytest.mark.asyncio
async def test_available_cities_for_global_admin():
    cities = [CityRef(id=1, name="Москва"), CityRef(id=2, name="Казань")]
    service = DummyOrdersService(cities)
    staff = _staff(StaffRole.GLOBAL_ADMIN, frozenset())

    result = await queue._available_cities(staff, service)

    assert [city.id for city in result] == [1, 2]


@pytest.mark.asyncio
async def test_available_cities_for_city_admin():
    cities = [CityRef(id=1, name="Москва"), CityRef(id=2, name="Казань"), CityRef(id=3, name="Пермь")]
    service = DummyOrdersService(cities)
    staff = _staff(StaffRole.CITY_ADMIN, {2, 3})

    result = await queue._available_cities(staff, service)

    assert [city.id for city in result] == [2, 3]
