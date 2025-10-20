-- ============================================================================
-- Миграция: Упрощение структуры районов
-- Дата: 2025-10-04
-- Описание: Приведение районов к административным округам/районам
-- ============================================================================

BEGIN;

-- ============================================================================
-- ЭТАП 0: ПОДГОТОВКА - Деактивация дубликата Санкт-Петербурга
-- ============================================================================

-- Деактивируем дубликат "Санкт Петербург" (id=5), оставляем "Санкт-Петербург" (id=2)
UPDATE cities SET is_active = false WHERE id = 5;

RAISE NOTICE 'Дубликат "Санкт Петербург" (id=5) деактивирован';


-- ============================================================================
-- ЭТАП 1: ИРКУТСК (id=4) - Оставляем только 4 административных округа
-- ============================================================================

-- Сохраняем ID административных округов Иркутска
CREATE TEMP TABLE irkutsk_keep_districts AS
SELECT id FROM districts 
WHERE city_id = 4 
  AND name IN (
    'Ленинский административный округ',
    'Октябрьский административный округ',
    'Правобережный административный округ',
    'Свердловский административный округ'
  );

-- Удаляем все остальные районы Иркутска (650 штук)
DELETE FROM districts 
WHERE city_id = 4 
  AND id NOT IN (SELECT id FROM irkutsk_keep_districts);

-- Проверка
DO $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM districts WHERE city_id = 4;
    IF cnt != 4 THEN
        RAISE EXCEPTION 'Ошибка: У Иркутска должно быть 4 района, а получилось %', cnt;
    END IF;
    RAISE NOTICE 'Иркутск (id=4): осталось % административных округа ✓', cnt;
END $$;


-- ============================================================================
-- ЭТАП 2: МОСКВА (id=1) - Добавляем 12 административных округов
-- ============================================================================

-- Удаляем все текущие районы Москвы
DELETE FROM districts WHERE city_id = 1;

-- Добавляем 12 административных округов
INSERT INTO districts (city_id, name) VALUES
(1, 'Центральный АО'),
(1, 'Северный АО'),
(1, 'Северо-Восточный АО'),
(1, 'Восточный АО'),
(1, 'Юго-Восточный АО'),
(1, 'Южный АО'),
(1, 'Юго-Западный АО'),
(1, 'Западный АО'),
(1, 'Северо-Западный АО'),
(1, 'Зеленоградский АО'),
(1, 'Новомосковский АО'),
(1, 'Троицкий АО');

-- Проверка
DO $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM districts WHERE city_id = 1;
    IF cnt != 12 THEN
        RAISE EXCEPTION 'Ошибка: У Москвы должно быть 12 округов, а получилось %', cnt;
    END IF;
    RAISE NOTICE 'Москва (id=1): добавлено % административных округов ✓', cnt;
END $$;


-- ============================================================================
-- ЭТАП 3: САНКТ-ПЕТЕРБУРГ (id=2) - Добавляем 18 районов
-- ============================================================================

-- Удаляем все текущие районы СПб
DELETE FROM districts WHERE city_id = 2;

-- Добавляем 18 районов
INSERT INTO districts (city_id, name) VALUES
(2, 'Адмиралтейский район'),
(2, 'Василеостровский район'),
(2, 'Выборгский район'),
(2, 'Калининский район'),
(2, 'Кировский район'),
(2, 'Колпинский район'),
(2, 'Красногвардейский район'),
(2, 'Красносельский район'),
(2, 'Кронштадтский район'),
(2, 'Курортный район'),
(2, 'Московский район'),
(2, 'Невский район'),
(2, 'Петроградский район'),
(2, 'Петродворцовый район'),
(2, 'Приморский район'),
(2, 'Пушкинский район'),
(2, 'Фрунзенский район'),
(2, 'Центральный район');

-- Проверка
DO $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM districts WHERE city_id = 2;
    IF cnt != 18 THEN
        RAISE EXCEPTION 'Ошибка: У СПб должно быть 18 районов, а получилось %', cnt;
    END IF;
    RAISE NOTICE 'Санкт-Петербург (id=2): добавлено % районов ✓', cnt;
END $$;


-- ============================================================================
-- ЭТАП 4: ОСТАЛЬНЫЕ ГОРОДА - Загрузка районов из CSV
-- ============================================================================

-- Казань (id=3)
DELETE FROM districts WHERE city_id = 3;
INSERT INTO districts (city_id, name) VALUES
(3, 'Авиастроительный район'),
(3, 'Вахитовский район'),
(3, 'Кировский район'),
(3, 'Московский район'),
(3, 'Ново-Савиновский район'),
(3, 'Приволжский район'),
(3, 'Советский район');

