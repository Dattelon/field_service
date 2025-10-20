"""admin bot core schema upgrades"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "2025_09_19_0014"
down_revision = "2025_09_19_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extend staff_role with CITY_ADMIN (if not already present)
    op.execute("ALTER TYPE staff_role ADD VALUE IF NOT EXISTS 'CITY_ADMIN'")

    # Order type enum + related columns
    order_type = postgresql.ENUM("NORMAL", "GUARANTEE", name="order_type")
    order_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "orders",
        sa.Column(
            "order_type",
            order_type,
            nullable=False,
            server_default="NORMAL",
        ),
    )
    op.add_column(
        "orders",
        sa.Column("category", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column(
            "late_visit",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Ensure new columns have sensible defaults for existing rows
    op.execute("UPDATE orders SET order_type='NORMAL' WHERE order_type IS NULL")
    op.execute("UPDATE orders SET company_payment=0 WHERE company_payment IS NULL")
    op.execute("UPDATE orders SET late_visit=FALSE WHERE late_visit IS NULL")

    # Staff access code multi-city support
    op.add_column(
        "staff_access_codes",
        sa.Column("comment", sa.Text(), nullable=True),
    )
    op.create_table(
        "staff_access_code_cities",
        sa.Column(
            "access_code_id",
            sa.Integer,
            sa.ForeignKey("staff_access_codes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "city_id",
            sa.Integer,
            sa.ForeignKey("cities.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_staff_code_cities__code",
        "staff_access_code_cities",
        ["access_code_id"],
    )
    op.create_index(
        "ix_staff_code_cities__city",
        "staff_access_code_cities",
        ["city_id"],
    )
    op.execute(
        """
        INSERT INTO staff_access_code_cities(access_code_id, city_id, created_at)
        SELECT id, city_id, NOW()
          FROM staff_access_codes
         WHERE city_id IS NOT NULL
        ON CONFLICT DO NOTHING
        """
    )


def downgrade() -> None:
    # Drop multi-city mapping table
    op.drop_index("ix_staff_code_cities__city", table_name="staff_access_code_cities")
    op.drop_index("ix_staff_code_cities__code", table_name="staff_access_code_cities")
    op.drop_table("staff_access_code_cities")
    op.drop_column("staff_access_codes", "comment")

    # Drop order-related additions
    op.drop_column("orders", "late_visit")
    op.drop_column("orders", "longitude")
    op.drop_column("orders", "latitude")
    op.drop_column("orders", "description")
    op.drop_column("orders", "category")
    op.drop_column("orders", "order_type")

    order_type = postgresql.ENUM("NORMAL", "GUARANTEE", name="order_type")
    order_type.drop(op.get_bind(), checkfirst=True)

    # Note: reverting enum value CITY_ADMIN is not supported (no action)
