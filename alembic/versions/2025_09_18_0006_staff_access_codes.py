"""staff_access_codes: invite codes for staff (merged after 0005)
Revision ID: 2025_09_18_0006
Revises: 2025_09_18_0005
Create Date: 2025-09-18 10:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2025_09_18_0006"
down_revision = "2025_09_18_0005"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    if "staff_access_codes" not in tables:
        # Create table compatible with existing 0005 layout
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
                "is_revoked",
                sa.Boolean,
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("NOW()"),
            ),
        )
        op.create_index(
            "ix_staff_access_codes__code", "staff_access_codes", ["code"], unique=True
        )
    # Ensure helpful state index exists
    existing_indexes = {ix.get("name") for ix in insp.get_indexes("staff_access_codes")}
    if "ix_staff_codes__state" not in existing_indexes:
        op.create_index(
            "ix_staff_codes__state", "staff_access_codes", ["is_revoked", "used_at"]
        )


def downgrade():
    # Best-effort: drop only the extra state index to avoid clobbering table from 0005
    op.drop_index("ix_staff_codes__state", table_name="staff_access_codes")
