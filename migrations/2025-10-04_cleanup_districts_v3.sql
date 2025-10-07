-- ============================================================================
-- МИГРАЦИЯ V3: Упрощение структуры районов (С ЯВНЫМИ ПРОВЕРКАМИ)
-- Дата: 2025-10-04
-- Версия: 3 (исправлена проблема с DELETE)
-- ============================================================================

BEGIN;

-- ============================================================================
-- ДИАГНОСТИКА ПЕРЕД НАЧАЛОМ
-- ============================================================================

DO $$
DECLARE
    moscow_count INTEGER;
    spb_count INTEGER;
    duplicate_exists BOOLEAN;
BEGIN
    SELECT COUNT(*) INTO moscow_count FROM districts WHERE city_id = 1;
    SELECT COUNT(*) INTO spb_count FROM districts WHERE city_id = 2;
    SELECT EXISTS(SELECT 1 FROM cities WHERE id = 5) INTO duplicate_exists;
    
    RAISE NOTICE '=== ТЕКУЩЕЕ СОСТОЯНИЕ ===';
    RAISE NOTICE 'Москва (city_id=1): % районов', moscow_count;
    RAISE NOTICE 'СПб (city_id=2): % районов', spb_count;
    RAISE NOTICE 'Дубль города (id=5): %', CASE WHEN duplicate_exists THEN 'ЕСТЬ' ELSE 'НЕТ' END;
    RAISE NOTICE '';
END $$;


-- ============================================================================
-- ШАГ 1: УДАЛЕНИЕ ДУБЛЯ ГОРОДА (id=5)
-- ============================================================================

DO $$
DECLARE
    duplicate_exists BOOLEAN;
    deleted_count INTEGER;
BEGIN
    SELECT EXISTS(SELECT 1 FROM cities WHERE id = 5) INTO duplicate_exists;
    
    IF duplicate_exists THEN
        RAISE NOTICE '>>> Удаление дубля города (id=5)...';
        
        -- Переносим заказы
        UPDATE orders SET city_id = 2 WHERE city_id = 5;
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        RAISE NOTICE '    Перенесено заказов: %', deleted_count;
        
        -- Переносим мастеров
        UPDATE masters SET city_id = 2 WHERE city_id = 5;
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        RAISE NOTICE '    Перенесено мастеров: %', deleted_count;
        
        -- Удаляем районы дубля
        DELETE FROM districts WHERE city_id = 5;
        GET DIAGNOSTICS deleted_count = ROW_COUNT;
        RAISE NOTICE '    Удалено районов дубля: %', deleted_count;
        
        -- Удаляем сам дубль
        DELETE FROM cities WHERE id = 5;
        
        RAISE NOTICE '    OK: Дубль города удалён';
    ELSE
        RAISE NOTICE '>>> Дубль города (id=5) отсутствует';
    END IF;
    RAISE NOTICE '';
END $$;


-- ============================================================================
-- ШАГ 2: МОСКВА - 12 АО
-- ============================================================================

DO $$
DECLARE
    before_count INTEGER;
    after_delete INTEGER;
    after_insert INTEGER;
BEGIN
    -- Текущее состояние
    SELECT COUNT(*) INTO before_count FROM districts WHERE city_id = 1;
    RAISE NOTICE '>>> МОСКВА: До очистки: % районов', before_count;
    
    -- КРИТИЧНО: Удаляем ВСЕ старые районы
    DELETE FROM districts WHERE city_id = 1;
    GET DIAGNOSTICS after_delete = ROW_COUNT;
    RAISE NOTICE '    Удалено: % районов', after_delete;
    
    -- Проверяем что действительно удалили ВСЁ
    SELECT COUNT(*) INTO after_delete FROM districts WHERE city_id = 1;
    IF after_delete != 0 THEN
        RAISE EXCEPTION 'ОШИБКА: После DELETE осталось % районов!', after_delete;
    END IF;
    RAISE NOTICE '    Проверка: 0 районов (OK)';
    
    -- Добавляем 12 АО
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
    
    -- Проверяем результат
    SELECT COUNT(*) INTO after_insert FROM districts WHERE city_id = 1;
    RAISE NOTICE '    После вставки: % АО', after_insert;
    
    IF after_insert != 12 THEN
        RAISE EXCEPTION 'ОШИБКА: Вставлено % АО вместо 12!', after_insert;
    END IF;
    
    RAISE NOTICE '    OK: 12 АО';
    RAISE NOTICE '';
