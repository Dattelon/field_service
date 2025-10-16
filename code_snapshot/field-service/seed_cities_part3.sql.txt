-- Города 250k-500k
DO $$
DECLARE
    v_city_id INTEGER;
BEGIN
    -- Брянск
    v_city_id := ensure_city('Брянск', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Бежицкий');
    PERFORM ensure_district(v_city_id, 'Володарский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Фокинский');

    -- Белгород
    v_city_id := ensure_city('Белгород', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Восточный');
    PERFORM ensure_district(v_city_id, 'Западный');

    -- Магнитогорск
    v_city_id := ensure_city('Магнитогорск', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Орджоникидзевский');
    PERFORM ensure_district(v_city_id, 'Правобережный');

    -- Великий Новгород
    v_city_id := ensure_city('Великий Новгород', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Калуга
    v_city_id := ensure_city('Калуга', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Московский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');

    -- Сургут
    v_city_id := ensure_city('Сургут', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Владикавказ
    v_city_id := ensure_city('Владикавказ', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Иристонский');
    PERFORM ensure_district(v_city_id, 'Промышленный');
    PERFORM ensure_district(v_city_id, 'Затеречный');

    -- Чита
    v_city_id := ensure_city('Чита', 'Asia/Chita');
    PERFORM ensure_district(v_city_id, 'Ингодинский');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Центральный');
    PERFORM ensure_district(v_city_id, 'Черновский');

    -- Симферополь
    v_city_id := ensure_city('Симферополь', 'Europe/Simferopol');
    PERFORM ensure_district(v_city_id, 'Киевский');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Волжский
    v_city_id := ensure_city('Волжский', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Смоленск
    v_city_id := ensure_city('Смоленск', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Заднепровский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Промышленный');

    -- Саранск
    v_city_id := ensure_city('Саранск', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Пролетарский');

    -- Курган
    v_city_id := ensure_city('Курган', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Орёл
    v_city_id := ensure_city('Орёл', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Заводской');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Северный');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Подольск
    v_city_id := ensure_city('Подольск', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Архангельск
    v_city_id := ensure_city('Архангельск', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Ломоносовский');
    PERFORM ensure_district(v_city_id, 'Маймаксанский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Соломбальский');

    -- Грозный
    v_city_id := ensure_city('Грозный', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Ахматовский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Старопромысловский');

    -- Якутск
    v_city_id := ensure_city('Якутск', 'Asia/Yakutsk');
    PERFORM ensure_district(v_city_id, 'Автодорожный');
    PERFORM ensure_district(v_city_id, 'Гагаринский');
    PERFORM ensure_district(v_city_id, 'Промышленный');
    PERFORM ensure_district(v_city_id, 'Сайсарский');
    PERFORM ensure_district(v_city_id, 'Строительный');

    -- Тверь
    v_city_id := ensure_city('Тверь', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Заволжский');
    PERFORM ensure_district(v_city_id, 'Московский');
    PERFORM ensure_district(v_city_id, 'Пролетарский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Старый Оскол
    v_city_id := ensure_city('Старый Оскол', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Улан-Удэ
    v_city_id := ensure_city('Улан-Удэ', 'Asia/Irkutsk');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Нижний Тагил
    v_city_id := ensure_city('Нижний Тагил', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Тагилстроевский');
    PERFORM ensure_district(v_city_id, 'Дзержинский');

    -- Нижневартовск
    v_city_id := ensure_city('Нижневартовск', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Псков
    v_city_id := ensure_city('Псков', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Йошкар-Ола
    v_city_id := ensure_city('Йошкар-Ола', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Ленинский');

    -- Кострома
    v_city_id := ensure_city('Кострома', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Новороссийск
    v_city_id := ensure_city('Новороссийск', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Дзержинск
    v_city_id := ensure_city('Дзержинск', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Таганрог
    v_city_id := ensure_city('Таганрог', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Химки
    v_city_id := ensure_city('Химки', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Березники
    v_city_id := ensure_city('Березники', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Энгельс
    v_city_id := ensure_city('Энгельс', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Шахты
    v_city_id := ensure_city('Шахты', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');
END $$;

-- Удаление функций (они больше не нужны)
DROP FUNCTION IF EXISTS ensure_city;
DROP FUNCTION IF EXISTS ensure_district;

-- Вывод статистики
DO $$
DECLARE
    cities_count INTEGER;
    districts_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO cities_count FROM cities;
    SELECT COUNT(*) INTO districts_count FROM districts;
    RAISE NOTICE 'Total cities: %', cities_count;
    RAISE NOTICE 'Total districts: %', districts_count;
END $$;
