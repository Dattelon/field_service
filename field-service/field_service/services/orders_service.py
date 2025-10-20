"""
Сервис для работы с заказами.

Централизует логику принятия/отклонения офферов, смены статусов заказов.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services.distribution_metrics_service import (
    DistributionMetricsService,
)

_log = logging.getLogger(__name__)


class OrdersService:
    """Сервис для работы с заказами."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.metrics_service = DistributionMetricsService()

    async def accept_offer(
        self,
        offer_id: int,
        master_id: int,
    ) -> tuple[bool, Optional[str]]:
        """
        Атомарное принятие оффера мастером.
        
        Использует SELECT ... FOR UPDATE SKIP LOCKED для предотвращения race condition
        при параллельных запросах от разных мастеров.
        
        Args:
            offer_id: ID оффера (из таблицы offers)
            master_id: ID мастера, который принимает оффер
        
        Returns:
            tuple[bool, Optional[str]]: (success, error_message)
            - (True, None) - успешное принятие
            - (False, "error") - ошибка с текстом
        """
        _log.info("accept_offer START: offer_id=%s master_id=%s", offer_id, master_id)

        # Шаг 1: Получаем информацию об оффере с атомарной блокировкой
        offer_stmt = (
            select(
                m.offers.id,
                m.offers.order_id,
                m.offers.master_id,
                m.offers.state,
                m.offers.expires_at,
            )
            .where(
                and_(
                    m.offers.id == offer_id,
                    m.offers.master_id == master_id,
                )
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        
        offer_result = await self.session.execute(offer_stmt)
        offer_row = offer_result.first()
        
        if offer_row is None:
            _log.warning("accept_offer: offer=%s not found or locked by another transaction", offer_id)
            return False, "⚠️ Оффер уже занят другим мастером"
        
        order_id = offer_row.order_id
        offer_state = offer_row.state
        expires_at = offer_row.expires_at
        
        _log.info(
            "accept_offer: offer=%s order=%s state=%s expires_at=%s",
            offer_id, order_id, offer_state, expires_at
        )

        # Шаг 2: Проверяем состояние оффера
        if offer_state not in (m.OfferState.SENT, m.OfferState.VIEWED):
            if offer_state == m.OfferState.EXPIRED:
                return False, "⏰ Время истекло. Заказ ушёл другим мастерам."
            elif offer_state == m.OfferState.DECLINED:
                return False, "❌ Вы уже отклонили этот заказ"
            elif offer_state == m.OfferState.ACCEPTED:
                return False, "✅ Вы уже приняли этот заказ"
            else:
                return False, "⚠️ Заказ уже занят"
        
        # Шаг 3: Проверяем что оффер не истёк по времени
        now_utc = datetime.now(timezone.utc)
        if expires_at and expires_at < now_utc:
            _log.info(
                "accept_offer: offer=%s expired (expires_at=%s now=%s)",
                offer_id, expires_at.isoformat(), now_utc.isoformat()
            )
            return False, "⏰ Время истекло. Заказ ушёл другим мастерам."

        # Шаг 4: Атомарная блокировка заказа
        order_stmt = (
            select(
                m.orders.id,
                m.orders.status,
                m.orders.assigned_master_id,
                m.orders.version,
                m.orders.city_id,
                m.orders.district_id,
                m.orders.category,
                m.orders.type,
                m.orders.preferred_master_id,
                m.orders.dist_escalated_logist_at,
                m.orders.dist_escalated_admin_at,
                m.orders.created_at,
            )
            .where(m.orders.id == order_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        
        order_result = await self.session.execute(order_stmt)
        order_row = order_result.first()
        
        if order_row is None:
            _log.warning("accept_offer: order=%s locked by another transaction", order_id)
            return False, "⚠️ Заказ уже занят другим мастером"
        
        current_status = order_row.status
        assigned_master_id = order_row.assigned_master_id
        current_version = order_row.version or 1
        
        _log.info(
            "accept_offer: order=%s status=%s assigned_master=%s",
            order_id, current_status, assigned_master_id
        )

        # Шаг 5: Проверяем что заказ доступен для принятия
        allowed_statuses = {
            m.OrderStatus.SEARCHING,
            m.OrderStatus.GUARANTEE,
            m.OrderStatus.CREATED,
            m.OrderStatus.DEFERRED,
        }
        
        if assigned_master_id is not None:
            _log.info("accept_offer: order=%s already assigned to master=%s", order_id, assigned_master_id)
            return False, "⚠️ Заказ уже занят"
        
        if current_status not in allowed_statuses:
            _log.info("accept_offer: order=%s in wrong status=%s", order_id, current_status)
            return False, "⚠️ Заказ уже занят"
        
        if current_status == m.OrderStatus.DEFERRED:
            _log.info(
                "accept_offer: accepting DEFERRED order=%s by master=%s",
                order_id, master_id
            )

        # Шаг 6: Атомарное обновление заказа
        update_result = await self.session.execute(
            update(m.orders)
            .where(
                and_(
                    m.orders.id == order_id,
                    m.orders.assigned_master_id.is_(None),
                    m.orders.status == current_status,
                    m.orders.version == current_version,
                )
            )
            .values(
                assigned_master_id=master_id,
                status=m.OrderStatus.ASSIGNED,
                updated_at=func.now(),
                version=current_version + 1,
            )
            .returning(m.orders.id)
        )
        
        if not update_result.first():
            _log.warning("accept_offer: order=%s UPDATE returned 0 rows (race condition)", order_id)
            return False, "⚠️ Заказ уже занят"

        _log.info("accept_offer: order=%s successfully assigned to master=%s", order_id, master_id)

        # Шаг 7: Обновляем оффер мастера на ACCEPTED
        await self.session.execute(
            update(m.offers)
            .where(
                and_(
                    m.offers.id == offer_id,
                    m.offers.order_id == order_id,
                    m.offers.master_id == master_id,
                    m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
                )
            )
            .values(state=m.OfferState.ACCEPTED, responded_at=func.now())
        )

        # Шаг 8: Отменяем офферы других мастеров
        await self.session.execute(
            update(m.offers)
            .where(
                and_(
                    m.offers.order_id == order_id,
                    m.offers.master_id != master_id,
                    m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
                )
            )
            .values(state=m.OfferState.CANCELED, responded_at=func.now())
        )

        # Шаг 9: Записываем историю статуса
        await self.session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=current_status,
                to_status=m.OrderStatus.ASSIGNED,
                changed_by_master_id=master_id,
                reason="accepted_by_master",
                actor_type=m.ActorType.MASTER,
                context={
                    "master_id": master_id,
                    "action": "offer_accepted",
                    "method": "atomic_accept",
                    "offer_id": offer_id,
                }
            )
        )

        # Шаг 10: Коммитим транзакцию
        await self.session.commit()
        _log.info("accept_offer: transaction committed for order=%s master=%s", order_id, master_id)

        # Шаг 11: Записываем метрики распределения (после commit, в отдельной транзакции)
        try:
            # Получаем статистику офферов
            offer_stats_stmt = select(
                func.max(m.offers.round_number).label("max_round"),
                func.count(func.distinct(m.offers.master_id)).label("total_candidates")
            ).where(m.offers.order_id == order_id)
            
            stats_result = await self.session.execute(offer_stats_stmt)
            stats_row = stats_result.first()
            
            if stats_row:
                time_to_assign = None
                if order_row.created_at:
                    time_to_assign = int((now_utc - order_row.created_at).total_seconds())
                
                # НЕ передаём session - метрики создадут свою транзакцию
                await self.metrics_service.record_assignment(
                    order_id=order_id,
                    master_id=master_id,
                    round_number=stats_row.max_round or 1,
                    candidates_count=stats_row.total_candidates or 1,
                    time_to_assign_seconds=time_to_assign,
                    preferred_master_used=(master_id == order_row.preferred_master_id),
                    was_escalated_to_logist=(order_row.dist_escalated_logist_at is not None),
                    was_escalated_to_admin=(order_row.dist_escalated_admin_at is not None),
                    city_id=order_row.city_id,
                    district_id=order_row.district_id,
                    category=order_row.category,
                    order_type=order_row.type,
                    metadata_json={
                        "accepted_via": "orders_service",
                        "from_status": current_status.value if hasattr(current_status, 'value') else str(current_status),
                    },
                    session=None,  # Пусть метрики создадут свою транзакцию
                )
                
                _log.info(
                    "accept_offer: metrics recorded for order=%s master=%s",
                    order_id, master_id
                )
        except Exception as metrics_err:
            # Метрики не должны ломать основной процесс
            _log.error(
                "accept_offer: failed to record metrics for order=%s: %s",
                order_id, metrics_err
            )

        _log.info("accept_offer SUCCESS: order=%s assigned to master=%s", order_id, master_id)
        return True, None

    async def decline_offer(
        self,
        offer_id: int,
        master_id: int,
    ) -> tuple[bool, Optional[str]]:
        """
        Отклонение оффера мастером.
        
        Args:
            offer_id: ID оффера
            master_id: ID мастера
        
        Returns:
            tuple[bool, Optional[str]]: (success, error_message)
        """
        _log.info("decline_offer: offer_id=%s master_id=%s", offer_id, master_id)
        
        # Обновляем оффер на DECLINED
        result = await self.session.execute(
            update(m.offers)
            .where(
                and_(
                    m.offers.id == offer_id,
                    m.offers.master_id == master_id,
                    m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
                )
            )
            .values(state=m.OfferState.DECLINED, responded_at=func.now())
            .returning(m.offers.id)
        )
        
        if not result.first():
            _log.warning("decline_offer: offer=%s not found or already processed", offer_id)
            return False, "Оффер не найден или уже обработан"
        
        await self.session.commit()
        _log.info("decline_offer SUCCESS: offer=%s declined by master=%s", offer_id, master_id)
        return True, None
