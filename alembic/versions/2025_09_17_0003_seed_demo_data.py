"""seed_demo_data:  // (dev)
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
    #  (  name)
    op.execute(
        """
        INSERT INTO cities (name, is_active)
        VALUES ('', true),
               ('-', true),
               ('', true)
        ON CONFLICT (name) DO NOTHING
        """
    )

    #  (  (city_id, name))
    #     
    op.execute(
        """
        WITH m AS (SELECT id AS city_id FROM cities WHERE name = '')
        INSERT INTO districts (city_id, name)
        SELECT m.city_id, x.name
        FROM m, (VALUES
            (''),(''),(''),(''),('')
        ) AS x(name)
        ON CONFLICT ON CONSTRAINT uq_districts__city_name DO NOTHING
        """
    )

    #  (  code)
    op.execute(
        """
        INSERT INTO skills (code, name, is_active)
        VALUES
            ('ELEC', '', true),
            ('PLUMB', '', true),
            ('FURN', ' ', true),
            ('APPLI', ' ', true)
        ON CONFLICT (code) DO NOTHING
        """
    )

    #  (K/V)     dev
    op.execute(
        """
        INSERT INTO settings (key, value, value_type, description)
        VALUES
            ('max_active_orders', '1', 'INT', '    '),
            ('commission_percent_default', '0', 'INT', '   (   )')
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade():
    #   demo,    
    op.execute("DELETE FROM skills WHERE code IN ('ELEC','PLUMB','FURN','APPLI')")
    op.execute("DELETE FROM districts WHERE name IN ('','','','','')")
    op.execute("DELETE FROM cities WHERE name IN ('','-','')")
    op.execute(
        "DELETE FROM settings WHERE key IN ('max_active_orders','commission_percent_default')"
    )
