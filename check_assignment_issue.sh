#!/bin/bash
# Скрипт для проверки проблемы с назначением заказа #15 на мастера #34

echo "=== ЗАКАЗ #15 ==="
docker exec field-service-postgres-1 psql -U fieldservice -d fieldservice -c "SELECT id, city_id, district_id, category, status FROM orders WHERE id=15;"

echo ""
echo "=== ГОРОД И РАЙОН ЗАКАЗА ==="
docker exec field-service-postgres-1 psql -U fieldservice -d fieldservice -c "
SELECT 
    o.id as order_id,
    c.name as city,
    d.name as district
FROM orders o
LEFT JOIN cities c ON o.city_id = c.id
LEFT JOIN districts d ON o.district_id = d.id
WHERE o.id = 15;"

echo ""
echo "=== МАСТЕР #34 ==="
docker exec field-service-postgres-1 psql -U fieldservice -d fieldservice -c "SELECT id, city_id, is_on_shift, verified, is_active, is_deleted FROM masters WHERE id=34;"

echo ""
echo "=== ГОРОД МАСТЕРА #34 ==="
docker exec field-service-postgres-1 psql -U fieldservice -d fieldservice -c "
SELECT 
    m.id as master_id,
    c.name as city
FROM masters m
LEFT JOIN cities c ON m.city_id = c.id
WHERE m.id = 34;"

echo ""
echo "=== РАЙОНЫ МАСТЕРА #34 ==="
docker exec field-service-postgres-1 psql -U fieldservice -d fieldservice -c "
SELECT 
    md.master_id,
    d.name as district
FROM master_districts md
LEFT JOIN districts d ON md.district_id = d.id
WHERE md.master_id = 34
ORDER BY d.name;"

echo ""
echo "=== НАВЫКИ МАСТЕРА #34 ==="
docker exec field-service-postgres-1 psql -U fieldservice -d fieldservice -c "
SELECT category FROM master_categories WHERE master_id = 34;"
