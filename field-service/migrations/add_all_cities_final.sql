-- =====================================================
-- СКРИПТ 1: Добавление всех 78 городов (финальная версия)
-- =====================================================
-- Выполнить: docker exec -i field-service-postgres-1 psql -U fs_user -d field_service -f /tmp/add_all_cities_final.sql

BEGIN;

-- Удаляем города с кракозябрами (если есть)
DELETE FROM cities WHERE name ~ '[^\x00-\x7F]' AND name !~ '[А-Яа-яЁё]';

-- Вставляем/обновляем все 78 городов (20 основных + 58 дополнительных)
INSERT INTO cities (name, is_active, timezone) VALUES 
('Москва', true, 'Europe/Moscow'),
('Санкт-Петербург', true, 'Europe/Moscow'),
('Новосибирск', true, 'Asia/Novosibirsk'),
('Екатеринбург', true, 'Asia/Yekaterinburg'),
('Казань', true, 'Europe/Moscow'),
('Нижний Новгород', true, 'Europe/Moscow'),
('Челябинск', true, 'Asia/Yekaterinburg'),
('Красноярск', true, 'Asia/Krasnoyarsk'),
('Самара', true, 'Europe/Samara'),
('Уфа', true, 'Asia/Yekaterinburg'),
('Ростов на Дону', true, 'Europe/Moscow'),
('Краснодар', true, 'Europe/Moscow'),
('Омск', true, 'Asia/Omsk'),
('Воронеж', true, 'Europe/Moscow'),
('Пермь', true, 'Asia/Yekaterinburg'),
('Волгоград', true, 'Europe/Volgograd'),
('Саратов', true, 'Europe/Saratov'),
('Тюмень', true, 'Asia/Yekaterinburg'),
('Тольятти', true, 'Europe/Samara'),
('Ижевск', true, 'Europe/Samara'),
('Барнаул', true, 'Asia/Barnaul'),
('Ульяновск', true, 'Europe/Ulyanovsk'),
('Иркутск', true, 'Asia/Irkutsk'),
('Хабаровск', true, 'Asia/Vladivostok'),
('Владивосток', true, 'Asia/Vladivostok'),
('Ярославль', true, 'Europe/Moscow'),
('Махачкала', true, 'Europe/Moscow'),
('Томск', true, 'Asia/Tomsk'),
('Оренбург', true, 'Asia/Yekaterinburg'),
('Кемерово', true, 'Asia/Novokuznetsk'),
('Новокузнецк', true, 'Asia/Novokuznetsk'),
('Рязань', true, 'Europe/Moscow'),
('Набережные Челны', true, 'Europe/Moscow'),
('Астрахань', true, 'Europe/Astrakhan'),
('Пенза', true, 'Europe/Moscow'),
('Киров', true, 'Europe/Kirov'),
('Липецк', true, 'Europe/Moscow'),
('Чебоксары', true, 'Europe/Moscow'),
('Калининград', true, 'Europe/Kaliningrad'),
('Тула', true, 'Europe/Moscow'),
('Курск', true, 'Europe/Moscow'),
('Сочи', true, 'Europe/Moscow'),
('Ставрополь', true, 'Europe/Moscow'),
('Балашиха (МО)', true, 'Europe/Moscow'),
('Севастополь', true, 'Europe/Simferopol'),
('Брянск', true, 'Europe/Moscow'),
('Белгород', true, 'Europe/Moscow'),
('Магнитогорск', true, 'Asia/Yekaterinburg'),
('Великий Новгород', true, 'Europe/Moscow'),
('Калуга', true, 'Europe/Moscow'),
('Сургут', true, 'Asia/Yekaterinburg'),
('Владикавказ', true, 'Europe/Moscow'),
('Чита', true, 'Asia/Chita'),
('Симферополь', true, 'Europe/Simferopol'),
('Волжский', true, 'Europe/Volgograd'),
('Смоленск', true, 'Europe/Moscow'),
('Саранск', true, 'Europe/Moscow'),
('Курган', true, 'Asia/Yekaterinburg'),
('Орёл', true, 'Europe/Moscow'),
('Подольск (МО)', true, 'Europe/Moscow'),
('Архангельск', true, 'Europe/Moscow'),
('Грозный', true, 'Europe/Moscow'),
('Якутск', true, 'Asia/Yakutsk'),
('Тверь', true, 'Europe/Moscow'),
('Старый Оскол', true, 'Europe/Moscow'),
('Улан Удэ', true, 'Asia/Irkutsk'),
('Нижний Тагил', true, 'Asia/Yekaterinburg'),
('Нижневартовск', true, 'Asia/Yekaterinburg'),
('Псков', true, 'Europe/Moscow'),
('Йошкар Ола', true, 'Europe/Moscow'),
('Кострома', true, 'Europe/Moscow'),
('Новороссийск', true, 'Europe/Moscow'),
('Дзержинск', true, 'Europe/Moscow'),
('Таганрог', true, 'Europe/Moscow'),
('Химки (МО)', true, 'Europe/Moscow'),
('Березники', true, 'Asia/Yekaterinburg'),
('Энгельс', true, 'Europe/Saratov'),
('Шахты', true, 'Europe/Moscow')
ON CONFLICT (name) DO UPDATE SET 
    is_active = EXCLUDED.is_active, 
    timezone = EXCLUDED.timezone,
    updated_at = NOW();

-- Проверка результата
SELECT COUNT(*) as total_cities FROM cities WHERE is_active = true;

COMMIT;

-- Вывод всех городов для проверки
SELECT name FROM cities WHERE is_active = true ORDER BY name;
