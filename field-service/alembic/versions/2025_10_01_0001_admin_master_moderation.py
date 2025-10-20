"""Admin masters moderation flows foundation

Revision ID: 2025_10_01_0001
Revises: 2cad62ab4b40
Create Date: 2025-10-01 09:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "2025_10_01_0001"
down_revision = "2cad62ab4b40"
branch_labels = None
depends_on = None

MASTER_STATUS_INDEX = "ix_masters__verified_active_deleted_city"


def upgrade() -> None:
    op.add_column(
        "masters",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "masters",
        sa.Column("moderation_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "masters",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "masters",
        sa.Column(
            "verified_by",
            sa.Integer(),
            sa.ForeignKey("staff_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.add_column(
        "attachments",
        sa.Column("document_type", sa.String(length=32), nullable=True),
    )

    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "admin_id",
            sa.Integer(),
            sa.ForeignKey("staff_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "master_id",
            sa.Integer(),
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_admin_audit_log_admin_id",
        "admin_audit_log",
        ["admin_id"],
    )
    op.create_index(
        "ix_admin_audit_log_master_id",
        "admin_audit_log",
        ["master_id"],
    )
    op.create_index(
        "ix_admin_audit_log_created_at",
        "admin_audit_log",
        ["created_at"],
    )

    op.create_table(
        "notifications_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "master_id",
            sa.Integer(),
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_notifications_outbox_master",
        "notifications_outbox",
        ["master_id"],
    )
    op.create_index(
        "ix_notifications_outbox_created",
        "notifications_outbox",
        ["created_at"],
    )

    op.create_index(
        MASTER_STATUS_INDEX,
        "masters",
        ["verified", "is_active", "is_deleted", "city_id"],
    )

    op.execute(
        "UPDATE masters SET moderation_reason = moderation_note WHERE moderation_note IS NOT NULL"
    )
    op.execute("UPDATE masters SET is_deleted = false WHERE is_deleted IS NULL")

    op.alter_column("masters", "is_deleted", server_default=None)


def downgrade() -> None:
    op.drop_index(MASTER_STATUS_INDEX, table_name="masters")
    op.drop_index("ix_notifications_outbox_created", table_name="notifications_outbox")
    op.drop_index("ix_notifications_outbox_master", table_name="notifications_outbox")
    op.drop_table("notifications_outbox")
    op.drop_index("ix_admin_audit_log_created_at", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_master_id", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_log_admin_id", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")

    op.drop_column("attachments", "document_type")

    op.drop_column("masters", "verified_by")
    op.drop_column("masters", "verified_at")
    op.drop_column("masters", "moderation_reason")
    op.drop_column("masters", "is_deleted")
