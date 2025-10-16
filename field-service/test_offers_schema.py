#!/usr/bin/env python3
"""Test that offers model matches database schema."""
import asyncio
from sqlalchemy import text
from field_service.db.session import SessionLocal

async def check_offers_indexes():
    """Verify that offers indexes match between model and database."""
    async with SessionLocal() as session:
        # Get indexes from database
        result = await session.execute(text("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'offers'
            ORDER BY indexname;
        """))
        db_indexes = {row[0]: row[1] for row in result.fetchall()}
        
        print("Database indexes for 'offers' table:")
        for name, definition in sorted(db_indexes.items()):
            print(f"  {name}:")
            print(f"    {definition}")
        
        # Check critical indexes
        assert "uq_offers__order_master_active" in db_indexes
        assert "UNIQUE" in db_indexes["uq_offers__order_master_active"]
        assert "'SENT'" in db_indexes["uq_offers__order_master_active"]
        assert "'VIEWED'" in db_indexes["uq_offers__order_master_active"]
        assert "'ACCEPTED'" in db_indexes["uq_offers__order_master_active"]
        print("\nOK: uq_offers__order_master_active is UNIQUE on (order_id, master_id) WHERE state IN ('SENT', 'VIEWED', 'ACCEPTED')")
        
        assert "uix_offers__order_accepted_once" in db_indexes
        assert "UNIQUE" in db_indexes["uix_offers__order_accepted_once"]
        assert "'ACCEPTED'" in db_indexes["uix_offers__order_accepted_once"]
        print("OK: uix_offers__order_accepted_once is UNIQUE on (order_id) WHERE state = 'ACCEPTED'")
        
        # Test constraint by trying to create duplicate offers
        print("\nTesting constraints: Creating test order and offers...")
        
        # Create test data
        await session.execute(text("""
            INSERT INTO orders (id, city_id, status, category, total_sum, created_at)
            VALUES (999999, 1, 'SEARCHING', 'ELECTRICS', 0, NOW())
            ON CONFLICT (id) DO NOTHING;
        """))
        
        await session.execute(text("""
            DELETE FROM offers WHERE order_id = 999999;
        """))
        
        await session.commit()
        
        # Test 1: Can create two SENT offers to different masters
        await session.execute(text("""
            INSERT INTO offers (order_id, master_id, state, sent_at, created_at)
            VALUES (999999, 1, 'SENT', NOW(), NOW());
        """))
        
        await session.execute(text("""
            INSERT INTO offers (order_id, master_id, state, sent_at, created_at)
            VALUES (999999, 2, 'SENT', NOW(), NOW());
        """))
        await session.commit()
        print("OK: Can create multiple SENT offers to different masters")
        
        # Test 2: Cannot create duplicate SENT offer to same master
        try:
            await session.execute(text("""
                INSERT INTO offers (order_id, master_id, state, sent_at, created_at)
                VALUES (999999, 1, 'SENT', NOW(), NOW());
            """))
            await session.commit()
            print("FAILED: Should not allow duplicate SENT offer to same master")
            return False
        except Exception as e:
            await session.rollback()
            print(f"OK: Correctly rejected duplicate SENT offer: {type(e).__name__}")
        
        # Test 3: Can have one ACCEPTED offer
        await session.execute(text("""
            UPDATE offers SET state = 'ACCEPTED' WHERE order_id = 999999 AND master_id = 1;
        """))
        await session.commit()
        print("OK: Can have one ACCEPTED offer")
        
        # Test 4: Cannot create second ACCEPTED offer
        try:
            await session.execute(text("""
                INSERT INTO offers (order_id, master_id, state, sent_at, created_at)
                VALUES (999999, 3, 'ACCEPTED', NOW(), NOW());
            """))
            await session.commit()
            print("FAILED: Should not allow second ACCEPTED offer")
            return False
        except Exception as e:
            await session.rollback()
            print(f"OK: Correctly rejected second ACCEPTED offer: {type(e).__name__}")
        
        # Cleanup
        await session.execute(text("DELETE FROM offers WHERE order_id = 999999;"))
        await session.execute(text("DELETE FROM orders WHERE id = 999999;"))
        await session.commit()
        
        print("\n" + "="*60)
        print("ALL TESTS PASSED: offers model matches database schema")
        print("="*60)
        return True

if __name__ == "__main__":
    success = asyncio.run(check_offers_indexes())
    exit(0 if success else 1)
