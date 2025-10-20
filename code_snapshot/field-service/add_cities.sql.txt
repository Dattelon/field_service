-- Добавление основных городов в БД
-- Используйте: docker exec -it field-service-db psql -U field_service -d field_service -f /path/to/add_cities.sql

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) VALUES
('Москва', true, 'Europe/Moscow', NOW(), NOW()),
('Санкт-Петербург', true, 'Europe/Moscow', NOW(), NOW()),
('Новосибирск', true, 'Asia/Novosibirsk', NOW(), NOW()),
('Екатеринбург', true, 'Asia/Yekaterinburg', NOW(), NOW()),
('Казань', true, 'Europe/Moscow', NOW(), NOW()),
('Нижний Новгород', true, 'Europe/Moscow', NOW(), NOW()),
('Челябинск', true, 'Asia/Yekaterinburg', NOW(), NOW()),
('Красноярск', true, 'Asia/Krasnoyarsk', NOW(), NOW()),
('Самара', true, 'Europe/Samara', NOW(), NOW()),
('Уфа', true, 'Asia/Yekaterinburg', NOW(), NOW()),
('Ростов на Дону', true, 'Europe/Moscow', NOW(), NOW()),
('Краснодар', true, 'Europe/Moscow', NOW(), NOW()),
('Омск', true, 'Asia/Omsk', NOW(), NOW()),
('Воронеж', true, 'Europe/Moscow', NOW(), NOW()),
('Пермь', true, 'Asia/Yekaterinburg', NOW(), NOW()),
('Волгоград', true, 'Europe/Volgograd', NOW(), NOW()),
('Саратов', true, 'Europe/Saratov', NOW(), NOW()),
('Тюмень', true, 'Asia/Yekaterinburg', NOW(), NOW()),
('Тольятти', true, 'Europe/Samara', NOW(), NOW()),
('Ижевск', true, 'Europe/Samara', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET
    is_active = EXCLUDED.is_active,
    timezone = EXCLUDED.timezone,
    updated_at = NOW();

-- Проверка
SELECT COUNT(*) as cities_count FROM cities WHERE is_active = true;
