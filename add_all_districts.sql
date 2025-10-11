-- ==================================================
-- DISTRICTS FOR ALL 79 CITIES
-- Field Service Project
-- ==================================================
-- Usage: 
-- docker exec -i field-service-postgres-1 psql -U fs_user -d field_service < add_all_districts.sql
--
-- NOTE: This script uses city IDs from the database.
-- Run SELECT id, name FROM cities ORDER BY id; to verify IDs first.
-- ==================================================

BEGIN;

-- Москва (ID=1): 12 административных округов
DELETE FROM districts WHERE city_id = 1;
INSERT INTO districts (city_id, name) VALUES 
(1, 'ЦАО'), (1, 'САО'), (1, 'СВАО'), (1, 'ВАО'), 
(1, 'ЮВАО'), (1, 'ЮАО'), (1, 'ЮЗАО'), (1, 'ЗАО'), 
(1, 'СЗАО'), (1, 'ЗелАО'), (1, 'НАО'), (1, 'ТАО');

-- Санкт-Петербург (ID=2): 18 районов
DELETE FROM districts WHERE city_id = 2;
INSERT INTO districts (city_id, name) VALUES 
(2, 'Адмиралтейский'), (2, 'Василеостровский'), (2, 'Выборгский'), 
(2, 'Калининский'), (2, 'Кировский'), (2, 'Колпинский'), 
(2, 'Красногвардейский'), (2, 'Красносельский'), (2, 'Кронштадтский'), 
(2, 'Курортный'), (2, 'Московский'), (2, 'Невский'), 
(2, 'Петроградский'), (2, 'Петродворцовый'), (2, 'Приморский'), 
(2, 'Пушкинский'), (2, 'Фрунзенский'), (2, 'Центральный');

-- Новосибирск (ID=3): 10 районов
DELETE FROM districts WHERE city_id = 3;
INSERT INTO districts (city_id, name) VALUES 
(3, 'Центральный'), (3, 'Железнодорожный'), (3, 'Заельцовский'), 
(3, 'Дзержинский'), (3, 'Калининский'), (3, 'Кировский'), 
(3, 'Ленинский'), (3, 'Октябрьский'), (3, 'Первомайский'), 
(3, 'Советский');

-- Екатеринбург (ID=4): 7 районов
DELETE FROM districts WHERE city_id = 4;
INSERT INTO districts (city_id, name) VALUES 
(4, 'Верх-Исетский'), (4, 'Железнодорожный'), (4, 'Кировский'), 
(4, 'Ленинский'), (4, 'Октябрьский'), (4, 'Орджоникидзевский'), 
(4, 'Чкаловский');

-- Казань (ID=5): 7 районов
DELETE FROM districts WHERE city_id = 5;
INSERT INTO districts (city_id, name) VALUES 
(5, 'Авиастроительный'), (5, 'Вахитовский'), (5, 'Кировский'), 
(5, 'Московский'), (5, 'Ново-Савиновский'), (5, 'Приволжский'), 
(5, 'Советский');

-- Нижний Новгород (ID=6): 8 районов
DELETE FROM districts WHERE city_id = 6;
INSERT INTO districts (city_id, name) VALUES 
(6, 'Автозаводский'), (6, 'Канавинский'), (6, 'Ленинский'), 
(6, 'Московский'), (6, 'Нижегородский'), (6, 'Приокский'), 
(6, 'Советский'), (6, 'Сормовский');

-- Челябинск (ID=7): 7 районов
DELETE FROM districts WHERE city_id = 7;
INSERT INTO districts (city_id, name) VALUES 
(7, 'Калининский'), (7, 'Курчатовский'), (7, 'Ленинский'), 
(7, 'Металлургический'), (7, 'Советский'), (7, 'Тракторозаводский'), 
(7, 'Центральный');

