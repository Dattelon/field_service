-- Добавление районов для небольших городов (микрорайоны и планировочные районы)
-- Дата: 2025-10-07

BEGIN;

-- Балашиха (МО) - 4 микрорайона
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Центральный'),
    ('Левый'),
    ('Западный')
) AS d(name) WHERE c.name = 'Балашиха (МО)'
ON CONFLICT (city_id, name) DO NOTHING;

-- Великий Новгород - 3 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Западный'),
    ('Заречный'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Великий Новгород'
ON CONFLICT (city_id, name) DO NOTHING;

-- Волжский - 3 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Южный'),
    ('Северный')
) AS d(name) WHERE c.name = 'Волжский'
ON CONFLICT (city_id, name) DO NOTHING;

-- Дзержинск - 2 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Западный'),
    ('Восточный')
) AS d(name) WHERE c.name = 'Дзержинск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Йошкар-Ола - 3 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинский'),
    ('Заречный'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Йошкар-Ола'
ON CONFLICT (city_id, name) DO NOTHING;

-- Нижневартовск - 2 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Северный')
) AS d(name) WHERE c.name = 'Нижневартовск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Новороссийск - 5 районов
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Восточный'),
    ('Западный'),
    ('Приморский'),
    ('Южный'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Новороссийск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Подольск (МО) - 3 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Кузнечики'),
    ('Климовск')
) AS d(name) WHERE c.name = 'Подольск (МО)'
ON CONFLICT (city_id, name) DO NOTHING;

-- Псков - 2 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Завеличье')
) AS d(name) WHERE c.name = 'Псков'
ON CONFLICT (city_id, name) DO NOTHING;

-- Саранск - 3 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинский'),
    ('Октябрьский'),
    ('Пролетарский')
) AS d(name) WHERE c.name = 'Саранск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Старый Оскол - 3 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Северо-Восточный'),
    ('Юго-Западный')
) AS d(name) WHERE c.name = 'Старый Оскол'
ON CONFLICT (city_id, name) DO NOTHING;

-- Сургут - 4 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Северный'),
    ('Восточный'),
    ('Западный')
) AS d(name) WHERE c.name = 'Сургут'
ON CONFLICT (city_id, name) DO NOTHING;

-- Таганрог - 3 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Западный'),
    ('Северо-Восточный')
) AS d(name) WHERE c.name = 'Таганрог'
ON CONFLICT (city_id, name) DO NOTHING;

-- Химки (МО) - 4 микрорайона
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Левобережный'),
    ('Подрезково'),
    ('Сходня'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Химки (МО)'
ON CONFLICT (city_id, name) DO NOTHING;

-- Шахты - 2 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Западный')
) AS d(name) WHERE c.name = 'Шахты'
ON CONFLICT (city_id, name) DO NOTHING;

-- Энгельс - 3 района
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Приволжский'),
    ('Покровский')
) AS d(name) WHERE c.name = 'Энгельс'
ON CONFLICT (city_id, name) DO NOTHING;

-- Березники - для маленьких городов можно оставить без районов
-- или добавить условные районы

COMMIT;
