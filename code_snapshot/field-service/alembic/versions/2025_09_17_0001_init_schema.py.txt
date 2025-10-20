"""init_schema: Field Service v1.2 core tables

Revision ID: 2025_09_17_0001
Revises:
Create Date: 2025-09-17 10:00:00.000000
"""

from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "2025_09_17_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ==== ENUMs ====
    order_status = postgresql.ENUM(
        "CREATED",
        "DISTRIBUTION",
        "ASSIGNED",
        "SCHEDULED",
        "IN_PROGRESS",
        "DONE",
        "CLOSED",
        "DEFERRED",
        "GUARANTEE",
        "CANCELED",
        name="order_status",
        create_type=True,
    )
    offer_state = postgresql.ENUM(
        "SENT",
        "VIEWED",
        "ACCEPTED",
        "DECLINED",
        "EXPIRED",
        "CANCELED",
        name="offer_state",
        create_type=True,
    )
    attachment_entity = postgresql.ENUM(
        "ORDER", "OFFER", "COMMISSION", name="attachment_entity", create_type=True
    )
    attachment_file_type = postgresql.ENUM(
        "PHOTO",
        "DOCUMENT",
        "AUDIO",
        "VIDEO",
        "OTHER",
        name="attachment_file_type",
        create_type=True,
    )
    commission_status = postgresql.ENUM(
        "PENDING", "PAID", "OVERDUE", name="commission_status", create_type=True
    )
    referral_reward_status = postgresql.ENUM(
        "ACCRUED", "PAID", "CANCELED", name="referral_reward_status", create_type=True
    )
    staff_role = postgresql.ENUM("ADMIN", "LOGIST", name="staff_role", create_type=True)

    # Rely on SQLAlchemy to create ENUM types automatically when first used
    # in table definitions below. Explicit creation here can cause duplicates
    # when the same type object is bound to table columns.

    # ==== Cities/Districts/Streets ====
    op.create_table(
        "cities",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    op.create_table(
        "districts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "city_id",
            sa.Integer,
            sa.ForeignKey("cities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint("city_id", "name", name="uq_districts__city_name"),
    )
    op.create_index("ix_districts__city_id", "districts", ["city_id"])

    op.create_table(
        "streets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "city_id",
            sa.Integer,
            sa.ForeignKey("cities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "district_id",
            sa.Integer,
            sa.ForeignKey("districts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint(
            "city_id", "district_id", "name", name="uq_streets__city_district_name"
        ),
    )
    op.create_index("ix_streets__city_id", "streets", ["city_id"])
    op.create_index("ix_streets__district_id", "streets", ["district_id"])

    # ==== Staff ====
    op.create_table(
        "staff_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tg_user_id", sa.BigInteger, unique=True, index=True),
        sa.Column("username", sa.String(length=64)),
        sa.Column("full_name", sa.String(length=160)),
        sa.Column("phone", sa.String(length=32)),
        sa.Column("role", staff_role, nullable=False),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )
    # Index on tg_user_id is already covered by unique/index flags on column

    op.create_table(
        "staff_cities",
        sa.Column(
            "staff_user_id",
            sa.Integer,
            sa.ForeignKey("staff_users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "city_id",
            sa.Integer,
            sa.ForeignKey("cities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )

    # ==== Masters ====
    op.create_table(
        "masters",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tg_user_id", sa.BigInteger, unique=True),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("phone", sa.String(length=32)),
        sa.Column(
            "city_id",
            sa.Integer,
            sa.ForeignKey("cities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rating", sa.Float, nullable=False, server_default="5.0"),
        sa.Column(
            "is_active", sa.Boolean, nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "is_blocked", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("blocked_at", sa.DateTime(timezone=True)),
        sa.Column("blocked_reason", sa.Text),
        sa.Column("referral_code", sa.String(length=32), unique=True),
        sa.Column(
            "referred_by_master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    )
    op.create_index("ix_masters__tg_user_id", "masters", ["tg_user_id"])
    op.create_index("ix_masters__phone", "masters", ["phone"])
    op.create_index("ix_masters__city_id", "masters", ["city_id"])
    op.create_index("ix_masters__referred_by", "masters", ["referred_by_master_id"])
    op.create_index("ix_masters__heartbeat", "masters", ["last_heartbeat_at"])

    # ==== Orders ====
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "city_id",
            sa.Integer,
            sa.ForeignKey("cities.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "district_id",
            sa.Integer,
            sa.ForeignKey("districts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "street_id",
            sa.Integer,
            sa.ForeignKey("streets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("house", sa.String(length=32)),
        sa.Column("apartment", sa.String(length=32)),
        sa.Column("address_comment", sa.Text),
        sa.Column("client_name", sa.String(length=160)),
        sa.Column("client_phone", sa.String(length=32)),
        sa.Column("status", order_status, nullable=False),
        sa.Column("scheduled_date", sa.Date),
        sa.Column("time_slot_start", sa.Time(timezone=False)),
        sa.Column("time_slot_end", sa.Time(timezone=False)),
        sa.Column("slot_label", sa.String(length=32)),
        sa.Column(
            "preferred_master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "assigned_master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("total_price", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column(
            "created_by_staff_id",
            sa.Integer,
            sa.ForeignKey("staff_users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.CheckConstraint(
            "(time_slot_start IS NULL AND time_slot_end IS NULL) OR "
            "(time_slot_start >= TIME '10:00' AND time_slot_end <= TIME '20:00' AND time_slot_start < time_slot_end)",
            name="ck_orders__slot_in_working_window",
        ),
    )
    op.create_index(
        "ix_orders__status_city_date", "orders", ["status", "city_id", "scheduled_date"]
    )
    op.create_index("ix_orders__city_status", "orders", ["city_id", "status"])
    op.create_index("ix_orders__assigned_master", "orders", ["assigned_master_id"])
    op.create_index("ix_orders__preferred_master", "orders", ["preferred_master_id"])
    op.create_index("ix_orders__created_at", "orders", ["created_at"])
    op.create_index("ix_orders__phone", "orders", ["client_phone"])
    op.create_index("ix_orders__city_id", "orders", ["city_id"])
    op.create_index("ix_orders__district_id", "orders", ["district_id"])
    op.create_index("ix_orders__street_id", "orders", ["street_id"])

    # ==== Order Status History ====
    op.create_table(
        "order_status_history",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer,
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", order_status, nullable=True),
        sa.Column("to_status", order_status, nullable=False),
        sa.Column("reason", sa.Text),
        sa.Column(
            "changed_by_staff_id",
            sa.Integer,
            sa.ForeignKey("staff_users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "changed_by_master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )
    op.create_index(
        "ix_order_status_history__order_created_at",
        "order_status_history",
        ["order_id", "created_at"],
    )

    # ==== Offers ====
    op.create_table(
        "offers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer,
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("round_number", sa.SmallInteger, nullable=False, server_default="1"),
        sa.Column("state", offer_state, nullable=False),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint("order_id", "master_id", name="uq_offers__order_master"),
    )
    op.create_index("ix_offers__order_state", "offers", ["order_id", "state"])
    op.create_index("ix_offers__master_state", "offers", ["master_id", "state"])
    # partial unique: one ACCEPTED offer per order
    op.create_index(
        "uix_offers__order_accepted_once",
        "offers",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("state = 'ACCEPTED'"),
    )
    op.create_index("ix_offers__expires_at", "offers", ["expires_at"])

    # ==== Attachments ====
    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_type", attachment_entity, nullable=False),
        sa.Column("entity_id", sa.BigInteger, nullable=False),
        sa.Column("file_type", attachment_file_type, nullable=False),
        sa.Column("file_id", sa.String(length=256), nullable=False),
        sa.Column("file_unique_id", sa.String(length=256)),
        sa.Column("file_name", sa.String(length=256)),
        sa.Column("mime_type", sa.String(length=128)),
        sa.Column("size", sa.Integer),
        sa.Column("caption", sa.Text),
        sa.Column(
            "uploaded_by_master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "uploaded_by_staff_id",
            sa.Integer,
            sa.ForeignKey("staff_users.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )
    op.create_index(
        "ix_attachments__etype_eid", "attachments", ["entity_type", "entity_id"]
    )

    # ==== Commissions ====
    op.create_table(
        "commissions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer,
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("percent", sa.Numeric(5, 2)),
        sa.Column("status", commission_status, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column(
            "blocked_applied",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("blocked_at", sa.DateTime(timezone=True)),
        sa.Column("payment_reference", sa.String(length=120)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )
    op.create_index("ix_commissions__status_due", "commissions", ["status", "due_at"])
    op.create_index(
        "ix_commissions__master_status", "commissions", ["master_id", "status"]
    )

    # ==== Referrals ====
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "referrer_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )
    op.create_index("ix_referrals__master", "referrals", ["master_id"])
    op.create_index("ix_referrals__referrer", "referrals", ["referrer_id"])

    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "referrer_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "referred_master_id",
            sa.Integer,
            sa.ForeignKey("masters.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "commission_id",
            sa.Integer,
            sa.ForeignKey("commissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.SmallInteger, nullable=False),
        sa.Column("percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column("status", referral_reward_status, nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.UniqueConstraint(
            "referrer_id",
            "commission_id",
            "level",
            name="uq_referral_rewards__once_per_level",
        ),
    )
    op.create_index(
        "ix_ref_rewards__referrer_status", "referral_rewards", ["referrer_id", "status"]
    )
    op.create_index(
        "ix_ref_rewards__referred", "referral_rewards", ["referred_master_id"]
    )
    op.create_index("ix_ref_rewards__commission", "referral_rewards", ["commission_id"])

    # ==== Settings ====
    op.create_table(
        "settings",
        sa.Column("key", sa.String(length=80), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column(
            "value_type", sa.String(length=16), nullable=False, server_default="STR"
        ),
        sa.Column("description", sa.Text),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")
        ),
    )


def downgrade() -> None:
    op.drop_table("settings")

    op.drop_index("ix_ref_rewards__commission", table_name="referral_rewards")
    op.drop_index("ix_ref_rewards__referred", table_name="referral_rewards")
    op.drop_index("ix_ref_rewards__referrer_status", table_name="referral_rewards")
    op.drop_table("referral_rewards")

    op.drop_index("ix_referrals__referrer", table_name="referrals")
    op.drop_index("ix_referrals__master", table_name="referrals")
    op.drop_table("referrals")

    op.drop_index("ix_commissions__master_status", table_name="commissions")
    op.drop_index("ix_commissions__status_due", table_name="commissions")
    op.drop_table("commissions")

    op.drop_index("ix_attachments__etype_eid", table_name="attachments")
    op.drop_table("attachments")

    op.drop_index("uix_offers__order_accepted_once", table_name="offers")
    op.drop_index("ix_offers__master_state", table_name="offers")
    op.drop_index("ix_offers__order_state", table_name="offers")
    op.drop_table("offers")

    op.drop_index(
        "ix_order_status_history__order_created_at", table_name="order_status_history"
    )
    op.drop_table("order_status_history")

    op.drop_index("ix_orders__street_id", table_name="orders")
    op.drop_index("ix_orders__district_id", table_name="orders")
    op.drop_index("ix_orders__city_id", table_name="orders")
    op.drop_index("ix_orders__phone", table_name="orders")
    op.drop_index("ix_orders__created_at", table_name="orders")
    op.drop_index("ix_orders__preferred_master", table_name="orders")
    op.drop_index("ix_orders__assigned_master", table_name="orders")
    op.drop_index("ix_orders__city_status", table_name="orders")
    op.drop_index("ix_orders__status_city_date", table_name="orders")
    op.drop_table("orders")

    op.drop_index("ix_masters__heartbeat", table_name="masters")
    op.drop_index("ix_masters__referred_by", table_name="masters")
    op.drop_index("ix_masters__city_id", table_name="masters")
    op.drop_index("ix_masters__phone", table_name="masters")
    op.drop_index("ix_masters__tg_user_id", table_name="masters")
    op.drop_table("masters")

    op.drop_table("staff_cities")
    op.drop_index("ix_staff_users__tg_user_id", table_name="staff_users")
    op.drop_table("staff_users")

    op.drop_index("ix_streets__district_id", table_name="streets")
    op.drop_index("ix_streets__city_id", table_name="streets")
    op.drop_table("streets")

    op.drop_index("ix_districts__city_id", table_name="districts")
    op.drop_table("districts")

    op.drop_table("cities")

    # drop enums
    for enum_name in (
        "staff_role",
        "referral_reward_status",
        "commission_status",
        "attachment_file_type",
        "attachment_entity",
        "offer_state",
        "order_status",
    ):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
