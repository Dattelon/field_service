BEGIN;

DELETE FROM districts WHERE id IN (1714, 1718, 1719);
DELETE FROM districts WHERE city_id = 1;

INSERT INTO districts (city_id, name) VALUES (1, 'ЦАО');
INSERT INTO districts (city_id, name) VALUES (1, 'САО');
INSERT INTO districts (city_id, name) VALUES (1, 'СВАО');
INSERT INTO districts (city_id, name) VALUES (1, 'ВАО');
INSERT INTO districts (city_id, name) VALUES (1, 'ЮВАО');
INSERT INTO districts (city_id, name) VALUES (1, 'ЮАО');
INSERT INTO districts (city_id, name) VALUES (1, 'ЮЗАО');
INSERT INTO districts (city_id, name) VALUES (1, 'ЗАО');
INSERT INTO districts (city_id, name) VALUES (1, 'СЗАО');
INSERT INTO districts (city_id, name) VALUES (1, 'ЗелАО');
INSERT INTO districts (city_id, name) VALUES (1, 'НАО');
INSERT INTO districts (city_id, name) VALUES (1, 'ТАО');

DELETE FROM orders WHERE city_id = 5;
DELETE FROM masters WHERE city_id = 5;
DELETE FROM districts WHERE city_id = 5;
DELETE FROM cities WHERE id = 5;

DELETE FROM districts WHERE city_id = 2;
INSERT INTO districts (city_id, name) VALUES (2, 'Адмиралтейский');
INSERT INTO districts (city_id, name) VALUES (2, 'Василеостровский');
INSERT INTO districts (city_id, name) VALUES (2, 'Выборгский');
INSERT INTO districts (city_id, name) VALUES (2, 'Калининский');
INSERT INTO districts (city_id, name) VALUES (2, 'Кировский');
INSERT INTO districts (city_id, name) VALUES (2, 'Колпинский');
INSERT INTO districts (city_id, name) VALUES (2, 'Красногвардейский');
INSERT INTO districts (city_id, name) VALUES (2, 'Красносельский');
INSERT INTO districts (city_id, name) VALUES (2, 'Кронштадтский');
INSERT INTO districts (city_id, name) VALUES (2, 'Курортный');
INSERT INTO districts (city_id, name) VALUES (2, 'Московский');
INSERT INTO districts (city_id, name) VALUES (2, 'Невский');
INSERT INTO districts (city_id, name) VALUES (2, 'Петроградский');
INSERT INTO districts (city_id, name) VALUES (2, 'Петродворцовый');
INSERT INTO districts (city_id, name) VALUES (2, 'Приморский');
INSERT INTO districts (city_id, name) VALUES (2, 'Пушкинский');
INSERT INTO districts (city_id, name) VALUES (2, 'Фрунзенский');
INSERT INTO districts (city_id, name) VALUES (2, 'Центральный');

DELETE FROM districts WHERE city_id = 3;
INSERT INTO districts (city_id, name) VALUES (3, 'Авиастроительный');
INSERT INTO districts (city_id, name) VALUES (3, 'Вахитовский');
INSERT INTO districts (city_id, name) VALUES (3, 'Кировский');
INSERT INTO districts (city_id, name) VALUES (3, 'Московский');
INSERT INTO districts (city_id, name) VALUES (3, 'Ново-Савиновский');
INSERT INTO districts (city_id, name) VALUES (3, 'Приволжский');
INSERT INTO districts (city_id, name) VALUES (3, 'Советский');

DELETE FROM districts WHERE city_id = 4 AND id NOT IN (1262, 1263, 1264, 1265);

DELETE FROM districts WHERE city_id = 6;
INSERT INTO districts (city_id, name) VALUES (6, 'Центральный');
INSERT INTO districts (city_id, name) VALUES (6, 'Железнодорожный');
INSERT INTO districts (city_id, name) VALUES (6, 'Заельцовский');
INSERT INTO districts (city_id, name) VALUES (6, 'Дзержинский');
INSERT INTO districts (city_id, name) VALUES (6, 'Калининский');
INSERT INTO districts (city_id, name) VALUES (6, 'Кировский');
INSERT INTO districts (city_id, name) VALUES (6, 'Ленинский');
INSERT INTO districts (city_id, name) VALUES (6, 'Октябрьский');
INSERT INTO districts (city_id, name) VALUES (6, 'Первомайский');
INSERT INTO districts (city_id, name) VALUES (6, 'Советский');

