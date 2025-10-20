-- Migration: Register Superusers in staff_users
-- Date: 2025-10-03
-- Purpose: Fix FK violation by ensuring all superusers have valid staff_users records

-- IMPORTANT: Replace placeholder Telegram IDs with real ones from your .env ADMIN_TG_IDS

BEGIN;

-- Check if superusers already exist
DO $$
DECLARE
    admin_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO admin_count 
    FROM staff_users 
    WHERE role = 'ADMIN' AND is_active = true;
    
    IF admin_count = 0 THEN
        RAISE NOTICE 'No active admin users found. Creating initial superusers...';
    ELSE
        RAISE NOTICE 'Found % active admin user(s)', admin_count;
    END IF;
END $$;

-- Insert superusers (ON CONFLICT DO NOTHING to avoid duplicates)
-- REPLACE THE TG_USER_IDs BELOW WITH YOUR REAL VALUES

INSERT INTO staff_users (tg_user_id, role, is_active, full_name, phone, username)
VALUES 
    -- Superuser 1 (REPLACE 123456789 with real Telegram ID)
    (123456789, 'ADMIN', true, 'Main Admin', '+71234567890', 'admin1'),
    
    -- Superuser 2 (REPLACE 987654321 with real Telegram ID)
    (987654321, 'ADMIN', true, 'Secondary Admin', '+79876543210', 'admin2')

ON CONFLICT (tg_user_id) DO UPDATE 
SET 
    role = EXCLUDED.role,
    is_active = EXCLUDED.is_active,
    updated_at = CURRENT_TIMESTAMP;

-- Verify insertion
SELECT 
    id,
    tg_user_id,
    full_name,
    role,
    is_active,
    created_at
FROM staff_users
WHERE role = 'ADMIN'
ORDER BY created_at;

COMMIT;

-- Post-migration check
DO $$
DECLARE
    admin_count INTEGER;
    admin_list TEXT;
BEGIN
    SELECT COUNT(*) INTO admin_count 
    FROM staff_users 
    WHERE role = 'ADMIN' AND is_active = true;
    
    SELECT string_agg(tg_user_id::TEXT || ' (' || full_name || ')', ', ')
    INTO admin_list
    FROM staff_users
    WHERE role = 'ADMIN' AND is_active = true;
    
    RAISE NOTICE '✅ Migration complete. Active admins: %', admin_count;
    RAISE NOTICE 'Admin list: %', admin_list;
END $$;