-- Новосибирск (id=6)
DELETE FROM districts WHERE city_id = 6;
INSERT INTO districts (city_id, name) VALUES
(6, 'Центральный район'),
(6, 'Железнодорожный район'),
(6, 'Заельцовский район'),
(6, 'Ленинский район'),
(6, 'Дзержинский район'),
(6, 'Калининский район'),
(6, 'Кировский район'),
(6, 'Октябрьский район'),
(6, 'Первомайский район'),
(6, 'Советский район');

-- Екатеринбург (id=7)
DELETE FROM districts WHERE city_id = 7;
INSERT INTO districts (city_id, name) VALUES
(7, 'Верх-Исетский район'),
(7, 'Железнодорожный район'),
(7, 'Кировский район'),
(7, 'Ленинский район'),
(7, 'Октябрьский район'),
(7, 'Орджоникидзевский район'),
(7, 'Чкаловский район');

-- Нижний Новгород (id=8)
DELETE FROM districts WHERE city_id = 8;
INSERT INTO districts (city_id, name) VALUES
(8, 'Автозаводский район'),
(8, 'Канавинский район'),
(8, 'Ленинский район'),
(8, 'Московский район'),
(8, 'Нижегородский район'),
(8, 'Приокский район'),
(8, 'Советский район'),
(8, 'Сормовский район');

-- Челябинск (id=9)
DELETE FROM districts WHERE city_id = 9;
INSERT INTO districts (city_id, name) VALUES
(9, 'Центральный район'),
(9, 'Калининский район'),
(9, 'Курчатовский район'),
(9, 'Ленинский район'),
(9, 'Металлургический район'),
(9, 'Советский район'),
(9, 'Тракторозаводский район');

-- Красноярск (id=10)
DELETE FROM districts WHERE city_id = 10;
INSERT INTO districts (city_id, name) VALUES
(10, 'Центральный район'),
(10, 'Железнодорожный район'),
(10, 'Кировский район'),
(10, 'Ленинский район'),
(10, 'Октябрьский район'),
(10, 'Свердловский район'),
(10, 'Советский район');

-- Самара (id=11)
DELETE FROM districts WHERE city_id = 11;
INSERT INTO districts (city_id, name) VALUES
(11, 'Железнодорожный район'),
(11, 'Кировский район'),
(11, 'Красноглинский район'),
(11, 'Куйбышевский район'),
(11, 'Ленинский район'),
(11, 'Октябрьский район'),
(11, 'Промышленный район'),
(11, 'Самарский район'),
(11, 'Советский район');

-- Уфа (id=12)
DELETE FROM districts WHERE city_id = 12;
INSERT INTO districts (city_id, name) VALUES
(12, 'Демский район'),
(12, 'Калининский район'),
(12, 'Кировский район'),
(12, 'Ленинский район'),
(12, 'Октябрьский район'),
(12, 'Орджоникидзевский район'),
(12, 'Советский район');

-- Ростов-на-Дону (id=13)
DELETE FROM districts WHERE city_id = 13;
INSERT INTO districts (city_id, name) VALUES
(13, 'Ворошиловский район'),
(13, 'Железнодорожный район'),
(13, 'Кировский район'),
(13, 'Ленинский район'),
(13, 'Октябрьский район'),
(13, 'Первомайский район'),
(13, 'Пролетарский район'),
(13, 'Советский район');

-- Краснодар (id=14)
DELETE FROM districts WHERE city_id = 14;
INSERT INTO districts (city_id, name) VALUES
(14, 'Центральный внутригородской округ'),
(14, 'Западный внутригородской округ'),
(14, 'Карасунский внутригородской округ'),
(14, 'Прикубанский внутригородской округ');

-- Омск (id=15)
DELETE FROM districts WHERE city_id = 15;
INSERT INTO districts (city_id, name) VALUES
(15, 'Центральный административный округ'),
(15, 'Кировский административный округ'),
(15, 'Ленинский административный округ'),
(15, 'Октябрьский административный округ'),
(15, 'Советский административный округ');

-- Воронеж (id=16)
DELETE FROM districts WHERE city_id = 16;
INSERT INTO districts (city_id, name) VALUES
(16, 'Центральный район'),
(16, 'Железнодорожный район'),
(16, 'Коминтерновский район'),
(16, 'Ленинский район'),
(16, 'Левобережный район'),
(16, 'Советский район');

-- Пермь (id=17)
DELETE FROM districts WHERE city_id = 17;
INSERT INTO districts (city_id, name) VALUES
(17, 'Дзержинский район'),
(17, 'Индустриальный район'),
(17, 'Кировский район'),
(17, 'Ленинский район'),
(17, 'Мотовилихинский район'),
(17, 'Орджоникидзевский район'),
(17, 'Свердловский район');

