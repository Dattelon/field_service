"""
Alembic migration: Auto-close orders after 24 hours in CLOSED status

Revision ID: 0010_order_autoclose
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0010_order_autoclose'
down_revision = '2025_10_05_0004_add_centroids'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создаём таблицу для очереди автозакрытия
    op.create_table(
        'order_autoclose_queue',
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('orders.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('autoclose_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    
    # Индекс для поиска заказов готовых к автозакрытию
    op.create_index(
        'ix_order_autoclose_queue__pending',
        'order_autoclose_queue',
        ['autoclose_at'],
        postgresql_where=sa.text('processed_at IS NULL')
    )


def downgrade() -> None:
    op.drop_index('ix_order_autoclose_queue__pending', table_name='order_autoclose_queue')
    op.drop_table('order_autoclose_queue')
