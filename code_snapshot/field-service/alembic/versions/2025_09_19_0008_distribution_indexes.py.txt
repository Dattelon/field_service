from alembic import op
import sqlalchemy as sa

revision = "2025_09_19_0008"
down_revision = "2025_09_18_0007"
branch_labels = None
depends_on = None


def upgrade():
    #  md.district_id=:did
    op.create_index(
        "ix_master_districts__district",
        "master_districts",
        ["district_id"],
        unique=False,
    )
    #       orders.skill_id
    op.create_index(
        "ix_master_skills__skill", "master_skills", ["skill_id"], unique=False
    )

    #   
    op.execute(
        """
    INSERT INTO settings(key, value, value_type, description) VALUES
      ('distribution_tick_seconds','30','INT','   ()'),
      ('distribution_log_topn','10','INT','    '),
      ('escalate_to_admin_after_min','10','INT','      ')
    ON CONFLICT (key) DO NOTHING
    """
    )


def downgrade():
    op.drop_index("ix_master_skills__skill", table_name="master_skills")
    op.drop_index("ix_master_districts__district", table_name="master_districts")
    # settings   ()