-- Волгоград (id=18)
DELETE FROM districts WHERE city_id = 18;
INSERT INTO districts (city_id, name) VALUES
(18, 'Центральный район'),
(18, 'Дзержинский район'),
(18, 'Ворошиловский район'),
(18, 'Кировский район'),
(18, 'Краснооктябрьский район'),
(18, 'Красноармейский район'),
(18, 'Советский район'),
(18, 'Тракторозаводский район');

-- Саратов (id=19)
DELETE FROM districts WHERE city_id = 19;
INSERT INTO districts (city_id, name) VALUES
(19, 'Волжский район'),
(19, 'Заводской район'),
(19, 'Кировский район'),
(19, 'Ленинский район'),
(19, 'Октябрьский район'),
(19, 'Фрунзенский район');

-- Тюмень (id=20)
DELETE FROM districts WHERE city_id = 20;
INSERT INTO districts (city_id, name) VALUES
(20, 'Центральный административный округ'),
(20, 'Восточный административный округ'),
(20, 'Калининский административный округ'),
(20, 'Ленинский административный округ');

-- Тольятти (id=21)
DELETE FROM districts WHERE city_id = 21;
INSERT INTO districts (city_id, name) VALUES
(21, 'Автозаводский район'),
(21, 'Центральный район'),
(21, 'Комсомольский район');

-- Ижевск (id=22)
DELETE FROM districts WHERE city_id = 22;
INSERT INTO districts (city_id, name) VALUES
(22, 'Индустриальный район'),
(22, 'Ленинский район'),
(22, 'Октябрьский район'),
(22, 'Первомайский район'),
(22, 'Устиновский район');

-- Барнаул (id=23)
DELETE FROM districts WHERE city_id = 23;
INSERT INTO districts (city_id, name) VALUES
(23, 'Центральный район'),
(23, 'Железнодорожный район'),
(23, 'Индустриальный район'),
(23, 'Ленинский район'),
(23, 'Октябрьский район');

-- Ульяновск (id=24)
DELETE FROM districts WHERE city_id = 24;
INSERT INTO districts (city_id, name) VALUES
(24, 'Железнодорожный район'),
(24, 'Заволжский район'),
(24, 'Ленинский район'),
(24, 'Засвияжский район');

-- Хабаровск (id=25)
DELETE FROM districts WHERE city_id = 25;
INSERT INTO districts (city_id, name) VALUES
(25, 'Центральный район'),
(25, 'Железнодорожный район'),
(25, 'Индустриальный район'),
(25, 'Кировский район');

-- Владивосток (id=26)
DELETE FROM districts WHERE city_id = 26;
INSERT INTO districts (city_id, name) VALUES
(26, 'Ленинский район'),
(26, 'Первомайский район'),
(26, 'Первореченский район'),
(26, 'Советский район'),
(26, 'Фрунзенский район');

-- Ярославль (id=27)
DELETE FROM districts WHERE city_id = 27;
INSERT INTO districts (city_id, name) VALUES
(27, 'Дзержинский район'),
(27, 'Заволжский район'),
(27, 'Кировский район'),
(27, 'Красноперекопский район'),
(27, 'Ленинский район'),
(27, 'Фрунзенский район');

-- Махачкала (id=28)
DELETE FROM districts WHERE city_id = 28;
INSERT INTO districts (city_id, name) VALUES
(28, 'Кировский район'),
(28, 'Ленинский район'),
(28, 'Советский район');

-- Томск (id=29)
DELETE FROM districts WHERE city_id = 29;
INSERT INTO districts (city_id, name) VALUES
(29, 'Кировский район'),
(29, 'Ленинский район'),
(29, 'Октябрьский район'),
(29, 'Советский район');

-- Оренбург (id=30)
DELETE FROM districts WHERE city_id = 30;
INSERT INTO districts (city_id, name) VALUES
(30, 'Центральный район'),
(30, 'Дзержинский район'),
(30, 'Ленинский район'),
(30, 'Промышленный район');

-- Кемерово (id=31)
DELETE FROM districts WHERE city_id = 31;
INSERT INTO districts (city_id, name) VALUES
(31, 'Центральный район'),
(31, 'Заводской район'),
(31, 'Кировский район'),
(31, 'Ленинский район'),
(31, 'Рудничный район');

-- Новокузнецк (id=32)
DELETE FROM districts WHERE city_id = 32;
INSERT INTO districts (city_id, name) VALUES
(32, 'Центральный район'),
(32, 'Заводской район'),
(32, 'Кузнецкий район'),
(32, 'Куйбышевский район'),
(32, 'Новоильинский район'),
(32, 'Орджоникидзевский район');

-- Рязань (id=33)
DELETE FROM districts WHERE city_id = 33;
INSERT INTO districts (city_id, name) VALUES
(33, 'Железнодорожный район'),
(33, 'Московский район'),
(33, 'Октябрьский район'),
(33, 'Советский район');

