-- ============================================================================
-- Migration V5: Force delete corrupted rows
-- Date: 2025-10-04
-- ============================================================================

BEGIN;

-- CRITICAL: Delete corrupted Moscow rows by ID
DELETE FROM districts WHERE id IN (1714, 1718, 1719);

-- Verify they are gone
DO $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM districts WHERE id IN (1714, 1718, 1719);
    IF cnt != 0 THEN
        RAISE EXCEPTION 'Corrupted rows still exist: %', cnt;
    END IF;
    RAISE NOTICE 'Corrupted rows deleted successfully';
END $$;

-- Now delete remaining Moscow districts
DELETE FROM districts WHERE city_id = 1;

-- Verify Moscow is empty
DO $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM districts WHERE city_id = 1;
    IF cnt != 0 THEN
        RAISE EXCEPTION 'Moscow still has % districts!', cnt;
    END IF;
    RAISE NOTICE 'Moscow cleaned: 0 districts';
END $$;

-- Add 12 Moscow AO
INSERT INTO districts (city_id, name) VALUES
(1, 'ЦАО'), (1, 'САО'), (1, 'СВАО'), (1, 'ВАО'),
(1, 'ЮВАО'), (1, 'ЮАО'), (1, 'ЮЗАО'), (1, 'ЗАО'),
(1, 'СЗАО'), (1, 'ЗелАО'), (1, 'НАО'), (1, 'ТАО');

-- Verify Moscow has 12
DO $$
DECLARE
    cnt INTEGER;
BEGIN
    SELECT COUNT(*) INTO cnt FROM districts WHERE city_id = 1;
    RAISE NOTICE 'Moscow now has: % districts', cnt;
    IF cnt != 12 THEN
        RAISE EXCEPTION 'Moscow has % instead of 12!', cnt;
    END IF;
END $$;

-- Delete duplicate city
DELETE FROM orders WHERE city_id = 5;
DELETE FROM masters WHERE city_id = 5;
DELETE FROM districts WHERE city_id = 5;
DELETE FROM cities WHERE id = 5;

-- SPB: 18 districts
DELETE FROM districts WHERE city_id = 2;
INSERT INTO districts (city_id, name) VALUES
(2, 'Адмиралтейский'), (2, 'Василеостровский'), (2, 'Выборгский'),
(2, 'Калининский'), (2, 'Кировский'), (2, 'Колпинский'),
(2, 'Красногвардейский'), (2, 'Красносельский'), (2, 'Кронштадтский'),
(2, 'Курортный'), (2, 'Московский'), (2, 'Невский'),
(2, 'Петроградский'), (2, 'Петродворцовый'), (2, 'Приморский'),
(2, 'Пушкинский'), (2, 'Фрунзенский'), (2, 'Центральный');

-- KAZAN: 7 districts
DELETE FROM districts WHERE city_id = 3;
INSERT INTO districts (city_id, name) VALUES
(3, 'Авиастроительный'), (3, 'Вахитовский'), (3, 'Кировский'),
(3, 'Московский'), (3, 'Ново-Савиновский'), (3, 'Приволжский'), (3, 'Советский');

-- IRKUTSK: keep 4 AO
DELETE FROM districts WHERE city_id = 4 AND id NOT IN (1262, 1263, 1264, 1265);

-- NOVOSIBIRSK: 10 districts
DELETE FROM districts WHERE city_id = 6;
INSERT INTO districts (city_id, name) VALUES
(6, 'Центральный'), (6, 'Железнодорожный'), (6, 'Заельцовский'),
(6, 'Дзержинский'), (6, 'Калининский'), (6, 'Кировский'),
(6, 'Ленинский'), (6, 'Октябрьский'), (6, 'Первомайский'), (6, 'Советский');

-- EKATERINBURG: 7 districts
DELETE FROM districts WHERE city_id = 7;
INSERT INTO districts (city_id, name) VALUES
(7, 'Верх-Исетский'), (7, 'Железнодорожный'), (7, 'Кировский'),
(7, 'Ленинский'), (7, 'Октябрьский'), (7, 'Орджоникидзевский'), (7, 'Чкаловский');

