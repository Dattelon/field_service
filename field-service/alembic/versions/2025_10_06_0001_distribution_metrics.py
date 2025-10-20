"""Add distribution_metrics table for analytics

Revision ID: 2025_10_06_0001
Revises: 2025_10_05_0005
Create Date: 2025-10-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '2025_10_06_0001'
down_revision = '2025_10_05_0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создание таблицы distribution_metrics
    op.create_table(
        'distribution_metrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('master_id', sa.Integer(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('round_number', sa.SmallInteger(), nullable=False),
        sa.Column('candidates_count', sa.SmallInteger(), nullable=False),
        sa.Column('time_to_assign_seconds', sa.Integer(), nullable=True),
        sa.Column('preferred_master_used', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('was_escalated_to_logist', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('was_escalated_to_admin', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('city_id', sa.Integer(), nullable=False),
        sa.Column('district_id', sa.Integer(), nullable=True),
        sa.Column('category', sa.Enum('ELECTRICS', 'PLUMBING', 'APPLIANCES', 'WINDOWS', 'HANDYMAN', 'ROADSIDE', name='ordercategory'), nullable=True),
        sa.Column('order_type', sa.String(length=32), nullable=True),
        sa.Column('metadata_json', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['master_id'], ['masters.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['city_id'], ['cities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['district_id'], ['districts.id'], ondelete='SET NULL'),
    )
    
    # Создание индексов для быстрого поиска и аналитики
    op.create_index('ix_distribution_metrics_order_id', 'distribution_metrics', ['order_id'])
    op.create_index('ix_distribution_metrics_master_id', 'distribution_metrics', ['master_id'])
    op.create_index('ix_distribution_metrics_assigned_at', 'distribution_metrics', ['assigned_at'])
    op.create_index('ix_distribution_metrics_city_id', 'distribution_metrics', ['city_id'])
    op.create_index('ix_distribution_metrics_district_id', 'distribution_metrics', ['district_id'])
    op.create_index('ix_distribution_metrics__assigned_at_desc', 'distribution_metrics', ['assigned_at'], postgresql_using='btree')
    op.create_index('ix_distribution_metrics__city_assigned', 'distribution_metrics', ['city_id', 'assigned_at'])
    op.create_index('ix_distribution_metrics__performance', 'distribution_metrics', ['round_number', 'time_to_assign_seconds'])


def downgrade() -> None:
    # Удаление индексов
    op.drop_index('ix_distribution_metrics__performance', table_name='distribution_metrics')
    op.drop_index('ix_distribution_metrics__city_assigned', table_name='distribution_metrics')
    op.drop_index('ix_distribution_metrics__assigned_at_desc', table_name='distribution_metrics')
    op.drop_index('ix_distribution_metrics_district_id', table_name='distribution_metrics')
    op.drop_index('ix_distribution_metrics_city_id', table_name='distribution_metrics')
    op.drop_index('ix_distribution_metrics_assigned_at', table_name='distribution_metrics')
    op.drop_index('ix_distribution_metrics_master_id', table_name='distribution_metrics')
    op.drop_index('ix_distribution_metrics_order_id', table_name='distribution_metrics')
    
    # Удаление таблицы
    op.drop_table('distribution_metrics')
