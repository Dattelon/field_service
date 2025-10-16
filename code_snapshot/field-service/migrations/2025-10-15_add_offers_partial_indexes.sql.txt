-- Миграция: Добавление частичных индексов для таблицы offers
-- Дата: 2025-10-15
-- Цель: Оптимизация SELECT ... FOR UPDATE SKIP LOCKED в accept_offer

-- Шаг 1: Добавляем частичный индекс для активных офферов (SENT, VIEWED)
-- Используется в WHERE условиях для быстрого поиска активных офферов
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_offers_active_state
ON offers (order_id, master_id, state)
WHERE state IN ('SENT', 'VIEWED');

-- Шаг 2: Добавляем частичный индекс для неистекших офферов
-- Используется для фильтрации офферов по expires_at
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_offers_not_expired
ON offers (order_id, master_id)
WHERE expires_at > NOW();

-- Шаг 3: Добавляем составной индекс для проверки уникальности активных офферов
-- Предотвращает создание дублирующихся офферов для одной пары order_id + master_id
CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_offers_order_master_active
ON offers (order_id, master_id)
WHERE state IN ('SENT', 'VIEWED', 'ACCEPTED');

-- Шаг 4: Добавляем индекс для быстрого поиска офферов по мастеру
-- Используется при загрузке списка офферов мастера
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_offers_master_active
ON offers (master_id, state, sent_at DESC)
WHERE state IN ('SENT', 'VIEWED');

-- Проверка созданных индексов
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'offers'
AND indexname LIKE 'idx_offers_%'
ORDER BY indexname;
