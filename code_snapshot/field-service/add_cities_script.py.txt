#!/usr/bin/env python3
"""
Скрипт для добавления всех 78 городов в базу данных.
Использует существующие модели SQLAlchemy для правильной работы с UTF-8.

Запуск:
docker exec -i field-service-admin-bot-1 python /app/add_cities_script.py
"""
import asyncio
from sqlalchemy import select
from field_service.db.session import SessionLocal
from field_service.db import models as m
from field_service.data.cities import ALLOWED_CITIES, CITY_TIMEZONES

async def add_all_cities():
    async with SessionLocal() as session:
        async with session.begin():
            # Получаем существующие города
            result = await session.execute(select(m.cities.name))
            existing = {row[0] for row in result.all()}
            
            added = 0
            updated = 0
            
            for city_name in ALLOWED_CITIES:
                timezone = CITY_TIMEZONES.get(city_name, 'Europe/Moscow')
                
                if city_name not in existing:
                    # Добавляем новый город
                    city = m.cities(
                        name=city_name,
                        is_active=True,
                        timezone=timezone
                    )
                    session.add(city)
                    added += 1
                    print(f"+ Добавлен: {city_name}")
                else:
                    # Обновляем существующий город
                    stmt = (
                        m.cities.__table__.update()
                        .where(m.cities.name == city_name)
                        .values(is_active=True, timezone=timezone)
                    )
                    await session.execute(stmt)
                    updated += 1
                    print(f"* Обновлён: {city_name}")
            
            await session.commit()
            
            print(f"\n✅ Готово!")
            print(f"   Добавлено новых: {added}")
            print(f"   Обновлено: {updated}")
            print(f"   Всего: {added + updated}")

if __name__ == "__main__":
    asyncio.run(add_all_cities())