-- Красноярск (ID=8): 7 районов
DELETE FROM districts WHERE city_id = 8;
INSERT INTO districts (city_id, name) VALUES 
(8, 'Железнодорожный'), (8, 'Кировский'), (8, 'Ленинский'), 
(8, 'Октябрьский'), (8, 'Свердловский'), (8, 'Советский'), 
(8, 'Центральный');

-- Самара (ID=9): 9 районов
DELETE FROM districts WHERE city_id = 9;
INSERT INTO districts (city_id, name) VALUES 
(9, 'Железнодорожный'), (9, 'Кировский'), (9, 'Красноглинский'), 
(9, 'Куйбышевский'), (9, 'Ленинский'), (9, 'Октябрьский'), 
(9, 'Промышленный'), (9, 'Самарский'), (9, 'Советский');

-- Уфа (ID=10): 7 районов
DELETE FROM districts WHERE city_id = 10;
INSERT INTO districts (city_id, name) VALUES 
(10, 'Демский'), (10, 'Калининский'), (10, 'Кировский'), 
(10, 'Ленинский'), (10, 'Октябрьский'), (10, 'Орджоникидзевский'), 
(10, 'Советский');

-- Ростов-на-Дону (ID=11): 8 районов
DELETE FROM districts WHERE city_id = 11;
INSERT INTO districts (city_id, name) VALUES 
(11, 'Ворошиловский'), (11, 'Железнодорожный'), (11, 'Кировский'), 
(11, 'Ленинский'), (11, 'Октябрьский'), (11, 'Первомайский'), 
(11, 'Пролетарский'), (11, 'Советский');

-- Краснодар (ID=12): 4 округа
DELETE FROM districts WHERE city_id = 12;
INSERT INTO districts (city_id, name) VALUES 
(12, 'Западный округ'), (12, 'Карасунский округ'), 
(12, 'Прикубанский округ'), (12, 'Центральный округ');

-- Омск (ID=13): 5 округов
DELETE FROM districts WHERE city_id = 13;
INSERT INTO districts (city_id, name) VALUES 
(13, 'Центральный'), (13, 'Советский'), (13, 'Кировский'), 
(13, 'Ленинский'), (13, 'Октябрьский');

-- Воронеж (ID=14): 6 районов
DELETE FROM districts WHERE city_id = 14;
INSERT INTO districts (city_id, name) VALUES 
(14, 'Железнодорожный'), (14, 'Коминтерновский'), (14, 'Левобережный'), 
(14, 'Ленинский'), (14, 'Советский'), (14, 'Центральный');

-- Пермь (ID=15): 7 районов
DELETE FROM districts WHERE city_id = 15;
INSERT INTO districts (city_id, name) VALUES 
(15, 'Дзержинский'), (15, 'Индустриальный'), (15, 'Кировский'), 
(15, 'Ленинский'), (15, 'Мотовилихинский'), (15, 'Орджоникидзевский'), 
(15, 'Свердловский');

-- Волгоград (ID=16): 8 районов
DELETE FROM districts WHERE city_id = 16;
INSERT INTO districts (city_id, name) VALUES 
(16, 'Тракторозаводский'), (16, 'Краснооктябрьский'), (16, 'Дзержинский'), 
(16, 'Центральный'), (16, 'Ворошиловский'), (16, 'Советский'), 
(16, 'Кировский'), (16, 'Красноармейский');

-- Саратов (ID=17): 6 районов
DELETE FROM districts WHERE city_id = 17;
INSERT INTO districts (city_id, name) VALUES 
(17, 'Волжский'), (17, 'Заводской'), (17, 'Кировский'), 
(17, 'Ленинский'), (17, 'Октябрьский'), (17, 'Фрунзенский');

-- Тюмень (ID=18): 4 округа
DELETE FROM districts WHERE city_id = 18;
INSERT INTO districts (city_id, name) VALUES 
(18, 'Калининский'), (18, 'Ленинский'), 
(18, 'Центральный'), (18, 'Восточный');

