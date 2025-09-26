from alembic import op
import sqlalchemy as sa

revision = "2025_09_19_0008"
down_revision = "2025_09_18_0007"
branch_labels = None
depends_on = None


def upgrade():
    # ускоряет md.district_id=:did
    op.create_index(
        "ix_master_districts__district",
        "master_districts",
        ["district_id"],
        unique=False,
    )
    # под фильтр по категории после добавления orders.skill_id
    op.create_index(
        "ix_master_skills__skill", "master_skills", ["skill_id"], unique=False
    )

    # настройки по планировщику
    op.execute(
        """
    INSERT INTO settings(key, value, value_type, description) VALUES
      ('distribution_tick_seconds','30','INT','Период тика распределения (сек)'),
      ('distribution_log_topn','10','INT','Сколько кандидатов писать в лог'),
      ('escalate_to_admin_after_min','10','INT','Через сколько минут после логиста эскалировать админу')
    ON CONFLICT (key) DO NOTHING
    """
    )


def downgrade():
    op.drop_index("ix_master_skills__skill", table_name="master_skills")
    op.drop_index("ix_master_districts__district", table_name="master_districts")
    # settings не трогаем (безопасность)
