"""Rename ADMIN staff role to GLOBAL_ADMIN"""

from alembic import op
import sqlalchemy as sa


revision = "2025_09_admin_role_rename"
down_revision = "2025_09_27_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new enum value and commit before using it
    conn = op.get_bind()
    conn.execute(sa.text("COMMIT"))
    conn.execute(sa.text("ALTER TYPE staff_role ADD VALUE IF NOT EXISTS 'GLOBAL_ADMIN'"))
    # Now it is safe to use the new enum value
    op.execute("UPDATE staff_users SET role='GLOBAL_ADMIN' WHERE role='ADMIN'")


def downgrade() -> None:
    op.execute("UPDATE staff_users SET role='ADMIN' WHERE role='GLOBAL_ADMIN'")
