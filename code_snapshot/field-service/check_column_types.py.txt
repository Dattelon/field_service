import asyncio
import asyncpg

async def check():
    conn = await asyncpg.connect(
        host='localhost',
        port=5439,
        user='fs_user',
        password='fs_password',
        database='field_service_test'
    )
    
    # Проверка через information_schema
    rows = await conn.fetch("""
        SELECT column_name, data_type, udt_name 
        FROM information_schema.columns 
        WHERE table_name = 'distribution_metrics' 
        AND column_name IN ('category', 'order_type')
    """)
    print("information_schema:")
    for row in rows:
        print(f"  {row['column_name']}: {row['data_type']} (udt: {row['udt_name']})")
    
    # Проверка через pg_attribute
    rows = await conn.fetch("""
        SELECT 
          a.attname AS column_name,
          pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
          t.typname AS base_type
        FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_type t ON a.atttypid = t.oid
        WHERE a.attrelid = 'distribution_metrics'::regclass
          AND a.attnum > 0 
          AND NOT a.attisdropped
          AND a.attname IN ('category', 'order_type')
    """)
    print("\npg_catalog:")
    for row in rows:
        print(f"  {row['column_name']}: {row['data_type']} (base: {row['base_type']})")
    
    await conn.close()

asyncio.run(check())
