from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from field_service.bots.admin_bot.access import visible_city_ids_for
from field_service.bots.admin_bot.dto import StaffRole, StaffUser
from field_service.bots.admin_bot.middlewares import (
    ACCESS_PROMPT,
    INACTIVE_PROMPT,
    StaffAccessMiddleware,
)
from field_service.bots.admin_bot.services_db import DBOrdersService, DBStaffService, AccessCodeError
from field_service.db import models as m

UTC = timezone.utc



@pytest.mark.asyncio
async def test_seed_global_admins_inserts_once(async_session) -> None:
    session_maker = async_sessionmaker(async_session.bind, expire_on_commit=False)
    service = DBStaffService(session_factory=session_maker)

    inserted = await service.seed_global_admins([111, 222])
    assert inserted == 2

    rows = await async_session.execute(select(m.staff_users.tg_user_id))
    tg_ids = {int(row[0]) for row in rows}
    assert tg_ids == {111, 222}

    second = await service.seed_global_admins([222, 333])
    assert second == 0

    remaining = await async_session.scalar(select(func.count()).select_from(m.staff_users))
    assert int(remaining or 0) == 2


@pytest.mark.asyncio
async def test_visible_city_ids_helper() -> None:
    global_staff = StaffUser(
        id=1,
        tg_id=10,
        role=StaffRole.GLOBAL_ADMIN,
        is_active=True,
        city_ids=frozenset({1, 2}),
    )
    assert visible_city_ids_for(global_staff) is None

    city_staff = StaffUser(
        id=2,
        tg_id=11,
        role=StaffRole.CITY_ADMIN,
        is_active=True,
        city_ids=frozenset({5, 3}),
    )
    assert visible_city_ids_for(city_staff) == [3, 5]

    logist_staff = StaffUser(
        id=3,
        tg_id=12,
        role=StaffRole.LOGIST,
        is_active=True,
        city_ids=frozenset(),
    )
    assert visible_city_ids_for(logist_staff) == []


@pytest.mark.asyncio
async def test_queue_visibility_by_city(async_session) -> None:
    session_maker = async_sessionmaker(async_session.bind, expire_on_commit=False)
    orders_service = DBOrdersService(session_factory=session_maker)

    city_a = m.cities(name="City A")
    city_b = m.cities(name="City B")
    async_session.add_all([city_a, city_b])
    await async_session.flush()

    order_a = m.orders(
        city_id=city_a.id,
        status=m.OrderStatus.SEARCHING,
        order_type=m.OrderType.NORMAL,
        client_name="Client A",
        client_phone="+70000000001",
        description="Issue A",
        total_price=Decimal("0"),
        created_at=datetime.now(UTC),
    )
    order_b = m.orders(
        city_id=city_b.id,
        status=m.OrderStatus.SEARCHING,
        order_type=m.OrderType.NORMAL,
        client_name="Client B",
        client_phone="+70000000002",
        description="Issue B",
        total_price=Decimal("0"),
        created_at=datetime.now(UTC),
    )
    async_session.add_all([order_a, order_b])
    await async_session.commit()

    city_staff = StaffUser(
        id=5,
        tg_id=101,
        role=StaffRole.CITY_ADMIN,
        is_active=True,
        city_ids=frozenset({city_a.id}),
    )
    city_items, has_next = await orders_service.list_queue(
        city_ids=visible_city_ids_for(city_staff),
        page=1,
        page_size=10,
    )
    assert has_next is False
    assert [item.city_id for item in city_items] == [city_a.id]

    logist_staff = StaffUser(
        id=6,
        tg_id=102,
        role=StaffRole.LOGIST,
        is_active=True,
        city_ids=frozenset(),
    )
    logist_items, logist_next = await orders_service.list_queue(
        city_ids=visible_city_ids_for(logist_staff),
        page=1,
        page_size=10,
    )
    assert logist_items == []
    assert logist_next is False

    global_staff = StaffUser(
        id=7,
        tg_id=103,
        role=StaffRole.GLOBAL_ADMIN,
        is_active=True,
        city_ids=frozenset(),
    )
    global_items, _ = await orders_service.list_queue(
        city_ids=visible_city_ids_for(global_staff),
        page=1,
        page_size=10,
    )
    assert {item.city_id for item in global_items} == {city_a.id, city_b.id}


class _DummyMessage:
    def __init__(self, user_id: int) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.messages: list[str] = []

    async def answer(self, text: str) -> None:
        self.messages.append(text)