-- Тольятти (ID=19): 3 района
DELETE FROM districts WHERE city_id = 19;
INSERT INTO districts (city_id, name) VALUES 
(19, 'Автозаводский'), (19, 'Комсомольский'), (19, 'Центральный');

-- Ижевск (ID=20): 5 районов
DELETE FROM districts WHERE city_id = 20;
INSERT INTO districts (city_id, name) VALUES 
(20, 'Индустриальный'), (20, 'Ленинский'), (20, 'Октябрьский'), 
(20, 'Первомайский'), (20, 'Устиновский');

-- Барнаул (ID=21): 5 районов
DELETE FROM districts WHERE city_id = 21;
INSERT INTO districts (city_id, name) VALUES 
(21, 'Железнодорожный'), (21, 'Индустриальный'), (21, 'Ленинский'), 
(21, 'Октябрьский'), (21, 'Центральный');

-- Ульяновск (ID=22): 4 района
DELETE FROM districts WHERE city_id = 22;
INSERT INTO districts (city_id, name) VALUES 
(22, 'Засвияжский'), (22, 'Заволжский'), 
(22, 'Железнодорожный'), (22, 'Ленинский');

-- Иркутск (ID=23): 4 округа
DELETE FROM districts WHERE city_id = 23;
INSERT INTO districts (city_id, name) VALUES 
(23, 'Куйбышевский'), (23, 'Ленинский'), 
(23, 'Октябрьский'), (23, 'Свердловский');

-- Хабаровск (ID=24): 4 района
DELETE FROM districts WHERE city_id = 24;
INSERT INTO districts (city_id, name) VALUES 
(24, 'Железнодорожный'), (24, 'Индустриальный'), 
(24, 'Кировский'), (24, 'Центральный');

-- Владивосток (ID=25): 5 районов
DELETE FROM districts WHERE city_id = 25;
INSERT INTO districts (city_id, name) VALUES 
(25, 'Ленинский'), (25, 'Первомайский'), (25, 'Первореченский'), 
(25, 'Советский'), (25, 'Фрунзенский');

-- Ярославль (ID=26): 6 районов
DELETE FROM districts WHERE city_id = 26;
INSERT INTO districts (city_id, name) VALUES 
(26, 'Дзержинский'), (26, 'Заволжский'), (26, 'Кировский'), 
(26, 'Красноперекопский'), (26, 'Ленинский'), (26, 'Фрунзенский');

-- Махачкала (ID=27): 3 района
DELETE FROM districts WHERE city_id = 27;
INSERT INTO districts (city_id, name) VALUES 
(27, 'Кировский'), (27, 'Ленинский'), (27, 'Советский');

-- Томск (ID=28): 4 района
DELETE FROM districts WHERE city_id = 28;
INSERT INTO districts (city_id, name) VALUES 
(28, 'Кировский'), (28, 'Ленинский'), 
(28, 'Октябрьский'), (28, 'Советский');

-- Оренбург (ID=29): 4 района
DELETE FROM districts WHERE city_id = 29;
INSERT INTO districts (city_id, name) VALUES 
(29, 'Дзержинский'), (29, 'Ленинский'), 
(29, 'Промышленный'), (29, 'Центральный');

-- Кемерово (ID=30): 5 районов
DELETE FROM districts WHERE city_id = 30;
INSERT INTO districts (city_id, name) VALUES 
(30, 'Заводский'), (30, 'Кировский'), (30, 'Ленинский'), 
(30, 'Рудничный'), (30, 'Центральный');

-- Новокузнецк (ID=31): 3 района
DELETE FROM districts WHERE city_id = 31;
INSERT INTO districts (city_id, name) VALUES 
(31, 'Заводский'), (31, 'Куйбышевский'), (31, 'Центральный');

-- Рязань (ID=32): 4 округа
DELETE FROM districts WHERE city_id = 32;
INSERT INTO districts (city_id, name) VALUES 
(32, 'Железнодорожный'), (32, 'Московский'), 
(32, 'Октябрьский'), (32, 'Советский');

