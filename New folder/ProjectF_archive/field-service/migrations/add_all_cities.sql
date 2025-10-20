-- Добавление всех 78 городов из каталога cities.py
-- Дата: 2025-10-07
-- Безопасно использует ON CONFLICT для предотвращения дубликатов

BEGIN;

-- Добавление всех городов из каталога
INSERT INTO cities (name, is_active, timezone) VALUES 
-- Города с А
('Архангельск', true, 'Europe/Moscow'),
('Астрахань', true, 'Europe/Astrakhan'),
-- Города с Б
('Балашиха (МО)', true, 'Europe/Moscow'),
('Барнаул', true, 'Asia/Barnaul'),
('Белгород', true, 'Europe/Moscow'),
('Березники', true, 'Asia/Yekaterinburg'),
('Брянск', true, 'Europe/Moscow'),
-- Города с В
('Великий Новгород', true, 'Europe/Moscow'),
('Владивосток', true, 'Asia/Vladivostok'),
('Владикавказ', true, 'Europe/Moscow'),
('Волгоград', true, 'Europe/Volgograd'),
('Волжский', true, 'Europe/Volgograd'),
('Воронеж', true, 'Europe/Moscow'),
-- Города с Г
('Грозный', true, 'Europe/Moscow'),
-- Города с Д
('Дзержинск', true, 'Europe/Moscow'),
-- Города с Е
('Екатеринбург', true, 'Asia/Yekaterinburg'),
-- Города с И
('Ижевск', true, 'Europe/Samara'),
('Иркутск', true, 'Asia/Irkutsk'),
-- Города с Й
('Йошкар-Ола', true, 'Europe/Moscow'),
-- Города с К
('Казань', true, 'Europe/Moscow'),
('Калининград', true, 'Europe/Kaliningrad'),
('Калуга', true, 'Europe/Moscow'),
('Кемерово', true, 'Asia/Novokuznetsk'),
('Киров', true, 'Europe/Kirov'),
('Кострома', true, 'Europe/Moscow'),
('Краснодар', true, 'Europe/Moscow'),
('Красноярск', true, 'Asia/Krasnoyarsk'),
('Курган', true, 'Asia/Yekaterinburg'),
('Курск', true, 'Europe/Moscow'),
-- Города с Л
('Липецк', true, 'Europe/Moscow'),
-- Города с М
('Магнитогорск', true, 'Asia/Yekaterinburg'),
('Махачкала', true, 'Europe/Moscow'),
('Москва', true, 'Europe/Moscow'),
-- Города с Н
('Набережные Челны', true, 'Europe/Moscow'),
('Нижневартовск', true, 'Asia/Yekaterinburg'),
('Нижний Новгород', true, 'Europe/Moscow'),
('Нижний Тагил', true, 'Asia/Yekaterinburg'),
('Новокузнецк', true, 'Asia/Novokuznetsk'),
('Новороссийск', true, 'Europe/Moscow'),
('Новосибирск', true, 'Asia/Novosibirsk'),
-- Города с О
('Омск', true, 'Asia/Omsk'),
('Оренбург', true, 'Asia/Yekaterinburg'),
('Орёл', true, 'Europe/Moscow'),
-- Города с П
('Пенза', true, 'Europe/Moscow'),
('Пермь', true, 'Asia/Yekaterinburg'),
('Подольск (МО)', true, 'Europe/Moscow'),
('Псков', true, 'Europe/Moscow'),
-- Города с Р
('Ростов-на-Дону', true, 'Europe/Moscow'),
('Рязань', true, 'Europe/Moscow'),
-- Города с С
('Самара', true, 'Europe/Samara'),
('Санкт-Петербург', true, 'Europe/Moscow'),
('Саранск', true, 'Europe/Moscow'),
('Саратов', true, 'Europe/Saratov'),
('Севастополь', true, 'Europe/Simferopol'),
('Симферополь', true, 'Europe/Simferopol'),
('Смоленск', true, 'Europe/Moscow'),
('Сочи', true, 'Europe/Moscow'),
('Ставрополь', true, 'Europe/Moscow'),
('Старый Оскол', true, 'Europe/Moscow'),
('Сургут', true, 'Asia/Yekaterinburg'),
-- Города с Т
('Тверь', true, 'Europe/Moscow'),
('Тагадог', true, 'Europe/Moscow'),
('Тольятти', true, 'Europe/Samara'),
('Томск', true, 'Asia/Tomsk'),
('Тула', true, 'Europe/Moscow'),
('Тюмень', true, 'Asia/Yekaterinburg'),
-- Города с У
('Улан-Удэ', true, 'Asia/Irkutsk'),
('Ульяновск', true, 'Europe/Ulyanovsk'),
('Уфа', true, 'Asia/Yekaterinburg'),
-- Города с Х
('Хабаровск', true, 'Asia/Vladivostok'),
('Химки (МО)', true, 'Europe/Moscow'),
-- Города с Ч
('Чебоксары', true, 'Europe/Moscow'),
('Челябинск', true, 'Asia/Yekaterinburg'),
('Чита', true, 'Asia/Chita'),
-- Города с Ш
('Шахты', true, 'Europe/Moscow'),
-- Города с Э
('Энгельс', true, 'Europe/Saratov'),
-- Города с Я
('Якутск', true, 'Asia/Yakutsk'),
('Ярославль', true, 'Europe/Moscow')
ON CONFLICT (name) DO UPDATE SET 
    is_active = EXCLUDED.is_active,
    timezone = EXCLUDED.timezone;

COMMIT;
