-- ============================================================
-- СКРИПТ 1: Назначение пользователя regizdrou глобальным админом
-- ============================================================
-- Дата: 2025-10-09
-- Назначение: Подготовка к тестированию жизненного цикла заказов

-- Обновление роли тестового пользователя
UPDATE staff_users 
SET role = 'GLOBAL_ADMIN',
    is_active = true,
    updated_at = NOW()
WHERE tg_user_id = '6022057382';

-- Проверка результата
SELECT id, tg_user_id, username, full_name, role, is_active 
FROM staff_users 
WHERE tg_user_id = '6022057382';

-- Вывод всех админов для проверки
SELECT id, tg_user_id, username, full_name, role, is_active 
FROM staff_users 
WHERE role IN ('GLOBAL_ADMIN', 'ADMIN')
ORDER BY id;