@pytest.mark.asyncio
async def test_inactive_staff_blocked_by_middleware(async_session) -> None:
    await async_session.execute(
        insert(m.staff_users),
        [
            {
                "tg_user_id": 555,
                "role": m.StaffRole.ADMIN.value,
                "is_active": False,
            }
        ],
    )
    await async_session.commit()

    session_maker = async_sessionmaker(async_session.bind, expire_on_commit=False)
    service = DBStaffService(session_factory=session_maker)
    middleware = StaffAccessMiddleware(service, superusers=())

    event = _DummyMessage(user_id=555)
    handler_called = False

    async def handler(_, __):
        nonlocal handler_called
        handler_called = True

    await middleware(handler, event, {})

    assert handler_called is False
    assert event.messages == [INACTIVE_PROMPT]


@pytest.mark.asyncio
async def test_unknown_staff_prompt_code(async_session) -> None:
    session_maker = async_sessionmaker(async_session.bind, expire_on_commit=False)
    service = DBStaffService(session_factory=session_maker)
    middleware = StaffAccessMiddleware(service, superusers=())

    event = _DummyMessage(user_id=999)
    handler_called = False

    async def handler(_, __):
        nonlocal handler_called
        handler_called = True

    await middleware(handler, event, {})

    assert handler_called is True
    assert event.messages == []


class _DummyCallback:
    def __init__(self, user_id: int) -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.alerts: list[str] = []
        self.messages: list[str] = []
        self.message = SimpleNamespace(answer=self._store_message)

    async def answer(self, text: str, show_alert: bool = False) -> None:
        if show_alert:
            self.alerts.append(text)
        else:
            self.messages.append(text)

    async def _store_message(self, text: str) -> None:
        self.messages.append(text)


@pytest.mark.asyncio
async def test_unknown_staff_callback_prompts(async_session) -> None:
    session_maker = async_sessionmaker(async_session.bind, expire_on_commit=False)
    service = DBStaffService(session_factory=session_maker)
    middleware = StaffAccessMiddleware(service, superusers=())

    event = _DummyCallback(user_id=404)
    handler_called = False

    async def handler(_, __):
        nonlocal handler_called
        handler_called = True

    await middleware(handler, event, {})

    assert handler_called is False
    combined = event.alerts + event.messages
    assert combined == [ACCESS_PROMPT]


@pytest.mark.asyncio
async def test_access_code_issue_and_use(async_session) -> None:
    session_maker = async_sessionmaker(async_session.bind, expire_on_commit=False)
    staff_service = DBStaffService(session_factory=session_maker, access_code_ttl_hours=1)

    city = m.cities(name="Alpha")
    issuer = m.staff_users(tg_user_id=500, role=m.StaffRole.ADMIN.value, is_active=True)
    async_session.add_all([city, issuer])
    await async_session.commit()

    code = await staff_service.create_access_code(
        role=StaffRole.CITY_ADMIN,
        city_ids=[city.id],
        issued_by_staff_id=issuer.id,
        expires_at=None,
        comment=None,
    )
    assert code.expires_at is not None

    validated = await staff_service.validate_access_code_value(code.code)
    assert validated is not None
    assert validated.city_ids == (city.id,)

    new_staff = await staff_service.register_staff_user_from_code(
        code_value=code.code,
        tg_user_id=700,
        username="city_manager",
        full_name="City Manager",
        phone="+79990000000",
    )
    assert new_staff.tg_id == 700
    assert new_staff.role is StaffRole.CITY_ADMIN
    assert set(new_staff.city_ids) == {city.id}

    city_rows = await async_session.execute(
        select(m.staff_cities.city_id).where(m.staff_cities.staff_user_id == new_staff.id)
    )
    assert {int(row[0]) for row in city_rows} == {city.id}

    assert await staff_service.validate_access_code_value(code.code) is None

    with pytest.raises(AccessCodeError):
        await staff_service.register_staff_user_from_code(
            code_value=code.code,
            tg_user_id=701,
            username="other_user",
            full_name="Other User",
            phone="+79990000001",
        )

    zero_ttl_service = DBStaffService(session_factory=session_maker, access_code_ttl_hours=0)
    code_without_expiry = await zero_ttl_service.create_access_code(
        role=StaffRole.CITY_ADMIN,
        city_ids=[city.id],
        issued_by_staff_id=issuer.id,
        expires_at=None,
        comment=None,
    )
    assert code_without_expiry.expires_at is None
