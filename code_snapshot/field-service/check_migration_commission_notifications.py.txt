"""
Проверка создания таблицы commission_deadline_notifications
"""
import asyncio
import asyncpg


async def check_table():
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="field_user",
        password="field_pass",
        database="field_service"
    )
    
    # Проверяем существование таблицы
    exists = await conn.fetchval("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name = 'commission_deadline_notifications'
        );
    """)
    
    print(f"✅ Таблица commission_deadline_notifications существует: {exists}")
    
    if exists:
        # Проверяем структуру
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'commission_deadline_notifications'
            ORDER BY ordinal_position;
        """)
        
        print("\n📋 Колонки таблицы:")
        for col in columns:
            print(f"  - {col['column_name']}: {col['data_type']} " +
                  f"(nullable={col['is_nullable']}, default={col['column_default']})")
        
        # Проверяем индексы
        indexes = await conn.fetch("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'commission_deadline_notifications';
        """)
        
        print("\n🔍 Индексы:")
        for idx in indexes:
            print(f"  - {idx['indexname']}")
            print(f"    {idx['indexdef']}")
        
        # Проверяем constraint'ы
        constraints = await conn.fetch("""
            SELECT con.conname, pg_get_constraintdef(con.oid) as definition
            FROM pg_constraint con
            INNER JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = 'commission_deadline_notifications';
        """)
        
        print("\n🔒 Constraints:")
        for cons in constraints:
            print(f"  - {cons['conname']}")
            print(f"    {cons['definition']}")
    
    await conn.close()


if __name__ == "__main__":
    asyncio.run(check_table())
