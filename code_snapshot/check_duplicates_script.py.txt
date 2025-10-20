"""
Скрипт для проверки дубликатов и несоответствий между models.py и БД.

Использование:
    python check_model_duplicates.py
"""

import sys
from pathlib import Path
from typing import Dict, List, Set
import re

# Путь к проекту
PROJECT_ROOT = Path(r"C:\ProjectF\field-service")
MODELS_FILE = PROJECT_ROOT / "field_service" / "db" / "models.py"
ALEMBIC_VERSIONS = PROJECT_ROOT / "alembic" / "versions"

# Каноническая схема из ALL_BD.md
CANONICAL_SCHEMA = {
    "orders": {
        "fields": {
            "id", "city_id", "district_id", "street_id", "house", "apartment",
            "address_comment", "client_name", "client_phone", "status",
            "preferred_master_id", "assigned_master_id", "created_by_staff_id",
            "created_at", "updated_at", "version", "company_payment",
            "guarantee_source_order_id", "order_type", "category", "description",
            "late_visit", "dist_escalated_logist_at", "dist_escalated_admin_at",
            "lat", "lon", "timeslot_start_utc", "timeslot_end_utc", "total_sum",
            "cancel_reason", "no_district", "type", "geocode_provider",
            "geocode_confidence", "escalation_logist_notified_at",
            "escalation_admin_notified_at"
        },
        "fks": {
            "city_id": "cities.id",
            "district_id": "districts.id",
            "street_id": "streets.id",
            "preferred_master_id": "masters.id",
            "assigned_master_id": "masters.id",
            "created_by_staff_id": "staff_users.id",
            "guarantee_source_order_id": "orders.id"
        }
    },
    "commissions": {
        "fields": {
            "id", "order_id", "master_id", "amount", "percent", "status",
            "deadline_at", "paid_at", "blocked_applied", "blocked_at",
            "payment_reference", "created_at", "updated_at", "rate",
            "paid_reported_at", "paid_approved_at", "paid_amount", "is_paid",
            "has_checks", "pay_to_snapshot"
        },
        "fks": {
            "order_id": "orders.id",
            "master_id": "masters.id"
        },
        "constraints": {
            "unique": ["order_id"]
        }
    },
    "offers": {
        "fields": {
            "id", "order_id", "master_id", "round_number", "state", "sent_at",
            "responded_at", "expires_at", "created_at"
        },
        "fks": {
            "order_id": "orders.id",
            "master_id": "masters.id"
        }
    },
    "staff_access_codes": {
        "fields": {
            "id", "code", "role", "city_id", "created_by_staff_id",
            "used_by_staff_id", "expires_at", "used_at", "created_at",
            "comment", "revoked_at"
        },
        "fks": {
            "city_id": "cities.id",
            "created_by_staff_id": "staff_users.id",
            "used_by_staff_id": "staff_users.id"
        }
    }
}


def extract_model_fields(model_text: str) -> Set[str]:
    """Извлекает имена полей из определения модели."""
    fields = set()
    # Паттерн для Mapped полей
    pattern = r'(\w+):\s*Mapped\[.*?\]\s*=\s*mapped_column'
    for match in re.finditer(pattern, model_text):
        fields.add(match.group(1))
    return fields


def check_model_consistency(model_name: str, model_text: str) -> List[str]:
    """Проверяет соответствие модели канонической схеме."""
    issues = []
    
    if model_name not in CANONICAL_SCHEMA:
        return issues
    
    canonical = CANONICAL_SCHEMA[model_name]
    actual_fields = extract_model_fields(model_text)
    
    # Проверка отсутствующих полей
    missing_fields = canonical["fields"] - actual_fields
    if missing_fields:
        issues.append(f"  ❌ Отсутствующие поля: {', '.join(sorted(missing_fields))}")
    
    # Проверка лишних полей (могут быть алиасами - это OK)
    extra_fields = actual_fields - canonical["fields"]
    if extra_fields:
        # Проверяем, являются ли они synonym
        non_synonym_extras = []
        for field in extra_fields:
            if not re.search(rf'{field}\s*=\s*synonym\(', model_text):
                non_synonym_extras.append(field)
        
        if non_synonym_extras:
            issues.append(f"  ⚠️  Дополнительные поля (не алиасы): {', '.join(sorted(non_synonym_extras))}")
    
    # Проверка FK
    if "fks" in canonical:
        for fk_field, fk_target in canonical["fks"].items():
            # Ищем ForeignKey в определении поля
            fk_pattern = rf'{fk_field}:\s*Mapped.*?ForeignKey\(["\']({fk_target})["\']'
            if not re.search(fk_pattern, model_text):
                # Проверяем, может быть FK определен без явного указания (только Integer)
                int_pattern = rf'{fk_field}:\s*Mapped.*?mapped_column\(\s*(?:Integer|BigInteger)'
                if re.search(int_pattern, model_text):
                    issues.append(f"  ❌ Поле {fk_field} должно иметь FK на {fk_target}")
    
    # Проверка unique constraints
    if "constraints" in canonical and "unique" in canonical["constraints"]:
        for unique_field in canonical["constraints"]["unique"]:
            if not re.search(rf'{unique_field}.*unique\s*=\s*True', model_text):
                issues.append(f"  ⚠️  Поле {unique_field} должно быть unique")
    
    return issues


