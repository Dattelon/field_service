-- ============================================================
-- СКРИПТ 2: Полная очистка тестовых данных
-- ============================================================
-- Дата: 2025-10-09
-- Назначение: Подготовка чистой БД для E2E тестирования
-- ВНИМАНИЕ: Сохраняет города, районы, навыки, настройки и админов

BEGIN;

-- 1. Очистка данных связанных с заказами (в правильном порядке из-за FK)
DELETE FROM attachments;
DELETE FROM order_status_history;
DELETE FROM commission_deadline_notifications;
DELETE FROM commissions;
DELETE FROM offers;
DELETE FROM order_autoclose_queue;
DELETE FROM orders;

-- 2. Очистка данных мастеров
DELETE FROM master_skills;
DELETE FROM master_districts;
DELETE FROM master_invite_codes;
DELETE FROM referral_rewards;
DELETE FROM referrals;
DELETE FROM masters;

-- 3. Очистка служебных таблиц
DELETE FROM notifications_outbox;
DELETE FROM distribution_metrics;
DELETE FROM admin_audit_log;

-- 4. Сброс последовательностей (автоинкременты)
ALTER SEQUENCE orders_id_seq RESTART WITH 1;
ALTER SEQUENCE masters_id_seq RESTART WITH 1;
ALTER SEQUENCE offers_id_seq RESTART WITH 1;
ALTER SEQUENCE commissions_id_seq RESTART WITH 1;
ALTER SEQUENCE attachments_id_seq RESTART WITH 1;
ALTER SEQUENCE referrals_id_seq RESTART WITH 1;
ALTER SEQUENCE master_invite_codes_id_seq RESTART WITH 1;

-- 5. Вывод статистики после очистки
SELECT 
    'orders' as table_name, COUNT(*) as count FROM orders
UNION ALL
SELECT 'masters', COUNT(*) FROM masters
UNION ALL
SELECT 'offers', COUNT(*) FROM offers
UNION ALL
SELECT 'commissions', COUNT(*) FROM commissions
UNION ALL
SELECT 'master_districts', COUNT(*) FROM master_districts
UNION ALL
SELECT 'order_status_history', COUNT(*) FROM order_status_history
UNION ALL
SELECT 'cities', COUNT(*) FROM cities
UNION ALL
SELECT 'districts', COUNT(*) FROM districts
UNION ALL
SELECT 'staff_users', COUNT(*) FROM staff_users
ORDER BY table_name;

COMMIT;

-- Финальное подтверждение
SELECT 'CLEANUP COMPLETE' as status, NOW() as timestamp;
