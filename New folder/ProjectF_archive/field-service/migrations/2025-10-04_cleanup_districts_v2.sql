-- ============================================================================
-- МИГРАЦИЯ V2: Упрощение структуры районов (ИСПРАВЛЕННАЯ ВЕРСИЯ)
-- Дата: 2025-10-04
-- Автор: Тимлид проекта
-- Причина v2: Первая версия не добавила все районы из-за ON CONFLICT
-- ============================================================================

BEGIN;

-- ============================================================================
-- ДИАГНОСТИКА: Проверяем текущее состояние
-- ============================================================================

DO $$
DECLARE
    moscow_before INTEGER;
    spb_before INTEGER;
    duplicate_city BOOLEAN;
BEGIN
    SELECT COUNT(*) INTO moscow_before FROM districts WHERE city_id = 1;
    SELECT COUNT(*) INTO spb_before FROM districts WHERE city_id = 2;
    SELECT EXISTS(SELECT 1 FROM cities WHERE id = 5) INTO duplicate_city;
    
    RAISE NOTICE '=== ДИАГНОСТИКА ДО МИГРАЦИИ ===';
    RAISE NOTICE 'Москва: % районов', moscow_before;
    RAISE NOTICE 'СПб: % районов', spb_before;
    RAISE NOTICE 'Дубль города (id=5): %', CASE WHEN duplicate_city THEN 'ДА' ELSE 'НЕТ' END;
END $$;


-- ============================================================================
-- ЧАСТЬ 1: УДАЛЕНИЕ ДУБЛЯ САНКТ-ПЕТЕРБУРГА (КРИТИЧНО!)
-- ============================================================================

DO $$
DECLARE
    duplicate_exists BOOLEAN;
    orders_count INTEGER;
    masters_count INTEGER;
BEGIN
    -- Проверяем наличие дубля
    SELECT EXISTS(SELECT 1 FROM cities WHERE id = 5) INTO duplicate_exists;
    
    IF duplicate_exists THEN
        RAISE NOTICE '>>> УДАЛЕНИЕ ДУБЛЯ ГОРОДА (id=5)...';
        
        -- Считаем что переносим
        SELECT COUNT(*) INTO orders_count FROM orders WHERE city_id = 5;
        SELECT COUNT(*) INTO masters_count FROM masters WHERE city_id = 5;
        
        RAISE NOTICE '  Найдено заказов для переноса: %', orders_count;
        RAISE NOTICE '  Найдено мастеров для переноса: %', masters_count;
        
        -- Переносим заказы
        UPDATE orders SET city_id = 2 WHERE city_id = 5;
        
        -- Переносим мастеров
        UPDATE masters SET city_id = 2 WHERE city_id = 5;
        
        -- Удаляем районы дубля
        DELETE FROM districts WHERE city_id = 5;
        
        -- Удаляем сам дубль города
        DELETE FROM cities WHERE id = 5 AND name = 'Санкт Петербург';
        
        RAISE NOTICE '  OK: Дубль города удалён';
    ELSE
        RAISE NOTICE '>>> Дубль города (id=5) не найден';
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 2: МОСКВА - ДОБАВИТЬ ВСЕ 12 АО (БЕЗ ON CONFLICT)
-- ============================================================================

