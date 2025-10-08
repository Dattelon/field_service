-- Добавление всех 78 городов построчно (версия 3 - безопасная)
-- Используйте: Get-Content migrations/2025-10-07_add_all_cities_v3.sql | docker exec -i field-service-postgres-1 psql -U fs_user -d field_service

BEGIN;

-- Вставляем/обновляем каждый город отдельно
INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Москва', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Санкт-Петербург', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Новосибирск', true, 'Asia/Novosibirsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Екатеринбург', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Казань', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Нижний Новгород', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Челябинск', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Красноярск', true, 'Asia/Krasnoyarsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Самара', true, 'Europe/Samara', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Уфа', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Ростов на Дону', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Краснодар', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Омск', true, 'Asia/Omsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Воронеж', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Пермь', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Волгоград', true, 'Europe/Volgograd', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Саратов', true, 'Europe/Saratov', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Тюмень', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Тольятти', true, 'Europe/Samara', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Ижевск', true, 'Europe/Samara', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Барнаул', true, 'Asia/Barnaul', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Ульяновск', true, 'Europe/Ulyanovsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Иркутск', true, 'Asia/Irkutsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Хабаровск', true, 'Asia/Vladivostok', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Владивосток', true, 'Asia/Vladivostok', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Ярославль', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Махачкала', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Томск', true, 'Asia/Tomsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Оренбург', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Кемерово', true, 'Asia/Novokuznetsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();
INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Новокузнецк', true, 'Asia/Novokuznetsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Рязань', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Набережные Челны', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Астрахань', true, 'Europe/Astrakhan', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Пенза', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Киров', true, 'Europe/Kirov', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Липецк', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Чебоксары', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Калининград', true, 'Europe/Kaliningrad', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Тула', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Курск', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Сочи', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Ставрополь', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Балашиха (МО)', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Севастополь', true, 'Europe/Simferopol', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Брянск', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Белгород', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Магнитогорск', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Великий Новгород', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Калуга', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Сургут', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Владикавказ', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Чита', true, 'Asia/Chita', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Симферополь', true, 'Europe/Simferopol', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Волжский', true, 'Europe/Volgograd', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Смоленск', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Саранск', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Курган', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Орёл', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Подольск (МО)', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();
INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Архангельск', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Грозный', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Якутск', true, 'Asia/Yakutsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Тверь', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Старый Оскол', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Улан Удэ', true, 'Asia/Irkutsk', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Нижний Тагил', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Нижневартовск', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Псков', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Йошкар Ола', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Кострома', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Новороссийск', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Дзержинск', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Таганрог', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Химки (МО)', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Березники', true, 'Asia/Yekaterinburg', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Энгельс', true, 'Europe/Saratov', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

INSERT INTO cities (name, is_active, timezone, created_at, updated_at) 
VALUES ('Шахты', true, 'Europe/Moscow', NOW(), NOW())
ON CONFLICT (name) DO UPDATE SET is_active = true, timezone = EXCLUDED.timezone, updated_at = NOW();

-- Проверка
SELECT COUNT(*) as total_cities, 
       COUNT(*) FILTER (WHERE is_active = true) as active_cities 
FROM cities;

SELECT 'Added/Updated ' || COUNT(*) || ' cities' as result FROM cities WHERE is_active = true;

COMMIT;
