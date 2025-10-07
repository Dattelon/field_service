-- Добавление районов для остальных 59 городов
-- Дата: 2025-10-07

BEGIN;

-- Архангельск (9 округов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ломоносовский'),
    ('Маймаксанский'),
    ('Октябрьский'),
    ('Соломбальский'),
    ('Цигломенский'),
    ('Исакогорский'),
    ('Майская Горка'),
    ('Варавино-Фактория'),
    ('Северный')
) AS d(name) WHERE c.name = 'Архангельск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Астрахань (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Кировский'),
    ('Ленинский'),
    ('Советский'),
    ('Трусовский')
) AS d(name) WHERE c.name = 'Астрахань'
ON CONFLICT (city_id, name) DO NOTHING;

-- Барнаул (5 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Индустриальный'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Барнаул'
ON CONFLICT (city_id, name) DO NOTHING;

-- Белгород (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Восточный'),
    ('Западный'),
    ('Юго-Западный')
) AS d(name) WHERE c.name = 'Белгород'
ON CONFLICT (city_id, name) DO NOTHING;

-- Брянск (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Бежицкий'),
    ('Володарский'),
    ('Советский'),
    ('Фокинский')
) AS d(name) WHERE c.name = 'Брянск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Владивосток (5 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинский'),
    ('Первомайский'),
    ('Первореченский'),
    ('Советский'),
    ('Фрунзенский')
) AS d(name) WHERE c.name = 'Владивосток'
ON CONFLICT (city_id, name) DO NOTHING;

-- Иркутск (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Свердловский')
) AS d(name) WHERE c.name = 'Иркутск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Калининград (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинградский'),
    ('Московский'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Калининград'
ON CONFLICT (city_id, name) DO NOTHING;

-- Кемерово (5 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Заводский'),
    ('Кировский'),
    ('Ленинский'),
    ('Рудничный'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Кемерово'
ON CONFLICT (city_id, name) DO NOTHING;

-- Киров (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинский'),
    ('Октябрьский'),
    ('Первомайский'),
    ('Нововятский')
) AS d(name) WHERE c.name = 'Киров'
ON CONFLICT (city_id, name) DO NOTHING;

-- Курск (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Ленинский'),
    ('Сеймский')
) AS d(name) WHERE c.name = 'Курск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Липецк (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Левобережный'),
    ('Октябрьский'),
    ('Правобережный'),
    ('Советский')
) AS d(name) WHERE c.name = 'Липецк'
ON CONFLICT (city_id, name) DO NOTHING;

-- Магнитогорск (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинский'),
    ('Орджоникидзевский'),
    ('Правобережный')
) AS d(name) WHERE c.name = 'Магнитогорск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Махачкала (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Кировский'),
    ('Ленинский'),
    ('Советский')
) AS d(name) WHERE c.name = 'Махачкала'
ON CONFLICT (city_id, name) DO NOTHING;

