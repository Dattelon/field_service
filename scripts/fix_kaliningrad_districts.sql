-- FIX: Добавление района для Калининграда
-- Дата: 2025-10-03
-- Проблема: Калининград (id=40) не имеет ни одного района

-- Добавляем базовый район "Город целиком" для Калининграда
INSERT INTO districts (city_id, name) 
VALUES (40, 'Город целиком')
ON CONFLICT DO NOTHING;

-- Проверка результата
SELECT 
    c.id,
    c.name AS city_name,
    COUNT(d.id) AS districts_count
FROM cities c
LEFT JOIN districts d ON d.city_id = c.id
WHERE c.id = 40
GROUP BY c.id, c.name;

-- Ожидаемый результат:
-- id | city_name    | districts_count
-- 40 | Калининград  | 1
