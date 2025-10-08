"""admin_enhancements: per-admin requisites, access codes, per-master limit
Revision ID: 2025_09_18_0005
Revises: 2025_09_17_0005
Create Date: 2025-09-18 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2025_09_18_0005"
down_revision = "2025_09_17_0005"
branch_labels = None
depends_on = None


def upgrade():
    # 1) Персональные реквизиты админа
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {ix.get("name") for ix in insp.get_indexes("staff_users")}
    if "ix_staff_users__tg_user_id" not in existing:
        op.create_index(
            "ix_staff_users__tg_user_id", "staff_users", ["tg_user_id"], unique=False
        )

    # 2) Персональный лимит активных (опционально, для adm:m:lim)
    op.add_column(
        "masters",
        sa.Column("max_active_orders_override", sa.SmallInteger(), nullable=True),
    )

    # 3) Коды доступа персонала
    staff_role = postgresql.ENUM(
        "ADMIN", "LOGIST", name="staff_role", create_type=False
    )
    op.create_table(
        "staff_access_codes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(length=16), nullable=False, unique=True),
        sa.Column("role", staff_role, nullable=False),
        sa.Column(
            "city_id", sa.Integer, sa.ForeignKey("cities.id", ondelete="SET NULL")
        ),
        sa.Column(
            "issued_by_staff_id",
            sa.Integer,
            sa.ForeignKey("staff_users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "used_by_staff_id",
            sa.Integer,
            sa.ForeignKey("staff_users.id", ondelete="SET NULL"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "is_revoked", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )
    op.create_index(
        "ix_staff_access_codes__code", "staff_access_codes", ["code"], unique=True
    )


def downgrade():
    op.drop_index("ix_staff_access_codes__code", table_name="staff_access_codes")
    op.drop_table("staff_access_codes")
    op.drop_column("masters", "max_active_orders_override")
    op.drop_index("ix_staff_users__tg_user_id", table_name="staff_users")
