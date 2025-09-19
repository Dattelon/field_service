"""owner pay settings (snapshot for commissions)"""
from alembic import op

revision = "2025_09_19_0010"
down_revision = "2025_09_19_0009"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("""
    INSERT INTO settings(key,value,value_type,description) VALUES
    ('owner_pay_methods_enabled','["card","sbp"]','JSON','Разрешённые методы оплаты комиссии'),
    ('owner_pay_card_number','2200123456789012','STR','Номер карты (без пробелов)'),
    ('owner_pay_card_holder','Иванов И.И.','STR','Держатель карты'),
    ('owner_pay_card_bank','Т-Банк','STR','Банк'),
    ('owner_pay_sbp_phone','+79991234567','STR','Телефон СБП'),
    ('owner_pay_sbp_bank','Т-Банк','STR','Банк СБП'),
    ('owner_pay_sbp_qr_file_id','','STR','QR file_id (Telegram)'),
    ('owner_pay_other_text','','STR','Иной способ (текст)'),
    ('owner_pay_comment_template','Комиссия #<order_id> от <master_fio>','STR','Шаблон комментария к платежу')
    ON CONFLICT (key) DO NOTHING
    """)

def downgrade() -> None:
    # оставляем значения — безопаснее
    pass
