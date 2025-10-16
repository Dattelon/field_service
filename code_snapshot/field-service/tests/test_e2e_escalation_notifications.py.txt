"""
E2E тесты для Шага 1.4: Проверка остановки повторных уведомлений эскалации

Тесты проверяют:
- Одноразовую отправку уведомлений эскалации к логисту (через timestamp)
- Одноразовую отправку уведомлений эскалации к админу (через timestamp)
- Сброс уведомлений при появлении нового оффера
- Работу под нагрузкой (параллельные тики)

Подход к тестированию:
- Проверяем установку timestamp вместо вызовов mock'ов
- Timestamp устанавливается ВСЕГДА (независимо от наличия bot)
- push_notify_admin вызывается только если bot и alerts_chat_id не None

Требования:
- PostgreSQL должна быть запущена
- База данных должна быть мигрирована (alembic upgrade head)
- pytest.ini должен содержать asyncio_mode = auto
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal
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

        # DEBUG: Проверяем что оффер действительно создан
        debug_result = await session.execute(
            text("SELECT id, state FROM offers WHERE order_id = :oid"),
            {"oid": order.id}
        )
        debug_offers = debug_result.fetchall()
        print(f"[DEBUG] Офферы для заказа {order.id}: {debug_offers}")

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


    @pytest.mark.asyncio
    async def test_double_tick_no_duplicate_notifications(
        self,
        session: AsyncSession,
        sample_city,
        sample_district,
    ):
        """
        Тест 5: Двойной последовательный вызов тика не вызывает дублирование уведомлений
        
        Сценарий:
        1. Создаём заказ без кандидатов
        2. Вызываем tick_once() первый раз - устанавливается timestamp
        3. Вызываем tick_once() второй раз - timestamp НЕ меняется
        4. Проверяем что notification отправлено только один раз
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

        cfg = DistConfig(
            tick_seconds=30,
            sla_seconds=120,
            rounds=2,
            top_log_n=10,
            to_admin_after_min=10,
        )

        # Act 1: Первый тик - устанавливается timestamp
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        session.expire_all()
        await session.refresh(order)
        
        # Сохраняем timestamp первого уведомления
        first_timestamp = order.escalation_logist_notified_at
        
        # Assert 1: Timestamp установлен после первого тика
        assert order.dist_escalated_logist_at is not None, "Эскалация должна быть установлена после первого тика"
        assert first_timestamp is not None, "Timestamp уведомления должен быть установлен после первого тика"
        
        print(f"[DEBUG] После первого тика: escalation_logist_notified_at={first_timestamp}")

        # Act 2: Второй тик сразу же - timestamp НЕ должен меняться
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        session.expire_all()
        await session.refresh(order)
        
        second_timestamp = order.escalation_logist_notified_at
        
        print(f"[DEBUG] После второго тика: escalation_logist_notified_at={second_timestamp}")
        
        # Assert 2: Timestamp НЕ изменился (повторная отправка заблокирована)
        assert second_timestamp == first_timestamp, \
            f"Timestamp НЕ должен меняться при повторном тике. " \
            f"Было: {first_timestamp}, стало: {second_timestamp}"
        
        print("[OK] Двойной вызов тика: уведомление отправлено только один раз")


# ============================================================================
# FIXTURES
# ============================================================================

@pytest_asyncio.fixture(scope="function")
async def session():
    """Создаёт новую сессию БД для каждого теста"""
    async with SessionLocal() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture(scope="function")
async def sample_city(async_session: AsyncSession):
    """Создаёт тестовый город"""
    city = m.cities(
        name="Test City",
        timezone="Europe/Moscow",
        is_active=True,
    )
    async_session.add(city)
    await async_session.commit()
    await async_session.refresh(city)
    return city


@pytest_asyncio.fixture(scope="function")
async def sample_district(async_session: AsyncSession, sample_city):
    """Создаёт тестовый район"""
    district = m.districts(
        city_id=sample_city.id,
        name="Test District",
    )
    async_session.add(district)
    await async_session.commit()
    await async_session.refresh(district)
    return district


