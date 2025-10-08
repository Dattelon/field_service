-- CR-2025-10-03-FIX: Создание GLOBAL_ADMIN в базе данных
-- Этот скрипт создает запись суперпользователя с реальным staff_users.id для корректной работы FK

-- 1. Проверка, есть ли уже запись для tg_id=332786197
DO $$
BEGIN
    -- Если записи нет - создаем
    IF NOT EXISTS (SELECT 1 FROM staff_users WHERE tg_user_id = 332786197) THEN
        INSERT INTO staff_users (
            tg_user_id,
            username,
            full_name,
            phone,
            role,
            is_active,
            commission_requisites,
            created_at,
            updated_at
        ) VALUES (
            332786197,
            'Superuser',
            'Superuser',
            '',
            'GLOBAL_ADMIN'::staff_role,
            true,
            '{}'::jsonb,
            NOW(),
            NOW()
        );
        
        RAISE NOTICE 'GLOBAL_ADMIN created with tg_user_id=332786197';
    ELSE
        RAISE NOTICE 'GLOBAL_ADMIN already exists with tg_user_id=332786197';
    END IF;
END $$;

-- 2. Вывести информацию о созданном/существующем GLOBAL_ADMIN
SELECT 
    id as staff_id,
    tg_user_id,
    full_name,
    role,
    is_active,
    created_at
FROM staff_users 
WHERE tg_user_id = 332786197;

-- 3. Обновить все записи в order_status_history, где changed_by_staff_id=0 (если такие есть)
-- UPDATE order_status_history 
-- SET changed_by_staff_id = (SELECT id FROM staff_users WHERE tg_user_id = 332786197)
-- WHERE changed_by_staff_id = 0;
