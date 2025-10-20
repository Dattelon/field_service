"""
Скрипт для проверки соответствия моделей SQLAlchemy и реальной схемы БД.

Использование:
    python check_models_db_sync.py

Проверяет:
1. Наличие всех колонок из БД в models.py
2. Соответствие типов данных
3. Наличие FK constraints
4. Отсутствие лишних полей в models.py
"""

import sys
from pathlib import Path

# Добавим путь к проекту
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import inspect, create_engine
from sqlalchemy.dialects import postgresql
from field_service.config import settings
from field_service.db.models import Base, orders, commissions, offers, staff_access_codes


def check_table_sync(table_name: str, model_class, inspector) -> tuple[list, list, list]:
    """
    Проверяет синхронизацию таблицы БД с моделью.
    
    Returns:
        tuple: (missing_in_model, extra_in_model, type_mismatches)
    """
    # Получаем колонки из БД
    db_columns = {col["name"]: col for col in inspector.get_columns(table_name)}
    
    # Получаем колонки из модели
    model_columns = {}
    for col_name, col in model_class.__table__.columns.items():
        # Пропускаем synonym'ы (они не реальные колонки)
        if hasattr(model_class, col_name):
            attr = getattr(model_class, col_name)
            if hasattr(attr, 'fget'):  # это property
                continue
        model_columns[col_name] = col
    
    missing_in_model = []
    extra_in_model = []
    type_mismatches = []
    
    # Проверяем отсутствующие в модели колонки
    for db_col_name, db_col in db_columns.items():
        if db_col_name not in model_columns:
            missing_in_model.append({
                "column": db_col_name,
                "type": str(db_col["type"]),
                "nullable": db_col["nullable"]
            })
    
    # Проверяем лишние колонки в модели
    for model_col_name in model_columns:
        if model_col_name not in db_columns:
            # Проверим, может это synonym
            if hasattr(model_class, model_col_name):
                attr = getattr(model_class, model_col_name)
                from sqlalchemy.orm import synonym as sa_synonym
                # Пропускаем synonym'ы
                if isinstance(getattr(model_class.__dict__.get(model_col_name, None), 'descriptor', None), 
                             type(sa_synonym('x'))):
                    continue
            extra_in_model.append(model_col_name)
    
    # Проверяем соответствие типов
    for col_name in set(db_columns.keys()) & set(model_columns.keys()):
        db_type = str(db_columns[col_name]["type"])
        model_col = model_columns[col_name]
        model_type = str(model_col.type.compile(dialect=postgresql.dialect()))
        
        # Упрощенная проверка типов (для основных случаев)
        if not types_compatible(db_type, model_type):
            type_mismatches.append({
                "column": col_name,
                "db_type": db_type,
                "model_type": model_type
            })
    
    return missing_in_model, extra_in_model, type_mismatches


def types_compatible(db_type: str, model_type: str) -> bool:
    """Проверяет совместимость типов данных."""
    # Нормализуем типы
    db_type = db_type.upper().replace("CHARACTER VARYING", "VARCHAR")
    model_type = model_type.upper()
    
    # Простые эквивалентности
    equivalents = {
        "INTEGER": ["INTEGER", "INT"],
        "BIGINT": ["BIGINT"],
        "BOOLEAN": ["BOOLEAN", "BOOL"],
        "TIMESTAMP WITH TIME ZONE": ["TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ"],
        "TEXT": ["TEXT"],
        "JSONB": ["JSONB"],
    }
    
    for db_eq, model_eqs in equivalents.items():
        if db_type.startswith(db_eq):
            return any(model_type.startswith(m) for m in model_eqs)
    
    # VARCHAR и NUMERIC с параметрами
    if "VARCHAR" in db_type or "CHARACTER VARYING" in db_type:
        return "VARCHAR" in model_type or "CHARACTER VARYING" in model_type
    
    if "NUMERIC" in db_type:
        return "NUMERIC" in model_type
    
    # USER-DEFINED (ENUM)
    if "USER-DEFINED" in db_type:
        # Enum'ы обычно совместимы, если имя совпадает
        return True
    
    return db_type == model_type