-- Набережные Челны (ID=33): 3 района
DELETE FROM districts WHERE city_id = 33;
INSERT INTO districts (city_id, name) VALUES 
(33, 'Автозаводский'), (33, 'Комсомольский'), (33, 'Центральный');

-- Астрахань (ID=34): 4 района
DELETE FROM districts WHERE city_id = 34;
INSERT INTO districts (city_id, name) VALUES 
(34, 'Кировский'), (34, 'Ленинский'), 
(34, 'Советский'), (34, 'Трусовский');

-- Пенза (ID=35): 4 района
DELETE FROM districts WHERE city_id = 35;
INSERT INTO districts (city_id, name) VALUES 
(35, 'Железнодорожный'), (35, 'Ленинский'), 
(35, 'Октябрьский'), (35, 'Первомайский');

-- Киров (ID=36): 4 района
DELETE FROM districts WHERE city_id = 36;
INSERT INTO districts (city_id, name) VALUES 
(36, 'Ленинский'), (36, 'Нововятский'), 
(36, 'Октябрьский'), (36, 'Первомайский');

-- Липецк (ID=37): 4 округа
DELETE FROM districts WHERE city_id = 37;
INSERT INTO districts (city_id, name) VALUES 
(37, 'Левобережный'), (37, 'Октябрьский'), 
(37, 'Правобережный'), (37, 'Советский');

-- Чебоксары (ID=38): 3 района
DELETE FROM districts WHERE city_id = 38;
INSERT INTO districts (city_id, name) VALUES 
(38, 'Калининский'), (38, 'Ленинский'), (38, 'Московский');

-- Калининград (ID=39): 3 района
DELETE FROM districts WHERE city_id = 39;
INSERT INTO districts (city_id, name) VALUES 
(39, 'Ленинградский'), (39, 'Московский'), (39, 'Центральный');

-- Тула (ID=40): 5 районов
DELETE FROM districts WHERE city_id = 40;
INSERT INTO districts (city_id, name) VALUES 
(40, 'Зареченский'), (40, 'Привокзальный'), (40, 'Пролетарский'), 
(40, 'Советский'), (40, 'Центральный');

-- Курск (ID=41): 3 округа
DELETE FROM districts WHERE city_id = 41;
INSERT INTO districts (city_id, name) VALUES 
(41, 'Железнодорожный'), (41, 'Сеймский'), (41, 'Центральный');

-- Сочи (ID=42): 4 района
DELETE FROM districts WHERE city_id = 42;
INSERT INTO districts (city_id, name) VALUES 
(42, 'Адлерский'), (42, 'Лазаревский'), 
(42, 'Хостинский'), (42, 'Центральный');

-- Ставрополь (ID=43): 3 района
DELETE FROM districts WHERE city_id = 43;
INSERT INTO districts (city_id, name) VALUES 
(43, 'Ленинский'), (43, 'Октябрьский'), (43, 'Промышленный');

-- Балашиха (МО) (ID=44): Город целиком
DELETE FROM districts WHERE city_id = 44;
INSERT INTO districts (city_id, name) VALUES (44, 'Город целиком');

-- Севастополь (ID=45): 4 района
DELETE FROM districts WHERE city_id = 45;
INSERT INTO districts (city_id, name) VALUES 
(45, 'Балаклавский'), (45, 'Гагаринский'), 
(45, 'Ленинский'), (45, 'Нахимовский');

-- Брянск (ID=46): 4 района
DELETE FROM districts WHERE city_id = 46;
INSERT INTO districts (city_id, name) VALUES 
(46, 'Бежицкий'), (46, 'Володарский'), 
(46, 'Советский'), (46, 'Фокинский');

-- Белгород (ID=47): 2 округа
DELETE FROM districts WHERE city_id = 47;
INSERT INTO districts (city_id, name) VALUES 
(47, 'Восточный'), (47, 'Западный');

