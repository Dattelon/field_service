-- P1.1: Создание недостающих индексов на таблице commissions
-- Дата: 2025-10-07
-- Описание: Индексы определены в models.py, но отсутствуют в БД

-- Проверка текущего состояния
-- SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'commissions' ORDER BY indexname;

-- 1. Индекс для фильтрации по статусу и дедлайну
--    Используется в: apply_overdue_commissions, watchdog_commissions_overdue
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_commissions__status_deadline 
ON commissions (status, deadline_at);

-- 2. Индекс для получения комиссий конкретного мастера по статусу
--    Используется в: админ-панель (финансы мастера), отчёты
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_commissions__master_status 
ON commissions (master_id, status);

-- Проверка результата
SELECT 
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'commissions'
ORDER BY indexname;

-- EXPLAIN: Проверка использования новых индексов
-- EXPLAIN ANALYZE 
-- SELECT * FROM commissions 
-- WHERE status = 'WAIT_PAY' AND deadline_at < NOW();
