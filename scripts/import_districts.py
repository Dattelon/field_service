"""
Скрипт для массового импорта районов городов из CSV/JSON файла.
Поддерживает несколько форматов данных и автоматическую загрузку.

Usage:
    python scripts/import_districts.py --file data/districts.csv
    python scripts/import_districts.py --file data/districts.json --format json
    python scripts/import_districts.py --city "Новосибирск" --file data/novosibirsk.csv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.db.session import SessionLocal

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


# ====== ФОРМАТЫ ДАННЫХ ======

# Формат 1: CSV с колонками city_name, district_name
# Пример:
# city_name,district_name
# Новосибирск,Центральный район
# Новосибирск,Ленинский район

# Формат 2: JSON
# {
#   "Новосибирск": ["Центральный район", "Ленинский район"],
#   "Екатеринбург": ["Верх-Исетский", "Железнодорожный"]
# }

# Формат 3: CSV расширенный (с ID города)
# city_id,city_name,district_name
# 6,Новосибирск,Центральный район


async def get_city_id(session: AsyncSession, city_name: str) -> int | None:
    """Получить ID города по названию."""
    result = await session.execute(
        select(m.cities.id).where(m.cities.name == city_name)
    )
    city_id = result.scalar_one_or_none()
    if city_id is None:
        logger.warning(f"Город не найден: {city_name}")
    return city_id


async def import_from_csv(
    session: AsyncSession,
    file_path: Path,
    *,
    city_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Импорт районов из CSV файла.
    
    Формат CSV:
    - city_name,district_name
    - или city_id,city_name,district_name
    """
    stats = {"added": 0, "skipped": 0, "errors": 0}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        
        # Определяем формат по заголовкам
        fieldnames = reader.fieldnames
        if not fieldnames:
            raise ValueError("CSV файл пустой или некорректный")
        
        has_city_id = 'city_id' in fieldnames
        has_city_name = 'city_name' in fieldnames
        has_district_name = 'district_name' in fieldnames
        
        if not has_district_name:
            raise ValueError("CSV должен содержать колонку 'district_name'")
        
        if not has_city_name and not has_city_id:
            raise ValueError("CSV должен содержать 'city_name' или 'city_id'")
        
        for row in reader:
            try:
                # Получаем город
                if has_city_id and row['city_id']:
                    city_id = int(row['city_id'])
                elif has_city_name:
                    city_name = row['city_name'].strip()
                    
                    # Фильтр по городу
                    if city_filter and city_name != city_filter:
                        continue
                    
                    city_id = await get_city_id(session, city_name)
                    if city_id is None:
                        stats["errors"] += 1
                        continue
                else:
                    logger.error(f"Не удалось определить город для строки: {row}")
                    stats["errors"] += 1
                    continue
                
                district_name = row['district_name'].strip()
                
                if not district_name:
                    logger.warning(f"Пустое название района, пропуск")
                    stats["skipped"] += 1
                    continue
                
                # Проверяем существование
                existing = await session.execute(
                    select(m.districts.id)
                    .where(m.districts.city_id == city_id)
                    .where(m.districts.name == district_name)
                )
                if existing.scalar_one_or_none():
                    logger.debug(f"Район уже существует: {district_name} (город {city_id})")
                    stats["skipped"] += 1
                    continue
                
                # Добавляем район
                if not dry_run:
                    await session.execute(
                        insert(m.districts).values(
                            city_id=city_id,
                            name=district_name,
                        )
                    )
                
                logger.info(f"✓ Добавлен: {district_name} (город {city_id})")
                stats["added"] += 1
                
            except Exception as e:
                logger.error(f"Ошибка обработки строки {row}: {e}")
                stats["errors"] += 1
                continue
    
    if not dry_run:
        await session.commit()
    
    return stats


