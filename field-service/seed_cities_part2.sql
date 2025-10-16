DO $$
DECLARE
    v_city_id INTEGER;
BEGIN
    -- Волгоград
    v_city_id := ensure_city('Волгоград', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Тракторозаводский');
    PERFORM ensure_district(v_city_id, 'Краснооктябрьский');
    PERFORM ensure_district(v_city_id, 'Центральный');
    PERFORM ensure_district(v_city_id, 'Дзержинский');
    PERFORM ensure_district(v_city_id, 'Ворошиловский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Красноармейский');

    -- Саратов
    v_city_id := ensure_city('Саратов', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Волжский');
    PERFORM ensure_district(v_city_id, 'Заводской');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Фрунзенский');

    -- Тюмень
    v_city_id := ensure_city('Тюмень', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Калининский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Центральный');
    PERFORM ensure_district(v_city_id, 'Восточный');

    -- Тольятти
    v_city_id := ensure_city('Тольятти', 'Europe/Samara');
    PERFORM ensure_district(v_city_id, 'Автозаводский');
    PERFORM ensure_district(v_city_id, 'Комсомольский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Ижевск
    v_city_id := ensure_city('Ижевск', 'Europe/Samara');
    PERFORM ensure_district(v_city_id, 'Индустриальный');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Первомайский');
    PERFORM ensure_district(v_city_id, 'Устиновский');

    -- Барнаул
    v_city_id := ensure_city('Барнаул', 'Asia/Barnaul');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Индустриальный');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Ульяновск
    v_city_id := ensure_city('Ульяновск', 'Europe/Samara');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Заволжский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Засвияжский');

    -- Иркутск
    v_city_id := ensure_city('Иркутск', 'Asia/Irkutsk');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Свердловский');

    -- Хабаровск
    v_city_id := ensure_city('Хабаровск', 'Asia/Vladivostok');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Индустриальный');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Краснофлотский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Владивосток
    v_city_id := ensure_city('Владивосток', 'Asia/Vladivostok');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Первомайский');
    PERFORM ensure_district(v_city_id, 'Первореченский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Фрунзенский');

    -- Ярославль
    v_city_id := ensure_city('Ярославль', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Дзержинский');
    PERFORM ensure_district(v_city_id, 'Заволжский');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Красноперекопский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Фрунзенский');

    -- Махачкала
    v_city_id := ensure_city('Махачкала', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Томск
    v_city_id := ensure_city('Томск', 'Asia/Tomsk');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Оренбург
    v_city_id := ensure_city('Оренбург', 'Asia/Yekaterinburg');
    PERFORM ensure_district(v_city_id, 'Дзержинский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Промышленный');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Кемерово
    v_city_id := ensure_city('Кемерово', 'Asia/Novokuznetsk');
    PERFORM ensure_district(v_city_id, 'Заводский');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Рудничный');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Новокузнецк
    v_city_id := ensure_city('Новокузнецк', 'Asia/Novokuznetsk');
    PERFORM ensure_district(v_city_id, 'Заводской');
    PERFORM ensure_district(v_city_id, 'Кузнецкий');
    PERFORM ensure_district(v_city_id, 'Куйбышевский');
    PERFORM ensure_district(v_city_id, 'Новоильинский');
    PERFORM ensure_district(v_city_id, 'Орджоникидзевский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Рязань
    v_city_id := ensure_city('Рязань', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Московский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Набережные Челны
    v_city_id := ensure_city('Набережные Челны', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Автозаводский');
    PERFORM ensure_district(v_city_id, 'Комсомольский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Астрахань
    v_city_id := ensure_city('Астрахань', 'Europe/Astrakhan');
    PERFORM ensure_district(v_city_id, 'Кировский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Трусовский');

    -- Пенза
    v_city_id := ensure_city('Пенза', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Первомайский');

    -- Киров
    v_city_id := ensure_city('Киров', 'Europe/Kirov');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Первомайский');
    PERFORM ensure_district(v_city_id, 'Нововятский');

    -- Липецк
    v_city_id := ensure_city('Липецк', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Левобережный');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Правобережный');
    PERFORM ensure_district(v_city_id, 'Советский');

    -- Чебоксары
    v_city_id := ensure_city('Чебоксары', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Калининский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Московский');

    -- Калининград
    v_city_id := ensure_city('Калининград', 'Europe/Kaliningrad');
    PERFORM ensure_district(v_city_id, 'Балтийский');
    PERFORM ensure_district(v_city_id, 'Ленинградский');
    PERFORM ensure_district(v_city_id, 'Московский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Тула
    v_city_id := ensure_city('Тула', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Зареченский');
    PERFORM ensure_district(v_city_id, 'Привокзальный');
    PERFORM ensure_district(v_city_id, 'Пролетарский');
    PERFORM ensure_district(v_city_id, 'Советский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Курск
    v_city_id := ensure_city('Курск', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Железнодорожный');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Сеймский');

    -- Сочи
    v_city_id := ensure_city('Сочи', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Адлерский');
    PERFORM ensure_district(v_city_id, 'Лазаревский');
    PERFORM ensure_district(v_city_id, 'Хостинский');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Ставрополь
    v_city_id := ensure_city('Ставрополь', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Октябрьский');
    PERFORM ensure_district(v_city_id, 'Промышленный');

    -- Балашиха
    v_city_id := ensure_city('Балашиха', 'Europe/Moscow');
    PERFORM ensure_district(v_city_id, 'Центральный');

    -- Севастополь
    v_city_id := ensure_city('Севастополь', 'Europe/Simferopol');
    PERFORM ensure_district(v_city_id, 'Гагаринский');
    PERFORM ensure_district(v_city_id, 'Ленинский');
    PERFORM ensure_district(v_city_id, 'Нахимовский');
    PERFORM ensure_district(v_city_id, 'Балаклавский');
END $$;
