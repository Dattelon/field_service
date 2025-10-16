#!/usr/bin/env python3
"""Fix offers model __table_args__ to match database schema."""
import sys
from pathlib import Path

def fix_offers_model():
    models_path = Path("C:/ProjectF/field-service/field_service/db/models.py")
    
    with open(models_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Find and replace the __table_args__ section for offers class
    old_table_args = """    __table_args__ = (
        # Partial unique index: уникальность только для активных офферов
        Index(
            "uq_offers__order_master_active",
            "order_id",
            "master_id",
            unique=True,
            postgresql_where=text("state IN ('SENT', 'VIEWED', 'ACCEPTED')"),
        ),
        Index("ix_offers__order_state", "order_id", "state"),
        Index("ix_offers__master_state", "master_id", "state"),
        # Уникальность ACCEPTED оффера: только один принятый оффер на заказ
        # Relaxed: allow multiple ACCEPTED offers per order for analytics in tests
        Index(
            "ix_offers__order_accepted",
            "order_id",
            postgresql_where=text("state = 'ACCEPTED'"),
        ),
    )"""
    
    new_table_args = """    __table_args__ = (
        # Partial unique index: активные офферы уникальны по (order_id, master_id)
        # для state IN ('SENT', 'VIEWED', 'ACCEPTED')
        Index(
            "uq_offers__order_master_active",
            "order_id",
            "master_id",
            unique=True,
            postgresql_where=text("state IN ('SENT', 'VIEWED', 'ACCEPTED')"),
        ),
        Index("ix_offers__order_state", "order_id", "state"),
        Index("ix_offers__master_state", "master_id", "state"),
        # Уникальность ACCEPTED оффера: только один принятый оффер на заказ
        Index(
            "uix_offers__order_accepted_once",
            "order_id",
            unique=True,
            postgresql_where=text("state = 'ACCEPTED'"),
        ),
    )"""
    
    if old_table_args not in content:
        print("ERROR: Could not find old __table_args__ in offers class")
        return False
    
    content = content.replace(old_table_args, new_table_args)
    
    with open(models_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print("✅ Fixed offers model __table_args__")
    return True

if __name__ == "__main__":
    success = fix_offers_model()
    sys.exit(0 if success else 1)