DO $$
DECLARE
    before_count INTEGER;
    after_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO before_count FROM districts WHERE city_id = 1;
    RAISE NOTICE '>>> МОСКВА: До миграции: %', before_count;
    
    -- Удаляем ВСЕ старые районы
    DELETE FROM districts WHERE city_id = 1;
    
    -- Добавляем ВСЕ 12 АО заново
    INSERT INTO districts (city_id, name) VALUES
    (1, 'ЦАО'),
    (1, 'САО'),
    (1, 'СВАО'),
    (1, 'ВАО'),
    (1, 'ЮВАО'),
    (1, 'ЮАО'),
    (1, 'ЮЗАО'),
    (1, 'ЗАО'),
    (1, 'СЗАО'),
    (1, 'ЗелАО'),
    (1, 'НАО'),
    (1, 'ТАО');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 1;
    RAISE NOTICE '    После миграции: %', after_count;
    
    IF after_count != 12 THEN
        RAISE EXCEPTION 'ОШИБКА: Москва имеет % АО вместо 12!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 3: САНКТ-ПЕТЕРБУРГ - ДОБАВИТЬ ВСЕ 18 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    before_count INTEGER;
    after_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO before_count FROM districts WHERE city_id = 2;
    RAISE NOTICE '>>> СПБ: До миграции: %', before_count;
    
    -- Удаляем ВСЕ старые районы
    DELETE FROM districts WHERE city_id = 2;
    
    -- Добавляем ВСЕ 18 районов заново
    INSERT INTO districts (city_id, name) VALUES
    (2, 'Адмиралтейский'),
    (2, 'Василеостровский'),
    (2, 'Выборгский'),
    (2, 'Калининский'),
    (2, 'Кировский'),
    (2, 'Колпинский'),
    (2, 'Красногвардейский'),
    (2, 'Красносельский'),
    (2, 'Кронштадтский'),
    (2, 'Курортный'),
    (2, 'Московский'),
    (2, 'Невский'),
    (2, 'Петроградский'),
    (2, 'Петродворцовый'),
    (2, 'Приморский'),
    (2, 'Пушкинский'),
    (2, 'Фрунзенский'),
    (2, 'Центральный');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 2;
    RAISE NOTICE '    После миграции: %', after_count;
    
    IF after_count != 18 THEN
        RAISE EXCEPTION 'ОШИБКА: СПб имеет % районов вместо 18!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 4: НОВОСИБИРСК - 10 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> НОВОСИБИРСК: Добавление 10 районов...';
    
    DELETE FROM districts WHERE city_id = 6;
    
    INSERT INTO districts (city_id, name) VALUES
    (6, 'Центральный'),
    (6, 'Железнодорожный'),
    (6, 'Заельцовский'),
    (6, 'Дзержинский'),
    (6, 'Калининский'),
    (6, 'Кировский'),
    (6, 'Ленинский'),
    (6, 'Октябрьский'),
    (6, 'Первомайский'),
    (6, 'Советский');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 6;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 10 THEN
        RAISE EXCEPTION 'ОШИБКА: Новосибирск имеет % районов вместо 10!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 5: ЕКАТЕРИНБУРГ - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> ЕКАТЕРИНБУРГ: Добавление 7 районов...';
    
    DELETE FROM districts WHERE city_id = 7;
    
    INSERT INTO districts (city_id, name) VALUES
    (7, 'Верх-Исетский'),
    (7, 'Железнодорожный'),
    (7, 'Кировский'),
    (7, 'Ленинский'),
    (7, 'Октябрьский'),
    (7, 'Орджоникидзевский'),
    (7, 'Чкаловский');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 7;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 7 THEN
        RAISE EXCEPTION 'ОШИБКА: Екатеринбург имеет % районов вместо 7!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 6: КАЗАНЬ - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> КАЗАНЬ: Добавление 7 районов...';
    
    DELETE FROM districts WHERE city_id = 3;
    
    INSERT INTO districts (city_id, name) VALUES
    (3, 'Авиастроительный'),
    (3, 'Вахитовский'),
    (3, 'Кировский'),
    (3, 'Московский'),
    (3, 'Ново-Савиновский'),
    (3, 'Приволжский'),
    (3, 'Советский');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 3;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 7 THEN
        RAISE EXCEPTION 'ОШИБКА: Казань имеет % районов вместо 7!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 7: НИЖНИЙ НОВГОРОД - 8 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> НИЖНИЙ НОВГОРОД: Добавление 8 районов...';
    
    DELETE FROM districts WHERE city_id = 8;
    
    INSERT INTO districts (city_id, name) VALUES
    (8, 'Автозаводский'),
    (8, 'Канавинский'),
    (8, 'Ленинский'),
    (8, 'Московский'),
    (8, 'Нижегородский'),
    (8, 'Приокский'),
    (8, 'Советский'),
    (8, 'Сормовский');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 8;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 8 THEN
        RAISE EXCEPTION 'ОШИБКА: Н.Новгород имеет % районов вместо 8!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 8: ЧЕЛЯБИНСК - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> ЧЕЛЯБИНСК: Добавление 7 районов...';
    
    DELETE FROM districts WHERE city_id = 9;
    
    INSERT INTO districts (city_id, name) VALUES
    (9, 'Калининский'),
    (9, 'Курчатовский'),
    (9, 'Ленинский'),
    (9, 'Металлургический'),
    (9, 'Советский'),
    (9, 'Тракторозаводский'),
    (9, 'Центральный');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 9;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 7 THEN
        RAISE EXCEPTION 'ОШИБКА: Челябинск имеет % районов вместо 7!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 9: КРАСНОЯРСК - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> КРАСНОЯРСК: Добавление 7 районов...';
    
    DELETE FROM districts WHERE city_id = 10;
    
    INSERT INTO districts (city_id, name) VALUES
    (10, 'Железнодорожный'),
    (10, 'Кировский'),
    (10, 'Ленинский'),
    (10, 'Октябрьский'),
    (10, 'Свердловский'),
    (10, 'Советский'),
    (10, 'Центральный');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 10;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 7 THEN
        RAISE EXCEPTION 'ОШИБКА: Красноярск имеет % районов вместо 7!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 10: САМАРА - 9 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> САМАРА: Добавление 9 районов...';
    
    DELETE FROM districts WHERE city_id = 11;
    
    INSERT INTO districts (city_id, name) VALUES
    (11, 'Железнодорожный'),
    (11, 'Кировский'),
    (11, 'Красноглинский'),
    (11, 'Куйбышевский'),
    (11, 'Ленинский'),
    (11, 'Октябрьский'),
    (11, 'Промышленный'),
    (11, 'Самарский'),
    (11, 'Советский');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 11;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 9 THEN
        RAISE EXCEPTION 'ОШИБКА: Самара имеет % районов вместо 9!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 11: УФА - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> УФА: Добавление 7 районов...';
    
    DELETE FROM districts WHERE city_id = 12;
    
    INSERT INTO districts (city_id, name) VALUES
    (12, 'Демский'),
    (12, 'Калининский'),
    (12, 'Кировский'),
    (12, 'Ленинский'),
    (12, 'Октябрьский'),
    (12, 'Орджоникидзевский'),
    (12, 'Советский');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 12;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 7 THEN
        RAISE EXCEPTION 'ОШИБКА: Уфа имеет % районов вместо 7!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 12: РОСТОВ-НА-ДОНУ - 8 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> РОСТОВ-НА-ДОНУ: Добавление 8 районов...';
    
    DELETE FROM districts WHERE city_id = 13;
    
    INSERT INTO districts (city_id, name) VALUES
    (13, 'Ворошиловский'),
    (13, 'Железнодорожный'),
    (13, 'Кировский'),
    (13, 'Ленинский'),
    (13, 'Октябрьский'),
    (13, 'Первомайский'),
    (13, 'Пролетарский'),
    (13, 'Советский');
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 13;
    RAISE NOTICE '    После: %', after_count;
    
    IF after_count != 8 THEN
        RAISE EXCEPTION 'ОШИБКА: Ростов имеет % районов вместо 8!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ЧАСТЬ 13: ИРКУТСК - ОСТАВИТЬ ТОЛЬКО 4 АО
