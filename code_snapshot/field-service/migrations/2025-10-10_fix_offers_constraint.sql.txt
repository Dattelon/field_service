-- Migration: Fix offers constraint to allow repeat offers after EXPIRED/DECLINED
-- Date: 2025-10-10
-- Issue: uq_offers__order_master blocked creating new offers for same (order_id, master_id)
--        even after previous offer was EXPIRED or DECLINED
-- Solution: Replace with partial unique index that only applies to active states

-- Удаляем старый constraint
ALTER TABLE offers DROP CONSTRAINT IF EXISTS uq_offers__order_master;

-- Создаём новый partial unique index (только для активных офферов)
CREATE UNIQUE INDEX IF NOT EXISTS uq_offers__order_master_active 
ON offers (order_id, master_id) 
WHERE state IN ('SENT', 'VIEWED', 'ACCEPTED');

-- Результат:
-- 1. Теперь можно создавать новые офферы после EXPIRED/DECLINED
-- 2. Защита от дублирования сохраняется для активных офферов
-- 3. Мастер может получить повторный оффер на тот же заказ
