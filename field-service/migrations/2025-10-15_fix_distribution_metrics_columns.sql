-- Переименование колонок category → category_name и order_type → type_name
-- чтобы избежать конфликта с ENUM типами из таблицы orders

ALTER TABLE distribution_metrics RENAME COLUMN category TO category_name;
ALTER TABLE distribution_metrics RENAME COLUMN order_type TO type_name;
