-- ============================================================
-- MIGRATION: Create distribution_metrics table
-- Date: 2025-10-07
-- Priority: P0 - CRITICAL
-- Description: Создание таблицы метрик распределения заказов
-- ============================================================

-- Проверяем что таблицы ещё нет
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'distribution_metrics'
    ) THEN
        RAISE NOTICE 'Table distribution_metrics already exists, skipping...';
    ELSE
        RAISE NOTICE 'Creating table distribution_metrics...';
        
        -- Создаём таблицу
        CREATE TABLE distribution_metrics (
            id SERIAL PRIMARY KEY,
            
            -- Связи с другими таблицами
            order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            master_id INTEGER REFERENCES masters(id) ON DELETE SET NULL,
            
            -- Метрики назначения
            assigned_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            round_number SMALLINT NOT NULL,
            candidates_count SMALLINT NOT NULL,
            time_to_assign_seconds INTEGER,
            
            -- Флаги процесса распределения
            preferred_master_used BOOLEAN NOT NULL DEFAULT FALSE,
            was_escalated_to_logist BOOLEAN NOT NULL DEFAULT FALSE,
            was_escalated_to_admin BOOLEAN NOT NULL DEFAULT FALSE,
            
            -- География и категория заказа
            city_id INTEGER NOT NULL REFERENCES cities(id) ON DELETE CASCADE,
            district_id INTEGER REFERENCES districts(id) ON DELETE SET NULL,
            category VARCHAR(50),
            order_type VARCHAR(32),
            
            -- Дополнительные метаданные в JSON
            metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            
            -- Временные метки
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        
        RAISE NOTICE 'Table distribution_metrics created successfully';
        
        -- Создаём индексы для производительности
        RAISE NOTICE 'Creating indexes...';
        
        -- Основные индексы по связям
        CREATE INDEX idx_distribution_metrics_order_id 
            ON distribution_metrics(order_id);
            
        CREATE INDEX idx_distribution_metrics_master_id 
            ON distribution_metrics(master_id);
            
        CREATE INDEX idx_distribution_metrics_city_id 
            ON distribution_metrics(city_id);
            
        CREATE INDEX idx_distribution_metrics_district_id 
            ON distribution_metrics(district_id);
        
        -- Индексы для аналитики и отчётности
        -- Сортировка по времени назначения (DESC для последних записей)
        CREATE INDEX ix_distribution_metrics__assigned_at_desc 
            ON distribution_metrics(assigned_at DESC);
        
        -- Аналитика по городам и времени
        CREATE INDEX ix_distribution_metrics__city_assigned 
            ON distribution_metrics(city_id, assigned_at);
        
        -- Анализ производительности (какие раунды, сколько времени)
        CREATE INDEX ix_distribution_metrics__performance 
            ON distribution_metrics(round_number, time_to_assign_seconds);
        
        RAISE NOTICE 'All indexes created successfully';
        RAISE NOTICE '✅ Migration completed: distribution_metrics table created';
    END IF;
END $$;

-- Проверка что таблица создана и имеет правильную структуру
DO $$
DECLARE
    column_count INTEGER;
    index_count INTEGER;
BEGIN
    -- Считаем количество колонок
    SELECT COUNT(*) INTO column_count
    FROM information_schema.columns
    WHERE table_schema = 'public' 
    AND table_name = 'distribution_metrics';
    
    -- Считаем количество индексов
    SELECT COUNT(*) INTO index_count
    FROM pg_indexes
    WHERE schemaname = 'public' 
    AND tablename = 'distribution_metrics';
    
    IF column_count = 0 THEN
        RAISE EXCEPTION '❌ Table distribution_metrics was not created!';
    ELSE
        RAISE NOTICE '✅ Table distribution_metrics has % columns', column_count;
    END IF;
    
    IF index_count < 7 THEN
        RAISE WARNING '⚠️  Expected at least 7 indexes, found %', index_count;
    ELSE
        RAISE NOTICE '✅ All % indexes created successfully', index_count;
    END IF;
    
    RAISE NOTICE '================================================';
    RAISE NOTICE 'MIGRATION STATUS: SUCCESS';
    RAISE NOTICE 'Table: distribution_metrics';
    RAISE NOTICE 'Columns: %', column_count;
    RAISE NOTICE 'Indexes: %', index_count;
    RAISE NOTICE '================================================';
END $$;

-- Показываем структуру созданной таблицы
SELECT 
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public' 
AND table_name = 'distribution_metrics'
ORDER BY ordinal_position;

-- Показываем созданные индексы
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public' 
AND tablename = 'distribution_metrics'
ORDER BY indexname;
