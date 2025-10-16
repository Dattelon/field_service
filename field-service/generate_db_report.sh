#!/bin/bash
# Генератор отчёта о тестовой БД field_service_test

OUTPUT="/tmp/test_db_report.md"

echo "# База данных Field Service - Полная структура (ТЕСТОВАЯ БД)" > $OUTPUT
echo "" >> $OUTPUT
echo "**Дата сбора:** $(date '+%Y-%m-%d %H:%M:%S')" >> $OUTPUT
echo "**База данных:** field_service_test" >> $OUTPUT
echo "**Контейнер:** field-service-postgres-1" >> $OUTPUT
echo "**Порт:** 5439 → 5432" >> $OUTPUT
echo "" >> $OUTPUT
echo "---" >> $OUTPUT
echo "" >> $OUTPUT

# Версия миграции
echo "## Версия миграций Alembic" >> $OUTPUT
echo "" >> $OUTPUT
VERSION=$(psql -U field_user -d field_service_test -t -c "SELECT version_num FROM alembic_version")
echo "**Текущая версия:** \`$VERSION\`" >> $OUTPUT
echo "" >> $OUTPUT

# Список всех таблиц
echo "## Список таблиц" >> $OUTPUT
echo "" >> $OUTPUT
psql -U field_user -d field_service_test -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename" >> $OUTPUT
echo "" >> $OUTPUT

# Статистика по записям
echo "## Статистика данных" >> $OUTPUT
echo "" >> $OUTPUT
echo "| Таблица | Записей |" >> $OUTPUT
echo "|---------|---------|" >> $OUTPUT

for table in $(psql -U field_user -d field_service_test -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"); do
    count=$(psql -U field_user -d field_service_test -t -c "SELECT COUNT(*) FROM $table" | tr -d ' ')
    echo "| $table | **$count** |" >> $OUTPUT
done

echo "" >> $OUTPUT
echo "---" >> $OUTPUT
echo "" >> $OUTPUT

# Детали каждой таблицы
for table in $(psql -U field_user -d field_service_test -t -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"); do
    count=$(psql -U field_user -d field_service_test -t -c "SELECT COUNT(*) FROM $table" | tr -d ' ')
    
    echo "## Таблица: \`$table\`" >> $OUTPUT
    echo "" >> $OUTPUT
    echo "**Количество записей:** $count" >> $OUTPUT
    echo "" >> $OUTPUT
    
    echo "### Структура таблицы" >> $OUTPUT
    echo "" >> $OUTPUT
    echo '```sql' >> $OUTPUT
    psql -U field_user -d field_service_test -c "\d+ $table" >> $OUTPUT
    echo '```' >> $OUTPUT
    echo "" >> $OUTPUT
    
    # Если есть записи, показать первые 10
    if [ "$count" -gt "0" ]; then
        echo "### Данные (до 10 записей)" >> $OUTPUT
        echo "" >> $OUTPUT
        echo '```' >> $OUTPUT
        psql -U field_user -d field_service_test -c "SELECT * FROM $table LIMIT 10" >> $OUTPUT
        echo '```' >> $OUTPUT
        echo "" >> $OUTPUT
    fi
    
    echo "---" >> $OUTPUT
    echo "" >> $OUTPUT
done

cat $OUTPUT
