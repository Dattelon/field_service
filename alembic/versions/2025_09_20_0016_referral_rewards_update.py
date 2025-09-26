"""adjust referral reward constraints"""

from alembic import op


revision = "2025_09_20_0016"
down_revision = "2025_09_20_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("referral_rewards") as batch_op:
        batch_op.drop_constraint(
            "uq_referral_rewards__once_per_level",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_referral_rewards__commission_level",
            ["commission_id", "level"],
        )

    op.drop_index("ix_ref_rewards__commission", table_name="referral_rewards")
    op.create_index(
        "ix_ref_rewards__referrer_created",
        "referral_rewards",
        ["referrer_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ref_rewards__referrer_created",
        table_name="referral_rewards",
    )
    op.create_index(
        "ix_ref_rewards__commission",
        "referral_rewards",
        ["commission_id"],
    )

    with op.batch_alter_table("referral_rewards") as batch_op:
        batch_op.drop_constraint(
            "uq_referral_rewards__commission_level",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_referral_rewards__once_per_level",
            ["referrer_id", "commission_id", "level"],
        )