def find_migration_duplicates() -> Dict[str, List[str]]:
    """Ищет дубликаты определений таблиц в миграциях."""
    duplicates = {}
    
    if not ALEMBIC_VERSIONS.exists():
        return duplicates
    
    table_creates = {
        "orders": [],
        "commissions": [],
        "offers": [],
        "staff_access_codes": []
    }
    
    for migration_file in ALEMBIC_VERSIONS.glob("*.py"):
        content = migration_file.read_text(encoding="utf-8")
        
        # Ищем op.create_table для каждой таблицы
        for table_name in table_creates.keys():
            pattern = rf'op\.create_table\(\s*["\']({table_name})["\']'
            if re.search(pattern, content):
                table_creates[table_name].append(migration_file.name)
    
    # Оставляем только таблицы с множественными созданиями
    for table_name, files in table_creates.items():
        if len(files) > 1:
            duplicates[table_name] = files
    
    return duplicates


def main():
    print("=" * 80)
    print("ПРОВЕРКА МОДЕЛЕЙ И ДУБЛИКАТОВ")
    print("=" * 80)
    print()
    
    # Проверка существования файла models.py
    if not MODELS_FILE.exists():
        print(f"❌ Файл не найден: {MODELS_FILE}")
        sys.exit(1)
    
    print(f"✅ Проверка файла: {MODELS_FILE}")
    print()
    
    # Читаем models.py
    models_content = MODELS_FILE.read_text(encoding="utf-8")
    
    # Проверяем каждую модель
    total_issues = 0
    for model_name in CANONICAL_SCHEMA.keys():
        # Извлекаем определение класса
        pattern = rf'class {model_name}\(Base\):.*?(?=\nclass\s|\n\n# =====|\Z)'
        match = re.search(pattern, models_content, re.DOTALL)
        
        if not match:
            print(f"⚠️  Модель {model_name} не найдена в models.py")
            print()
            continue
        
        model_text = match.group(0)
        issues = check_model_consistency(model_name, model_text)
        
        if issues:
            print(f"📋 Модель: {model_name}")
            for issue in issues:
                print(issue)
            print()
            total_issues += len(issues)
        else:
            print(f"✅ Модель {model_name} - соответствует схеме")
            print()
    
    # Проверка дубликатов в миграциях
    print("=" * 80)
    print("ПРОВЕРКА ДУБЛИКАТОВ В МИГРАЦИЯХ")
    print("=" * 80)
    print()
    
    duplicates = find_migration_duplicates()
    
    if duplicates:
        print("⚠️  Обнаружены множественные создания таблиц:")
        print()
        for table_name, files in duplicates.items():
            print(f"  Таблица '{table_name}' создается в {len(files)} миграциях:")
            for file in files:
                print(f"    - {file}")
            print()
    else:
        print("✅ Дубликатов в миграциях не обнаружено")
        print()
    
    # Итоги
    print("=" * 80)
    print("ИТОГИ")
    print("=" * 80)
    print()
    print(f"Всего проблем в models.py: {total_issues}")
    print(f"Таблиц с дубликатами в миграциях: {len(duplicates)}")
    print()
    
    if total_issues > 0 or duplicates:
        print("⚠️  Требуется исправление")
        print("Используйте артефакт 'models_patch' для применения изменений")
        sys.exit(1)
    else:
        print("✅ Все проверки пройдены успешно!")
        sys.exit(0)


if __name__ == "__main__":
    main()
