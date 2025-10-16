"""seed_ci_minimal: Минимальный набор данных для CI/тестов
Revision ID: 2025_10_15_0001
Revises: 2025_10_09_0001
Create Date: 2025-10-15 12:00:00.000000

Содержит только необходимый минимум:
- 1 город (Москва)
- 3 района (для тестов распределения)
- 4 базовых навыка (ELECTRICS, PLUMBING, APPLIANCES, HANDYMAN)
- Базовые настройки

Без пустых имён, без демо-данных.
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "2025_10_15_0001"
down_revision = "2025_10_09_0001"
branch_labels = None
depends_on = None


def upgrade():
    """Применяет минимальный набор данных для CI."""
    
    # Один город для тестов - Москва
    op.execute(
        """
        INSERT INTO cities (name, is_active, timezone)
        VALUES ('Москва', true, 'Europe/Moscow')
        ON CONFLICT (name) DO NOTHING
        """
    )

    # Три района для тестов распределения
    op.execute(
        """
        WITH m AS (SELECT id AS city_id FROM cities WHERE name = 'Москва')
        INSERT INTO districts (city_id, name)
        SELECT m.city_id, x.name
        FROM m, (VALUES
            ('ЦАО'),('СВАО'),('ЮАО')
        ) AS x(name)
        ON CONFLICT ON CONSTRAINT uq_districts__city_name DO NOTHING
        """
    )

    # Четыре базовых навыка
    op.execute(
        """
        INSERT INTO skills (code, name, is_active)
        VALUES
            ('ELEC', 'Электрика', true),
            ('PLUMB', 'Сантехника', true),
            ('APPLI', 'Бытовая техника', true),
            ('HAND', 'Универсал', true)
        ON CONFLICT (code) DO NOTHING
        """
    )

    # Базовые настройки для тестов
    op.execute(
        """
        INSERT INTO settings (key, value, value_type, description)
        VALUES
            ('max_active_orders', '5', 'INT', 'Макс активных заказов на мастера'),
            ('commission_percent_default', '50', 'INT', 'Базовая комиссия 50%'),
            ('commission_percent_high_volume', '40', 'INT', 'Комиссия при чеке >= 7000'),
            ('commission_high_volume_threshold', '7000', 'INT', 'Порог для пониженной комиссии')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    """Откатывает минимальный набор данных."""
    # Удаляем в обратном порядке (из-за FK)
    op.execute("DELETE FROM settings WHERE key LIKE '%commission%' OR key = 'max_active_orders'")
    op.execute("DELETE FROM skills WHERE code IN ('ELEC', 'PLUMB', 'APPLI', 'HAND')")
    op.execute(
        "DELETE FROM districts WHERE city_id IN (SELECT id FROM cities WHERE name = 'Москва') AND name IN ('ЦАО', 'СВАО', 'ЮАО')"
    )
    # Не удаляем Москву - она может быть добавлена из seed_cities
