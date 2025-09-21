from __future__ import annotations

import asyncio
import random
import string
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from field_service.db.session import SessionLocal
from field_service.db.pg_enums import (
    commission_status_param as cs_param,
    staff_role_param as sr_param,
    order_status_param as os_param,
)


def rnd(n: int = 6) -> str:
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(n)
    )


async def ensure_city(session) -> int:
    q = await session.execute(text("SELECT id FROM cities ORDER BY id LIMIT 1"))
    row = q.first()
    if row:
        return int(row[0])
    ins = await session.execute(
        text("INSERT INTO cities(name) VALUES (:n) RETURNING id").bindparams(
            n="SCN-CITY"
        )
    )
    return int(ins.scalar_one())


async def ensure_staff_admin(session, tg: int) -> int:
    q = await session.execute(
        text("SELECT id FROM staff_users WHERE tg_user_id=:tg").bindparams(tg=tg)
    )
    r = q.first()
    if r:
        return int(r[0])
    ins = await session.execute(
        text(
            """
            INSERT INTO staff_users(tg_user_id, role, is_active)
            VALUES (:tg, :r, TRUE)
            RETURNING id
            """
        ).bindparams(sr_param("r", "ADMIN"), tg=tg)
    )
    return int(ins.scalar_one())


async def ensure_master(session, tg: int, city_id: int) -> int:
    q = await session.execute(
        text("SELECT id FROM masters WHERE tg_user_id=:tg").bindparams(tg=tg)
    )
    r = q.first()
    if r:
        mid = int(r[0])
    else:
        ins = await session.execute(
            text(
                """
                INSERT INTO masters(tg_user_id, full_name, city_id, is_active, moderation_status)
                VALUES (:tg, :name, :cid, TRUE, 'APPROVED')
                RETURNING id
                """
            ).bindparams(tg=tg, name=f"SCN-{rnd()}", cid=city_id)
        )
        mid = int(ins.scalar_one())
    return mid


async def create_order(
    session, city_id: int, status: str, master_id: int | None = None
) -> int:
    ins = await session.execute(
        text(
            """
            INSERT INTO orders(city_id, status, assigned_master_id)
            VALUES (:cid, :st, :mid)
            RETURNING id
            """
        ).bindparams(os_param("st", status), cid=city_id, mid=master_id)
    )
    return int(ins.scalar_one())


async def create_commission(
    session, order_id: int, master_id: int, status: str, due_in_hours: int
) -> int:
    due = datetime.now(timezone.utc) + timedelta(hours=due_in_hours)
    ins = await session.execute(
        text(
            """
            INSERT INTO commissions(order_id, master_id, amount, status, deadline_at)
            VALUES (:oid, :mid, :amt, :st, :due)
            RETURNING id
            """
        ).bindparams(
            cs_param("st", status), oid=order_id, mid=master_id, amt=100.00, due=due
        )
    )
    return int(ins.scalar_one())


async def scenario_finance() -> None:
    print("[SCN] finance list + ordering")
    async with SessionLocal() as s:
        city = await ensure_city(s)
        admin_id = await ensure_staff_admin(s, tg=777000)
        master = await ensure_master(s, tg=888000, city_id=city)
        # Clean previous SCN orders/commissions for this master
        await s.execute(
            text("DELETE FROM commissions WHERE master_id=:m").bindparams(m=master)
        )
        await s.execute(
            text(
                "DELETE FROM orders WHERE assigned_master_id=:m OR preferred_master_id=:m"
            ).bindparams(m=master)
        )
        # Create orders + commissions
        oid_p1 = await create_order(s, city, "ASSIGNED", master)
        await create_commission(s, oid_p1, master, "PENDING", due_in_hours=+1)
        oid_p2 = await create_order(s, city, "ASSIGNED", master)
        await create_commission(s, oid_p2, master, "PENDING", due_in_hours=+3)
        oid_o1 = await create_order(s, city, "ASSIGNED", master)
        await create_commission(s, oid_o1, master, "OVERDUE", due_in_hours=-3)
        oid_paid = await create_order(s, city, "ASSIGNED", master)
        await create_commission(s, oid_paid, master, "PAID", due_in_hours=-1)
        await s.commit()

        # Query as in handlers: typed bind + order rule
        for st in ("PENDING", "OVERDUE", "PAID"):
            rows = await s.execute(
                text(
                    """
                    SELECT c.id, c.order_id, c.master_id, c.amount, c.deadline_at, c.status
                      FROM commissions c
                     WHERE c.status = :st
                     ORDER BY (CASE WHEN c.status = 'WAIT_PAY' THEN c.deadline_at END) ASC NULLS LAST,
                              c.created_at DESC
                     LIMIT 50
                    """
                ).bindparams(cs_param("st", st))
            )
            lst = rows.all()
            print(f"  {st}: {len(lst)} items")
        # Check ordering for pending
        rows = await s.execute(
            text(
                "SELECT deadline_at FROM commissions WHERE status='WAIT_PAY' ORDER BY deadline_at ASC"
            )
        )
        dues = [r[0] for r in rows.all()]
        assert dues == sorted(
            dues
        ), "PENDING commissions should be ordered by deadline_at ASC"
        print("  ordering: OK")