-- ============================================================================

DO $$
DECLARE
    before_count INTEGER;
    after_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO before_count FROM districts WHERE city_id = 4;
    RAISE NOTICE '>>> ИРКУТСК: До миграции: %', before_count;
    
    -- Удаляем все КРОМЕ 4 АО
    DELETE FROM districts 
    WHERE city_id = 4 
      AND id NOT IN (1262, 1263, 1264, 1265);
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 4;
    RAISE NOTICE '    После миграции: %', after_count;
    RAISE NOTICE '    Удалено: %', before_count - after_count;
    
    IF after_count != 4 THEN
        RAISE EXCEPTION 'ОШИБКА: Иркутск имеет % АО вместо 4!', after_count;
    END IF;
END $$;


-- ============================================================================
-- ФИНАЛЬНАЯ ПРОВЕРКА
-- ============================================================================

DO $$
DECLARE
    total_districts INTEGER;
    moscow_count INTEGER;
    spb_count INTEGER;
    irkutsk_count INTEGER;
    novosibirsk_count INTEGER;
    duplicate_cities INTEGER;
BEGIN
    SELECT COUNT(*) INTO total_districts FROM districts;
    SELECT COUNT(*) INTO moscow_count FROM districts WHERE city_id = 1;
    SELECT COUNT(*) INTO spb_count FROM districts WHERE city_id = 2;
    SELECT COUNT(*) INTO irkutsk_count FROM districts WHERE city_id = 4;
    SELECT COUNT(*) INTO novosibirsk_count FROM districts WHERE city_id = 6;
    
    SELECT COUNT(*) INTO duplicate_cities 
    FROM (
        SELECT name 
        FROM cities 
        GROUP BY name 
        HAVING COUNT(*) > 1
    ) AS duplicates;
    
    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'ФИНАЛЬНАЯ ПРОВЕРКА';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Всего районов: %', total_districts;
    RAISE NOTICE '';
    RAISE NOTICE 'Критические города:';
    RAISE NOTICE '  Москва:       % (OK=12)', moscow_count;
    RAISE NOTICE '  СПб:          % (OK=18)', spb_count;
    RAISE NOTICE '  Иркутск:      % (OK=4)', irkutsk_count;
    RAISE NOTICE '  Новосибирск:  % (OK=10)', novosibirsk_count;
    RAISE NOTICE '';
    RAISE NOTICE 'Дублей городов: % (OK=0)', duplicate_cities;
    RAISE NOTICE '========================================';
    
    -- Проверка успешности
    IF moscow_count = 12 AND spb_count = 18 AND irkutsk_count = 4 
       AND novosibirsk_count = 10 AND duplicate_cities = 0 THEN
        RAISE NOTICE '';
        RAISE NOTICE 'SUCCESS: Миграция завершена успешно!';
        RAISE NOTICE '';
    ELSE
        RAISE EXCEPTION 'ОШИБКА: Миграция завершилась с ошибками!';
    END IF;
END $$;

-- Итоговая статистика
SELECT 
    c.id,
    c.name AS city_name,
    COUNT(d.id) AS districts_count
FROM cities c
LEFT JOIN districts d ON d.city_id = c.id
GROUP BY c.id, c.name
ORDER BY COUNT(d.id) DESC, c.name;

COMMIT;
