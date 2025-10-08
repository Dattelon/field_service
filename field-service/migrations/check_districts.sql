-- Проверка текущего состояния районов

-- 1. МОСКВА (должно быть 12)
SELECT 'МОСКВА' as city, id, name 
FROM districts 
WHERE city_id = 1 
ORDER BY id;

-- 2. САНКТ-ПЕТЕРБУРГ (должно быть 18)
SELECT 'СПБ' as city, id, name 
FROM districts 
WHERE city_id = 2 
ORDER BY id;

-- 3. ИРКУТСК (должно быть 4)
SELECT 'ИРКУТСК' as city, id, name 
FROM districts 
WHERE city_id = 4 
ORDER BY id;

-- 4. НОВОСИБИРСК (должно быть 10)
SELECT 'НОВОСИБИРСК' as city, id, name 
FROM districts 
WHERE city_id = 6 
ORDER BY id;

-- 5. Проверка дубля города
SELECT 'ДУБЛЬ ГОРОДА' as check_type, id, name 
FROM cities 
WHERE id = 5;

-- 6. Проверка конфликтов имён
SELECT city_id, name, COUNT(*) as duplicate_count
FROM districts
GROUP BY city_id, name
HAVING COUNT(*) > 1;
