-- P1: Добавление индексов для оптимизации commissions
-- Дата: 2025-10-07
-- Автор: AI Assistant

-- 1. Составной индекс для запросов по мастеру и статусу
-- Покрывает: получение комиссий мастера, фильтрация в админке
CREATE INDEX IF NOT EXISTS ix_commissions__master_status 
ON commissions(master_id, status);

-- 2. Составной индекс для watchdog запросов (apply_overdue_commissions)
-- Покрывает: поиск просроченных комиссий
CREATE INDEX IF NOT EXISTS ix_commissions__overdue_lookup
ON commissions(status, deadline_at, blocked_applied)
WHERE status = 'WAIT_PAY' AND blocked_applied = FALSE;

-- 3. Индекс для сортировки по дате создания (используется в export)
CREATE INDEX IF NOT EXISTS ix_commissions__created_at
ON commissions(created_at DESC);

-- Проверка созданных индексов
SELECT 
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename = 'commissions'
ORDER BY indexname;
