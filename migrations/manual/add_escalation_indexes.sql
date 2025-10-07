-- P2.6: Индексы для эффективного поиска заказов, требующих уведомления об эскалации
-- Применяется вручную через: docker exec -it field-service-db psql -U field_user -d field_db -f /path/to/this/file.sql

-- 1. Частичный индекс для неотправленных уведомлений логисту
-- Используется в: distribution_scheduler.py:900, 944, 1045
CREATE INDEX IF NOT EXISTS ix_orders__escalation_logist_pending 
ON orders(id, dist_escalated_logist_at) 
WHERE escalation_logist_notified_at IS NULL AND dist_escalated_logist_at IS NOT NULL;

-- 2. Частичный индекс для неотправленных уведомлений админу
-- Используется аналогично логисту для эскалаций админу
CREATE INDEX IF NOT EXISTS ix_orders__escalation_admin_pending 
ON orders(id, dist_escalated_admin_at) 
WHERE escalation_admin_notified_at IS NULL AND dist_escalated_admin_at IS NOT NULL;

-- Проверка созданных индексов
SELECT 
    indexname,
    indexdef
FROM pg_indexes 
WHERE tablename = 'orders'
  AND indexname LIKE '%escalation%'
ORDER BY indexname;