END $$;


-- ============================================================================
-- ШАГ 3: САНКТ-ПЕТЕРБУРГ - 18 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    before_count INTEGER;
    after_delete INTEGER;
    after_insert INTEGER;
BEGIN
    SELECT COUNT(*) INTO before_count FROM districts WHERE city_id = 2;
    RAISE NOTICE '>>> СПБ: До очистки: % районов', before_count;
    
    DELETE FROM districts WHERE city_id = 2;
    GET DIAGNOSTICS after_delete = ROW_COUNT;
    RAISE NOTICE '    Удалено: % районов', after_delete;
    
    SELECT COUNT(*) INTO after_delete FROM districts WHERE city_id = 2;
    IF after_delete != 0 THEN
        RAISE EXCEPTION 'ОШИБКА: После DELETE осталось % районов!', after_delete;
    END IF;
    RAISE NOTICE '    Проверка: 0 районов (OK)';
    
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
    
    SELECT COUNT(*) INTO after_insert FROM districts WHERE city_id = 2;
    RAISE NOTICE '    После вставки: % районов', after_insert;
    
    IF after_insert != 18 THEN
        RAISE EXCEPTION 'ОШИБКА: Вставлено % районов вместо 18!', after_insert;
    END IF;
    
    RAISE NOTICE '    OK: 18 районов';
    RAISE NOTICE '';
END $$;


-- ============================================================================
-- ШАГ 4: КАЗАНЬ - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> КАЗАНЬ...';
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
    IF after_count != 7 THEN
        RAISE EXCEPTION 'Казань: % районов вместо 7', after_count;
    END IF;
    RAISE NOTICE '    OK: 7 районов';
END $$;


-- ============================================================================
-- ШАГ 5: ИРКУТСК - ОСТАВИТЬ 4 АО
-- ============================================================================

DO $$
DECLARE
    before_count INTEGER;
    deleted_count INTEGER;
    after_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO before_count FROM districts WHERE city_id = 4;
    RAISE NOTICE '>>> ИРКУТСК: До очистки: % районов', before_count;
    
    -- Удаляем всё КРОМЕ 4 АО
    DELETE FROM districts 
    WHERE city_id = 4 
      AND id NOT IN (1262, 1263, 1264, 1265);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    
    SELECT COUNT(*) INTO after_count FROM districts WHERE city_id = 4;
    RAISE NOTICE '    Удалено: % районов', deleted_count;
    RAISE NOTICE '    Осталось: % АО', after_count;
    
    IF after_count != 4 THEN
        RAISE EXCEPTION 'Иркутск: % АО вместо 4', after_count;
    END IF;
    RAISE NOTICE '    OK: 4 АО';
    RAISE NOTICE '';
END $$;


-- ============================================================================
-- ШАГ 6: НОВОСИБИРСК - 10 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> НОВОСИБИРСК...';
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
    IF after_count != 10 THEN
        RAISE EXCEPTION 'Новосибирск: % районов вместо 10', after_count;
    END IF;
    RAISE NOTICE '    OK: 10 районов';
END $$;


-- ============================================================================
-- ШАГ 7: ЕКАТЕРИНБУРГ - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> ЕКАТЕРИНБУРГ...';
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
    IF after_count != 7 THEN
        RAISE EXCEPTION 'Екатеринбург: % районов вместо 7', after_count;
    END IF;
    RAISE NOTICE '    OK: 7 районов';
END $$;


-- ============================================================================
-- ШАГ 8: НИЖНИЙ НОВГОРОД - 8 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> НИЖНИЙ НОВГОРОД...';
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
    IF after_count != 8 THEN
        RAISE EXCEPTION 'Н.Новгород: % районов вместо 8', after_count;
    END IF;
    RAISE NOTICE '    OK: 8 районов';
END $$;


