-- ====================================================================
-- Скрипт для очистки тестовых данных из БД Field Service
-- Использование: docker exec -i field-service-postgres-1 psql -U fs_user -d field_service < clear_test_data.sql
-- ====================================================================

-- Начинаем транзакцию для безопасности
BEGIN;

-- 1. Очистка уведомлений и метрик
DELETE FROM commission_deadline_notifications;
DELETE FROM notifications_outbox;
DELETE FROM distribution_metrics;
DELETE FROM admin_audit_log;

-- 2. Очистка заказов и связанных данных
DELETE FROM attachments;
DELETE FROM order_autoclose_queue;
DELETE FROM order_status_history;
DELETE FROM offers;
DELETE FROM commissions;
DELETE FROM orders;

-- 3. Очистка мастеров и связанных данных
DELETE FROM master_skills;
DELETE FROM master_districts;
DELETE FROM referral_rewards;
DELETE FROM referrals;
DELETE FROM master_invite_codes;
DELETE FROM masters;

-- 4. Очистка географии (города, районы, улицы)
DELETE FROM staff_cities;
DELETE FROM streets;
DELETE FROM districts;
DELETE FROM cities;

-- 5. Очистка навыков (если есть тестовые)
DELETE FROM skills;

-- 6. Очистка кодов доступа персонала
DELETE FROM staff_access_code_cities;
DELETE FROM staff_access_codes;

-- 7. Очистка геокэша
DELETE FROM geocache;

-- Фиксируем изменения
COMMIT;

-- Показываем итоговую статистику
SELECT 
    'orders' as table_name, COUNT(*) as remaining_count FROM orders 
UNION ALL SELECT 'masters', COUNT(*) FROM masters 
UNION ALL SELECT 'offers', COUNT(*) FROM offers 
UNION ALL SELECT 'commissions', COUNT(*) FROM commissions 
UNION ALL SELECT 'cities', COUNT(*) FROM cities 
UNION ALL SELECT 'districts', COUNT(*) FROM districts 
UNION ALL SELECT 'streets', COUNT(*) FROM streets 
UNION ALL SELECT 'skills', COUNT(*) FROM skills 
UNION ALL SELECT 'staff_users', COUNT(*) FROM staff_users
ORDER BY remaining_count DESC;

-- Сообщение об успехе
\echo '✅ База данных очищена от тестовых данных'
