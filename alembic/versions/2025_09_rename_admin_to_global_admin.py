"""Rename ADMIN staff role to GLOBAL_ADMIN"""

from alembic import op


revision = "2025_09_rename_admin_to_global_admin"
down_revision = "2025_09_27_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE staff_users SET role='GLOBAL_ADMIN' WHERE role='ADMIN'")


def downgrade() -> None:
    op.execute("UPDATE staff_users SET role='ADMIN' WHERE role='GLOBAL_ADMIN'")
