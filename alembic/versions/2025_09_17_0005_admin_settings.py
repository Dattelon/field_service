"""admin_settings: dynamic working hours, admin requisites, seed keys
Revision ID: 2025_09_17_0005
Revises: 2025_09_17_0004
Create Date: 2025-09-17 20:10:00.000000
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2025_09_17_0005"
down_revision = "2025_09_17_0004"
branch_labels = None
depends_on = None

def upgrade() -> None:
    # 1) orders: заменить CHECK на динамично-нейтральный
    op.drop_constraint("ck_orders__slot_in_working_window", "orders", type_="check")
    op.create_check_constraint(
        "ck_orders__slot_interval_valid",
        "orders",
        "(time_slot_start IS NULL AND time_slot_end IS NULL) OR (time_slot_start < time_slot_end)"
    )

    # 2) staff_users: реквизиты админа для комиссий
    op.add_column(
        "staff_users",
        sa.Column(
            "commission_requisites",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb")
        ),
    )

    # 3) settings: базовые ключи
    op.execute("""
    INSERT INTO settings(key, value, value_type, description) VALUES
        ('working_hours_start','10:00','TIME','Начало рабочего окна'),
        ('working_hours_end','20:00','TIME','Конец рабочего окна'),
        ('slot_step_minutes','120','INT','Шаг генерации слотов (мин)'),
        ('distribution_sla_seconds','120','INT','SLA оффера (сек)'),
        ('distribution_rounds','2','INT','Круги до эскалации'),
        ('commission_deadline_hours','3','INT','Дедлайн оплаты комиссии (часы)'),
        ('max_active_orders','1','INT','Лимит активных заказов на мастера')
    ON CONFLICT (key) DO NOTHING
    """)

def downgrade() -> None:
    # settings — откатывать значения не будем
    op.drop_column("staff_users", "commission_requisites")
    op.drop_constraint("ck_orders__slot_interval_valid", "orders", type_="check")
    # возвращать «жёсткий» CHECK небезопасно, поэтому не делаем
