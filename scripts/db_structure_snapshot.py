"""
Скрипт для создания снапшота структуры базы данных PostgreSQL
Создает детальный текстовый файл со всей структурой БД
"""

import asyncio
import asyncpg
from datetime import datetime
from pathlib import Path


async def get_db_structure():
    """Получить полную структуру БД"""
    
    # Параметры подключения
    conn = await asyncpg.connect(
        host='localhost',
        port=5432,
        user='fs_user',
        password='fs_password',
        database='field_service'
    )
    
    output = []
    output.append("=" * 80)
    output.append("СНАПШОТ СТРУКТУРЫ БАЗЫ ДАННЫХ")
    output.append("=" * 80)
    output.append(f"Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    output.append(f"База данных: field_service")
    output.append("=" * 80)
    output.append("")
    
    # Получить список таблиц
    tables = await conn.fetch("""
        SELECT tablename 
        FROM pg_tables 
        WHERE schemaname = 'public' 
        ORDER BY tablename
    """)
    
    output.append(f"ВСЕГО ТАБЛИЦ: {len(tables)}")
    output.append("")
    output.append("СПИСОК ТАБЛИЦ:")
    for i, table in enumerate(tables, 1):
        output.append(f"  {i}. {table['tablename']}")
    output.append("")
    output.append("=" * 80)
    output.append("")
    
    # Для каждой таблицы получить детальную информацию
    for table_row in tables:
        table_name = table_row['tablename']
        
        output.append("")
        output.append("=" * 80)
        output.append(f"ТАБЛИЦА: {table_name}")
        output.append("=" * 80)
        output.append("")
        
        # Получить структуру колонок
        columns = await conn.fetch(f"""
            SELECT 
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = 'public' 
                AND table_name = $1
            ORDER BY ordinal_position
        """, table_name)
        
        output.append("КОЛОНКИ:")
        output.append("-" * 80)
        for col in columns:
            col_name = col['column_name']
            col_type = col['data_type']
            
            # Добавить длину для varchar
            if col['character_maximum_length']:
                col_type += f"({col['character_maximum_length']})"
            
            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            default = f"DEFAULT {col['column_default']}" if col['column_default'] else ""
            
            output.append(f"  {col_name:30} {col_type:30} {nullable:10} {default}")
        
        output.append("")
        
        # Получить Primary Key
        pk = await conn.fetch(f"""
            SELECT a.attname
            FROM pg_index i
            JOIN pg_attribute a ON a.attrelid = i.indrelid
                AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = $1::regclass
                AND i.indisprimary
        """, table_name)
        
        if pk:
            pk_cols = ', '.join([row['attname'] for row in pk])
            output.append(f"PRIMARY KEY: {pk_cols}")
            output.append("")
        
        # Получить индексы
        indexes = await conn.fetch(f"""
            SELECT
                i.relname as index_name,
                am.amname as index_type,
                idx.indisunique as is_unique,
                ARRAY(
                    SELECT pg_get_indexdef(idx.indexrelid, k + 1, true)
                    FROM generate_subscripts(idx.indkey, 1) as k
                    ORDER BY k
                ) as index_keys
            FROM pg_index idx
            JOIN pg_class i ON i.oid = idx.indexrelid
            JOIN pg_am am ON i.relam = am.oid
            WHERE idx.indrelid = $1::regclass
                AND NOT idx.indisprimary
            ORDER BY i.relname
        """, table_name)
        
        if indexes:
            output.append("ИНДЕКСЫ:")
            output.append("-" * 80)
            for idx in indexes:
                idx_type = "UNIQUE" if idx['is_unique'] else "INDEX"
                keys = ', '.join(idx['index_keys'])
                output.append(f"  {idx['index_name']:40} {idx_type:10} ({keys})")
            output.append("")
        
        # Получить Foreign Keys
        fks = await conn.fetch(f"""
            SELECT
                tc.constraint_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name,
                rc.update_rule,
                rc.delete_rule
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            JOIN information_schema.referential_constraints AS rc
                ON rc.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
                AND tc.table_schema = 'public'
                AND tc.table_name = $1
        """, table_name)
        
        if fks:
            output.append("FOREIGN KEYS:")
            output.append("-" * 80)
            for fk in fks:
                output.append(f"  {fk['constraint_name']}")
                output.append(f"    {fk['column_name']} -> {fk['foreign_table_name']}({fk['foreign_column_name']})")
                output.append(f"    ON UPDATE {fk['update_rule']} ON DELETE {fk['delete_rule']}")
            output.append("")
        
        # Получить UNIQUE constraints
        uniques = await conn.fetch(f"""
            SELECT
                tc.constraint_name,
                STRING_AGG(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) as columns
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'UNIQUE'
                AND tc.table_schema = 'public'
                AND tc.table_name = $1
            GROUP BY tc.constraint_name
        """, table_name)
        
        if uniques:
            output.append("UNIQUE CONSTRAINTS:")
            output.append("-" * 80)
            for uniq in uniques:
                output.append(f"  {uniq['constraint_name']:40} ({uniq['columns']})")
            output.append("")
        
        # Получить CHECK constraints
        checks = await conn.fetch(f"""
            SELECT
                con.conname as constraint_name,
                pg_get_constraintdef(con.oid) as definition
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = $1
                AND con.contype = 'c'
        """, table_name)
        
        if checks:
            output.append("CHECK CONSTRAINTS:")
            output.append("-" * 80)
            for chk in checks:
                output.append(f"  {chk['constraint_name']}")
                output.append(f"    {chk['definition']}")
            output.append("")
        
        # Получить количество записей
        count = await conn.fetchval(f'SELECT COUNT(*) FROM "{table_name}"')
        output.append(f"КОЛИЧЕСТВО ЗАПИСЕЙ: {count:,}")
        output.append("")
    
    # Получить ENUM типы
    output.append("")
    output.append("=" * 80)
    output.append("ENUM ТИПЫ")
    output.append("=" * 80)
    output.append("")
    
    enums = await conn.fetch("""
        SELECT 
            t.typname as enum_name,
            ARRAY_AGG(e.enumlabel ORDER BY e.enumsortorder) as enum_values
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
        GROUP BY t.typname
        ORDER BY t.typname
    """)
    
    if enums:
        for enum in enums:
            output.append(f"ENUM: {enum['enum_name']}")
            values = ', '.join([f"'{v}'" for v in enum['enum_values']])
            output.append(f"  VALUES: {values}")
            output.append("")
    else:
        output.append("Нет ENUM типов")
        output.append("")
    
    # Получить последовательности (sequences)
    output.append("=" * 80)
    output.append("SEQUENCES")
    output.append("=" * 80)
    output.append("")
    
    sequences = await conn.fetch("""
        SELECT sequencename 
        FROM pg_sequences 
        WHERE schemaname = 'public'
        ORDER BY sequencename
    """)
    
    if sequences:
        for seq in sequences:
            output.append(f"  - {seq['sequencename']}")
        output.append("")
    else:
        output.append("Нет sequences")
        output.append("")
    
    await conn.close()
    
    return "\n".join(output)


async def main():
    """Главная функция"""
    print("Получение структуры базы данных...")
    
    try:
        structure = await get_db_structure()
        
        # Сохранить в файл
        output_file = Path("db_structure_snapshot.txt")
        output_file.write_text(structure, encoding='utf-8')
        
        print(f"✅ Структура БД сохранена в файл: {output_file.absolute()}")
        print(f"📊 Размер файла: {output_file.stat().st_size:,} байт")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
