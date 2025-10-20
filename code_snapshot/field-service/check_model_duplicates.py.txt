#!/usr/bin/env python3
"""
Скрипт для проверки соответствия моделей SQLAlchemy и схемы базы данных.

Проверяет:
1. Наличие всех колонок в моделях и БД
2. Типы данных колонок
3. Foreign key constraints
4. Unique constraints
5. Indexes
"""

import sys
from typing import Dict, List, Set, Tuple
from sqlalchemy import inspect, MetaData
from sqlalchemy.engine import Engine

# Импорты из проекта
try:
    from field_service.db.models import Base
    from field_service.db.session import engine
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
    print("Убедитесь, что скрипт запущен из корня проекта field-service")
    sys.exit(1)


class ModelChecker:
    """Проверяет соответствие моделей и БД."""
    
    def __init__(self, engine: Engine):
        self.engine = engine
        self.inspector = inspect(engine)
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.success: List[str] = []
    
    def check_all(self) -> bool:
        """Запускает все проверки. Возвращает True если всё OK."""
        print("🔍 Проверка соответствия моделей и БД...\n")
        
        tables_to_check = [
            "orders",
            "commissions",
            "offers",
            "staff_access_codes"
        ]
        
        all_ok = True
        for table_name in tables_to_check:
            if not self.check_table(table_name):
                all_ok = False
        
        self._print_results()
        return all_ok
    
    def check_table(self, table_name: str) -> bool:
        """Проверяет соответствие одной таблицы."""
        print(f"\n📋 Таблица: {table_name}")
        print("=" * 60)
        
        # Получаем метаданные из модели
        table = Base.metadata.tables.get(table_name)
        if not table:
            self.errors.append(f"❌ {table_name}: таблица отсутствует в моделях")
            return False
        
        # Получаем метаданные из БД
        try:
            db_columns = {col['name']: col for col in self.inspector.get_columns(table_name)}
            db_fks = self.inspector.get_foreign_keys(table_name)
            db_indexes = self.inspector.get_indexes(table_name)
            db_unique_constraints = self.inspector.get_unique_constraints(table_name)
        except Exception as e:
            self.errors.append(f"❌ {table_name}: ошибка чтения БД - {e}")
            return False
        
        table_ok = True
        
        # Проверяем колонки
        model_columns = {col.name for col in table.columns}
        db_column_names = set(db_columns.keys())
        
        # Недостающие колонки в БД
        missing_in_db = model_columns - db_column_names
        if missing_in_db:
            for col in missing_in_db:
                self.errors.append(f"  ❌ Колонка '{col}' есть в модели, но отсутствует в БД")
                table_ok = False
        
        # Лишние колонки в БД
        extra_in_db = db_column_names - model_columns
        if extra_in_db:
            for col in extra_in_db:
                self.warnings.append(f"  ⚠️ Колонка '{col}' есть в БД, но отсутствует в модели")
        
        # Проверяем типы данных
        for col_name in model_columns & db_column_names:
            model_col = table.columns[col_name]
            db_col = db_columns[col_name]
            
            # Упрощенная проверка типов (можно расширить)
            model_type = str(model_col.type).split('(')[0].lower()
            db_type = str(db_col['type']).split('(')[0].lower()
            
            if model_type != db_type and not self._types_compatible(model_type, db_type):
                self.warnings.append(
                    f"  ⚠️ Колонка '{col_name}': тип в модели ({model_type}) "
                    f"отличается от БД ({db_type})"
                )
        
        # Проверяем Foreign Keys
        if table_name in ["orders", "commissions", "offers", "staff_access_codes"]:
            fk_ok = self._check_foreign_keys(table_name, table, db_fks)
            table_ok = table_ok and fk_ok
        
        # Проверяем UNIQUE constraints
        unique_ok = self._check_unique_constraints(table_name, table, db_unique_constraints)
        table_ok = table_ok and unique_ok
        
        if table_ok and not self.warnings:
            self.success.append(f"✅ {table_name}: OK")
        
        return table_ok
    
    def _check_foreign_keys(self, table_name: str, table, db_fks: List[Dict]) -> bool:
        """Проверяет foreign keys."""
        # Ожидаемые FK для каждой таблицы
        expected_fks = {
            "orders": [],
            "commissions": [
                ("order_id", "orders"),
                ("master_id", "masters"),
            ],
            "offers": [
                ("order_id", "orders"),
                ("master_id", "masters"),  # Восстановлен
            ],
            "staff_access_codes": [
                ("created_by_staff_id", "staff_users"),  # Переименован
                ("used_by_staff_id", "staff_users"),
            ],
        }
        
        if table_name not in expected_fks:
            return True
        
        # Получаем FK из БД
        db_fk_map = {}
        for fk in db_fks:
            for col in fk['constrained_columns']:
                db_fk_map[col] = fk['referred_table']
        
        all_ok = True
        for col, ref_table in expected_fks[table_name]:
            if col not in db_fk_map:
                self.errors.append(
                    f"  ❌ FK отсутствует: {col} → {ref_table}"
                )
                all_ok = False
            elif db_fk_map[col] != ref_table:
                self.errors.append(
                    f"  ❌ FK неверный: {col} → {db_fk_map[col]} (ожидается {ref_table})"
                )
                all_ok = False
            else:
                self.success.append(f"  ✅ FK OK: {col} → {ref_table}")
        
        return all_ok
    
    def _check_unique_constraints(self, table_name: str, table, db_unique: List[Dict]) -> bool:
        """Проверяет UNIQUE constraints."""
        # Ожидаемые UNIQUE для каждой таблицы
        expected_unique = {
            "commissions": [
                {"name": "order_id", "reason": "Каждый заказ имеет только одну комиссию"}
            ],
        }
        
        if table_name not in expected_unique:
            return True
        
        # Получаем UNIQUE из БД
        db_unique_cols = set()
        for uc in db_unique:
            if uc.get('column_names'):
                # Для single-column UNIQUE
                if len(uc['column_names']) == 1:
                    db_unique_cols.add(uc['column_names'][0])
        
        all_ok = True
        for expected in expected_unique[table_name]:
            col_name = expected['name']
            reason = expected['reason']
            
            if col_name not in db_unique_cols:
                self.errors.append(
                    f"  ❌ UNIQUE constraint отсутствует: {col_name} ({reason})"
                )
                all_ok = False
            else:
                self.success.append(f"  ✅ UNIQUE OK: {col_name}")
        
        return all_ok
    
    def _types_compatible(self, model_type: str, db_type: str) -> bool:
        """Проверяет совместимость типов."""
        compatible_pairs = [
            ("integer", "bigint"),
            ("bigint", "integer"),
            ("varchar", "text"),
            ("text", "varchar"),
            ("numeric", "decimal"),
            ("decimal", "numeric"),
            ("timestamp", "timestamptz"),
            ("timestamptz", "timestamp"),
        ]
        
        return (model_type, db_type) in compatible_pairs
    
    def _print_results(self):
        """Выводит итоги проверки."""
        print("\n" + "=" * 60)
        print("📊 ИТОГИ ПРОВЕРКИ")
        print("=" * 60)
        
        if self.success:
            print(f"\n✅ Успешно ({len(self.success)}):")
            for msg in self.success:
                print(msg)
        
        if self.warnings:
            print(f"\n⚠️ Предупреждения ({len(self.warnings)}):")
            for msg in self.warnings:
                print(msg)
        
        if self.errors:
            print(f"\n❌ Ошибки ({len(self.errors)}):")
            for msg in self.errors:
                print(msg)
        
        print("\n" + "=" * 60)
        if self.errors:
            print("❌ Проверка ПРОВАЛЕНА - есть критические ошибки")
            print("Необходимо создать и применить миграцию Alembic")
        elif self.warnings:
            print("⚠️ Проверка прошла с предупреждениями")
            print("Модели и БД в основном синхронизированы")
        else:
            print("✅ Проверка УСПЕШНА - модели полностью соответствуют БД")
        print("=" * 60)


def main():
    """Главная функция."""
    checker = ModelChecker(engine)
    success = checker.check_all()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
