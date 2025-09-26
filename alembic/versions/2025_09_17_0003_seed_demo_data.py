"""seed_demo_data: базовые города/районы/навыки (dev)
Revision ID: 2025_09_17_0003
Revises: 2025_09_17_0002
Create Date: 2025-09-17 18:30:00.000000
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "2025_09_17_0003"
down_revision = "2025_09_17_0002a"
branch_labels = None
depends_on = None


def upgrade():
    # Города (уникальность по name)
    op.execute(
        """
        INSERT INTO cities (name, is_active)
        VALUES ('Москва', true),
               ('Санкт-Петербург', true),
               ('Казань', true)
        ON CONFLICT (name) DO NOTHING
        """
    )

    # Районы (уникальность по (city_id, name))
    # Пример — только для Москвы
    op.execute(
        """
        WITH m AS (SELECT id AS city_id FROM cities WHERE name = 'Москва')
        INSERT INTO districts (city_id, name)
        SELECT m.city_id, x.name
        FROM m, (VALUES
            ('ЦАО'),('САО'),('ЮАО'),('ВАО'),('ЗАО')
        ) AS x(name)
        ON CONFLICT ON CONSTRAINT uq_districts__city_name DO NOTHING
        """
    )

    # Навыки (уникальность по code)
    op.execute(
        """
        INSERT INTO skills (code, name, is_active)
        VALUES
            ('ELEC', 'Электрика', true),
            ('PLUMB', 'Сантехника', true),
            ('FURN', 'Сборка мебели', true),
            ('APPLI', 'Бытовая техника', true)
        ON CONFLICT (code) DO NOTHING
        """
    )

    # Настройки (K/V) — полезные дефолты для dev
    op.execute(
        """
        INSERT INTO settings (key, value, value_type, description)
        VALUES
            ('max_active_orders', '1', 'INT', 'Лимит активных заказов на мастера'),
            ('commission_percent_default', '0', 'INT', 'Комиссия по умолчанию (не используется для гарантий)')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    # Откатываем только demo‑данные, не трогая реальный прод
    op.execute("DELETE FROM skills WHERE code IN ('ELEC','PLUMB','FURN','APPLI')")
    op.execute("DELETE FROM districts WHERE name IN ('ЦАО','САО','ЮАО','ВАО','ЗАО')")
    op.execute("DELETE FROM cities WHERE name IN ('Москва','Санкт-Петербург','Казань')")
    op.execute(
        "DELETE FROM settings WHERE key IN ('max_active_orders','commission_percent_default')"
    )
