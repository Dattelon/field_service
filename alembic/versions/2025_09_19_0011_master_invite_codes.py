"""master_invite_codes table (onboarding invite for masters)"""

from alembic import op
import sqlalchemy as sa

#      ;   0009,  
revision = "2025_09_19_0011b"
down_revision = "2025_09_19_0010"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "master_invite_codes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("city_id", sa.Integer, sa.ForeignKey("cities.id", ondelete="SET NULL")),
        sa.Column("issued_by_staff_id", sa.Integer, sa.ForeignKey("staff_users.id", ondelete="SET NULL")),
        sa.Column("used_by_master_id", sa.Integer, sa.ForeignKey("masters.id", ondelete="SET NULL")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("is_revoked", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("comment", sa.String(length=255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_master_invite_codes__code", "master_invite_codes", ["code"], unique=True)
    #     ( ,  )
    # NOTE: PostgreSQL requires IMMUTABLE functions in index predicates; NOW() is not allowed.
    # Use a stable predicate without time dependency; application code should validate expiry.
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ix_master_invite_codes__available
        ON master_invite_codes (code)
        WHERE used_by_master_id IS NULL AND is_revoked = FALSE AND expires_at IS NULL
        """
    )

def downgrade() -> None:
    op.drop_index("ix_master_invite_codes__available", table_name=None)  # raw SQL 
    op.drop_index("ix_master_invite_codes__code", table_name="master_invite_codes")
    op.drop_table("master_invite_codes")
