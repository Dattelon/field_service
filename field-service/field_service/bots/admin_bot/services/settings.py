"""Settings service: system configuration management."""
from __future__ import annotations

import json
from datetime import time
from typing import Any, Optional, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import time_service
from field_service.services import settings_service as settings_store
from field_service.services import owner_requisites_service as owner_reqs
from field_service.services._session_utils import maybe_managed_session


# Common utilities from _common
from ._common import (
    UTC,
    QUEUE_STATUSES,
    ACTIVE_ORDER_STATUSES,
    AVG_CHECK_STATUSES,
    STREET_DUPLICATE_THRESHOLD,
    STREET_MIN_SCORE,
    PAYMENT_METHOD_LABELS,
    OWNER_PAY_SETTING_FIELDS,
    _is_column_missing_error,
    _normalize_street_name,
    _format_datetime_local,
    _format_created_at,
    _zone_storage_value,
    _workday_window,
    _load_staff_access,
    _visible_city_ids_for_staff,
    _staff_can_access_city,
    _load_staff_city_map,
    _collect_code_cities,
    _prepare_setting_value,
    _raw_order_type,
    _map_staff_role,
    _map_staff_role_to_db,
    _sorted_city_tuple,
    _order_type_from_db,
    _map_order_type_to_db,
    _attachment_type_from_string,
    _generate_staff_code,
    _push_dist_log,
    _coerce_order_status,
)


class DBSettingsService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def get_channel_settings(self) -> dict[str, Optional[int]]:
        keys = ("alerts_channel_id", "logs_channel_id", "reports_channel_id")
        async with self._session_factory() as session:
            rows = await session.execute(
                select(m.settings.key, m.settings.value).where(m.settings.key.in_(keys))
            )
            result: dict[str, Optional[int]] = {key: None for key in keys}
            for key, value in rows:
                try:
                    result[str(key)] = int(value) if value is not None else None
                except (TypeError, ValueError):
                    result[str(key)] = None
            return result



    async def get_values(self, keys: Sequence[str]) -> dict[str, tuple[str, str]]:
        if not keys:
            return {}
        async with self._session_factory() as session:
            rows = await session.execute(
                select(m.settings.key, m.settings.value, m.settings.value_type).where(
                    m.settings.key.in_(list(keys))
                )
            )
            return {row[0]: (row[1], row[2]) for row in rows}

    async def get_owner_pay_snapshot(self) -> dict[str, Any]:
        keys = [setting_key for setting_key, _ in OWNER_PAY_SETTING_FIELDS.values()]
        async with self._session_factory() as session:
            rows = await session.execute(
                select(m.settings.key, m.settings.value, m.settings.value_type).where(
                    m.settings.key.in_(keys)
                )
            )
            raw_values = {row[0]: (row[1], row[2]) for row in rows}
        snapshot: dict[str, Any] = {}
        for field, (setting_key, expected_type) in OWNER_PAY_SETTING_FIELDS.items():
            value, stored_type = raw_values.get(setting_key, (None, expected_type))
            value_type = (stored_type or expected_type).upper()
            if value_type == 'JSON':
                try:
                    parsed = json.loads(value) if value else []
                except (TypeError, json.JSONDecodeError):
                    parsed = []
                snapshot[field] = parsed
            else:
                snapshot[field] = value or ''
        return owner_reqs.ensure_schema(snapshot)

    async def update_owner_pay_snapshot(self, **payload: Any) -> None:
        normalized = owner_reqs.ensure_schema(payload)
        values: dict[str, tuple[object, str]] = {}
        for field, (setting_key, value_type) in OWNER_PAY_SETTING_FIELDS.items():
            values[setting_key] = (normalized.get(field), value_type)
        await settings_store.set_values(values)

    async def set_value(self, key: str, value: object, *, value_type: str = "STR", session: Optional[AsyncSession] = None) -> None:
        normalized = settings_store._normalize_value_type(value_type)
        payload = settings_store._serialize_value(value, normalized)

        async def _apply(s: AsyncSession) -> None:
            stmt = insert(m.settings).values(key=key, value=payload, value_type=normalized)
            if hasattr(stmt, "on_conflict_do_update"):
                stmt = stmt.on_conflict_do_update(
                    index_elements=[m.settings.key],
                    set_={"value": payload, "value_type": normalized},
                )
                await s.execute(stmt)
            else:
                existing = await s.execute(
                    select(m.settings).where(m.settings.key == key)
                )
                if existing.scalar_one_or_none():
                    await s.execute(
                        update(m.settings)
                        .where(m.settings.key == key)
                        .values(value=payload, value_type=normalized)
                    )
                else:
                    await s.execute(
                        insert(m.settings).values(
                            key=key,
                            value=payload,
                            value_type=normalized,
                        )
                    )

        async with maybe_managed_session(session) as s:
            for attempt in range(2):
                try:
                    await _apply(s)
                except OperationalError as exc:
                    message = str(exc).lower()
                    if "no such table" in message and "settings" in message and attempt == 0:
                        await s.run_sync(
                            lambda sync_session: m.settings.__table__.create(
                                sync_session.connection(), checkfirst=True
                            )
                        )
                        continue
                    raise
                else:
                    break
        settings_store.invalidate_working_window_cache()


    async def get_owner_pay_requisites(self, *, staff_id: int | None = None) -> dict[str, Any]:
        async with self._session_factory() as session:
            if staff_id is not None:
                data = await owner_reqs.fetch_for_staff(session, staff_id)
                if not owner_reqs.is_default(data):
                    return data
            return await owner_reqs.fetch_effective(session)

    async def update_owner_pay_requisites(self, staff_id: int, payload: dict[str, Any], *, session: Optional[AsyncSession] = None) -> None:
        async with maybe_managed_session(session) as s:
            await owner_reqs.update_for_staff(s, staff_id, payload)


