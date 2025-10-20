-- Вставка городов и районов для Field Service
-- Скрипт идемпотентный: можно запускать много раз

-- Удаление функций если они есть
DROP FUNCTION IF EXISTS ensure_city;
DROP FUNCTION IF EXISTS ensure_district;

-- Функция для создания города (если не существует)
CREATE OR REPLACE FUNCTION ensure_city(city_name TEXT, city_tz TEXT DEFAULT 'Europe/Moscow')
RETURNS INTEGER AS $$
DECLARE
    v_city_id INTEGER;
BEGIN
    SELECT id INTO v_city_id FROM cities WHERE name = city_name;
    IF v_city_id IS NULL THEN
        INSERT INTO cities (name, is_active, timezone, created_at)
        VALUES (city_name, TRUE, city_tz, NOW())
        RETURNING id INTO v_city_id;
    END IF;
    RETURN v_city_id;
END;
$$ LANGUAGE plpgsql;

-- Функция для создания района (если не существует)
CREATE OR REPLACE FUNCTION ensure_district(p_city_id INTEGER, district_name TEXT)
RETURNS VOID AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM districts WHERE city_id = p_city_id AND name = district_name) THEN
        INSERT INTO districts (city_id, name, created_at)
        VALUES (p_city_id, district_name, NOW());
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Топ-15 городов
DO $$
DECLARE
    v_city_id INTEGER;
BEGIN
    -- Москва
    v_city_id := ensure_city('Москва', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'ЦАО');
    PERFORM ensure_district(v_city_id, 'САО');
    PERFORM ensure_district(v_city_id, 'СВАО');
    PERFORM ensure_district(v_city_id, 'ВАО');
    PERFORM ensure_district(v_city_id, 'ЮВАО');
    PERFORM ensure_district(v_city_id, 'ЮАО');
    PERFORM ensure_district(v_city_id, 'ЮЗАО');
    PERFORM ensure_district(v_city_id, 'ЗАО');
    PERFORM ensure_district(v_city_id, 'СЗАО');
    PERFORM ensure_district(v_city_id, 'Зеленоград');
    PERFORM ensure_district(v_city_id, 'Новомосковский');
    PERFORM ensure_district(v_city_id, 'Троицкий');

    -- Санкт-Петербург
    v_city_id := ensure_city('Санкт-Петербург', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Адмиралтейский');
    PERFORM ensure_district(v_city_id, 'Василеостровский');
    PERFORM ensure_district(v_city_id, 'Выборгский');
    PERFORM ensure_district(v_city_id, 'Калининский');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Колпинский');
    PERFORM ensure_district(v_city_id, 'Красногвардейский');
    PERFORM ensure_district(v_city_id, 'Красносельский');
    PERFORM ensure_district(v_city_id, 'Кронштадтский');
    PERFORM ensure_district(v_city_id, 'Курортный');
    PERFORM ensure_district(v_city_id, 'Московский');
    PERFORM ensure_district(v_city_id, 'Невский');
    PERFORM ensure_district(v_city_id, 'Петроградский');
    PERFORM ensure_district(v_city_id, 'Петродворцовый');
    PERFORM ensure_district(v_city_id, 'Приморский');
    PERFORM ensure_district(v_city_id, 'Пушкинский');
    PERFORM ensure_district(v_city_id, 'Фрунзенский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Новосибирск
    v_city_id := ensure_city('Новосибирск', 'Asia/Novosibirsk');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Заельцовский');
    PERFORM ensure_district(v_city_id, 'Калининский');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Первомайский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Центральный');
    PERFORM ensure_district(v_city_id, 'Дзержинский');

    -- Екатеринбург
    v_city_id := ensure_city('Екатеринбург', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Верх-Исетский');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Орджоникидзевский');
    PERFORM ensure_district(v_city_id, 'Чкаловский');

    -- Казань
    v_city_id := ensure_city('Казань', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Авиастроительный');
    PERFORM ensure_district(v_city_id, 'Вахитовский');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Московский');
    PERFORM ensure_district(v_city_id, 'Ново-Савиновский');
    PERFORM ensure_district(v_city_id, 'Приволжский');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Нижний Новгород
    v_city_id := ensure_city('Нижний Новгород', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Автозаводский');
    PERFORM ensure_district(v_city_id, 'Канавинский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Московский');
    PERFORM ensure_district(v_city_id, 'Нижегородский');
    PERFORM ensure_district(v_city_id, 'Приокский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Сормовский');

    -- Челябинск
    v_city_id := ensure_city('Челябинск', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Калининский');
    PERFORM ensure_district(v_city_id, 'Курчатовский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Металлургический');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Тракторозаводский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Красноярск
    v_city_id := ensure_city('Красноярск', 'Asia/Krasnoyarsk');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Свердловский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Самара
    v_city_id := ensure_city('Самара', 'Europe/Samara');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Красноглинский');
    PERFORM ensure_district(v_city_id, 'Куйбышевский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Промышленный');
    PERFORM ensure_district(v_city_id, 'Самарский');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Уфа
    v_city_id := ensure_city('Уфа', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Демский');
    PERFORM ensure_district(v_city_id, 'Калининский');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Орджоникидзевский');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Ростов-на-Дону
    v_city_id := ensure_city('Ростов-на-Дону', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Ворошиловский');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Первомайский');
    PERFORM ensure_district(v_city_id, 'Пролетарский');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Краснодар
    v_city_id := ensure_city('Краснодар', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Карасунский');
    PERFORM ensure_district(v_city_id, 'Прикубанский');
    PERFORM ensure_district(v_city_id, 'Центральный');
    PERFORM ensure_district(v_city_id, 'Западный');

    -- Омск
    v_city_id := ensure_city('Омск', 'Asia/Omsk');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Воронеж
    v_city_id := ensure_city('Воронеж', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Коминтерновский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Левобережный');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Пермь
    v_city_id := ensure_city('Пермь', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Дзержинский');
    PERFORM ensure_district(v_city_id, 'Индустриальный');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Мотовилихинский');
    PERFORM ensure_district(v_city_id, 'Орджоникидзевский');
    PERFORM ensure_district(v_city_id, 'Свердловский');
END $$;
