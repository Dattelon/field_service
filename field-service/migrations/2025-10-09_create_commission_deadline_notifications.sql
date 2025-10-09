-- ============================================================
-- MIGRATION: Create commission_deadline_notifications table
-- Date: 2025-10-09
-- Priority: P1-21 - Commission deadline reminders
-- Description: Таблица для отслеживания отправленных уведомлений о дедлайне комиссии
-- ============================================================

-- Проверяем что таблицы ещё нет
DO $$
BEGIN
    IF EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_schema = 'public' 
        AND table_name = 'commission_deadline_notifications'
    ) THEN
        RAISE NOTICE 'Table commission_deadline_notifications already exists, skipping...';
    ELSE
        RAISE NOTICE 'Creating table commission_deadline_notifications...';
        
        -- Создаём таблицу
        CREATE TABLE commission_deadline_notifications (
            id SERIAL PRIMARY KEY,
            
            -- Связь с комиссией
            commission_id INTEGER NOT NULL REFERENCES commissions(id) ON DELETE CASCADE,
            
            -- За сколько часов до дедлайна было отправлено уведомление (24, 6, или 1)
            hours_before SMALLINT NOT NULL CHECK (hours_before IN (1, 6, 24)),
            
            -- Когда отправлено
            sent_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            
            -- Уникальность: одна комиссия + один тип уведомления = одна запись
            CONSTRAINT uq_commission_deadline_notifications__commission_hours 
                UNIQUE (commission_id, hours_before)
        );
        
        -- Индексы для быстрого поиска
        CREATE INDEX ix_commission_deadline_notifications__commission 
            ON commission_deadline_notifications(commission_id);
        
        RAISE NOTICE 'Table commission_deadline_notifications created successfully!';
    END IF;
END $$;

-- Проверка создания
SELECT COUNT(*) as total_notifications 
FROM commission_deadline_notifications;
