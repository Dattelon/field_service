-- CR-2025-10-03-FIX: Обновление существующей записи GLOBAL_ADMIN

-- Обновить роль с 'ADMIN' на 'GLOBAL_ADMIN' и имя
UPDATE staff_users 
SET 
    role = 'GLOBAL_ADMIN'::staff_role,
    full_name = 'Superuser',
    updated_at = NOW()
WHERE tg_user_id = 332786197;

-- Проверить результат
SELECT 
    id as staff_id,
    tg_user_id,
    full_name,
    role,
    is_active,
    created_at
FROM staff_users 
WHERE tg_user_id = 332786197;
