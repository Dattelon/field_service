from __future__ import annotations

import asyncio
import os
import random
import string
from datetime import datetime

from sqlalchemy import text

os.environ.setdefault("PYTHONASYNCDEBUG", "0")


async def main() -> int:
    print("== Smoke: imports ==")
    try:
        from field_service.db.session import SessionLocal
        from field_service.db.pg_enums import (
            commission_status_param as cs_param,
            staff_role_param as sr_param,
        )
        from field_service.services import settings_service as ss
        import field_service.bots.admin_bot.handlers as adm_handlers
        import field_service.bots.admin_bot.handlers_staff as adm_staff
        import field_service.bots.master_bot.handlers as master_handlers

        print("imports: OK")
    except Exception as e:
        print("imports: FAIL:", repr(e))
        return 1

    print("\n== Smoke: DB connectivity ==")
    try:
        async with SessionLocal() as s:
            ver = await s.execute(text("select version(), now()"))
            v = ver.first()
            print("db:", v[0].split()[0], v[1])
    except Exception as e:
        print("db: FAIL:", repr(e))
        return 1

    print("\n== Smoke: finance query per status ==")
    try:
        async with SessionLocal() as s:
            for st in ("PENDING", "OVERDUE", "PAID"):
                q = await s.execute(
                    text(
                        """
                        SELECT count(*)
                          FROM commissions c
                         WHERE c.status = :st
                        """
                    ).bindparams(cs_param("st", st))
                )
                print(f"commissions[{st}] =", int(q.scalar_one()))
        print("finance: OK")
    except Exception as e:
        print("finance: FAIL:", repr(e))
        return 1

    print("\n== Smoke: staff_access_codes insert/delete ==")
    code = "T" + "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(7)
    )
    try:
        async with SessionLocal() as s:
            await s.execute(
                text(
                    """
                    INSERT INTO staff_access_codes (code, role, issued_by_staff_id)
                    VALUES (:c, :r, (SELECT id FROM staff_users WHERE tg_user_id=:tg LIMIT 1))
                    """
                ).bindparams(sr_param("r", "ADMIN"), c=code, tg=0)
            )
            await s.execute(
                text("DELETE FROM staff_access_codes WHERE code=:c").bindparams(c=code)
            )
            await s.commit()
        print("codes: OK")
    except Exception as e:
        print("codes: FAIL:", repr(e))
        return 1

    print("\n== Smoke: settings service ==")
    try:
        start, end = await ss.get_working_window()
        print("working_window:", start, end)
        print("settings: OK")
    except Exception as e:
        print("settings: FAIL:", repr(e))
        return 1

    print("\n== Smoke: timezone ==")
    try:
        tz = ss.get_timezone()
        print("zone:", tz)
    except Exception as e:
        print("timezone: FAIL:", repr(e))
        return 1

    print("\nAll smoke checks passed at", datetime.now())
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
