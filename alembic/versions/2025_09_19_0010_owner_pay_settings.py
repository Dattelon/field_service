"""owner pay settings (snapshot for commissions)"""

from alembic import op

revision = "2025_09_19_0010"
down_revision = "2025_09_19_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
    INSERT INTO settings(key,value,value_type,description) VALUES
    ('owner_pay_methods_enabled','["card","sbp"]','JSON','   '),
    ('owner_pay_card_number','2200123456789012','STR','  ( )'),
    ('owner_pay_card_holder',' ..','STR',' '),
    ('owner_pay_card_bank','-','STR',''),
    ('owner_pay_sbp_phone','+79991234567','STR',' '),
    ('owner_pay_sbp_bank','-','STR',' '),
    ('owner_pay_sbp_qr_file_id','','STR','QR file_id (Telegram)'),
    ('owner_pay_other_text','','STR','  ()'),
    ('owner_pay_comment_template',' #<order_id>  <master_fio>','STR','   ')
    ON CONFLICT (key) DO NOTHING
    """
    )


def downgrade() -> None:
    #    
    pass