-- ============================================================================
-- ШАГ 9: ЧЕЛЯБИНСК - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> ЧЕЛЯБИНСК...';
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
    IF after_count != 7 THEN
        RAISE EXCEPTION 'Челябинск: % районов вместо 7', after_count;
    END IF;
    RAISE NOTICE '    OK: 7 районов';
END $$;


-- ============================================================================
-- ШАГ 10: КРАСНОЯРСК - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> КРАСНОЯРСК...';
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
    IF after_count != 7 THEN
        RAISE EXCEPTION 'Красноярск: % районов вместо 7', after_count;
    END IF;
    RAISE NOTICE '    OK: 7 районов';
END $$;


-- ============================================================================
-- ШАГ 11: САМАРА - 9 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> САМАРА...';
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
    IF after_count != 9 THEN
        RAISE EXCEPTION 'Самара: % районов вместо 9', after_count;
    END IF;
    RAISE NOTICE '    OK: 9 районов';
END $$;


-- ============================================================================
-- ШАГ 12: УФА - 7 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> УФА...';
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
    IF after_count != 7 THEN
        RAISE EXCEPTION 'Уфа: % районов вместо 7', after_count;
    END IF;
    RAISE NOTICE '    OK: 7 районов';
END $$;


-- ============================================================================
-- ШАГ 13: РОСТОВ-НА-ДОНУ - 8 РАЙОНОВ
-- ============================================================================

DO $$
DECLARE
    after_count INTEGER;
BEGIN
    RAISE NOTICE '>>> РОСТОВ-НА-ДОНУ...';
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
    IF after_count != 8 THEN
        RAISE EXCEPTION 'Ростов: % районов вместо 8', after_count;
    END IF;
    RAISE NOTICE '    OK: 8 районов';
    RAISE NOTICE '';
END $$;


-- ============================================================================
-- ФИНАЛЬНАЯ ПРОВЕРКА
-- ============================================================================

DO $$
DECLARE
    total INTEGER;
    moscow INTEGER;
    spb INTEGER;
    irkutsk INTEGER;
    novosibirsk INTEGER;
    duplicates INTEGER;
BEGIN
    SELECT COUNT(*) INTO total FROM districts;
    SELECT COUNT(*) INTO moscow FROM districts WHERE city_id = 1;
    SELECT COUNT(*) INTO spb FROM districts WHERE city_id = 2;
    SELECT COUNT(*) INTO irkutsk FROM districts WHERE city_id = 4;
    SELECT COUNT(*) INTO novosibirsk FROM districts WHERE city_id = 6;
    
    SELECT COUNT(*) INTO duplicates 
    FROM (SELECT name FROM cities GROUP BY name HAVING COUNT(*) > 1) AS d;
    
    RAISE NOTICE '========================================';
    RAISE NOTICE 'ФИНАЛЬНАЯ ПРОВЕРКА';
    RAISE NOTICE '========================================';
    RAISE NOTICE 'Всего районов: %', total;
    RAISE NOTICE '';
    RAISE NOTICE 'Критические города:';
    RAISE NOTICE '  Москва:       % (OK=12)', moscow;
    RAISE NOTICE '  СПб:          % (OK=18)', spb;
    RAISE NOTICE '  Иркутск:      % (OK=4)', irkutsk;
    RAISE NOTICE '  Новосибирск:  % (OK=10)', novosibirsk;
    RAISE NOTICE '';
    RAISE NOTICE 'Дублей городов: % (OK=0)', duplicates;
    RAISE NOTICE '========================================';
    
    IF moscow = 12 AND spb = 18 AND irkutsk = 4 AND novosibirsk = 10 AND duplicates = 0 THEN
        RAISE NOTICE '';
        RAISE NOTICE 'SUCCESS: Миграция завершена успешно!';
    ELSE
        RAISE EXCEPTION 'ОШИБКА: Проверка не прошла!';
    END IF;
END $$;

-- Итоговая статистика
SELECT 
    c.id,
    c.name,
    COUNT(d.id) AS districts_count
FROM cities c
LEFT JOIN districts d ON d.city_id = c.id
GROUP BY c.id, c.name
ORDER BY COUNT(d.id) DESC, c.name;

COMMIT;
