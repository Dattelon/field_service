from pathlib import Path

path = Path('field-service/field_service/services/commission_service.py')
text = path.read_text(encoding='utf-8')
if 'from typing import Sequence' not in text:
    text = text.replace('from decimal import Decimal\n\nfrom sqlalchemy', 'from decimal import Decimal\nfrom typing import Sequence\n\nfrom sqlalchemy')
text = text.replace('from sqlalchemy import func', 'from sqlalchemy import func, select, update')
if 'async def apply_overdue_commissions' not in text:
    text = text.rstrip() + '\n\n\nasync def apply_overdue_commissions(\n    session: AsyncSession, *, now: datetime | None = None\n) -> Sequence[int]:\n    """Mark expired WAIT_PAY commissions as OVERDUE and block masters."""\n\n    current_time = now or datetime.now(UTC)\n\n    result = await session.execute(\n        select(m.commissions.id, m.commissions.master_id)\n        .where(\n            (m.commissions.status == m.CommissionStatus.WAIT_PAY)\n            & (m.commissions.deadline_at < current_time)\n            & (m.commissions.blocked_applied.is_(False))\n        )\n        .with_for_update()\n    )\n    rows = result.all()\n    if not rows:\n        return []\n\n    commission_ids = [row.id for row in rows]\n    master_ids = sorted({row.master_id for row in rows if row.master_id is not None})\n\n    await session.execute(\n        update(m.commissions)\n        .where(m.commissions.id.in_(commission_ids))\n        .values(\n            status=m.CommissionStatus.OVERDUE,\n            blocked_applied=True,\n            blocked_at=current_time,\n            updated_at=func.now(),\n        )\n    )\n\n    if master_ids:\n        await session.execute(\n            update(m.masters)\n            .where(m.masters.id.in_(master_ids))\n            .values(\n                is_blocked=True,\n                blocked_at=current_time,\n                blocked_reason='commission_overdue',\n            )\n        )\n\n    return master_ids\n'
path.write_text(text, encoding='utf-8')
