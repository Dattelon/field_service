-- Добавление всех 78 городов из каталога cities.py (версия 2 - без дубликатов)
-- Используйте: Get-Content migrations/2025-10-07_add_all_cities_v2.sql | docker exec -i field-service-postgres-1 psql -U fs_user -d field_service

BEGIN;

-- Создаём временную таблицу с городами
CREATE TEMP TABLE cities_to_add (
    name VARCHAR(100),
    timezone VARCHAR(50)
);

-- Вставляем все города
INSERT INTO cities_to_add (name, timezone) VALUES
('Москва', 'Europe/Moscow'),
('Санкт-Петербург', 'Europe/Moscow'),
('Новосибирск', 'Asia/Novosibirsk'),
('Екатеринбург', 'Asia/Yekaterinburg'),
('Казань', 'Europe/Moscow'),
('Нижний Новгород', 'Europe/Moscow'),
('Челябинск', 'Asia/Yekaterinburg'),
('Красноярск', 'Asia/Krasnoyarsk'),
('Самара', 'Europe/Samara'),
('Уфа', 'Asia/Yekaterinburg'),
('Ростов на Дону', 'Europe/Moscow'),
('Краснодар', 'Europe/Moscow'),
('Омск', 'Asia/Omsk'),
('Воронеж', 'Europe/Moscow'),
('Пермь', 'Asia/Yekaterinburg'),
('Волгоград', 'Europe/Volgograd'),
('Саратов', 'Europe/Saratov'),
('Тюмень', 'Asia/Yekaterinburg'),
('Тольятти', 'Europe/Samara'),
('Ижевск', 'Europe/Samara'),
('Барнаул', 'Asia/Barnaul'),
('Ульяновск', 'Europe/Ulyanovsk'),
('Иркутск', 'Asia/Irkutsk'),
('Хабаровск', 'Asia/Vladivostok'),
('Владивосток', 'Asia/Vladivostok'),
('Ярославль', 'Europe/Moscow'),
('Махачкала', 'Europe/Moscow'),
('Томск', 'Asia/Tomsk'),
('Оренбург', 'Asia/Yekaterinburg'),
('Кемерово', 'Asia/Novokuznetsk'),
('Новокузнецк', 'Asia/Novokuznetsk'),
('Рязань', 'Europe/Moscow'),
('Набережные Челны', 'Europe/Moscow'),
('Астрахань', 'Europe/Astrakhan'),
('Пенза', 'Europe/Moscow'),
('Киров', 'Europe/Kirov'),
('Липецк', 'Europe/Moscow'),
('Чебоксары', 'Europe/Moscow'),
('Калининград', 'Europe/Kaliningrad'),
('Тула', 'Europe/Moscow'),
('Курск', 'Europe/Moscow'),
('Сочи', 'Europe/Moscow'),
('Ставрополь', 'Europe/Moscow'),
('Балашиха (МО)', 'Europe/Moscow'),
('Севастополь', 'Europe/Simferopol'),
('Брянск', 'Europe/Moscow'),
('Белгород', 'Europe/Moscow'),
('Магнитогорск', 'Asia/Yekaterinburg'),
('Великий Новгород', 'Europe/Moscow'),
('Калуга', 'Europe/Moscow'),
('Сургут', 'Asia/Yekaterinburg'),
('Владикавказ', 'Europe/Moscow'),
('Чита', 'Asia/Chita'),
('Симферополь', 'Europe/Simferopol'),
('Волжский', 'Europe/Volgograd'),
('Смоленск', 'Europe/Moscow'),
('Саранск', 'Europe/Moscow'),
('Курган', 'Asia/Yekaterinburg'),
('Орёл', 'Europe/Moscow'),
('Подольск (МО)', 'Europe/Moscow'),
('Архангельск', 'Europe/Moscow'),
('Грозный', 'Europe/Moscow'),
('Якутск', 'Asia/Yakutsk'),
('Тверь', 'Europe/Moscow'),
('Старый Оскол', 'Europe/Moscow'),
('Улан Удэ', 'Asia/Irkutsk'),
('Нижний Тагил', 'Asia/Yekaterinburg'),
('Нижневартовск', 'Asia/Yekaterinburg'),
('Псков', 'Europe/Moscow'),
('Йошкар Ола', 'Europe/Moscow'),
('Кострома', 'Europe/Moscow'),
('Новороссийск', 'Europe/Moscow'),
('Дзержинск', 'Europe/Moscow'),
('Таганрог', 'Europe/Moscow'),
('Химки (МО)', 'Europe/Moscow'),
('Березники', 'Asia/Yekaterinburg'),
('Энгельс', 'Europe/Saratov'),
('Шахты', 'Europe/Moscow');

-- Вставляем только новые города
INSERT INTO cities (name, is_active, timezone, created_at, updated_at)
SELECT t.name, true, t.timezone, NOW(), NOW()
FROM cities_to_add t
WHERE NOT EXISTS (
    SELECT 1 FROM cities c WHERE c.name = t.name
);

-- Обновляем существующие города
UPDATE cities c
SET 
    is_active = true,
    timezone = t.timezone,
    updated_at = NOW()
FROM cities_to_add t
WHERE c.name = t.name;

-- Проверка
SELECT COUNT(*) as total_cities, 
       COUNT(*) FILTER (WHERE is_active = true) as active_cities 
FROM cities;

COMMIT;
