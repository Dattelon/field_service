-- Добавление районов для основных городов России
-- Дата: 2025-10-07
-- Исправлено: убрана несуществующая колонка is_active

BEGIN;

-- Москва (12 округов)
INSERT INTO districts (city_id, name) 
SELECT c.id, d.name
FROM cities c, (VALUES 
    ('ЦАО (Центральный АО)'),
    ('САО (Северный АО)'),
    ('СВАО (Северо-Восточный АО)'),
    ('ВАО (Восточный АО)'),
    ('ЮВАО (Юго-Восточный АО)'),
    ('ЮАО (Южный АО)'),
    ('ЮЗАО (Юго-Западный АО)'),
    ('ЗАО (Западный АО)'),
    ('СЗАО (Северо-Западный АО)'),
    ('ЗелАО (Зеленоградский АО)'),
    ('НАО (Новомосковский АО)'),
    ('ТАО (Троицкий АО)')
) AS d(name)
WHERE c.name = 'Москва'
ON CONFLICT (city_id, name) DO NOTHING;

-- Санкт-Петербург (18 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
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
) AS d(name)
WHERE c.name = 'Санкт-Петербург'
ON CONFLICT (city_id, name) DO NOTHING;

-- Новосибирск (10 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Центральный'),
    ('Железнодорожный'),
    ('Заельцовский'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Первомайский'),
    ('Советский'),
    ('Дзержинский'),
    ('Калининский')
) AS d(name)
WHERE c.name = 'Новосибирск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Екатеринбург (7 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Верх-Исетский'),
    ('Железнодорожный'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Орджоникидзевский'),
    ('Чкаловский')
) AS d(name)
WHERE c.name = 'Екатеринбург'
ON CONFLICT (city_id, name) DO NOTHING;

-- Казань (7 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Авиастроительный'),
    ('Вахитовский'),
    ('Кировский'),
    ('Московский'),
    ('Ново-Савиновский'),
    ('Приволжский'),
    ('Советский')
) AS d(name)
WHERE c.name = 'Казань'
ON CONFLICT (city_id, name) DO NOTHING;

-- Нижний Новгород (8 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Автозаводский'),
    ('Канавинский'),
    ('Ленинский'),
    ('Московский'),
    ('Нижегородский'),
    ('Приокский'),
    ('Советский'),
    ('Сормовский')
) AS d(name)
WHERE c.name = 'Нижний Новгород'
ON CONFLICT (city_id, name) DO NOTHING;

-- Челябинск (7 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Калининский'),
    ('Курчатовский'),
    ('Ленинский'),
    ('Металлургический'),
    ('Советский'),
    ('Тракторозаводский'),
    ('Центральный')
) AS d(name)
WHERE c.name = 'Челябинск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Красноярск (7 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Свердловский'),
    ('Советский'),
    ('Центральный')
) AS d(name)
WHERE c.name = 'Красноярск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Самара (9 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Кировский'),
    ('Красноглинский'),
    ('Куйбышевский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Промышленный'),
    ('Самарский'),
    ('Советский')
) AS d(name)
WHERE c.name = 'Самара'
ON CONFLICT (city_id, name) DO NOTHING;

-- Уфа (7 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Демский'),
    ('Калининский'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Орджоникидзевский'),
    ('Советский')
) AS d(name)
WHERE c.name = 'Уфа'
ON CONFLICT (city_id, name) DO NOTHING;

-- Ростов-на-Дону (8 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Ворошиловский'),
    ('Железнодорожный'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Первомайский'),
    ('Пролетарский'),
    ('Советский')
) AS d(name)
WHERE c.name = 'Ростов-на-Дону'
ON CONFLICT (city_id, name) DO NOTHING;

-- Краснодар (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Карасунский'),
    ('Прикубанский'),
    ('Центральный'),
    ('Западный')
) AS d(name)
WHERE c.name = 'Краснодар'
ON CONFLICT (city_id, name) DO NOTHING;

-- Омск (5 округов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Кировский АО'),
    ('Ленинский АО'),
    ('Октябрьский АО'),
    ('Советский АО'),
    ('Центральный АО')
) AS d(name)
WHERE c.name = 'Омск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Воронеж (6 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Коминтерновский'),
    ('Ленинский'),
    ('Левобережный'),
    ('Советский'),
    ('Центральный')
) AS d(name)
WHERE c.name = 'Воронеж'
ON CONFLICT (city_id, name) DO NOTHING;

-- Пермь (7 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Дзержинский'),
    ('Индустриальный'),
    ('Кировский'),
    ('Ленинский'),
    ('Мотовилихинский'),
    ('Орджоникидзевский'),
    ('Свердловский')
) AS d(name)
WHERE c.name = 'Пермь'
ON CONFLICT (city_id, name) DO NOTHING;

-- Волгоград (8 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Дзержинский'),
    ('Кировский'),
    ('Краснооктябрьский'),
    ('Красноармейский'),
    ('Центральный'),
    ('Тракторозаводский'),
    ('Советский'),
    ('Ворошиловский')
) AS d(name)
WHERE c.name = 'Волгоград'
ON CONFLICT (city_id, name) DO NOTHING;

-- Саратов (6 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Волжский'),
    ('Заводской'),
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Фрунзенский')
) AS d(name)
WHERE c.name = 'Саратов'
ON CONFLICT (city_id, name) DO NOTHING;

-- Тюмень (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Калининский'),
    ('Ленинский'),
    ('Центральный'),
    ('Восточный')
) AS d(name)
WHERE c.name = 'Тюмень'
ON CONFLICT (city_id, name) DO NOTHING;

-- Тольятти (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Автозаводский'),
    ('Комсомольский'),
    ('Центральный')
) AS d(name)
WHERE c.name = 'Тольятти'
ON CONFLICT (city_id, name) DO NOTHING;

-- Ижевск (5 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name
FROM cities c, (VALUES
    ('Индустриальный'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Первомайский'),
    ('Устиновский')
) AS d(name)
WHERE c.name = 'Ижевск'
ON CONFLICT (city_id, name) DO NOTHING;

COMMIT;
