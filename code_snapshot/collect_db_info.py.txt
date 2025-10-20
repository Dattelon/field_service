#!/usr/bin/env python3
"""
Скрипт для сбора полной информации из БД PostgreSQL проекта Field Service
"""
import subprocess
import json
from datetime import datetime

def run_psql_command(command):
    """Выполнить команду psql через docker"""
    full_command = f'docker exec field-service-postgres-1 psql -U field_user -d field_service -c "{command}"'
    result = subprocess.run(
        full_command,
        shell=True,
        capture_output=True,
        text=True,
        encoding='utf-8'
    )
    return result.stdout

def get_table_list():
    """Получить список всех таблиц"""
    output = run_psql_command("SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;")
    lines = output.strip().split('\n')
    tables = []
    for line in lines[2:-2]:  # Пропускаем заголовок и футер
        table_name = line.strip()
        if table_name and table_name != '---':
            tables.append(table_name)
    return tables

def get_table_structure(table_name):
    """Получить структуру таблицы"""
    return run_psql_command(f"\\d+ {table_name}")

def get_table_data(table_name):
    """Получить данные из таблицы"""
    return run_psql_command(f"SELECT * FROM {table_name} LIMIT 1000;")

def get_table_count(table_name):
    """Получить количество записей"""
    output = run_psql_command(f"SELECT COUNT(*) FROM {table_name};")
    lines = output.strip().split('\n')
    if len(lines) >= 3:
        return lines[2].strip()
    return "0"

def main():
    """Основная функция"""
    print("Начинаю сбор информации из БД...")
    
    output = []
    output.append("# База данных Field Service - Полная структура и данные")
    output.append(f"\n**Дата сбора:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output.append("\n---\n")
    
    # Получаем список таблиц
    tables = get_table_list()
    print(f"Найдено таблиц: {len(tables)}")
    
    output.append(f"## Обзор\n")
    output.append(f"Всего таблиц в базе: **{len(tables)}**\n")
    output.append("\n### Список таблиц:\n")
    for i, table in enumerate(tables, 1):
        output.append(f"{i}. `{table}`")
    output.append("\n---\n")
    
    # Собираем информацию по каждой таблице
    for i, table in enumerate(tables, 1):
        print(f"[{i}/{len(tables)}] Обрабатываю таблицу: {table}")
        
        output.append(f"\n## {i}. Таблица: `{table}`\n")
        
        # Количество записей
        count = get_table_count(table)
        output.append(f"**Количество записей:** {count}\n")
        
        # Структура
        output.append(f"### Структура таблицы\n")
        output.append("```sql")
        structure = get_table_structure(table)
        output.append(structure)
        output.append("```\n")
        
        # Данные
        output.append(f"### Данные (до 1000 записей)\n")
        output.append("```")
        data = get_table_data(table)
        output.append(data)
        output.append("```\n")
        output.append("\n---\n")
    
    # Сохраняем в файл
    output_file = r"C:\ProjectF\ALL_BD.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(output))
    
    print(f"Готово! Файл сохранен: {output_file}")
    print(f"Обработано таблиц: {len(tables)}")

if __name__ == "__main__":
    main()
