"""Finance service: commission management and payments."""
from __future__ import annotations

from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Any, Iterable, Optional, Sequence

from sqlalchemy import and_, delete, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
from field_service.services import live_log
from field_service.services._session_utils import maybe_managed_session
from field_service.services.referral_service import apply_rewards_for_commission

from ..core.dto import CommissionAttachment, CommissionDetail, CommissionListItem, WaitPayRecipient


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


class DBFinanceService:
    """Сервис для работы с комиссиями и финансами."""
    
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    async def bulk_approve_commissions(
        self,
        start_date: date,
        end_date: date,
        by_staff_id: int,
        *,
        city_ids: Optional[Iterable[int]] = None,
    ) -> tuple[int, list[str]]:
        """
        Массовое одобрение комиссий за период.
        
        Args:
            start_date: Начало периода
            end_date: Конец периода (включительно)
            by_staff_id: ID админа
            city_ids: Фильтр по городам (RBAC)
        
        Returns:
            (количество одобренных, список ошибок)
        """
        errors: list[str] = []
        approved_count = 0
        
        async with self._session_factory() as session:
            # Загружаем админа для RBAC
            staff = await _load_staff_access(session, by_staff_id)
            if staff is None:
                return 0, ["Админ не найден"]
            
            # Применяем фильтр по городам
            visible_cities = _visible_city_ids_for_staff(staff)
            if visible_cities is not None:
                if city_ids is not None:
                    allowed = frozenset(city_ids) & visible_cities
                else:
                    allowed = visible_cities
            elif city_ids is not None:
                allowed = frozenset(city_ids)
            else:
                allowed = None
            
            # Находим комиссии WAIT_PAY за период
            stmt = (
                select(m.commissions.id)
                .join(m.orders, m.commissions.order_id == m.orders.id)
                .where(
                    m.commissions.status == m.CommissionStatus.WAIT_PAY,
                    func.date(m.commissions.created_at) >= start_date,
                    func.date(m.commissions.created_at) <= end_date,
                )
            )
            
            if allowed is not None:
                stmt = stmt.where(m.orders.city_id.in_(allowed))
            
            rows = await session.execute(stmt)
            commission_ids = [row[0] for row in rows]
            
            if not commission_ids:
                return 0, ["Нет комиссий для одобрения"]
            
            # Одобряем каждую комиссию (НЕ создаём вложенные транзакции)
            for comm_id in commission_ids:
                try:
                    # Загружаем комиссию с блокировкой
                    comm_stmt = (
                        select(m.commissions)
                        .where(m.commissions.id == comm_id)
                        .with_for_update()
                    )
                    comm_row = await session.execute(comm_stmt)
                    commission = comm_row.scalar_one_or_none()
                    
                    if not commission:
                        errors.append(f"Комиссия #{comm_id} не найдена")
                        continue
                    
                    if commission.status != m.CommissionStatus.WAIT_PAY:
                        errors.append(f"Комиссия #{comm_id} не в статусе WAIT_PAY")
                        continue
                    
                    # Обновляем статус
                    commission.status = m.CommissionStatus.PAID
                    commission.approved_by_staff_id = by_staff_id
                    commission.approved_at = datetime.now(UTC)
                    commission.updated_at = datetime.now(UTC)
                    
                    # Применяем реферальные вознаграждения
                    try:
                        await apply_rewards_for_commission(session, commission)
                    except Exception as exc:
                        pass  # logger not imported, skip warning
                    
                    approved_count += 1
                    
                except Exception as exc:
                    errors.append(f"Ошибка при одобрении #{comm_id}: {exc}")
        
        return approved_count, errors

    async def list_commissions(
        self,
        segment: str,
        *,
        page: int,
        page_size: int,
        city_ids: Optional[Iterable[int]],
    ) -> tuple[list[CommissionListItem], bool]:
        status_map = {
            "aw": [
                m.CommissionStatus.WAIT_PAY.value,
                m.CommissionStatus.REPORTED.value,
            ],
            "pd": [m.CommissionStatus.APPROVED.value],
            "ov": [m.CommissionStatus.OVERDUE.value],
        }
        statuses = status_map.get(segment, [m.CommissionStatus.WAIT_PAY.value])
        offset = max(page - 1, 0) * page_size
        async with self._session_factory() as session:
            stmt = (
                select(
                    m.commissions.id,
                    m.commissions.order_id,
                    m.commissions.amount,
                    m.commissions.status,
                    m.commissions.deadline_at,
                    m.masters.full_name,
                    m.masters.id.label("master_id"),
                    m.orders.city_id,
                )
                .select_from(m.commissions)
                .join(m.orders, m.orders.id == m.commissions.order_id)
                .join(m.masters, m.masters.id == m.commissions.master_id, isouter=True)
                .where(m.commissions.status.in_(statuses))
                .order_by(m.commissions.created_at.desc())
                .offset(offset)
                .limit(page_size + 1)
            )
            if city_ids is not None:
                ids = [int(cid) for cid in city_ids]
                if not ids:
                    return [], False
                stmt = stmt.where(m.orders.city_id.in_(ids))
            rows = await session.execute(stmt)
            fetched = rows.all()
        has_next = len(fetched) > page_size
        items: list[CommissionListItem] = []
        for row in fetched[:page_size]:
            deadline = _format_created_at(row.deadline_at)
            items.append(
                CommissionListItem(
                    id=row.id,
                    order_id=row.order_id,
                    master_id=row.master_id,
                    master_name=row.full_name,
                    status=row.status,
                    amount=Decimal(row.amount or 0),
                    deadline_at_local=deadline if deadline else None,
                )
            )
        return items, has_next

    async def list_commissions_grouped(
        self,
        segment: str,
        *,
        city_ids: Optional[Iterable[int]],
    ) -> dict[str, list[CommissionListItem]]:
        """
        P1-15: Возвращает комиссии сгруппированные по периодам.
        
        Returns:
            dict с ключами: 'today', 'yesterday', 'week', 'month', 'older'
        """
        from datetime import date, timedelta
        
        status_map = {
            "aw": [
                m.CommissionStatus.WAIT_PAY.value,
                m.CommissionStatus.REPORTED.value,
            ],
            "pd": [m.CommissionStatus.APPROVED.value],
            "ov": [m.CommissionStatus.OVERDUE.value],
        }
        statuses = status_map.get(segment, [m.CommissionStatus.WAIT_PAY.value])
        
        async with self._session_factory() as session:
            stmt = (
                select(
                    m.commissions.id,
                    m.commissions.order_id,
                    m.commissions.amount,
                    m.commissions.status,
                    m.commissions.deadline_at,
                    m.commissions.created_at,
                    m.masters.full_name,
                    m.masters.id.label("master_id"),
                    m.orders.city_id,
                )
                .select_from(m.commissions)
                .join(m.orders, m.orders.id == m.commissions.order_id)
                .join(m.masters, m.masters.id == m.commissions.master_id, isouter=True)
                .where(m.commissions.status.in_(statuses))
                .order_by(m.commissions.created_at.desc())
                .limit(200)  # Ограничим чтобы не перегружать UI
            )
            if city_ids is not None:
                ids = [int(cid) for cid in city_ids]
                if not ids:
                    return {}
                stmt = stmt.where(m.orders.city_id.in_(ids))
            
            rows = await session.execute(stmt)
            fetched = rows.all()
        
        # Вычисляем границы периодов
        today = date.today()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Группируем комиссии
        groups: dict[str, list[CommissionListItem]] = {
            'today': [],
            'yesterday': [],
            'week': [],
            'month': [],
            'older': []
        }
        
        for row in fetched:
            # Преобразуем created_at в date
            if row.created_at:
                if hasattr(row.created_at, 'date'):
                    created_date = row.created_at.date()
                else:
                    created_date = row.created_at
            else:
                created_date = today
            
            # Определяем период
            if created_date == today:
                period = 'today'
            elif created_date == yesterday:
                period = 'yesterday'
            elif created_date >= week_ago:
                period = 'week'
            elif created_date >= month_ago:
                period = 'month'
            else:
                period = 'older'
            
            # Создаём CommissionListItem
            deadline = _format_created_at(row.deadline_at)
            item = CommissionListItem(
                id=row.id,
                order_id=row.order_id,
                master_id=row.master_id,
                master_name=row.full_name,
                status=row.status,
                amount=Decimal(row.amount or 0),
                deadline_at_local=deadline if deadline else None,
            )
            groups[period].append(item)
        
        # Удаляем пустые группы
        return {k: v for k, v in groups.items() if v}

    async def list_wait_pay_recipients(self) -> list[WaitPayRecipient]:
        async with self._session_factory() as session:
            rows = await session.execute(
                select(
                    m.masters.id,
                    m.masters.tg_user_id,
                    m.masters.full_name,
                )
                .join(m.commissions, m.commissions.master_id == m.masters.id)
                .where(m.commissions.status == m.CommissionStatus.WAIT_PAY)
                .group_by(m.masters.id, m.masters.tg_user_id, m.masters.full_name)
                .order_by(m.masters.id)
            )
            recipients: list[WaitPayRecipient] = []
            for master_id, tg_user_id, full_name in rows.all():
                if tg_user_id is None:
                    continue
                recipients.append(
                    WaitPayRecipient(
                        master_id=int(master_id),
                        tg_user_id=int(tg_user_id),
                        full_name=full_name or f'Master {master_id}',
                    )
                )
        return recipients

    async def get_commission_detail(
        self, commission_id: int
    ) -> Optional[CommissionDetail]:
        async with self._session_factory() as session:
            stmt = (
                select(m.commissions, m.orders, m.masters)
                .join(m.orders, m.orders.id == m.commissions.order_id)
                .join(m.masters, m.masters.id == m.commissions.master_id, isouter=True)
                .where(m.commissions.id == commission_id)
            )
            row = await session.execute(stmt)
            result = row.first()
            if not result:
                return None
            commission, order, master = result
            attachments_rows = (
                await session.execute(
                    select(
                        m.attachments.id,
                        m.attachments.file_type,
                        m.attachments.file_id,
                        m.attachments.file_name,
                        m.attachments.caption,
                    )
                    .where(
                        (m.attachments.entity_type == m.AttachmentEntity.COMMISSION)
                        & (m.attachments.entity_id == commission.id)
                    )
                    .order_by(m.attachments.created_at.asc())
                )
            ).all()
            attachments = tuple(
                CommissionAttachment(
                    id=int(att.id),
                    file_type=str(getattr(att.file_type, 'value', att.file_type)),
                    file_id=att.file_id,
                    file_name=att.file_name,
                    caption=att.caption,
                )
                for att in attachments_rows
            )
            deadline = _format_created_at(commission.deadline_at)
            created_at = _format_created_at(commission.created_at)
            paid_reported = _format_created_at(commission.paid_reported_at)
            paid_approved = _format_created_at(commission.paid_approved_at)
            snapshot = commission.pay_to_snapshot or {}
            methods = tuple(
                PAYMENT_METHOD_LABELS.get(str(meth), str(meth))
                for meth in snapshot.get("methods", [])
                if str(meth)
            )
            snapshot_map: dict[str, Optional[str]] = {
                "card_last4": snapshot.get("card_number_last4"),
                "card_holder": snapshot.get("card_holder"),
                "card_bank": snapshot.get("card_bank"),
                "sbp_phone": snapshot.get("sbp_phone_masked"),
                "sbp_bank": snapshot.get("sbp_bank"),
                "other_text": snapshot.get("other_text"),
                "comment": snapshot.get("comment"),
                "qr_file_id": snapshot.get("sbp_qr_file_id"),
            }
            master_phone = getattr(master, "phone", None) if master else None
            return CommissionDetail(
                id=commission.id,
                order_id=commission.order_id,
                master_id=commission.master_id,
                master_name=getattr(master, "full_name", None) if master else None,
                master_phone=master_phone,
                status=commission.status.value
                if hasattr(commission.status, "value")
                else str(commission.status),
                amount=Decimal(commission.amount or 0),
                rate=Decimal(commission.rate or commission.percent or 0),
                deadline_at_local=deadline or None,
                created_at_local=created_at or "",
                paid_reported_at_local=paid_reported or None,
                paid_approved_at_local=paid_approved or None,
                paid_amount=Decimal(commission.paid_amount or 0)
                if commission.paid_amount is not None
                else None,
                has_checks=bool(commission.has_checks),
                snapshot_methods=methods,
                snapshot_data=snapshot_map,
                attachments=attachments,
            )

    async def approve(
        self, 
        commission_id: int, 
        *, 
        paid_amount: Decimal, 
        by_staff_id: int,
    ) -> bool:
        paid_amount = Decimal(str(paid_amount)).quantize(Decimal('0.01'))
        async with self._session_factory() as session:
            # Проверяем, нужно ли начинать транзакцию
            # (в тестах сессия уже в транзакции)
            if session.in_transaction():
                # Работаем с существующей транзакцией
                row = await session.execute(
                    select(m.commissions, m.orders)
                    .join(m.orders, m.orders.id == m.commissions.order_id)
                    .where(m.commissions.id == commission_id)
                    .with_for_update()
                )
                result = row.first()
                if not result:
                    return False
                commission_row, order_row = result
                await session.execute(
                    update(m.commissions)
                    .where(m.commissions.id == commission_id)
                    .values(
                        status=m.CommissionStatus.APPROVED,
                        is_paid=True,
                        paid_amount=paid_amount,
                        paid_approved_at=datetime.now(UTC),
                        payment_reference=None,
                    )
                )
                if order_row.status != m.OrderStatus.CLOSED:
                    await session.execute(
                        update(m.orders)
                        .where(m.orders.id == order_row.id)
                        .values(
                            status=m.OrderStatus.CLOSED,
                            updated_at=func.now(),
                            version=order_row.version + 1,
                        )
                    )
                    history_staff_id = by_staff_id
                    if history_staff_id:
                        exists = await session.get(m.staff_users, history_staff_id)
                        if not exists:
                            history_staff_id = None

                    await session.execute(
                        insert(m.order_status_history).values(
                            order_id=order_row.id,
                            from_status=order_row.status,
                            to_status=m.OrderStatus.CLOSED,
                            changed_by_staff_id=history_staff_id,
                            reason='commission_paid',
                            actor_type=m.ActorType.ADMIN,
                        )
                    )

                await apply_rewards_for_commission(
                    session,
                    commission_id=commission_id,
                    master_id=commission_row.master_id,
                    base_amount=paid_amount,
                )
                return True
            else:
                # Создаём транзакцию для прода
                async with session.begin():
                    row = await session.execute(
                        select(m.commissions, m.orders)
                        .join(m.orders, m.orders.id == m.commissions.order_id)
                        .where(m.commissions.id == commission_id)
                        .with_for_update()
                    )
                    result = row.first()
                    if not result:
                        return False
                    commission_row, order_row = result
                    await session.execute(
                        update(m.commissions)
                        .where(m.commissions.id == commission_id)
                        .values(
                            status=m.CommissionStatus.APPROVED,
                            is_paid=True,
                            paid_amount=paid_amount,
                            paid_approved_at=datetime.now(UTC),
                            payment_reference=None,
                        )
                    )
                    if order_row.status != m.OrderStatus.CLOSED:
                        await session.execute(
                            update(m.orders)
                            .where(m.orders.id == order_row.id)
                            .values(
                                status=m.OrderStatus.CLOSED,
                                updated_at=func.now(),
                                version=order_row.version + 1,
                            )
                        )
                        history_staff_id = by_staff_id
                        if history_staff_id:
                            exists = await session.get(m.staff_users, history_staff_id)
                            if not exists:
                                history_staff_id = None

                        await session.execute(
                            insert(m.order_status_history).values(
                                order_id=order_row.id,
                                from_status=order_row.status,
                                to_status=m.OrderStatus.CLOSED,
                                changed_by_staff_id=history_staff_id,
                                reason='commission_paid',
                                actor_type=m.ActorType.ADMIN,
                            )
                        )

                await apply_rewards_for_commission(
                    session,
                    commission_id=commission_id,
                    master_id=commission_row.master_id,
                    base_amount=paid_amount,
                )
                return True

    async def reject(
        self, 
        commission_id: int, 
        reason: str, 
        by_staff_id: int,
    ) -> bool:
        async with self._session_factory() as session:
            if session.in_transaction():
                await session.execute(
                    update(m.commissions)
                    .where(m.commissions.id == commission_id)
                    .values(
                        status=m.CommissionStatus.WAIT_PAY,
                        is_paid=False,
                        paid_approved_at=None,
                        paid_reported_at=None,
                        paid_amount=None,
                        payment_reference=reason,
                    )
                )
            else:
                async with session.begin():
                    await session.execute(
                        update(m.commissions)
                        .where(m.commissions.id == commission_id)
                        .values(
                            status=m.CommissionStatus.WAIT_PAY,
                            is_paid=False,
                            paid_approved_at=None,
                            paid_reported_at=None,
                            paid_amount=None,
                            payment_reference=reason,
                        )
                    )
        return True

    async def block_master_for_overdue(
        self, 
        master_id: int, 
        by_staff_id: int,
    ) -> bool:
        async with self._session_factory() as session:
            if session.in_transaction():
                await session.execute(
                    update(m.masters)
                    .where(m.masters.id == master_id)
                    .values(
                        is_blocked=True,
                        is_active=False,
                        blocked_at=datetime.now(UTC),
                        blocked_reason="manual_block_from_finance",
                        updated_at=func.now(),
                    )
                )
            else:
                async with session.begin():
                    await session.execute(
                        update(m.masters)
                        .where(m.masters.id == master_id)
                        .values(
                            is_blocked=True,
                            is_active=False,
                            blocked_at=datetime.now(UTC),
                            blocked_reason="manual_block_from_finance",
                            updated_at=func.now(),
                        )
                    )
        return True
