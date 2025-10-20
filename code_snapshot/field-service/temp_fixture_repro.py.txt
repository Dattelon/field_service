import asyncio
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from field_service.db import models as m
from field_service.db.base import metadata

DATABASE_URL = "postgresql+asyncpg://fs_user:fs_password@localhost:5439/field_service_test"

TABLES = [
    m.cities.__table__,
    m.districts.__table__,
    m.streets.__table__,
    m.staff_cities.__table__,
    m.staff_access_codes.__table__,
    m.staff_access_code_cities.__table__,
    m.masters.__table__,
    m.master_invite_codes.__table__,
    m.skills.__table__,
    m.master_skills.__table__,
    m.master_districts.__table__,
    m.offers.__table__,
    m.orders.__table__,
    m.attachments.__table__,
    m.commissions.__table__,
    m.commission_deadline_notifications.__table__,
    m.referrals.__table__,
    m.referral_rewards.__table__,
    m.order_status_history.__table__,
    m.settings.__table__,
    m.geocache.__table__,
    m.admin_audit_log.__table__,
    m.notifications_outbox.__table__,
    m.order_autoclose_queue.__table__,
    m.distribution_metrics.__table__,
]

def make_constraints_deferrable(sync_conn):
    inspector = sa.inspect(sync_conn)
    for table in TABLES:
        table_name = table.name
        schema = table.schema
        for fk in inspector.get_foreign_keys(table_name, schema=schema):
            constraint = fk.get("name")
            if not constraint:
                continue
            qualified_table = f"{schema}.{table_name}" if schema else table_name
            sync_conn.execute(
                sa.text(
                    f"ALTER TABLE {qualified_table} "
                    f"ALTER CONSTRAINT {constraint} DEFERRABLE INITIALLY DEFERRED"
                )
            )

async def clean_database(session: AsyncSession):
    tables_to_clean = [
        "commission_deadline_notifications",
        "order_status_history",
        "attachments",
        "offers",
        "commissions",
        "referrals",
        "referral_rewards",
        "notifications_outbox",
        "order_autoclose_queue",
        "distribution_metrics",
        "orders",
        "master_districts",
        "master_skills",
        "master_invite_codes",
        "masters",
        "staff_access_code_cities",
        "staff_access_codes",
        "staff_cities",
        "staff_users",
        "streets",
        "districts",
        "cities",
        "skills",
        "settings",
        "geocache",
        "admin_audit_log",
    ]
    try:
        for table in tables_to_clean:
            await session.execute(sa.text(f"TRUNCATE TABLE {table} CASCADE"))
        await session.commit()
    except Exception:
        await session.rollback()
        for table in tables_to_clean:
            try:
                await session.execute(sa.text(f"DELETE FROM {table}"))
            except Exception:
                pass
        await session.commit()

async def setup_engine():
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )
    async with engine.begin() as conn:
        await conn.execute(sa.text("DROP TYPE IF EXISTS staff_role CASCADE"))
        await conn.execute(sa.text("""
            CREATE TYPE staff_role AS ENUM ('GLOBAL_ADMIN', 'CITY_ADMIN', 'LOGIST')
        """))
        await conn.execute(sa.text("DROP TABLE IF EXISTS staff_users CASCADE"))
        await conn.execute(sa.text("""
            CREATE TABLE staff_users (
                id SERIAL PRIMARY KEY,
                tg_user_id BIGINT UNIQUE,
                username VARCHAR(64),
                full_name VARCHAR(160),
                phone VARCHAR(32),
                role staff_role NOT NULL,
                is_active BOOLEAN DEFAULT TRUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                commission_requisites TEXT DEFAULT '{}'
            )
        """))
        await conn.run_sync(metadata.create_all, tables=TABLES)
        await conn.run_sync(make_constraints_deferrable)
    return engine

async def main():
    engine = await setup_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        await clean_database(session)
        db_now = await session.scalar(sa.text("SELECT now()"))
        city = m.cities(id=1, name="City", is_active=True, timezone="UTC")
        session.add(city)
        master = m.masters(id=100, telegram_id=111, full_name="Master", city_id=1, moderation_status=m.ModerationStatus.APPROVED)
        session.add(master)
        order = m.orders(id=500, city_id=1, category=m.OrderCategory.ELECTRICS, type=m.OrderType.NORMAL, status=m.OrderStatus.SEARCHING, created_at=db_now)
        session.add(order)
        offer = m.offers(order_id=500, master_id=100, state=m.OfferState.SENT)
        session.add(offer)
        try:
            await session.commit()
            print('commit succeeded')
        except Exception as exc:
            import traceback
            traceback.print_exception(exc)
        finally:
            await session.rollback()
    await engine.dispose()

asyncio.run(main())
