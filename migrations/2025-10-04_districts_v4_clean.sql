-- ============================================================================
-- Migration V4: Clean districts (UTF-8)
-- Date: 2025-10-04
-- Fix: Remove corrupted rows by ID
-- ============================================================================

BEGIN;

-- Step 1: Remove duplicate city (id=5)
DELETE FROM orders WHERE city_id = 5;
DELETE FROM masters WHERE city_id = 5;
DELETE FROM districts WHERE city_id = 5;
DELETE FROM cities WHERE id = 5;

-- Step 2: MOSCOW - Remove ALL including corrupted rows
DELETE FROM districts WHERE city_id = 1;

-- Verify empty
DO $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM districts WHERE city_id = 1;
    IF cnt != 0 THEN
        RAISE EXCEPTION 'Moscow still has % districts after DELETE!', cnt;
    END IF;
END $$;

-- Add 12 AO
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

-- Step 3: SPB - 18 districts
DELETE FROM districts WHERE city_id = 2;
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

-- Step 4: KAZAN - 7 districts
DELETE FROM districts WHERE city_id = 3;
INSERT INTO districts (city_id, name) VALUES
(3, 'Авиастроительный'),
(3, 'Вахитовский'),
(3, 'Кировский'),
(3, 'Московский'),
(3, 'Ново-Савиновский'),
(3, 'Приволжский'),
(3, 'Советский');

-- Step 5: IRKUTSK - keep only 4 AO
DELETE FROM districts 
WHERE city_id = 4 
  AND id NOT IN (1262, 1263, 1264, 1265);

-- Step 6: NOVOSIBIRSK - 10 districts
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

-- Step 7: EKATERINBURG - 7 districts
DELETE FROM districts WHERE city_id = 7;
INSERT INTO districts (city_id, name) VALUES
(7, 'Верх-Исетский'),
(7, 'Железнодорожный'),
(7, 'Кировский'),
(7, 'Ленинский'),
(7, 'Октябрьский'),
(7, 'Орджоникидзевский'),
(7, 'Чкаловский');

-- Step 8: N.NOVGOROD - 8 districts
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

-- Step 9: CHELYABINSK - 7 districts
DELETE FROM districts WHERE city_id = 9;
INSERT INTO districts (city_id, name) VALUES
(9, 'Калининский'),
(9, 'Курчатовский'),
(9, 'Ленинский'),
(9, 'Металлургический'),
(9, 'Советский'),
(9, 'Тракторозаводский'),
(9, 'Центральный');

-- Step 10: KRASNOYARSK - 7 districts
DELETE FROM districts WHERE city_id = 10;
INSERT INTO districts (city_id, name) VALUES
(10, 'Железнодорожный'),
(10, 'Кировский'),
(10, 'Ленинский'),
(10, 'Октябрьский'),
(10, 'Свердловский'),
(10, 'Советский'),
(10, 'Центральный');

-- Step 11: SAMARA - 9 districts
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

-- Step 12: UFA - 7 districts
DELETE FROM districts WHERE city_id = 12;
INSERT INTO districts (city_id, name) VALUES
(12, 'Демский'),
(12, 'Калининский'),
(12, 'Кировский'),
(12, 'Ленинский'),
(12, 'Октябрьский'),
(12, 'Орджоникидзевский'),
(12, 'Советский');

-- Step 13: ROSTOV - 8 districts
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

-- Final verification
DO $$
DECLARE
    moscow_cnt INTEGER;
    spb_cnt INTEGER;
    irkutsk_cnt INTEGER;
    novosibirsk_cnt INTEGER;
    duplicate_city INTEGER;
BEGIN
    SELECT COUNT(*) INTO moscow_cnt FROM districts WHERE city_id = 1;
    SELECT COUNT(*) INTO spb_cnt FROM districts WHERE city_id = 2;
    SELECT COUNT(*) INTO irkutsk_cnt FROM districts WHERE city_id = 4;
    SELECT COUNT(*) INTO novosibirsk_cnt FROM districts WHERE city_id = 6;
    SELECT COUNT(*) INTO duplicate_city FROM cities WHERE id = 5;
    
    RAISE NOTICE 'Moscow: % (expected 12)', moscow_cnt;
    RAISE NOTICE 'SPB: % (expected 18)', spb_cnt;
    RAISE NOTICE 'Irkutsk: % (expected 4)', irkutsk_cnt;
    RAISE NOTICE 'Novosibirsk: % (expected 10)', novosibirsk_cnt;
    RAISE NOTICE 'Duplicate city: % (expected 0)', duplicate_city;
    
    IF moscow_cnt != 12 OR spb_cnt != 18 OR irkutsk_cnt != 4 
       OR novosibirsk_cnt != 10 OR duplicate_city != 0 THEN
        RAISE EXCEPTION 'Verification failed!';
    END IF;
    
    RAISE NOTICE 'SUCCESS: Migration completed!';
END $$;

-- Show final stats
SELECT 
    c.id,
    c.name,
    COUNT(d.id) AS districts_count
FROM cities c
LEFT JOIN districts d ON d.city_id = c.id
GROUP BY c.id, c.name
ORDER BY COUNT(d.id) DESC, c.name;

COMMIT;
