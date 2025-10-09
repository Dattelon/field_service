"""Add detailed history tracking to order_status_history

Revision ID: 2025_10_09_0001
Revises: 2025_10_06_0001
Create Date: 2025-10-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = '2025_10_09_0001'
down_revision = '2025_10_06_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Создание ENUM для типа актора
    op.execute("""
        CREATE TYPE actor_type AS ENUM (
            'SYSTEM',
            'ADMIN', 
            'MASTER',
            'AUTO_DISTRIBUTION'
        )
    """)
    
    # Добавление новых полей
    op.add_column(
        'order_status_history',
        sa.Column('actor_type', sa.Enum('SYSTEM', 'ADMIN', 'MASTER', 'AUTO_DISTRIBUTION', name='actor_type'), nullable=True)
    )
    
    op.add_column(
        'order_status_history',
        sa.Column('context', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb"))
    )
    
    # Заполнение actor_type для существующих записей на основе имеющихся данных
    op.execute("""
        UPDATE order_status_history
        SET actor_type = CASE
            WHEN changed_by_staff_id IS NOT NULL THEN 'ADMIN'::actor_type
            WHEN changed_by_master_id IS NOT NULL THEN 'MASTER'::actor_type
            WHEN reason LIKE '%auto%' OR reason LIKE '%distribution%' THEN 'AUTO_DISTRIBUTION'::actor_type
            ELSE 'SYSTEM'::actor_type
        END
        WHERE actor_type IS NULL
    """)
    
    # Делаем actor_type обязательным после заполнения
    op.alter_column('order_status_history', 'actor_type', nullable=False)
    
    # Создание индекса для быстрого поиска по типу актора
    op.create_index('ix_order_status_history__actor_type', 'order_status_history', ['actor_type'])


def downgrade() -> None:
    # Удаление индекса
    op.drop_index('ix_order_status_history__actor_type', table_name='order_status_history')
    
    # Удаление колонок
    op.drop_column('order_status_history', 'context')
    op.drop_column('order_status_history', 'actor_type')
    
    # Удаление ENUM типа
    op.execute("DROP TYPE actor_type")
