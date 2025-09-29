"""Add revoked_at to staff_access_codes and rename issued_by column"""

from alembic import op
import sqlalchemy as sa


revision = "2025_09_23_0003"
down_revision = "2025_09_22_0002"
branch_labels = None
depends_on = None


TABLE = "staff_access_codes"
OLD_STATE_INDEX = "ix_staff_codes__state"
NEW_AVAILABLE_INDEX = "ix_staff_access_codes__code_available"


def upgrade() -> None:
    op.alter_column(TABLE, "issued_by_staff_id", new_column_name="created_by_staff_id")
    op.add_column(TABLE, sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))

    op.execute(
        sa.text(
            "UPDATE staff_access_codes SET revoked_at = NOW()"
            " WHERE revoked_at IS NULL AND is_revoked = TRUE"
        )
    )

    op.drop_index(OLD_STATE_INDEX, table_name=TABLE)
    op.drop_column(TABLE, "is_revoked")

    op.create_index(
        NEW_AVAILABLE_INDEX,
        TABLE,
        ["code"],
        unique=True,
        postgresql_where=sa.text("used_by_staff_id IS NULL AND revoked_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index(NEW_AVAILABLE_INDEX, table_name=TABLE)

    op.add_column(
        TABLE,
        sa.Column(
            "is_revoked",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.execute(
        sa.text(
            "UPDATE staff_access_codes SET is_revoked = TRUE"
            " WHERE revoked_at IS NOT NULL"
        )
    )

    op.create_index(OLD_STATE_INDEX, TABLE, ["is_revoked", "used_at"])

    op.drop_column(TABLE, "revoked_at")
    op.alter_column(TABLE, "created_by_staff_id", new_column_name="issued_by_staff_id")

