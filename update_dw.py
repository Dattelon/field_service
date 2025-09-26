from __future__ import annotations

from pathlib import Path
import re

path = Path('field-service/field_service/services/distribution_worker.py')
text = path.read_text(encoding='utf-8')

def ensure_replace(src: str, old: str, new: str, label: str) -> str:
    if old not in src:
        raise SystemExit(f'Pattern not found for {label}')
    return src.replace(old, new, 1)

text = text.replace(
    'from datetime import datetime, timedelta, timezone',
    'from datetime import datetime, time, timedelta, timezone',
    1,
)
text = text.replace(
    'from sqlalchemy import select, text',
    'from sqlalchemy import insert, select, text',
    1,
)
if 'services.settings_service' not in text:
    text = ensure_replace(
        text,
        'from field_service.db import models as m\n',
        'from field_service.db import models as m\nfrom field_service.services.settings_service import get_timezone, get_working_window\n',
        'settings import',
    )

marker_line = '    return DistConfig(sla_seconds=sla, rounds=rnd, escalate_to_admin_after_min=esc)\n'
if 'ESCALATE_LOGIST_REASON' not in text:
    idx = text.index(marker_line) + len(marker_line)
    text = (
        text[:idx]
        + '\nESCALATE_LOGIST_REASON = "distribution_escalate_logist"\n'
        + 'ESCALATE_ADMIN_REASON = "distribution_escalate_admin"\n\n'
        + text[idx:]
    )

helper_block = '''def _coerce_status(value: Any) -> m.OrderStatus:
    if isinstance(value, m.OrderStatus):
        return value
    if value is None:
        return m.OrderStatus.SEARCHING
    try:
        return m.OrderStatus(str(value))
    except ValueError:
        return m.OrderStatus.SEARCHING


async def _get_escalation_time(
    session: AsyncSession | None, order: Any, reason: str
) -> datetime | None:
    if session is None:
        return getattr(order, f"_dw_escalated_dt_{reason}", None)
    row = await session.execute(
        text(
            """
        SELECT created_at
          FROM order_status_history
         WHERE order_id=:oid AND reason=:reason
         ORDER BY created_at DESC
         LIMIT 1
        """
        ).bindparams(oid=getattr(order, 'id'), reason=reason)
    )
    return row.scalar_one_or_none()


async def _ensure_escalation_record(
    session: AsyncSession | None, order: Any, reason: str
) -> tuple[datetime, bool]:
    marker_flag = f"_dw_escalated_{reason}"
    marker_dt = f"_dw_escalated_dt_{reason}"
    if session is None:
        if getattr(order, marker_flag, False):
            existing = getattr(order, marker_dt, _now())
            return existing, False
        stamp = _now()
        setattr(order, marker_flag, True)
        setattr(order, marker_dt, stamp)
        return stamp, True

    existing = await _get_escalation_time(session, order, reason)
    if existing:
        return existing, False

    status = _coerce_status(getattr(order, 'status', None))
    stamp = _now()
    await session.execute(
        insert(m.order_status_history).values(
            order_id=getattr(order, 'id'),
            from_status=status.value,
            to_status=status.value,
            reason=reason,
            created_at=stamp,
        )
    )
    return stamp, True


async def _maybe_escalate_admin(
    session: AsyncSession | None, cfg: DistConfig, order: Any
) -> None:
    minutes = max(0, int(cfg.escalate_to_admin_after_min))
    logistic_time = await _get_escalation_time(session, order, ESCALATE_LOGIST_REASON)
    if logistic_time is None:
        return

    if await _get_escalation_time(session, order, ESCALATE_ADMIN_REASON) is not None:
        return

    threshold = timedelta(minutes=minutes)
    if threshold <= timedelta(0):
        due = True
    else:
        due = logistic_time + threshold <= _now()

    if not due:
        return

    await _ensure_escalation_record(session, order, ESCALATE_ADMIN_REASON)
    print(log_escalate_admin(order.id))


'''

if '_coerce_status' not in text:
    anchor = 'def _now() -> datetime:\n    return datetime.now(UTC)\n\n'
    idx = text.index(anchor) + len(anchor)
    text = text[:idx] + '\n' + helper_block + text[idx:]