-- Магнитогорск (ID=48): 3 района
DELETE FROM districts WHERE city_id = 48;
INSERT INTO districts (city_id, name) VALUES 
(48, 'Ленинский'), (48, 'Орджоникидзевский'), (48, 'Правобережный');

-- Великий Новгород (ID=49): Город целиком
DELETE FROM districts WHERE city_id = 49;
INSERT INTO districts (city_id, name) VALUES (49, 'Город целиком');

-- Калуга (ID=50): 3 района
DELETE FROM districts WHERE city_id = 50;
INSERT INTO districts (city_id, name) VALUES 
(50, 'Ленинский'), (50, 'Московский'), (50, 'Октябрьский');

-- Сургут (ID=51): 5 районов
DELETE FROM districts WHERE city_id = 51;
INSERT INTO districts (city_id, name) VALUES 
(51, 'Восточный'), (51, 'Западный'), (51, 'Северный жилой'), 
(51, 'Северный промышленный'), (51, 'Центральный');

-- Владикавказ (ID=52): 4 района
DELETE FROM districts WHERE city_id = 52;
INSERT INTO districts (city_id, name) VALUES 
(52, 'Затеречный'), (52, 'Иристонский'), 
(52, 'Промышленный'), (52, 'Северо-Западный');

-- Чита (ID=53): 4 района
DELETE FROM districts WHERE city_id = 53;
INSERT INTO districts (city_id, name) VALUES 
(53, 'Железнодорожный'), (53, 'Ингодинский'), 
(53, 'Центральный'), (53, 'Черновский');

-- Симферополь (ID=54): 3 района
DELETE FROM districts WHERE city_id = 54;
INSERT INTO districts (city_id, name) VALUES 
(54, 'Железнодорожный'), (54, 'Киевский'), (54, 'Центральный');

-- Волжский (ID=55): Город целиком
DELETE FROM districts WHERE city_id = 55;
INSERT INTO districts (city_id, name) VALUES (55, 'Город целиком');

-- Смоленск (ID=56): 3 района
DELETE FROM districts WHERE city_id = 56;
INSERT INTO districts (city_id, name) VALUES 
(56, 'Заднепровский'), (56, 'Ленинский'), (56, 'Промышленный');

-- Саранск (ID=57): Город целиком
DELETE FROM districts WHERE city_id = 57;
INSERT INTO districts (city_id, name) VALUES (57, 'Город целиком');

-- Курган (ID=58): Город целиком
DELETE FROM districts WHERE city_id = 58;
INSERT INTO districts (city_id, name) VALUES (58, 'Город целиком');

-- Орёл (ID=59): Город целиком
DELETE FROM districts WHERE city_id = 59;
INSERT INTO districts (city_id, name) VALUES (59, 'Город целиком');

-- Подольск (МО) (ID=60): Город целиком
DELETE FROM districts WHERE city_id = 60;
INSERT INTO districts (city_id, name) VALUES (60, 'Город целиком');

-- Архангельск (ID=61): 9 округов
DELETE FROM districts WHERE city_id = 61;
INSERT INTO districts (city_id, name) VALUES 
(61, 'Варавино-Фактория'), (61, 'Исакогорский'), (61, 'Ломоносовский'), 
(61, 'Майская горка'), (61, 'Маймаксанский'), (61, 'Октябрьский'), 
(61, 'Северный'), (61, 'Соломбальский'), (61, 'Цигломенский');

-- Грозный (ID=62): 4 района (с 2020)
DELETE FROM districts WHERE city_id = 62;
INSERT INTO districts (city_id, name) VALUES 
(62, 'Ахматовский'), (62, 'Байсангуровский'), 
(62, 'Висаитовский'), (62, 'Шейх-Мансуровский');

