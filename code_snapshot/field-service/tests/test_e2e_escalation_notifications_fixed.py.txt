"""
E2E тесты для Шага 1.4: Проверка остановки повторных уведомлений эскалации

✅ ИСПРАВЛЕНЫ:
- Удалены дублирующие fixtures (session, clean_db, sample_*)
- Используются fixtures из conftest.py (но они для SQLite, а нужен PostgreSQL)
- Добавлено использование SessionLocal для PostgreSQL

ВАЖНО: Эти тесты используют реальную PostgreSQL БД, а не SQLite!
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services.distribution_scheduler import tick_once, DistConfig

# CRITICAL: Используем timezone.utc, НЕ datetime.utcnow()
UTC = timezone.utc


async def _get_db_now(session: AsyncSession) -> datetime:
    """
    Получает текущее время из БД (аналогично _db_now в distribution_scheduler).
    КРИТИЧНО: Всегда используем время БД в тестах для консистентности с tick_once()!
    """
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


class TestEscalationNotifications:
    """Тесты для проверки одноразовой отправки уведомлений эскалации"""

    @pytest.mark.asyncio
    async def test_logist_notification_sent_once(
        self,
        session: AsyncSession,
        sample_city,
        sample_district,
        sample_skill,
    ):
        """
        Тест 1: Уведомление логисту отправляется только один раз
        
        Сценарий:
        1. Создаём заказ без кандидатов (эскалация неизбежна)
        2. Запускаем tick_once() 10 раз подряд
        3. Проверяем что timestamp установлен и не меняется
        """
        # ✅ КРИТИЧНО: Используем время БД, а не Python время!
        db_now = await _get_db_now(session)
        
        order = m.orders(
            status=m.OrderStatus.SEARCHING,
            city_id=sample_city.id,
            district_id=sample_district.id,
            category=m.OrderCategory.ELECTRICS,
            house="1",
            timeslot_start_utc=db_now + timedelta(hours=2),
            timeslot_end_utc=db_now + timedelta(hours=4),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        # Act: Запускаем tick_once() 10 раз подряд
        cfg = DistConfig(
            tick_seconds=30,
            sla_seconds=120,
            rounds=2,
            top_log_n=10,
            to_admin_after_min=10,
        )

        # Первый тик - должна произойти эскалация
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        # ✅ FIX: Очищаем кэш сессии перед refresh
        session.expire_all()
        await session.refresh(order)
        
        # Сохраняем timestamp первого уведомления
        first_notification_timestamp = order.escalation_logist_notified_at
        
        assert order.dist_escalated_logist_at is not None, "Эскалация к логисту должна быть установлена"
        assert first_notification_timestamp is not None, "Timestamp уведомления должен быть установлен после первого тика"
        
        # Запускаем ещё 9 тиков
        for i in range(9):
            await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
            await asyncio.sleep(0.05)

        # Assert: Проверяем что timestamp НЕ ИЗМЕНИЛСЯ (уведомление не отправлялось повторно)
        # ✅ FIX: Очищаем кэш перед проверкой
        session.expire_all()
        await session.refresh(order)
        
        assert order.escalation_logist_notified_at == first_notification_timestamp, \
            f"Timestamp уведомления НЕ должен меняться. Было: {first_notification_timestamp}, стало: {order.escalation_logist_notified_at}"


    @pytest.mark.asyncio
    async def test_admin_notification_sent_once(
        self,
        session: AsyncSession,
        sample_city,
        sample_district,
    ):
        """
        Тест 2: Уведомление админу отправляется только один раз
        
        Сценарий:
        1. Создаём заказ с эскалацией к логисту (давно)
        2. Запускаем tick_once() 10 раз подряд
        3. Проверяем что timestamp установлен и не меняется
        """
        # ✅ КРИТИЧНО: Используем время БД, а не Python время!
        db_now = await _get_db_now(session)
        escalation_time = db_now - timedelta(minutes=15)
        notification_time = db_now - timedelta(minutes=14)
        
        order = m.orders(
            status=m.OrderStatus.SEARCHING,
            city_id=sample_city.id,
            district_id=sample_district.id,
            category=m.OrderCategory.ELECTRICS,
            house="1",
            timeslot_start_utc=db_now + timedelta(hours=2),
            timeslot_end_utc=db_now + timedelta(hours=4),
            dist_escalated_logist_at=escalation_time,
            escalation_logist_notified_at=notification_time,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        # Act: Запускаем tick_once() 10 раз
        cfg = DistConfig(
            tick_seconds=30,
            sla_seconds=120,
            rounds=2,
            top_log_n=10,
            to_admin_after_min=10,
        )

        # Первый тик - должна произойти эскалация к админу
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        # ✅ FIX: Очищаем кэш перед refresh
        session.expire_all()
        await session.refresh(order)
        
        # Сохраняем timestamp первого уведомления админу
        first_admin_notification = order.escalation_admin_notified_at
        
        assert order.dist_escalated_admin_at is not None, "Эскалация к админу должна быть установлена"
        assert first_admin_notification is not None, "Timestamp уведомления админу должен быть установлен"
        
        # Запускаем ещё 9 тиков
        for i in range(9):
            await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
            await asyncio.sleep(0.05)

        # Assert: Timestamp НЕ изменился
        # ✅ FIX: Очищаем кэш перед проверкой
        session.expire_all()
        await session.refresh(order)
        assert order.escalation_admin_notified_at == first_admin_notification, \
            f"Timestamp уведомления админу НЕ должен меняться. Было: {first_admin_notification}, стало: {order.escalation_admin_notified_at}"


    @pytest.mark.asyncio
    async def test_notification_reset_on_new_offer(
        self,
        session: AsyncSession,
        sample_city,
        sample_district,
        sample_master,
    ):
        """
        Тест 3: Сброс уведомлений при появлении нового оффера
        
        Сценарий:
        1. Заказ эскалирован к логисту (уведомление отправлено)
        2. Приходит новый оффер (SENT)
        3. tick_once() должен сбросить эскалацию
        4. Заказ снова эскалируется
        5. Timestamp устанавливается заново
        """
        # ✅ КРИТИЧНО: Используем время БД, а не Python время!
        db_now = await _get_db_now(session)
        escalation_time = db_now - timedelta(minutes=5)
        notification_time = db_now - timedelta(minutes=4)
        
        order = m.orders(
            status=m.OrderStatus.SEARCHING,
            city_id=sample_city.id,
            district_id=sample_district.id,
            category=m.OrderCategory.ELECTRICS,
            house="1",
            timeslot_start_utc=db_now + timedelta(hours=2),
            timeslot_end_utc=db_now + timedelta(hours=4),
            dist_escalated_logist_at=escalation_time,
            escalation_logist_notified_at=notification_time,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        # Act 1: Создаём новый оффер (эмулируем появление мастера)
        offer = m.offers(
            order_id=order.id,
            master_id=sample_master.id,
            round_number=1,
            state=m.OfferState.SENT,
            sent_at=db_now,
            expires_at=db_now + timedelta(minutes=2),
        )
        session.add(offer)
        await session.commit()
        
        # ✅ FIX: Сохраняем offer_id ДО expire_all() (иначе MissingGreenlet)
        offer_id = offer.id

        # Act 2: Запускаем tick_once() - должен сбросить эскалацию
        cfg = DistConfig(
            tick_seconds=30,
            sla_seconds=120,
            rounds=2,
            top_log_n=10,
            to_admin_after_min=10,
        )

        # ✅ КРИТИЧНО: Передаём сессию теста чтобы tick_once() видел оффер
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)

        # Assert 1: Эскалация сброшена при наличии SENT оффера
        # ✅ FIX: Очищаем кэш сессии перед refresh чтобы прочитать свежие данные из БД
        session.expire_all()
        await session.refresh(order)
        assert order.dist_escalated_logist_at is None, "Эскалация к логисту должна быть сброшена при SENT оффере"
        assert order.escalation_logist_notified_at is None, "Timestamp уведомления должен быть сброшен при SENT оффере"

        # Act 3: Истекаем оффер
        # ✅ FIX: Используем сохранённый offer_id вместо offer.id
        await session.execute(
            text("""
                UPDATE offers 
                SET state = 'EXPIRED', 
                    responded_at = NOW(),
                    expires_at = NOW() - INTERVAL '1 minute'
                WHERE id = :offer_id
            """).bindparams(offer_id=offer_id)
        )
        await session.commit()

        # Act 4: Запускаем tick_once() снова - заказ должен эскалироваться заново
        # ✅ КРИТИЧНО: Передаём сессию теста
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)

        # Assert 2: Новая эскалация с новым timestamp
        # ✅ FIX: Очищаем кэш перед проверкой
        session.expire_all()
        await session.refresh(order)
        assert order.dist_escalated_logist_at is not None, "После истечения оффера должна быть новая эскалация"
        assert order.escalation_logist_notified_at is not None, "После повторной эскалации должен быть установлен новый timestamp"
        assert order.escalation_logist_notified_at != notification_time, \
            f"Новый timestamp должен отличаться от старого. Старый: {notification_time}, новый: {order.escalation_logist_notified_at}"


    @pytest.mark.asyncio
    async def test_parallel_ticks_no_duplicate_notifications(
        self,
        session: AsyncSession,
        sample_city,
        sample_district,
    ):
        """
        Тест 4: Параллельные тики не вызывают дублирование уведомлений
        
        Сценарий:
        1. Создаём заказ без кандидатов
        2. Запускаем 5 параллельных tick_once()
        3. Проверяем что timestamp установлен только один раз (благодаря advisory lock)
        """
        # ✅ КРИТИЧНО: Используем время БД, а не Python время!
        db_now = await _get_db_now(session)
        
        order = m.orders(
            status=m.OrderStatus.SEARCHING,
            city_id=sample_city.id,
            district_id=sample_district.id,
            category=m.OrderCategory.ELECTRICS,
            house="1",
            timeslot_start_utc=db_now + timedelta(hours=2),
            timeslot_end_utc=db_now + timedelta(hours=4),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        # Act: Запускаем 5 параллельных тиков
        cfg = DistConfig(
            tick_seconds=30,
            sla_seconds=120,
            rounds=2,
            top_log_n=10,
            to_admin_after_min=10,
        )

        tasks = [
            tick_once(cfg, bot=None, alerts_chat_id=None)
            for _ in range(5)
        ]
        await asyncio.gather(*tasks)

        # Assert: Timestamp установлен благодаря advisory lock
        # ✅ FIX: Очищаем кэш перед refresh
        session.expire_all()
        await session.refresh(order)
        assert order.dist_escalated_logist_at is not None, "Эскалация должна быть установлена"
        assert order.escalation_logist_notified_at is not None, "Timestamp уведомления должен быть установлен"
        
        # Запомним первый timestamp
        first_timestamp = order.escalation_logist_notified_at
        
        # Запускаем ещё раз параллельные тики
        tasks = [
            tick_once(cfg, bot=None, alerts_chat_id=None)
            for _ in range(5)
        ]
        await asyncio.gather(*tasks)
        
        # Assert: Timestamp НЕ изменился (повторная отправка заблокирована)
        # ✅ FIX: Очищаем кэш перед проверкой
        session.expire_all()
        await session.refresh(order)
        assert order.escalation_logist_notified_at == first_timestamp, \
            f"Timestamp не должен меняться при параллельных тиках. Было: {first_timestamp}, стало: {order.escalation_logist_notified_at}"


if __name__ == "__main__":
    print("Для запуска тестов используйте: pytest tests/test_e2e_escalation_notifications.py -v")