def check_foreign_keys(table_name: str, model_class, inspector) -> tuple[list, list]:
    """Проверяет соответствие FK constraints."""
    db_fks = inspector.get_foreign_keys(table_name)
    
    # Собираем FK из модели
    model_fks = []
    for col in model_class.__table__.columns:
        if col.foreign_keys:
            for fk in col.foreign_keys:
                model_fks.append({
                    "column": col.name,
                    "ref_table": fk.column.table.name,
                    "ref_column": fk.column.name
                })
    
    # Собираем FK из БД в удобный формат
    db_fks_normalized = []
    for fk in db_fks:
        db_fks_normalized.append({
            "column": fk["constrained_columns"][0],
            "ref_table": fk["referred_table"],
            "ref_column": fk["referred_columns"][0]
        })
    
    missing_fk = []
    extra_fk = []
    
    # Проверяем отсутствующие FK в модели
    for db_fk in db_fks_normalized:
        if db_fk not in model_fks:
            # Проверим, может колонка вообще отсутствует в модели
            col_exists = db_fk["column"] in [c.name for c in model_class.__table__.columns]
            if col_exists:
                missing_fk.append(db_fk)
    
    # Проверяем лишние FK в модели
    for model_fk in model_fks:
        if model_fk not in db_fks_normalized:
            extra_fk.append(model_fk)
    
    return missing_fk, extra_fk


def main():
    """Основная функция проверки."""
    print("Проверка синхронизации models.py с базой данных...")
    print("=" * 70)
    
    # Подключаемся к БД (используем синхронный драйвер для скрипта проверки)
    db_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    engine = create_engine(db_url)
    inspector = inspect(engine)
    
    # Список таблиц для проверки
    tables_to_check = [
        ("orders", orders),
        ("commissions", commissions),
        ("offers", offers),
        ("staff_access_codes", staff_access_codes),
    ]
    
    all_ok = True
    
    for table_name, model_class in tables_to_check:
        print(f"\nТаблица: {table_name}")
        print("-" * 70)
        
        # Проверяем колонки
        missing, extra, type_mismatches = check_table_sync(table_name, model_class, inspector)
        
        if missing:
            all_ok = False
            print(f"\n[!] Отсутствуют в models.py ({len(missing)}):")
            for col in missing:
                print(f"   - {col['column']}: {col['type']} (nullable={col['nullable']})")
        
        if extra:
            all_ok = False
            print(f"\n[!] Лишние в models.py ({len(extra)}):")
            for col in extra:
                print(f"   - {col}")
        
        if type_mismatches:
            all_ok = False
            print(f"\n[!] Несоответствие типов ({len(type_mismatches)}):")
            for mismatch in type_mismatches:
                print(f"   - {mismatch['column']}:")
                print(f"     БД:     {mismatch['db_type']}")
                print(f"     Модель: {mismatch['model_type']}")
        
        # Проверяем FK
        missing_fk, extra_fk = check_foreign_keys(table_name, model_class, inspector)
        
        if missing_fk:
            all_ok = False
            print(f"\n[!] Отсутствующие FK в models.py ({len(missing_fk)}):")
            for fk in missing_fk:
                print(f"   - {fk['column']} -> {fk['ref_table']}.{fk['ref_column']}")
        
        if extra_fk:
            all_ok = False
            print(f"\n[!] Лишние FK в models.py ({len(extra_fk)}):")
            for fk in extra_fk:
                print(f"   - {fk['column']} -> {fk['ref_table']}.{fk['ref_column']}")
        
        if not (missing or extra or type_mismatches or missing_fk or extra_fk):
            print("[OK] Все в порядке!")
    
    print("\n" + "=" * 70)
    if all_ok:
        print("[OK] Все таблицы синхронизированы!")
        return 0
    else:
        print("[ERROR] Обнаружены несоответствия. Требуется исправление.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
