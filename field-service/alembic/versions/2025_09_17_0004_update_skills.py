"""update_skills: refresh active categories to requested set
Revision ID: 2025_09_17_0004
Revises: 2025_09_17_0003
Create Date: 2025-09-17 19:05:00.000000
"""

import os
from alembic import op

# revision identifiers, used by Alembic.
revision = "2025_09_17_0004"
down_revision = "2025_09_17_0003"
branch_labels = None
depends_on = None


def upgrade():
    if os.getenv("FS_SKIP_SEED", "").lower() in {"1", "true", "yes"}:
        return
    # Ensure exactly these categories are active with proper labels
    op.execute(
        """
        INSERT INTO skills (code, name, is_active) VALUES
            ('ELEC', 'Электрика', true),
            ('PLUMB', 'Сантехника', true),
            ('APPLI', 'Бытовая техника', true),
            ('WINDOWS', 'Окна и двери', true),
            ('HANDY', 'Мелкий ремонт', true),
            ('AUTOHELP', 'Автопомощь', true)
        ON CONFLICT (code) DO UPDATE SET
            name = EXCLUDED.name,
            is_active = EXCLUDED.is_active
        """
    )
    op.execute(
        """
        UPDATE skills
        SET is_active = false
        WHERE code NOT IN ('ELEC','PLUMB','APPLI','WINDOWS','HANDY','AUTOHELP');
        """
    )


def downgrade():
    # Re-activate previously seeded defaults, and remove added ones
    op.execute(
        """
        -- deactivate our added extras
        UPDATE skills SET is_active = false WHERE code IN ('WINDOWS','HANDY','AUTOHELP');
        -- best-effort: re-activate earlier demo ones if present
        UPDATE skills SET is_active = true WHERE code IN ('ELEC','PLUMB','APPLI','FURN');
        """
    )
