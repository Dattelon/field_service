"""make actor_type not null with default SYSTEM

Revision ID: 2025_10_16_0002
Revises: 2025_10_16_0001
Create Date: 2025-10-16 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "2025_10_16_0002"
down_revision = "2025_10_16_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Make actor_type NOT NULL with default SYSTEM.
    
    Steps:
    1. Fill existing NULL values with 'SYSTEM'
    2. Set column default to 'SYSTEM'
    3. Make column NOT NULL
    """
    # Step 1: Fill existing NULL values
    op.execute(
        """
        UPDATE order_status_history
        SET actor_type = 'SYSTEM'
        WHERE actor_type IS NULL
        """
    )
    
    # Step 2: Set default value for new rows
    op.alter_column(
        "order_status_history",
        "actor_type",
        server_default="SYSTEM",
        nullable=True  # still nullable for now
    )
    
    # Step 3: Make column NOT NULL
    op.alter_column(
        "order_status_history",
        "actor_type",
        nullable=False
    )


def downgrade() -> None:
    """Revert actor_type to nullable without default."""
    # Step 1: Make column nullable
    op.alter_column(
        "order_status_history",
        "actor_type",
        nullable=True
    )
    
    # Step 2: Remove default
    op.alter_column(
        "order_status_history",
        "actor_type",
        server_default=None
    )