async def import_from_json(
    session: AsyncSession,
    file_path: Path,
    *,
    city_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Импорт районов из JSON файла.
    
    Формат JSON:
    {
        "Новосибирск": ["Центральный район", "Ленинский район"],
        "Екатеринбург": ["Верх-Исетский", "Железнодорожный"]
    }
    """
    stats = {"added": 0, "skipped": 0, "errors": 0}
    
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not isinstance(data, dict):
        raise ValueError("JSON должен быть объектом с городами как ключами")
    
    for city_name, districts in data.items():
        # Фильтр по городу
        if city_filter and city_name != city_filter:
            continue
        
        city_id = await get_city_id(session, city_name)
        if city_id is None:
            logger.error(f"Город не найден: {city_name}")
            stats["errors"] += len(districts) if isinstance(districts, list) else 1
            continue
        
        if not isinstance(districts, list):
            logger.error(f"Для города {city_name} районы должны быть списком")
            stats["errors"] += 1
            continue
        
        for district_name in districts:
            district_name = str(district_name).strip()
            
            if not district_name:
                stats["skipped"] += 1
                continue
            
            # Проверяем существование
            existing = await session.execute(
                select(m.districts.id)
                .where(m.districts.city_id == city_id)
                .where(m.districts.name == district_name)
            )
            if existing.scalar_one_or_none():
                logger.debug(f"Район уже существует: {district_name} (город {city_id})")
                stats["skipped"] += 1
                continue
            
            # Добавляем район
            if not dry_run:
                await session.execute(
                    insert(m.districts).values(
                        city_id=city_id,
                        name=district_name,
                    )
                )
            
            logger.info(f"✓ Добавлен: {district_name} для города {city_name}")
            stats["added"] += 1
    
    if not dry_run:
        await session.commit()
    
    return stats


async def remove_placeholder_districts(
    session: AsyncSession,
    *,
    placeholder: str = "Город целиком",
    dry_run: bool = False,
) -> int:
    """
    Удалить placeholder районы после импорта реальных.
    
    Внимание: Удаляет только если есть другие районы для города!
    """
    removed = 0
    
    # Находим города с placeholder И другими районами
    result = await session.execute(
        select(m.districts.city_id)
        .where(m.districts.name == placeholder)
    )
    city_ids = [row[0] for row in result.fetchall()]
    
    for city_id in city_ids:
        # Проверяем что есть другие районы
        count_result = await session.execute(
            select(m.districts.id)
            .where(m.districts.city_id == city_id)
            .where(m.districts.name != placeholder)
        )
        other_districts = count_result.fetchall()
        
        if len(other_districts) > 0:
            # Есть другие районы - можно удалить placeholder
            if not dry_run:
                await session.execute(
                    m.districts.__table__.delete()
                    .where(m.districts.city_id == city_id)
                    .where(m.districts.name == placeholder)
                )
            logger.info(f"✓ Удалён placeholder для города {city_id} ({len(other_districts)} других районов)")
            removed += 1
        else:
            logger.warning(f"Нет других районов для города {city_id}, placeholder сохранён")
    
    if not dry_run:
        await session.commit()
    
    return removed


async def main() -> int:
    parser = argparse.ArgumentParser(
        description='Импорт районов городов из файла',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры использования:

  # Импорт из CSV
  python scripts/import_districts.py --file data/districts.csv

  # Импорт из JSON
  python scripts/import_districts.py --file data/districts.json --format json

  # Только для одного города
  python scripts/import_districts.py --file data/all.csv --city "Новосибирск"

  # Тестовый прогон (без сохранения)
  python scripts/import_districts.py --file data/districts.csv --dry-run

  # Удалить "Город целиком" после импорта
  python scripts/import_districts.py --remove-placeholder

Форматы файлов:

  CSV:
    city_name,district_name
    Новосибирск,Центральный район
    Новосибирск,Ленинский район

  JSON:
    {
      "Новосибирск": ["Центральный район", "Ленинский район"],
      "Екатеринбург": ["Верх-Исетский", "Железнодорожный"]
    }
        """
    )
    
    parser.add_argument(
        '--file', '-f',
        type=str,
        help='Путь к файлу с данными'
    )
    parser.add_argument(
        '--format',
        type=str,
        choices=['csv', 'json'],
        default='csv',
        help='Формат файла (default: csv)'
    )
    parser.add_argument(
        '--city',
        type=str,
        help='Импортировать только для указанного города'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Тестовый прогон без сохранения в БД'
    )
    parser.add_argument(
        '--remove-placeholder',
        action='store_true',
        help='Удалить "Город целиком" после импорта'
    )
    
    args = parser.parse_args()
    
    if not args.file and not args.remove_placeholder:
        parser.error('Требуется --file или --remove-placeholder')
    
    async with SessionLocal() as session:
        try:
            if args.file:
                file_path = Path(args.file)
                
                if not file_path.exists():
                    logger.error(f"Файл не найден: {file_path}")
                    return 1
                
                logger.info(f"Импорт из файла: {file_path}")
                logger.info(f"Формат: {args.format}")
                if args.city:
                    logger.info(f"Фильтр по городу: {args.city}")
                if args.dry_run:
                    logger.info("ТЕСТОВЫЙ РЕЖИМ - изменения не сохраняются")
                
                if args.format == 'json':
                    stats = await import_from_json(
                        session,
                        file_path,
                        city_filter=args.city,
                        dry_run=args.dry_run,
                    )
                else:
                    stats = await import_from_csv(
                        session,
                        file_path,
                        city_filter=args.city,
                        dry_run=args.dry_run,
                    )
                
                logger.info("")
                logger.info("=" * 60)
                logger.info("СТАТИСТИКА ИМПОРТА:")
                logger.info(f"  Добавлено районов: {stats['added']}")
                logger.info(f"  Пропущено (дубликаты): {stats['skipped']}")
                logger.info(f"  Ошибок: {stats['errors']}")
                logger.info("=" * 60)
            
            if args.remove_placeholder:
                logger.info("")
                logger.info("Удаление placeholder районов...")
                removed = await remove_placeholder_districts(
                    session,
                    dry_run=args.dry_run,
                )
                logger.info(f"Удалено placeholder районов: {removed}")
            
            return 0
            
        except Exception as e:
            logger.exception(f"Ошибка импорта: {e}")
            return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    raise SystemExit(exit_code)
