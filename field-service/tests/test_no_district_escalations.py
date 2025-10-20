"""
Упрощённый интеграционный тест для сценария эскалаций заказа без района

Сценарий:
1. Создаём заказ SEARCHING без district_id (no_district=True)
2. Прогоняем tick_once() → dist_escalated_logist_at устанавливается
3. Эмулируем 10+ минут
4. Прогоняем tick_once() снова → dist_escalated_admin_at устанавливается
5. Проверяем timestamps эскалаций (без проверки уведомлений, т.к. они зависят от бота)
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services.distribution_scheduler import tick_once, DistConfig

UTC = timezone.utc


async def _get_db_now(session: AsyncSession) -> datetime:
    """Получает текущее время из БД для консистентности"""
    row = await session.execute(text("SELECT NOW()"))
    return row.scalar()


@pytest.mark.asyncio
async def test_no_district_double_escalation_simplified(
    session: AsyncSession,
    sample_city,
    sample_skill,
):
    """
    Упрощённый тест: Заказ без района проходит двойную эскалацию (логист → админ)
    
    Проверяем ТОЛЬКО timestamps эскалаций:
    - Первый тик: dist_escalated_logist_at устанавливается, dist_escalated_admin_at = NULL
    - После 10+ минут: dist_escalated_admin_at устанавливается
    """
    
    # ============ ФАЗА 1: Подготовка заказа без района ============
    db_now = await _get_db_now(session)
    start_time = time.time()
    
    order = m.orders(
        status=m.OrderStatus.SEARCHING,
        city_id=sample_city.id,
        district_id=None,  # ❌ НЕТ РАЙОНА
        category=m.OrderCategory.ELECTRICS,
        house="1",
        timeslot_start_utc=db_now + timedelta(hours=2),
        timeslot_end_utc=db_now + timedelta(hours=4),
        assigned_master_id=None,
        no_district=True,  # Флаг отсутствия района
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    
    order_id = order.id
    print(f"\n✅ Создан заказ #{order_id} без района (district_id=None, no_district=True)")
    
    cfg = DistConfig(
        tick_seconds=30,
        sla_seconds=120,
        rounds=2,
        top_log_n=10,
        to_admin_after_min=10,  # ⏱ Админ через 10 минут
    )
    
    # ============ ФАЗА 2: Первый тик → Эскалация логисту ============
    print("\n🔄 ФАЗА 2: Запускаем первый tick_once()...")
    tick1_start = time.time()
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    tick1_duration = time.time() - tick1_start
    print(f"   ⏱ Tick #1 выполнен за {tick1_duration:.3f}с")
    
    # Обновляем данные из БД
    session.expire_all()
    await session.refresh(order)
    
    print(f"   dist_escalated_logist_at: {order.dist_escalated_logist_at}")
    print(f"   dist_escalated_admin_at: {order.dist_escalated_admin_at}")
    
    # ✅ ПРОВЕРКА 1: Логист эскалирован
    assert order.dist_escalated_logist_at is not None, \
        "❌ После первого тика dist_escalated_logist_at должен быть установлен"
    
    # ✅ ПРОВЕРКА 2: Админ сброшен (т.к. это первая эскалация)
    assert order.dist_escalated_admin_at is None, \
        "❌ После первого тика dist_escalated_admin_at должен быть NULL"
    
    print("✅ ФАЗА 2 завершена: логист эскалирован, админ сброшен")
    
    first_logist_escalation = order.dist_escalated_logist_at
    
    # ============ ФАЗА 3: Эмуляция времени (10+ минут) ============
    print("\n⏳ ФАЗА 3: Эмулируем прохождение 11 минут...")
    
    # Перематываем эскалацию логиста на 11 минут назад
    past_time = db_now - timedelta(minutes=11)
    await session.execute(
        text("""
            UPDATE orders 
            SET dist_escalated_logist_at = :past_time
            WHERE id = :order_id
        """).bindparams(past_time=past_time, order_id=order_id)
    )
    await session.commit()
    print(f"   Timestamp эскалации логиста перенесён на {past_time.isoformat()}")
    
    # ============ ФАЗА 4: Второй тик → Эскалация админу ============
    print("\n🔄 ФАЗА 4: Запускаем второй tick_once() (11 минут спустя)...")
    tick2_start = time.time()
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    tick2_duration = time.time() - tick2_start
    print(f"   ⏱ Tick #2 выполнен за {tick2_duration:.3f}с")
    
    # Обновляем данные из БД
    session.expire_all()
    await session.refresh(order)
    
    print(f"   dist_escalated_logist_at: {order.dist_escalated_logist_at}")
    print(f"   dist_escalated_admin_at: {order.dist_escalated_admin_at}")
    
    # ✅ ПРОВЕРКА 3: Логист остаётся эскалированным (старый timestamp)
    assert order.dist_escalated_logist_at is not None, \
        "❌ dist_escalated_logist_at не должен сбрасываться при эскалации админу"
    
    # ✅ ПРОВЕРКА 4: Админ эскалирован (новый timestamp)
    assert order.dist_escalated_admin_at is not None, \
        "❌ После 11 минут dist_escalated_admin_at должен быть установлен"
    
    # ✅ ПРОВЕРКА 5: Админ эскалирован позже логиста
    assert order.dist_escalated_admin_at > past_time, \
        "❌ Timestamp эскалации админа должен быть новее timestamp логиста"
    
    print("✅ ФАЗА 4 завершена: админ эскалирован")
    
    # ============ ФАЗА 5: Третий тик → Проверка стабильности ============
    print("\n🔄 ФАЗА 5: Запускаем третий tick_once() (проверка стабильности)...")
    tick3_start = time.time()
    
    saved_logist_timestamp = order.dist_escalated_logist_at
    saved_admin_timestamp = order.dist_escalated_admin_at
    
    await tick_once(cfg, bot=None, alerts_chat_id=None, session=session)
    
    tick3_duration = time.time() - tick3_start
    print(f"   ⏱ Tick #3 выполнен за {tick3_duration:.3f}с")
    
    # Обновляем данные из БД
    session.expire_all()
    await session.refresh(order)
    
    # ✅ ПРОВЕРКА 6: Timestamps не изменились
    assert order.dist_escalated_logist_at == saved_logist_timestamp, \
        "❌ Timestamp логиста не должен меняться при повторных тиках"
    
    assert order.dist_escalated_admin_at == saved_admin_timestamp, \
        "❌ Timestamp админа не должен меняться при повторных тиках"
    
    print("✅ ФАЗА 5 завершена: timestamps стабильны")
    
    # ============ ИТОГИ ============
    total_duration = time.time() - start_time
    
    print("\n" + "="*60)
    print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ УСПЕШНО!")
    print("="*60)
    print(f"📊 Тайминги:")
    print(f"   Tick #1: {tick1_duration:.3f}с")
    print(f"   Tick #2: {tick2_duration:.3f}с")
    print(f"   Tick #3: {tick3_duration:.3f}с")
    print(f"   Всего:   {total_duration:.3f}с")
    print("="*60)


if __name__ == "__main__":
    print("Запуск: pytest tests/test_no_district_escalations.py::test_no_district_double_escalation_simplified -v -s")