-- Набережные Челны (id=34)
DELETE FROM districts WHERE city_id = 34;
INSERT INTO districts (city_id, name) VALUES
(34, 'Автозаводский район'),
(34, 'Центральный район'),
(34, 'Комсомольский район');

-- Астрахань (id=35)
DELETE FROM districts WHERE city_id = 35;
INSERT INTO districts (city_id, name) VALUES
(35, 'Кировский район'),
(35, 'Ленинский район'),
(35, 'Советский район'),
(35, 'Трусовский район');

-- Пенза (id=36)
DELETE FROM districts WHERE city_id = 36;
INSERT INTO districts (city_id, name) VALUES
(36, 'Железнодорожный район'),
(36, 'Ленинский район'),
(36, 'Октябрьский район'),
(36, 'Первомайский район');

-- Киров (id=37)
DELETE FROM districts WHERE city_id = 37;
INSERT INTO districts (city_id, name) VALUES
(37, 'Ленинский район'),
(37, 'Октябрьский район'),
(37, 'Первомайский район'),
(37, 'Нововятский район');

-- Липецк (id=38)
DELETE FROM districts WHERE city_id = 38;
INSERT INTO districts (city_id, name) VALUES
(38, 'Левобережный округ'),
(38, 'Правобережный округ'),
(38, 'Советский округ'),
(38, 'Октябрьский округ');

-- Чебоксары (id=39)
DELETE FROM districts WHERE city_id = 39;
INSERT INTO districts (city_id, name) VALUES
(39, 'Калининский район'),
(39, 'Ленинский район'),
(39, 'Московский район');

-- Калининград (id=40)
DELETE FROM districts WHERE city_id = 40;
INSERT INTO districts (city_id, name) VALUES
(40, 'Центральный район'),
(40, 'Балтийский район'),
(40, 'Ленинградский район'),
(40, 'Московский район');


-- ============================================================================
-- ФИНАЛЬНАЯ ПРОВЕРКА
-- ============================================================================

DO $$
DECLARE
    total_cities INTEGER;
    total_districts INTEGER;
    cities_without_districts INTEGER;
BEGIN
    -- Подсчёт
    SELECT COUNT(*) INTO total_cities FROM cities WHERE is_active = true;
    SELECT COUNT(*) INTO total_districts FROM districts;
    SELECT COUNT(*) INTO cities_without_districts 
    FROM cities c 
    WHERE c.is_active = true 
      AND NOT EXISTS (SELECT 1 FROM districts d WHERE d.city_id = c.id);
    
    -- Отчёт
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'МИГРАЦИЯ ЗАВЕРШЕНА';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Всего активных городов: %', total_cities;
    RAISE NOTICE 'Всего районов в системе: %', total_districts;
    RAISE NOTICE 'Городов без районов: %', cities_without_districts;
    RAISE NOTICE '';
    
    IF cities_without_districts > 0 THEN
        RAISE WARNING 'ВНИМАНИЕ: Есть города без районов!';
        RAISE NOTICE 'Список городов без районов:';
        FOR r IN 
            SELECT c.name 
            FROM cities c 
            WHERE c.is_active = true 
              AND NOT EXISTS (SELECT 1 FROM districts d WHERE d.city_id = c.id)
            ORDER BY c.name
        LOOP
            RAISE NOTICE '  - %', r.name;
        END LOOP;
    ELSE
        RAISE NOTICE '✓ Все активные города имеют районы';
    END IF;
    
    RAISE NOTICE '';
    RAISE NOTICE 'Детали по ключевым городам:';
    FOR r IN 
        SELECT 
            c.name AS city_name,
            COUNT(d.id) AS districts_count
        FROM cities c
        LEFT JOIN districts d ON d.city_id = c.id
        WHERE c.name IN ('Москва', 'Санкт-Петербург', 'Иркутск')
        GROUP BY c.id, c.name
        ORDER BY c.name
    LOOP
        RAISE NOTICE '  % - % районов', r.city_name, r.districts_count;
    END LOOP;
    
    RAISE NOTICE '';
    RAISE NOTICE 'ТОП-5 городов по количеству районов:';
    FOR r IN 
        SELECT 
            c.name AS city_name,
            COUNT(d.id) AS districts_count
        FROM cities c
        LEFT JOIN districts d ON d.city_id = c.id
        WHERE c.is_active = true
        GROUP BY c.id, c.name
        ORDER BY districts_count DESC
        LIMIT 5
    LOOP
        RAISE NOTICE '  % - % районов', r.city_name, r.districts_count;
    END LOOP;
    RAISE NOTICE '========================================';
END $$;

COMMIT;

-- Конец миграции
