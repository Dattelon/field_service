"""master_fsm: .  , , ,  MASTER
Revision ID: 2025_09_17_0002
Revises: 2025_09_17_0001
Create Date: 2025-09-17 15:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2025_09_17_0002"
down_revision = "2025_09_17_0001"
branch_labels = None
depends_on = None


def upgrade():
    # --- ENUMs ---
    moderation_status = postgresql.ENUM(
        "PENDING", "APPROVED", "REJECTED", name="moderation_status"
    )
    shift_status = postgresql.ENUM(
        "SHIFT_OFF", "SHIFT_ON", "BREAK", name="shift_status"
    )
    payout_method = postgresql.ENUM(
        "CARD", "SBP", "YOOMONEY", "BANK_ACCOUNT", name="payout_method"
    )
    for e in (moderation_status, shift_status, payout_method):
        e.create(op.get_bind(), checkfirst=True)

    # --- masters: add columns ---
    op.add_column(
        "masters",
        sa.Column(
            "moderation_status",
            moderation_status,
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column("masters", sa.Column("moderation_note", sa.Text(), nullable=True))
    op.add_column(
        "masters",
        sa.Column(
            "shift_status", shift_status, nullable=False, server_default="SHIFT_OFF"
        ),
    )
    op.add_column(
        "masters", sa.Column("break_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "masters",
        sa.Column("pdn_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("masters", sa.Column("payout_method", payout_method, nullable=True))
    op.add_column(
        "masters",
        sa.Column(
            "payout_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "masters",
        sa.Column(
            "has_vehicle", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.add_column(
        "masters", sa.Column("vehicle_plate", sa.String(length=16), nullable=True)
    )
    op.add_column(
        "masters", sa.Column("home_latitude", sa.Numeric(9, 6), nullable=True)
    )
    op.add_column(
        "masters", sa.Column("home_longitude", sa.Numeric(9, 6), nullable=True)
    )
    op.create_index(
        "ix_masters__mod_shift", "masters", ["moderation_status", "shift_status"]
    )

    # --- skills ---
    op.create_table(
        "skills",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )
    op.create_table(
        "master_skills",
        sa.Column(
            "master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "skill_id",
            sa.Integer,
            sa.ForeignKey("skills.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    # --- master_districts ---
    op.create_table(
        "master_districts",
        sa.Column(
            "master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "district_id",
            sa.Integer,
            sa.ForeignKey("districts.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    # --- attachments: add MASTER to enum ---
    op.execute("ALTER TYPE attachment_entity ADD VALUE IF NOT EXISTS 'MASTER'")


def downgrade():
    op.drop_table("master_districts")
    op.drop_table("master_skills")
    op.drop_table("skills")
    op.drop_index("ix_masters__mod_shift", table_name="masters")
    for col in (
        "home_longitude",
        "home_latitude",
        "vehicle_plate",
        "has_vehicle",
        "payout_data",
        "payout_method",
        "pdn_accepted_at",
        "break_until",
        "shift_status",
        "moderation_note",
        "moderation_status",
    ):
        op.drop_column("masters", col)
    for enum_name in ("payout_method", "shift_status", "moderation_status"):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
    # attachment_entity: enum  MASTER    ()
