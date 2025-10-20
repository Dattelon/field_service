"""seed_demo_data: Демо-данные (только для локальной разработки)
Revision ID: 2025_09_17_0003
Revises: 2025_09_17_0002a
Create Date: 2025-09-17 18:30:00.000000

ВАЖНО: Эта миграция применяется ТОЛЬКО в dev-окружении:
- APP_ENV=development
- ALLOW_DEV_SEEDS=1
- В pytest (автоматически)

Для CI/тестов используйте seed_ci_minimal.
"""

from alembic import op
import sys
from pathlib import Path

# Добавляем alembic в путь для импорта guards
alembic_dir = Path(__file__).parent.parent
if str(alembic_dir) not in sys.path:
    sys.path.insert(0, str(alembic_dir))

from guards import skip_unless_dev  # noqa: E402

# revision identifiers, used by Alembic.
revision = "2025_09_17_0003"
down_revision = "2025_09_17_0002a"
branch_labels = None
depends_on = None


def upgrade():
    """Применяет демо-данные только в dev окружении."""
    # Пропускаем в production/staging/CI
    if skip_unless_dev(op, "demo data with empty names"):
        return
    
    # Города с пустыми именами (только для dev/тестирования)
    op.execute(
        """
        INSERT INTO cities (name, is_active)
        VALUES ('Тестовград', true),
               ('Демосити', true)
        ON CONFLICT (name) DO NOTHING
        """
    )

    # Районы с пустыми именами для тестового города
    op.execute(
        """
        WITH m AS (SELECT id AS city_id FROM cities WHERE name = 'Тестовград')
        INSERT INTO districts (city_id, name)
        SELECT m.city_id, x.name
        FROM m, (VALUES
            ('Северный'),('Южный'),('Западный'),('Восточный'),('Центральный')
        ) AS x(name)
        ON CONFLICT ON CONSTRAINT uq_districts__city_name DO NOTHING
        """
    )

    # Навыки с пустыми кодами (только для dev)
    op.execute(
        """
        INSERT INTO skills (code, name, is_active)
        VALUES
            ('DEV_ELEC', 'Тестовая электрика', true),
            ('DEV_PLUMB', 'Тестовая сантехника', true),
            ('DEV_FURN', 'Тестовая мебель', true),
            ('DEV_APPLI', 'Тестовая техника', true)
        ON CONFLICT (code) DO NOTHING
        """
    )

    # Настройки для локальной разработки
    op.execute(
        """
        INSERT INTO settings (key, value, value_type, description)
        VALUES
            ('dev_max_active_orders', '1', 'INT', 'Лимит для dev (быстрое тестирование)'),
            ('dev_commission_percent', '0', 'INT', 'Комиссия 0% для dev')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    """Откатывает демо-данные."""
    # Удаляем демо-данные (безопасно в любом окружении)
    op.execute("DELETE FROM skills WHERE code LIKE 'DEV_%'")
    op.execute(
        "DELETE FROM districts WHERE city_id IN (SELECT id FROM cities WHERE name IN ('Тестовград', 'Демосити'))"
    )
    op.execute("DELETE FROM cities WHERE name IN ('Тестовград', 'Демосити')")
    op.execute(
        "DELETE FROM settings WHERE key IN ('dev_max_active_orders', 'dev_commission_percent')"
    )
