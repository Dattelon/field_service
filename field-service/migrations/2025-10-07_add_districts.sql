-- Добавление районов для основных городов
-- Используйте: docker exec -i field-service-db psql -U field_service -d field_service < migrations/2025-10-07_add_districts.sql

BEGIN;

-- Москва (id=203)
INSERT INTO districts (city_id, name) 
SELECT 203, district_name FROM (VALUES
    ('ЦАО'),
    ('САО'),
    ('СВАО'),
    ('ВАО'),
    ('ЮВАО'),
    ('ЮАО'),
    ('ЮЗАО'),
    ('ЗАО'),
    ('СЗАО'),
    ('ЗелАО'),
    ('НАО'),
    ('ТАО')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 203 AND name = district_name
);

-- Санкт-Петербург (id=204)
INSERT INTO districts (city_id, name) 
SELECT 204, district_name FROM (VALUES
    ('Адмиралтейский'),
    ('Василеостровский'),
    ('Выборгский'),
    ('Калининский'),
    ('Кировский'),
    ('Колпинский'),
    ('Красногвардейский'),
    ('Красносельский'),
    ('Кронштадтский'),
    ('Курортный'),
    ('Московский'),
    ('Невский'),
    ('Петроградский'),
    ('Петродворцовый'),
    ('Приморский'),
    ('Пушкинский'),
    ('Фрунзенский'),
    ('Центральный')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 204 AND name = district_name
);

-- Новосибирск (id=205)
INSERT INTO districts (city_id, name) 
SELECT 205, district_name FROM (VALUES
    ('Центральный'),
    ('Железнодорожный'),
    ('Заельцовский'),
    ('Дзержинский'),
    ('Калининский'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Первомайский'),
    ('Советский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 205 AND name = district_name
);

-- Екатеринбург (id=206)
INSERT INTO districts (city_id, name) 
SELECT 206, district_name FROM (VALUES
    ('Верх-Исетский'),
    ('Железнодорожный'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Орджоникидзевский'),
    ('Чкаловский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 206 AND name = district_name
);

-- Казань (id=207)
INSERT INTO districts (city_id, name) 
SELECT 207, district_name FROM (VALUES
    ('Авиастроительный'),
    ('Вахитовский'),
    ('Кировский'),
    ('Московский'),
    ('Ново-Савиновский'),
    ('Приволжский'),
    ('Советский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 207 AND name = district_name
);

-- Нижний Новгород (id=208)
INSERT INTO districts (city_id, name) 
SELECT 208, district_name FROM (VALUES
    ('Автозаводский'),
    ('Канавинский'),
    ('Ленинский'),
    ('Московский'),
    ('Нижегородский'),
    ('Приокский'),
    ('Советский'),
    ('Сормовский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 208 AND name = district_name
);

-- Челябинск (id=209)
INSERT INTO districts (city_id, name) 
SELECT 209, district_name FROM (VALUES
    ('Калининский'),
    ('Курчатовский'),
    ('Ленинский'),
    ('Металлургический'),
    ('Советский'),
    ('Тракторозаводский'),
    ('Центральный')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 209 AND name = district_name
);

-- Красноярск (id=210)
INSERT INTO districts (city_id, name) 
SELECT 210, district_name FROM (VALUES
    ('Железнодорожный'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Свердловский'),
    ('Советский'),
    ('Центральный')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 210 AND name = district_name
);

-- Самара (id=211)
INSERT INTO districts (city_id, name) 
SELECT 211, district_name FROM (VALUES
    ('Железнодорожный'),
    ('Кировский'),
    ('Красноглинский'),
    ('Куйбышевский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Промышленный'),
    ('Самарский'),
    ('Советский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 211 AND name = district_name
);

-- Уфа (id=212)
INSERT INTO districts (city_id, name) 
SELECT 212, district_name FROM (VALUES
    ('Демский'),
    ('Калининский'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Орджоникидзевский'),
    ('Советский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 212 AND name = district_name
);

-- Ростов-на-Дону (id=213)
INSERT INTO districts (city_id, name) 
SELECT 213, district_name FROM (VALUES
    ('Ворошиловский'),
    ('Железнодорожный'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Первомайский'),
    ('Пролетарский'),
    ('Советский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 213 AND name = district_name
);

-- Краснодар (id=214)
INSERT INTO districts (city_id, name) 
SELECT 214, district_name FROM (VALUES
    ('Западный'),
    ('Карасунский'),
    ('Прикубанский'),
    ('Центральный')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 214 AND name = district_name
);

-- Омск (id=215)
INSERT INTO districts (city_id, name) 
SELECT 215, district_name FROM (VALUES
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Советский'),
    ('Центральный')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 215 AND name = district_name
);

-- Воронеж (id=216)
INSERT INTO districts (city_id, name) 
SELECT 216, district_name FROM (VALUES
    ('Железнодорожный'),
    ('Коминтерновский'),
    ('Ленинский'),
    ('Левобережный'),
    ('Советский'),
    ('Центральный')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 216 AND name = district_name
);

-- Пермь (id=217)
INSERT INTO districts (city_id, name) 
SELECT 217, district_name FROM (VALUES
    ('Дзержинский'),
    ('Индустриальный'),
    ('Кировский'),
    ('Ленинский'),
    ('Мотовилихинский'),
    ('Орджоникидзевский'),
    ('Свердловский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 217 AND name = district_name
);

-- Волгоград (id=218)
INSERT INTO districts (city_id, name) 
SELECT 218, district_name FROM (VALUES
    ('Ворошиловский'),
    ('Дзержинский'),
    ('Кировский'),
    ('Красноармейский'),
    ('Краснооктябрьский'),
    ('Центральный'),
    ('Советский'),
    ('Тракторозаводский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 218 AND name = district_name
);

-- Саратов (id=219)
INSERT INTO districts (city_id, name) 
SELECT 219, district_name FROM (VALUES
    ('Волжский'),
    ('Заводской'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Фрунзенский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 219 AND name = district_name
);

-- Тюмень (id=220)
INSERT INTO districts (city_id, name) 
SELECT 220, district_name FROM (VALUES
    ('Калининский'),
    ('Ленинский'),
    ('Центральный'),
    ('Восточный')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 220 AND name = district_name
);

-- Тольятти (id=221)
INSERT INTO districts (city_id, name) 
SELECT 221, district_name FROM (VALUES
    ('Автозаводский'),
    ('Центральный'),
    ('Комсомольский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 221 AND name = district_name
);

-- Ижевск (id=222)
INSERT INTO districts (city_id, name) 
SELECT 222, district_name FROM (VALUES
    ('Индустриальный'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Первомайский'),
    ('Устиновский')
) AS t(district_name)
WHERE NOT EXISTS (
    SELECT 1 FROM districts WHERE city_id = 222 AND name = district_name
);

-- Проверка результатов
SELECT c.name as city, COUNT(d.id) as districts_count 
FROM cities c 
LEFT JOIN districts d ON d.city_id = c.id 
WHERE c.id IN (203, 204, 205, 206, 207, 208, 209, 210, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 221, 222)
GROUP BY c.id, c.name 
ORDER BY c.name;

COMMIT;