DELETE FROM districts WHERE city_id = 7;
INSERT INTO districts (city_id, name) VALUES (7, 'Верх-Исетский');
INSERT INTO districts (city_id, name) VALUES (7, 'Железнодорожный');
INSERT INTO districts (city_id, name) VALUES (7, 'Кировский');
INSERT INTO districts (city_id, name) VALUES (7, 'Ленинский');
INSERT INTO districts (city_id, name) VALUES (7, 'Октябрьский');
INSERT INTO districts (city_id, name) VALUES (7, 'Орджоникидзевский');
INSERT INTO districts (city_id, name) VALUES (7, 'Чкаловский');

DELETE FROM districts WHERE city_id = 8;
INSERT INTO districts (city_id, name) VALUES (8, 'Автозаводский');
INSERT INTO districts (city_id, name) VALUES (8, 'Канавинский');
INSERT INTO districts (city_id, name) VALUES (8, 'Ленинский');
INSERT INTO districts (city_id, name) VALUES (8, 'Московский');
INSERT INTO districts (city_id, name) VALUES (8, 'Нижегородский');
INSERT INTO districts (city_id, name) VALUES (8, 'Приокский');
INSERT INTO districts (city_id, name) VALUES (8, 'Советский');
INSERT INTO districts (city_id, name) VALUES (8, 'Сормовский');

DELETE FROM districts WHERE city_id = 9;
INSERT INTO districts (city_id, name) VALUES (9, 'Калининский');
INSERT INTO districts (city_id, name) VALUES (9, 'Курчатовский');
INSERT INTO districts (city_id, name) VALUES (9, 'Ленинский');
INSERT INTO districts (city_id, name) VALUES (9, 'Металлургический');
INSERT INTO districts (city_id, name) VALUES (9, 'Советский');
INSERT INTO districts (city_id, name) VALUES (9, 'Тракторозаводский');
INSERT INTO districts (city_id, name) VALUES (9, 'Центральный');

DELETE FROM districts WHERE city_id = 10;
INSERT INTO districts (city_id, name) VALUES (10, 'Железнодорожный');
INSERT INTO districts (city_id, name) VALUES (10, 'Кировский');
INSERT INTO districts (city_id, name) VALUES (10, 'Ленинский');
INSERT INTO districts (city_id, name) VALUES (10, 'Октябрьский');
INSERT INTO districts (city_id, name) VALUES (10, 'Свердловский');
INSERT INTO districts (city_id, name) VALUES (10, 'Советский');
INSERT INTO districts (city_id, name) VALUES (10, 'Центральный');

DELETE FROM districts WHERE city_id = 11;
INSERT INTO districts (city_id, name) VALUES (11, 'Железнодорожный');
INSERT INTO districts (city_id, name) VALUES (11, 'Кировский');
INSERT INTO districts (city_id, name) VALUES (11, 'Красноглинский');
INSERT INTO districts (city_id, name) VALUES (11, 'Куйбышевский');
INSERT INTO districts (city_id, name) VALUES (11, 'Ленинский');
INSERT INTO districts (city_id, name) VALUES (11, 'Октябрьский');
INSERT INTO districts (city_id, name) VALUES (11, 'Промышленный');
INSERT INTO districts (city_id, name) VALUES (11, 'Самарский');
INSERT INTO districts (city_id, name) VALUES (11, 'Советский');

DELETE FROM districts WHERE city_id = 12;
INSERT INTO districts (city_id, name) VALUES (12, 'Демский');
INSERT INTO districts (city_id, name) VALUES (12, 'Калининский');
INSERT INTO districts (city_id, name) VALUES (12, 'Кировский');
INSERT INTO districts (city_id, name) VALUES (12, 'Ленинский');
INSERT INTO districts (city_id, name) VALUES (12, 'Октябрьский');
INSERT INTO districts (city_id, name) VALUES (12, 'Орджоникидзевский');
INSERT INTO districts (city_id, name) VALUES (12, 'Советский');

DELETE FROM districts WHERE city_id = 13;
INSERT INTO districts (city_id, name) VALUES (13, 'Ворошиловский');
INSERT INTO districts (city_id, name) VALUES (13, 'Железнодорожный');
INSERT INTO districts (city_id, name) VALUES (13, 'Кировский');
INSERT INTO districts (city_id, name) VALUES (13, 'Ленинский');
INSERT INTO districts (city_id, name) VALUES (13, 'Октябрьский');
INSERT INTO districts (city_id, name) VALUES (13, 'Первомайский');
INSERT INTO districts (city_id, name) VALUES (13, 'Пролетарский');
INSERT INTO districts (city_id, name) VALUES (13, 'Советский');

SELECT c.id, c.name, COUNT(d.id) AS cnt
FROM cities c LEFT JOIN districts d ON d.city_id=c.id
WHERE c.id IN (1,2,3,4,6,7,8,9,10,11,12,13)
GROUP BY c.id, c.name ORDER BY c.id;

COMMIT;