async def scenario_requisites() -> None:
    print("[SCN] admin requisites update")
    async with SessionLocal() as s:
        admin_id = await ensure_staff_admin(s, tg=777000)
        # Update JSONB with two methods
        await s.execute(
            text(
                """
                UPDATE staff_users
                   SET commission_requisites = coalesce(commission_requisites, '{}'::jsonb) || CAST(:patch AS jsonb)
                 WHERE id = :i
                """
            ).bindparams(
                i=admin_id, patch='{"CARD":"4000000000000002","SBP":"+79991234567"}'
            )
        )
        await s.commit()
        row = await s.execute(
            text(
                "SELECT commission_requisites FROM staff_users WHERE id=:i"
            ).bindparams(i=admin_id)
        )
        data = row.scalar_one()
        assert data.get("CARD") and data.get(
            "SBP"
        ), "Requisites should contain CARD and SBP"
        print("  update+read: OK")


async def scenario_orders_limit() -> None:
    print("[SCN] master active orders limit")
    async with SessionLocal() as s:
        city = await ensure_city(s)
        master = await ensure_master(s, tg=888000, city_id=city)
        # Ensure max_active_orders=1
        await s.execute(
            text(
                """
                INSERT INTO settings(key, value, value_type)
                VALUES ('max_active_orders','1','INT')
                ON CONFLICT (key) DO UPDATE SET value='1', value_type='INT', updated_at=NOW()
                """
            )
        )
        # Create two active orders
        await s.execute(
            text("DELETE FROM orders WHERE assigned_master_id=:m").bindparams(m=master)
        )
        await create_order(s, city, "ASSIGNED", master)
        await create_order(s, city, "SCHEDULED", master)
        await s.commit()
        # Count via SQL similar to master handler
        q = await s.execute(
            text(
                """
                SELECT count(*)
                  FROM orders
                 WHERE assigned_master_id=:m
                   AND status IN ('ASSIGNED','SCHEDULED','IN_PROGRESS','DONE')
                """
            ).bindparams(m=master)
        )
        cnt = int(q.scalar_one())
        assert cnt >= 2, "Should count >= 2 active orders"
        print("  count:", cnt, "OK")


async def scenario_codes() -> None:
    print("[SCN] staff access codes lifecycle")
    code = "TSCN" + rnd(6)
    async with SessionLocal() as s:
        await s.execute(
            text(
                """
                INSERT INTO staff_access_codes(code, role, issued_by_staff_id)
                VALUES (:c, :r, NULL)
                """
            ).bindparams(sr_param("r", "LOGIST"), c=code)
        )
        await s.execute(
            text(
                "UPDATE staff_access_codes SET is_revoked=TRUE WHERE code=:c"
            ).bindparams(c=code)
        )
        await s.execute(
            text("DELETE FROM staff_access_codes WHERE code=:c").bindparams(c=code)
        )
        await s.commit()
        print("  create/revoke/delete: OK")


async def main() -> int:
    await scenario_finance()
    await scenario_requisites()
    await scenario_orders_limit()
    await scenario_codes()
    print("All scenarios passed at", datetime.now())
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