@pytest_asyncio.fixture(scope="function")
async def sample_skill(async_session: AsyncSession):
    """Создаёт тестовый навык"""
    skill = m.skills(
        code="ELEC",
        name="Электрика",
        is_active=True,
    )
    async_session.add(skill)
    await async_session.commit()
    await async_session.refresh(skill)
    return skill


@pytest_asyncio.fixture(scope="function")
async def sample_master(async_session: AsyncSession, sample_city, sample_district, sample_skill):
    """Создаёт тестового мастера"""
    master = m.masters(
        tg_user_id=123456789,
        full_name="Test Master",
        phone="+79001112233",
        city_id=sample_city.id,
        is_active=True,
        is_blocked=False,
        verified=True,
        is_on_shift=True,
        has_vehicle=True,
        rating=4.5,
    )
    async_session.add(master)
    await async_session.commit()
    await async_session.refresh(master)

    # Связываем мастера с районом
    master_district = m.master_districts(
        master_id=master.id,
        district_id=sample_district.id,
    )
    async_session.add(master_district)

    # Связываем мастера с навыком
    master_skill = m.master_skills(
        master_id=master.id,
        skill_id=sample_skill.id,
    )
    async_session.add(master_skill)

    await async_session.commit()
    return master


# ============================================================================
# INTEGRATION TEST: Полный цикл эскалации
# ============================================================================

