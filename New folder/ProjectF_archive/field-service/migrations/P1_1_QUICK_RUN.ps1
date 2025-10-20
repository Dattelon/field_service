# БЫСТРОЕ ПРИМЕНЕНИЕ P1.1

# Копируем SQL в контейнер
docker cp C:\ProjectF\field-service\migrations\P1_1_add_missing_commissions_indexes.sql field-service-postgres-1:/tmp/

# Выполняем миграцию
docker exec -i field-service-postgres-1 psql -U postgres -d field_service -f /tmp/P1_1_add_missing_commissions_indexes.sql

# Готово! Индексы созданы.
