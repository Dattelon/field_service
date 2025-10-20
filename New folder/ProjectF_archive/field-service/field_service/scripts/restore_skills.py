from __future__ import annotations

import asyncio

from sqlalchemy import select

from field_service.db.session import SessionLocal
from field_service.db import models as m


SEED_SKILLS: tuple[tuple[str, str], ...] = (
    ("ELEC", "Электрика"),
    ("PLUMB", "Сантехника"),
    ("APPLI", "Бытовая техника"),
    ("WINDOWS", "Окна и остекление"),
    ("HANDY", "Мастер на все руки"),
    ("AUTOHELP", "Автопомощь"),
)


async def main() -> None:
    async with SessionLocal() as session:
        async with session.begin():
            existing_codes = set(
                code for (code,) in (await session.execute(select(m.skills.code))).all()
            )
            added = 0
            for code, name in SEED_SKILLS:
                if code in existing_codes:
                    # ensure active and name up to date
                    await session.execute(
                        m.skills.__table__.update().where(m.skills.code == code).values(name=name, is_active=True)
                    )
                else:
                    session.add(m.skills(code=code, name=name, is_active=True))
                    added += 1
        await session.commit()
    print(f"SKILLS RESTORE DONE: added={added}, total={(len(existing_codes)+added)}")


if __name__ == "__main__":
    asyncio.run(main())

