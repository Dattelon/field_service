"""
P0 тесты жизненного цикла заказа
Критические сценарии, которые должны работать всегда
"""
import pytest
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from tests.telegram_ui.bot_client import BotTestClient
from tests.telegram_ui.helpers import (
    create_master_via_onboarding,
    change_master_status,
    accept_offer,
    start_work,
    complete_work,
    create_order_via_admin,
    wait_for_offer,
    get_order_status,
)
from tests.telegram_ui.helpers.admin_helpers import finalize_order


@pytest.mark.p0
@pytest.mark.telegram_ui
@pytest.mark.asyncio
async def test_tp001_full_order_cycle(
    clean_db,
    db_session: AsyncSession,
    telegram_client: BotTestClient,
):
    """
    TP-001: Полный цикл заказа (успешное выполнение)
    
    Сценарий:
    1. Создать 2 мастеров (онбординг)
    2. Создать заказ через админ-бота
    3. Дождаться автораспределения
    4. Мастер 1 принимает заказ
    5. Мастер 1 начинает работу
    6. Мастер 1 завершает работу
    7. Админ финализирует заказ
    8. Проверить комиссию
    
    Ожидаемый результат:
    - Заказ закрыт (CLOSED)
    - Комиссия создана (50%)
    - История статусов полная
    """
    
    print("\n=== STEP 1: Создание мастеров ===")
    
    # Создаем Мастера 1
    master1_id = await create_master_via_onboarding(
        telegram_client,
        db_session,
        city="Москва",
        district="ЦАО",
        phone="+79991111111",
        auto_approve=True,
    )
    print(f"✓ Мастер 1 создан (ID: {master1_id})")
    
    # Создаем Мастера 2
    master2_id = await create_master_via_onboarding(
        telegram_client,
        db_session,
        city="Москва",
        district="ЦАО",
        phone="+79992222222",
        auto_approve=True,
    )
    print(f"✓ Мастер 2 создан (ID: {master2_id})")
    
    # Переводим обоих в статус "Работаю"
    await change_master_status(telegram_client, "working")
    print("✓ Мастера переведены в статус 'Работаю'")
    
    print("\n=== STEP 2: Создание заказа ===")
    
    order_id = await create_order_via_admin(
        telegram_client,
        db_session,
        service="Ремонт iPhone",
        city="Москва",
        district="ЦАО",
        address="ул. Тверская, 1",
        client_phone="+79991234567",
        cost=3000,
    )
    print(f"✓ Заказ создан (ID: {order_id})")
    
    # Проверяем статус заказа
    status = await get_order_status(db_session, order_id)
    assert status in ("NEW", "IN_QUEUE"), f"Unexpected initial status: {status}"
    print(f"✓ Статус заказа: {status}")
    
    print("\n=== STEP 3: Ожидание автораспределения ===")
    
    # Ждем появления офферов (до 30 секунд)
    offer1_received = await wait_for_offer(db_session, order_id, master1_id, timeout=30)
    offer2_received = await wait_for_offer(db_session, order_id, master2_id, timeout=30)
    
    assert offer1_received, "Мастер 1 не получил оффер"
    assert offer2_received, "Мастер 2 не получил оффер"
    print("✓ Оба мастера получили офферы")
    
    print("\n=== STEP 4: Мастер 1 принимает заказ ===")
    
    await accept_offer(telegram_client, order_id)
    await asyncio.sleep(2)
    
    # Проверяем статус
    db_session.expire_all()
    status = await get_order_status(db_session, order_id)
    assert status == "ASSIGNED", f"Expected ASSIGNED, got {status}"
    print(f"✓ Заказ принят, статус: {status}")
    
    # Проверяем что у Мастера 2 оффер исчез/отменился
    result = await db_session.execute(
        text("""
            SELECT status FROM offers 
            WHERE order_id = :order_id AND master_id = :master_id
        """),
        {"order_id": order_id, "master_id": master2_id}
    )
    offer2_status = result.scalar()
    assert offer2_status in ("EXPIRED", "CANCELLED"), \
        f"Мастер 2 оффер должен быть отменен, но статус: {offer2_status}"
    print("✓ Оффер Мастера 2 отменён")
    
    print("\n=== STEP 5: Мастер 1 начинает работу ===")
    
    await start_work(telegram_client, order_id)
    await asyncio.sleep(2)
    
    db_session.expire_all()
    status = await get_order_status(db_session, order_id)
    assert status == "STARTED", f"Expected STARTED, got {status}"
    print(f"✓ Работа начата, статус: {status}")
    
    print("\n=== STEP 6: Мастер 1 завершает работу ===")
    
    await complete_work(telegram_client, order_id)
    await asyncio.sleep(2)
    
    db_session.expire_all()
    status = await get_order_status(db_session, order_id)
    assert status == "MASTER_COMPLETED", f"Expected MASTER_COMPLETED, got {status}"
    print(f"✓ Работа завершена, статус: {status}")
    
    print("\n=== STEP 7: Админ финализирует заказ ===")
    
    await finalize_order(telegram_client, order_id)
    await asyncio.sleep(2)
    
    db_session.expire_all()
    status = await get_order_status(db_session, order_id)
    assert status == "CLOSED", f"Expected CLOSED, got {status}"
    print(f"✓ Заказ закрыт, статус: {status}")
    
    print("\n=== STEP 8: Проверка комиссии ===")
    
    # Проверяем что комиссия создана
    result = await db_session.execute(
        text("""
            SELECT id, amount, rate, status 
            FROM commissions 
            WHERE order_id = :order_id AND master_id = :master_id
        """),
        {"order_id": order_id, "master_id": master1_id}
    )
    commission = result.first()
    
    assert commission is not None, "Комиссия не создана"
    assert commission.amount == 1500, f"Expected 1500 (50%), got {commission.amount}"
    assert commission.rate == 0.5, f"Expected rate 0.5, got {commission.rate}"
    assert commission.status == "PENDING", f"Expected PENDING, got {commission.status}"
    print(f"✓ Комиссия создана: {commission.amount} руб (50%)")
    
    print("\n=== STEP 9: Проверка истории статусов ===")
    
    result = await db_session.execute(
        text("""
            SELECT status 
            FROM order_status_history 
            WHERE order_id = :order_id 
            ORDER BY created_at
        """),
        {"order_id": order_id}
    )
    statuses = [row.status for row in result.fetchall()]
    
    expected_statuses = ["NEW", "IN_QUEUE", "ASSIGNED", "STARTED", "MASTER_COMPLETED", "CLOSED"]
    assert statuses == expected_statuses, \
        f"История статусов не соответствует ожидаемой.\nОжидается: {expected_statuses}\nПолучено: {statuses}"
    print(f"✓ История статусов полная: {' → '.join(statuses)}")
    
    print("\n✅ TP-001: PASSED - Полный цикл заказа выполнен успешно")
