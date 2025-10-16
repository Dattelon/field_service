import asyncio
import asyncpg

async def fix():
    conn = await asyncpg.connect(
        host='localhost',
        port=5439,
        user='fs_user',
        password='fs_password',
        database='field_service_test'
    )
    
    try:
        print("Пересоздание таблицы distribution_metrics с правильными типами...")
        
        # DROP + CREATE с явным указанием VARCHAR
        await conn.execute('''
            DROP TABLE IF EXISTS distribution_metrics CASCADE;
            
            CREATE TABLE distribution_metrics (
                id SERIAL PRIMARY KEY,
                order_id INTEGER NOT NULL,
                master_id INTEGER,
                assigned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
                round_number SMALLINT NOT NULL,
                candidates_count SMALLINT NOT NULL,
                time_to_assign_seconds INTEGER,
                preferred_master_used BOOLEAN DEFAULT FALSE NOT NULL,
                was_escalated_to_logist BOOLEAN DEFAULT FALSE NOT NULL,
                was_escalated_to_admin BOOLEAN DEFAULT FALSE NOT NULL,
                city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
                district_id INTEGER REFERENCES districts(id) ON DELETE SET NULL,
                category VARCHAR(32),
                order_type VARCHAR(32),
                metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
            );
            
            CREATE INDEX idx_distribution_metrics_order_id ON distribution_metrics(order_id);
            CREATE INDEX idx_distribution_metrics_master_id ON distribution_metrics(master_id);
            CREATE INDEX idx_distribution_metrics_city_id ON distribution_metrics(city_id);
            CREATE INDEX idx_distribution_metrics_district_id ON distribution_metrics(district_id);
            CREATE INDEX ix_distribution_metrics__assigned_at_desc ON distribution_metrics(assigned_at DESC);
            CREATE INDEX ix_distribution_metrics__city_assigned ON distribution_metrics(city_id, assigned_at);
            CREATE INDEX ix_distribution_metrics__performance ON distribution_metrics(round_number, time_to_assign_seconds);
        ''')
        
        print("OK: Таблица пересоздана успешно!")
        
        # Проверка
        rows = await conn.fetch("""
            SELECT column_name, data_type, udt_name 
            FROM information_schema.columns 
            WHERE table_name = 'distribution_metrics' 
            AND column_name IN ('category', 'order_type')
        """)
        print("\nПроверка типов:")
        for row in rows:
            print(f"  {row['column_name']}: {row['data_type']} (udt: {row['udt_name']})")
        
    finally:
        await conn.close()

asyncio.run(fix())