pattern_log_tick = r'def log_tick_header\([\s\S]+?\)\n\n\n'
replacement_log_tick = '''def log_tick_header(
    order_row: Any, round_num: int, rounds_total: int, sla: int, candidates_cnt: int
) -> str:
    raw_status = getattr(order_row, "status", None)
    raw_type = getattr(order_row, "order_type", None)
    status_value = _coerce_status(raw_status)
    if isinstance(raw_type, m.OrderType):
        type_value = raw_type.value
    elif raw_type:
        type_value = str(raw_type).upper()
    elif status_value == m.OrderStatus.GUARANTEE:
        type_value = m.OrderType.GUARANTEE.value
    else:
        type_value = m.OrderType.NORMAL.value
    district = getattr(order_row, "district_id", None)
    cat = (
        getattr(order_row, "category", None)
        or getattr(order_row, "category_code", None)
        or "-"
    )
    cat = str(cat).upper()
    return (
        f"[dist] order={order_row.id} city={order_row.city_id} "
        f"district={district if district is not None else '-'} cat={cat} type={type_value}\n"
        f"round={round_num}/{rounds_total} sla={sla}s candidates={candidates_cnt}"
    )


'''
text, count = re.subn(pattern_log_tick, replacement_log_tick, text, count=1)
if count != 1:
    raise SystemExit('log_tick_header replacement failed')

text = text.replace('>', '->')

pattern_skip_district = r'(def log_skip_no_district\(order_id: int\) -> str:\n\s+return f"\[dist] order=\{order_id\} skip_auto: no_district )[^\n"]+("\n)'
text, count = re.subn(pattern_skip_district, r"\\1-> escalate=logist_now\\2", text)
if count != 1:
    raise SystemExit('log_skip_no_district replacement failed')

log_escalate_block = '''def log_escalate(order_id: int) -> str:
    return f"[dist] order={order_id} candidates=0 -> escalate=logist"


'''
additional_logs = '''def log_escalate_admin(order_id: int) -> str:
    return f"[dist] order={order_id} escalate=admin"


def log_skip_preferred_master(mid: int, reason: str) -> str:
    return f"[dist] preferred_mid={mid} skip reason={reason}"


'''
text = ensure_replace(text, log_escalate_block, log_escalate_block + additional_logs, 'log_escalate extension')

old_force_block = '''    if force_preferred_first and preferred_master_id:
        idx = next(
            (i for i, x in enumerate(out) if int(x["mid"]) == int(preferred_master_id)),
            -1,
        )
        if idx >= 0:
            pm = out.pop(idx)
            out.insert(0, pm)
            print(log_force_first(int(preferred_master_id)))
    return out
'''
new_force_block = '''    if force_preferred_first and preferred_master_id:
        idx = next(
            (i for i, x in enumerate(out) if int(x["mid"]) == int(preferred_master_id)),
            -1,
        )
        if idx >= 0:
            pm = out.pop(idx)
            out.insert(0, pm)
            print(log_force_first(int(preferred_master_id)))
        else:
            print(log_skip_preferred_master(int(preferred_master_id), 'not_eligible'))
    return out
'''
text = ensure_replace(text, old_force_block, new_force_block, 'force_preferred block')

start = text.index('async def process_one_order(')
core_marker = '\n\n\n# ---------- core queries ----------'
end = text.index(core_marker)
old_process = text[start:end]
new_process = '''async def process_one_order(session: AsyncSession | None, cfg: DistConfig, o: Any) -> None:
    await _maybe_escalate_admin(session, cfg, o)

    if getattr(o, 'district_id', None) is None:
        await _ensure_escalation_record(session, o, ESCALATE_LOGIST_REASON)
        print(log_skip_no_district(o.id))
        await _maybe_escalate_admin(session, cfg, o)
        return

    if await has_active_sent_offer(session, o.id):
        return

    if await finalize_accepted_if_any(session, o.id):
        print(f"[dist] order={o.id} assigned_by_offer")
        return

    cur = await current_round(session, o.id)
    if cur >= cfg.rounds:
        await _ensure_escalation_record(session, o, ESCALATE_LOGIST_REASON)
        print(log_escalate(o.id))
        await _maybe_escalate_admin(session, cfg, o)
        return
    next_round = cur + 1

    order_type = getattr(o, 'order_type', None)
    status = getattr(o, 'status', None)
    is_guarantee = False
    if status is not None and str(status) == m.OrderStatus.GUARANTEE.value:
        is_guarantee = True
    if not is_guarantee and order_type is not None:
        try:
            is_guarantee = str(order_type) == m.OrderType.GUARANTEE.value
        except AttributeError:
            is_guarantee = str(order_type).upper() == 'GUARANTEE'

    category = getattr(o, 'category', None)
    skill_code = _skill_code_for_category(category)
    if skill_code is None:
        await _ensure_escalation_record(session, o, ESCALATE_LOGIST_REASON)
        print(log_skip_no_category(o.id, category))
        await _maybe_escalate_admin(session, cfg, o)
        return

    cand = await candidate_rows(
        session=session,
        order_id=o.id,
        city_id=o.city_id,
        district_id=o.district_id,
        preferred_master_id=o.preferred_master_id,
        skill_code=skill_code,
        limit=50,
        force_preferred_first=is_guarantee,
    )

    header = log_tick_header(o, next_round, cfg.rounds, cfg.sla_seconds, len(cand))
    print(header)
    if cand:
        top = cand[:10]
        ranked = ", ".join(
            fmt_rank_item(
                {
                    'mid': x['mid'],
                    'car': x['car'],
                    'avg_week': float(x['avg_week'] or 0),
                    'rating': float(x['rating'] or 0),
                    'rnd': float(x['rnd'] or 0),
                }
            )
            for x in top
        )
        print('ranked=[\n  ' + ranked + '\n]')

        first = cand[0]
        ok = await send_offer(
            session, o.id, int(first['mid']), next_round, cfg.sla_seconds
        )
        if ok:
            until = _now() + timedelta(seconds=cfg.sla_seconds)
            print(log_decision_offer(int(first['mid']), until))
        else:
            print(
                f"[dist] order={o.id} race_conflict: offer exists for mid={first['mid']}"
            )
    else:
        await _ensure_escalation_record(session, o, ESCALATE_LOGIST_REASON)
        print(log_escalate(o.id))
        await _maybe_escalate_admin(session, cfg, o)
        return

    await _maybe_escalate_admin(session, cfg, o)
'''
text = text.replace(old_process, new_process + '\n\n\n', 1)