-- Набережные Челны (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Автозаводский'),
    ('Комсомольский'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Набережные Челны'
ON CONFLICT (city_id, name) DO NOTHING;

-- Новокузнецк (7 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Заводской'),
    ('Кузнецкий'),
    ('Куйбышевский'),
    ('Новоильинский'),
    ('Орджоникидзевский'),
    ('Центральный'),
    ('Кузнецкий-Центральный')
) AS d(name) WHERE c.name = 'Новокузнецк'
ON CONFLICT (city_id, name) DO NOTHING;

-- Оренбург (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Дзержинский'),
    ('Ленинский'),
    ('Промышленный'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Оренбург'
ON CONFLICT (city_id, name) DO NOTHING;

-- Пенза (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Первомайский')
) AS d(name) WHERE c.name = 'Пенза'
ON CONFLICT (city_id, name) DO NOTHING;

-- Рязань (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Московский'),
    ('Октябрьский'),
    ('Советский')
) AS d(name) WHERE c.name = 'Рязань'
ON CONFLICT (city_id, name) DO NOTHING;

-- Сочи (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Адлерский'),
    ('Лазаревский'),
    ('Хостинский'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Сочи'
ON CONFLICT (city_id, name) DO NOTHING;

-- Ставрополь (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинский'),
    ('Октябрьский'),
    ('Промышленный')
) AS d(name) WHERE c.name = 'Ставрополь'
ON CONFLICT (city_id, name) DO NOTHING;

-- Томск (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Кировский'),
    ('Ленинский'),
    ('Октябрьский'),
    ('Советский')
) AS d(name) WHERE c.name = 'Томск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Тула (5 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Зареченский'),
    ('Привокзальный'),
    ('Пролетарский'),
    ('Советский'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Тула'
ON CONFLICT (city_id, name) DO NOTHING;

-- Ульяновск (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Заволжский'),
    ('Ленинский'),
    ('Засвияжский')
) AS d(name) WHERE c.name = 'Ульяновск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Хабаровск (5 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Индустриальный'),
    ('Кировский'),
    ('Краснофлотский'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Хабаровск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Чебоксары (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Калининский'),
    ('Ленинский'),
    ('Московский')
) AS d(name) WHERE c.name = 'Чебоксары'
ON CONFLICT (city_id, name) DO NOTHING;

-- Ярославль (6 районов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Дзержинский'),
    ('Заволжский'),
    ('Кировский'),
    ('Красноперекопский'),
    ('Ленинский'),
    ('Фрунзенский')
) AS d(name) WHERE c.name = 'Ярославль'
ON CONFLICT (city_id, name) DO NOTHING;

-- Севастополь (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Гагаринский'),
    ('Ленинский'),
    ('Нахимовский'),
    ('Балаклавский')
) AS d(name) WHERE c.name = 'Севастополь'
ON CONFLICT (city_id, name) DO NOTHING;

-- Симферополь (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Киевский'),
    ('Центральный'),
    ('Железнодорожный')
) AS d(name) WHERE c.name = 'Симферополь'
ON CONFLICT (city_id, name) DO NOTHING;

-- Тверь (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Заволжский'),
    ('Московский'),
    ('Пролетарский'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Тверь'
ON CONFLICT (city_id, name) DO NOTHING;

-- Улан-Удэ (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Железнодорожный'),
    ('Октябрьский'),
    ('Советский')
) AS d(name) WHERE c.name = 'Улан-Удэ'
ON CONFLICT (city_id, name) DO NOTHING;

-- Чита (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ингодинский'),
    ('Центральный'),
    ('Черновский'),
    ('Железнодорожный')
) AS d(name) WHERE c.name = 'Чита'
ON CONFLICT (city_id, name) DO NOTHING;

-- Якутск (5 округов)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Автодорожный округ'),
    ('Гагаринский округ'),
    ('Промышленный округ'),
    ('Сайсарский округ'),
    ('Строительный округ')
) AS d(name) WHERE c.name = 'Якутск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Калуга (округа и микрорайоны - основные)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Московский округ'),
    ('Ленинский округ'),
    ('Октябрьский округ')
) AS d(name) WHERE c.name = 'Калуга'
ON CONFLICT (city_id, name) DO NOTHING;

-- Смоленск (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Заднепровский'),
    ('Ленинский'),
    ('Промышленный')
) AS d(name) WHERE c.name = 'Смоленск'
ON CONFLICT (city_id, name) DO NOTHING;

-- Владикавказ (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Иристонский'),
    ('Промышленный'),
    ('Северо-Западный'),
    ('Затеречный')
) AS d(name) WHERE c.name = 'Владикавказ'
ON CONFLICT (city_id, name) DO NOTHING;

-- Курган (2 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Центральный'),
    ('Промышленный')
) AS d(name) WHERE c.name = 'Курган'
ON CONFLICT (city_id, name) DO NOTHING;

-- Орёл (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Заводской'),
    ('Железнодорожный'),
    ('Северный'),
    ('Советский')
) AS d(name) WHERE c.name = 'Орёл'
ON CONFLICT (city_id, name) DO NOTHING;

-- Кострома (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Заволжский'),
    ('Фабричный'),
    ('Центральный')
) AS d(name) WHERE c.name = 'Кострома'
ON CONFLICT (city_id, name) DO NOTHING;

-- Грозный (4 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинский'),
    ('Октябрьский'),
    ('Старопромысловский'),
    ('Заводской')
) AS d(name) WHERE c.name = 'Грозный'
ON CONFLICT (city_id, name) DO NOTHING;

-- Нижний Тагил (3 района)
INSERT INTO districts (city_id, name)
SELECT c.id, d.name FROM cities c, (VALUES
    ('Ленинский'),
    ('Дзержинский'),
    ('Тагилстроевский')
) AS d(name) WHERE c.name = 'Нижний Тагил'
ON CONFLICT (city_id, name) DO NOTHING;

COMMIT;
