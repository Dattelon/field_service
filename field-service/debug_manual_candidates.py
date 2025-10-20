"""
Отладочный скрипт для проверки manual_candidates для заказа #309
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корневую папку проекта в PATH
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from field_service.config import settings
from field_service.bots.admin_bot.services.masters import DBMastersService

async def main():
    # Создаём движок БД
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    
    # Создаём сервис мастеров
    masters_service = DBMastersService(session_factory)
    
    # Проверяем кандидатов для заказа #309
    order_id = 309
    print(f"Проверка кандидатов для заказа #{order_id}...")
    print()
    
    candidates, has_next = await masters_service.manual_candidates(
        order_id=order_id,
        page=1,
        page_size=10,
    )
    
    print(f"Найдено кандидатов: {len(candidates)}")
    print(f"Есть следующая страница: {has_next}")
    print()
    
    if candidates:
        for i, candidate in enumerate(candidates, 1):
            print(f"{i}. Master #{candidate.id}: {candidate.full_name}")
            print(f"   City ID: {candidate.city_id}")
            print(f"   On shift: {candidate.is_on_shift}")
            print(f"   Verified: {candidate.verified}")
            print(f"   Active: {candidate.is_active}")
            print(f"   In district: {candidate.in_district}")
            print(f"   On break: {candidate.on_break}")
            print(f"   Has car: {candidate.has_car}")
            print(f"   Active orders: {candidate.active_orders}/{candidate.max_active_orders}")
            print()
    else:
        print("No candidates found via manual_candidates!")
        print()
        print("Checking raw SQL query...")
        
        from field_service.services.candidates import select_candidates
        from types import SimpleNamespace
        from field_service.db import models as m
        from sqlalchemy import select as sa_select
        
        async with session_factory() as session:
            order_q = await session.execute(
                sa_select(m.orders.id, m.orders.city_id, m.orders.district_id, m.orders.category).where(m.orders.id == order_id)
            )
            order_row = order_q.first()
            
            if order_row:
                print(f"Order: city={order_row.city_id}, district={order_row.district_id}, category={order_row.category}")
                
                order_payload = SimpleNamespace(id=order_id, city_id=order_row.city_id, district_id=order_row.district_id, category=order_row.category)
                all_cand = await select_candidates(order_payload, "manual", session=session)
                
                print(f"select_candidates returned: {len(all_cand)} total")
                for c in all_cand[:5]:
                    print(f"  Master #{c.master_id}: {c.full_name}, on_shift={c.is_on_shift}, in_district={c.in_district}")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