window_helpers = '''# ---------- core queries ----------


async def _transition_orders(
    session: AsyncSession,
    *,
    old_status: m.OrderStatus,
    new_status: m.OrderStatus,
    reason: str,
) -> int:
    result = await session.execute(
        text(
            """
        UPDATE orders
           SET status=:new_status,
               updated_at=NOW(),
               version=version+1
         WHERE status=:old_status
           AND assigned_master_id IS NULL
         RETURNING id
        """
        ).bindparams(old_status=old_status.value, new_status=new_status.value)
    )
    order_ids = [row[0] for row in result.fetchall()]
    if not order_ids:
        return 0
    stamp = _now()
    await session.execute(
        insert(m.order_status_history),
        [
            {
                'order_id': oid,
                'from_status': old_status.value,
                'to_status': new_status.value,
                'reason': reason,
                'created_at': stamp,
            }
            for oid in order_ids
        ],
    )
    return len(order_ids)


async def _sync_working_window(
    session: AsyncSession, *, now_utc: datetime
) -> tuple[int, int, datetime]:
    tz = get_timezone()
    work_start, work_end = await get_working_window()
    now_local = now_utc.astimezone(tz)
    local_time = now_local.timetz()
    if getattr(local_time, 'tzinfo', None) is not None:
        local_time = local_time.replace(tzinfo=None)
    reopened = deferred = 0
    if work_start <= local_time < work_end:
        reopened = await _transition_orders(
            session,
            old_status=m.OrderStatus.DEFERRED,
            new_status=m.OrderStatus.SEARCHING,
            reason='working_window_open',
        )
    else:
        deferred = await _transition_orders(
            session,
            old_status=m.OrderStatus.SEARCHING,
            new_status=m.OrderStatus.DEFERRED,
            reason='working_window_closed',
        )
    return reopened, deferred, now_local


'''
text = ensure_replace(text, '# ---------- core queries ----------', window_helpers, 'core queries header')

start_tick = text.index('async def tick_once(')
end_tick = text.index('\n\n\n\nasync def run_loop(')
old_tick = text[start_tick:end_tick]
new_tick = '''async def tick_once() -> None:
    async with SessionLocal() as s:
        cfg = await _load_config(s)
        now = _now()

        reopened, deferred, now_local = await _sync_working_window(s, now_utc=now)
        if reopened:
            print(f"[dist] window_open reopened={reopened} at {now_local.isoformat()}")
        if deferred:
            print(f"[dist] window_closed deferred={deferred} at {now_local.isoformat()}")
        if reopened or deferred:
            await s.commit()

        expired = await expire_sent_offers(s, now)
        if expired:
            await s.commit()
        blocked = await autoblock_guarantee_timeouts(s)
        if blocked:
            await s.commit()
        declined_blocked = await autoblock_guarantee_declines(s)
        if declined_blocked:
            await s.commit()

        rows = await fetch_orders_batch(s, limit=100)
        for o in rows:
            await process_one_order(s, cfg, o)
        await s.commit()
'''
text = text.replace(old_tick, new_tick, 1)

path.write_text(text, encoding='utf-8')