-- Якутск (ID=63): 8 округов
DELETE FROM districts WHERE city_id = 63;
INSERT INTO districts (city_id, name) VALUES 
(63, 'Автодорожный'), (63, 'Гагаринский'), (63, 'Губинский'), 
(63, 'Октябрьский'), (63, 'Промышленный'), (63, 'Сайсарский'), 
(63, 'Строительный'), (63, 'Центральный');

-- Тверь (ID=64): 4 района
DELETE FROM districts WHERE city_id = 64;
INSERT INTO districts (city_id, name) VALUES 
(64, 'Заволжский'), (64, 'Московский'), 
(64, 'Пролетарский'), (64, 'Центральный');

-- Старый Оскол (ID=65): Город целиком
DELETE FROM districts WHERE city_id = 65;
INSERT INTO districts (city_id, name) VALUES (65, 'Город целиком');

-- Улан-Удэ (ID=66): 3 района
DELETE FROM districts WHERE city_id = 66;
INSERT INTO districts (city_id, name) VALUES 
(66, 'Железнодорожный'), (66, 'Октябрьский'), (66, 'Советский');

-- Нижний Тагил (ID=67): 3 района
DELETE FROM districts WHERE city_id = 67;
INSERT INTO districts (city_id, name) VALUES 
(67, 'Дзержинский'), (67, 'Ленинский'), (67, 'Тагилстроевский');

-- Нижневартовск (ID=68): Город целиком
DELETE FROM districts WHERE city_id = 68;
INSERT INTO districts (city_id, name) VALUES (68, 'Город целиком');

-- Псков (ID=69): Город целиком
DELETE FROM districts WHERE city_id = 69;
INSERT INTO districts (city_id, name) VALUES (69, 'Город целиком');

-- Йошкар-Ола (ID=70): Город целиком
DELETE FROM districts WHERE city_id = 70;
INSERT INTO districts (city_id, name) VALUES (70, 'Город целиком');

-- Кострома (ID=71): Город целиком
DELETE FROM districts WHERE city_id = 71;
INSERT INTO districts (city_id, name) VALUES (71, 'Город целиком');

-- Новороссийск (ID=72): Город целиком
DELETE FROM districts WHERE city_id = 72;
INSERT INTO districts (city_id, name) VALUES (72, 'Город целиком');

-- Дзержинск (ID=73): Город целиком
DELETE FROM districts WHERE city_id = 73;
INSERT INTO districts (city_id, name) VALUES (73, 'Город целиком');

-- Таганрог (ID=74): Город целиком
DELETE FROM districts WHERE city_id = 74;
INSERT INTO districts (city_id, name) VALUES (74, 'Город целиком');

-- Химки (МО) (ID=75): Город целиком
DELETE FROM districts WHERE city_id = 75;
INSERT INTO districts (city_id, name) VALUES (75, 'Город целиком');

-- Березники (ID=76): Город целиком
DELETE FROM districts WHERE city_id = 76;
INSERT INTO districts (city_id, name) VALUES (76, 'Город целиком');

-- Энгельс (ID=77): Город целиком
DELETE FROM districts WHERE city_id = 77;
INSERT INTO districts (city_id, name) VALUES (77, 'Город целиком');

-- Шахты (ID=78): Город целиком
DELETE FROM districts WHERE city_id = 78;
INSERT INTO districts (city_id, name) VALUES (78, 'Город целиком');

-- ==================================================
-- STATISTICS AND VERIFICATION
-- ==================================================

-- Show cities with district counts
SELECT 
    c.id,
    c.name,
    COUNT(d.id) as district_count
FROM cities c
LEFT JOIN districts d ON d.city_id = c.id
GROUP BY c.id, c.name
ORDER BY c.id;

-- Overall statistics
SELECT 
    (SELECT COUNT(*) FROM cities WHERE is_active = true) as total_cities,
    (SELECT COUNT(*) FROM districts) as total_districts,
    (SELECT COUNT(DISTINCT city_id) FROM districts) as cities_with_districts;

COMMIT;

-- ==================================================
-- END OF SCRIPT
-- ==================================================