-- N.NOVGOROD: 8 districts
DELETE FROM districts WHERE city_id = 8;
INSERT INTO districts (city_id, name) VALUES
(8, 'Автозаводский'), (8, 'Канавинский'), (8, 'Ленинский'), (8, 'Московский'),
(8, 'Нижегородский'), (8, 'Приокский'), (8, 'Советский'), (8, 'Сормовский');

-- CHELYABINSK: 7 districts
DELETE FROM districts WHERE city_id = 9;
INSERT INTO districts (city_id, name) VALUES
(9, 'Калининский'), (9, 'Курчатовский'), (9, 'Ленинский'), (9, 'Металлургический'),
(9, 'Советский'), (9, 'Тракторозаводский'), (9, 'Центральный');

-- KRASNOYARSK: 7 districts
DELETE FROM districts WHERE city_id = 10;
INSERT INTO districts (city_id, name) VALUES
(10, 'Железнодорожный'), (10, 'Кировский'), (10, 'Ленинский'), (10, 'Октябрьский'),
(10, 'Свердловский'), (10, 'Советский'), (10, 'Центральный');

-- SAMARA: 9 districts
DELETE FROM districts WHERE city_id = 11;
INSERT INTO districts (city_id, name) VALUES
(11, 'Железнодорожный'), (11, 'Кировский'), (11, 'Красноглинский'), (11, 'Куйбышевский'),
(11, 'Ленинский'), (11, 'Октябрьский'), (11, 'Промышленный'), (11, 'Самарский'), (11, 'Советский');

-- UFA: 7 districts
DELETE FROM districts WHERE city_id = 12;
INSERT INTO districts (city_id, name) VALUES
(12, 'Демский'), (12, 'Калининский'), (12, 'Кировский'), (12, 'Ленинский'),
(12, 'Октябрьский'), (12, 'Орджоникидзевский'), (12, 'Советский');

-- ROSTOV: 8 districts
DELETE FROM districts WHERE city_id = 13;
INSERT INTO districts (city_id, name) VALUES
(13, 'Ворошиловский'), (13, 'Железнодорожный'), (13, 'Кировский'), (13, 'Ленинский'),
(13, 'Октябрьский'), (13, 'Первомайский'), (13, 'Пролетарский'), (13, 'Советский');

-- FINAL CHECK
DO $$
DECLARE
    moscow INTEGER; spb INTEGER; irkutsk INTEGER; novosibirsk INTEGER; dup INTEGER;
BEGIN
    SELECT COUNT(*) INTO moscow FROM districts WHERE city_id = 1;
    SELECT COUNT(*) INTO spb FROM districts WHERE city_id = 2;
    SELECT COUNT(*) INTO irkutsk FROM districts WHERE city_id = 4;
    SELECT COUNT(*) INTO novosibirsk FROM districts WHERE city_id = 6;
    SELECT COUNT(*) INTO dup FROM cities WHERE id = 5;
    
    RAISE NOTICE '=== FINAL CHECK ===';
    RAISE NOTICE 'Moscow: % (OK=12)', moscow;
    RAISE NOTICE 'SPB: % (OK=18)', spb;
    RAISE NOTICE 'Irkutsk: % (OK=4)', irkutsk;
    RAISE NOTICE 'Novosibirsk: % (OK=10)', novosibirsk;
    RAISE NOTICE 'Duplicate city: % (OK=0)', dup;
    
    IF moscow=12 AND spb=18 AND irkutsk=4 AND novosibirsk=10 AND dup=0 THEN
        RAISE NOTICE 'SUCCESS!';
    ELSE
        RAISE EXCEPTION 'Check failed!';
    END IF;
END $$;

SELECT c.id, c.name, COUNT(d.id) AS cnt
FROM cities c LEFT JOIN districts d ON d.city_id=c.id
GROUP BY c.id, c.name ORDER BY cnt DESC, c.name;

COMMIT;