class TestEscalationFullCycle:
    """Интеграционные тесты полного цикла эскалации"""

    @pytest.mark.asyncio
    async def test_full_escalation_cycle(
        self,
        session: AsyncSession,
        sample_city,
        sample_district,
        sample_skill,
        sample_master,
    ):
        """
        Тест 6: Полный цикл эскалации от создания до админа
        
        Сценарий:
        1. Создаём заказ
        2. Нет кандидатов → эскалация к логисту
        3. Через 10 минут → эскалация к админу
        4. Проверяем что timestamp'ы установлены и не меняются
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

        # Убираем мастера чтобы гарантировать эскалацию
        await session.execute(text("UPDATE masters SET is_active = FALSE"))
        await session.commit()

        cfg = DistConfig(
            tick_seconds=30,
            sla_seconds=120,
            rounds=2,
            top_log_n=10,
            to_admin_after_min=10,
        )

        # Act 1: Запускаем тики для эскалации к логисту
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        # ✅ FIX: Очищаем кэш перед refresh
        session.expire_all()
        await session.refresh(order)
        
        # Сохраняем timestamp эскалации к логисту
        logist_notification_timestamp = order.escalation_logist_notified_at
        
        # Assert 1: Эскалация к логисту произошла
        assert order.dist_escalated_logist_at is not None, "Эскалация к логисту должна быть установлена"
        assert logist_notification_timestamp is not None, "Timestamp уведомления логисту должен быть установлен"

        print(f"[OK] Эскалация к логисту: timestamp={logist_notification_timestamp}")

        # Запускаем ещё 4 тика - timestamp не должен меняться
        for i in range(4):
            await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
            await asyncio.sleep(0.05)
        
        # ✅ FIX: Очищаем кэш перед проверкой
        session.expire_all()
        await session.refresh(order)
        assert order.escalation_logist_notified_at == logist_notification_timestamp, \
            "Timestamp уведомления логисту НЕ должен меняться"

        # Act 2: Имитируем прошедшие 15 минут
        await session.execute(
            text("""
                UPDATE orders 
                SET dist_escalated_logist_at = dist_escalated_logist_at - INTERVAL '15 minutes',
                    escalation_logist_notified_at = escalation_logist_notified_at - INTERVAL '15 minutes'
                WHERE id = :oid
            """),
            {"oid": order.id}
        )
        await session.commit()

        # Запускаем тик для эскалации к админу
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        # ✅ FIX: Очищаем кэш перед refresh
        session.expire_all()
        await session.refresh(order)
        
        # Сохраняем timestamp эскалации к админу
        admin_notification_timestamp = order.escalation_admin_notified_at

        # Assert 2: Эскалация к админу произошла
        assert order.dist_escalated_admin_at is not None, "Эскалация к админу должна быть установлена"
        assert admin_notification_timestamp is not None, "Timestamp уведомления админу должен быть установлен"

        print(f"[OK] Эскалация к админу: timestamp={admin_notification_timestamp}")
        
        # Запускаем ещё 4 тика - timestamp админу не должен меняться
        for i in range(4):
            await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
            await asyncio.sleep(0.05)

        # ✅ FIX: Очищаем кэш перед проверкой
        session.expire_all()
        await session.refresh(order)
        assert order.escalation_admin_notified_at == admin_notification_timestamp, \
            "Timestamp уведомления админу НЕ должен меняться"

        print("[OK] Полный цикл эскалации: оба timestamp установлены и не меняются")


    @pytest.mark.asyncio
    async def test_escalation_with_rounds_exhaustion(
        self,
        session: AsyncSession,
        sample_city,
        sample_district,
        sample_skill,
    ):
        """
        Тест 7: Эскалация при исчерпании раундов
        
        Сценарий:
        1. Создаём заказ с 2 раундами офферов
        2. Оба оффера истекают
        3. Раунды исчерпаны → эскалация
        4. Проверяем что timestamp установлен только один раз
        """
        # Arrange: Создаём двух мастеров для офферов
        master1 = m.masters(
            tg_user_id=100001,
            full_name="Test Master 1",
            phone="+79001111111",
            city_id=sample_city.id,
            is_active=True,
            is_blocked=False,
            verified=True,
        )
        master2 = m.masters(
            tg_user_id=100002,
            full_name="Test Master 2",
            phone="+79002222222",
            city_id=sample_city.id,
            is_active=True,
            is_blocked=False,
            verified=True,
        )
        session.add(master1)
        session.add(master2)
        await session.commit()
        await session.refresh(master1)
        await session.refresh(master2)
        
        # ✅ КРИТИЧНО: Используем время БД, а не Python время!
        db_now = await _get_db_now(session)
        
        # Создаём заказ
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

        # Создаём 2 просроченных оффера (2 раунда) с реальными мастерами
        masters = [master1, master2]
        for round_num in [1, 2]:
            offer = m.offers(
                order_id=order.id,
                master_id=masters[round_num - 1].id,  # Реальные ID мастеров
                round_number=round_num,
                state=m.OfferState.EXPIRED,
                sent_at=db_now - timedelta(minutes=10),
                expires_at=db_now - timedelta(minutes=5),
                responded_at=db_now - timedelta(minutes=5),
            )
            session.add(offer)
        await session.commit()

        cfg = DistConfig(
            tick_seconds=30,
            sla_seconds=120,
            rounds=2,  # Максимум 2 раунда
            top_log_n=10,
            to_admin_after_min=10,
        )

        # Act: Запускаем первый тик - должна произойти эскалация
        await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
        # ✅ FIX: Очищаем кэш перед refresh
        session.expire_all()
        await session.refresh(order)
        
        # Сохраняем timestamp первого уведомления
        first_notification_timestamp = order.escalation_logist_notified_at

        # Assert: Эскалация произошла
        assert order.dist_escalated_logist_at is not None, "Эскалация должна быть установлена"
        assert first_notification_timestamp is not None, "Timestamp уведомления должен быть установлен"

        print(f"[OK] При исчерпании раундов эскалация произошла: timestamp={first_notification_timestamp}")
        
        # Запускаем ещё 9 тиков - timestamp не должен меняться
        for i in range(9):
            await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
            await asyncio.sleep(0.05)

        # ✅ FIX: Очищаем кэш перед проверкой
        session.expire_all()
        await session.refresh(order)
        assert order.escalation_logist_notified_at == first_notification_timestamp, \
            f"Timestamp НЕ должен меняться. Было: {first_notification_timestamp}, стало: {order.escalation_logist_notified_at}"

        print("[OK] После 10 тиков timestamp не изменился")


if __name__ == "__main__":
    print("Для запуска тестов используйте: pytest tests/test_e2e_escalation_notifications.py -v")
