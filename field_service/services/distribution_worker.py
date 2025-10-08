"""Legacy distribution worker compatibility facade.

The production system migrated to a scheduler-based distribution service,
leaving a thin layer so historical tests – and any remaining scripts – can
still import the former ``distribution_worker`` module.  Only a subset of the
original behaviour is needed by the test-suite: formatting helpers and the
high-level ``process_one_order`` orchestration hook.  The heavy database
queries were refactored elsewhere, so their public functions are left as
extension points that can be monkeypatched in tests.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

UTC = timezone.utc


@dataclass(slots=True)
class DistConfig:
    """Runtime configuration for the distribution loop."""

    sla_seconds: int
    rounds: int
    escalate_to_admin_after_min: int


def fmt_rank_item(row: dict[str, Any]) -> str:
    """Render candidate ranking information in a compact log-friendly form."""

    mid = int(row.get("mid", 0))
    shift_flag = "on" if row.get("shift") else "off"
    car_flag = 1 if row.get("car") else 0
    avg_val = float(row.get("avg_week") or 0)
    rating_val = float(row.get("rating") or 0)
    rnd_val = float(row.get("rnd") or 0)
    return (
        f"{{mid={mid} shift={shift_flag} car={car_flag} avg_week={avg_val:.0f} "
        f"rating={rating_val:.1f} score=car({car_flag})>avg({avg_val:.0f})>"
        f"rat({rating_val:.1f})>rnd({rnd_val:.2f})}}"
    )


def log_tick_header(
    order_row: Any, round_num: int, rounds_total: int, sla: int, candidates_cnt: int
) -> str:
    """Build a legacy header describing the current distribution iteration."""

    status = getattr(order_row, "status", "")
    order_type = "GUARANTEE" if str(status).upper() == "GUARANTEE" else "NORMAL"
    district = getattr(order_row, "district_id", None)
    category = (
        getattr(order_row, "category", None)
        or getattr(order_row, "category_code", None)
        or "-"
    )
    district_value = district if district is not None else "-"
    return (
        f"[dist] order={order_row.id} city={order_row.city_id} "
        f"district={district_value} cat={category} type={order_type}\n"
        f"round={round_num}/{rounds_total} sla={sla}s candidates={candidates_cnt}"
    )


def log_decision_offer(mid: int, until: datetime) -> str:
    """Log message emitted when a candidate receives an offer."""

    return f"decision=offer mid={mid} until={until.isoformat()}"


def log_escalate(order_id: int) -> str:
    """Log message emitted when the system escalates the order."""

    return f"[dist] order={order_id} escalate=logist"


async def has_active_sent_offer(*_: Any, **__: Any) -> bool:  # pragma: no cover - shim
    """Placeholder for the historical query implementation.

    The legacy tests monkeypatch this coroutine with a deterministic stub.  At
    runtime the new distribution scheduler owns this responsibility.
    """

    raise NotImplementedError("has_active_sent_offer moved to distribution scheduler")


async def finalize_accepted_if_any(*_: Any, **__: Any) -> bool:  # pragma: no cover - shim
    raise NotImplementedError("finalize_accepted_if_any moved to distribution scheduler")


async def current_round(*_: Any, **__: Any) -> int:  # pragma: no cover - shim
    raise NotImplementedError("current_round moved to distribution scheduler")


async def candidate_rows(*_: Any, **__: Any) -> Iterable[dict[str, Any]]:  # pragma: no cover - shim
    raise NotImplementedError("candidate_rows moved to distribution scheduler")


async def send_offer(*_: Any, **__: Any) -> bool:  # pragma: no cover - shim
    raise NotImplementedError("send_offer moved to distribution scheduler")


async def process_one_order(session: Any, cfg: DistConfig, o: Any) -> bool:
    """High-level orchestration that mirrors the legacy worker loop."""

    if await has_active_sent_offer(session, o.id):
        return False

    if await finalize_accepted_if_any(session, o.id):
        return True

    current = await current_round(session, o.id)
    if current >= cfg.rounds:
        print(log_escalate(o.id))
        return False

    next_round = current + 1
    candidates = await candidate_rows(
        session,
        o.id,
        getattr(o, "city_id", None),
        getattr(o, "district_id", None),
        getattr(o, "preferred_master_id", None),
        getattr(o, "category", None),
        limit=50,
        force_preferred_first=False,
    )
    candidates = list(candidates)

    header = log_tick_header(o, next_round, cfg.rounds, cfg.sla_seconds, len(candidates))
    print(header)

    if not candidates:
        print(log_escalate(o.id))
        return False

    first = candidates[0]
    sent = await send_offer(
        session,
        o.id,
        int(first.get("mid")),
        next_round,
        cfg.sla_seconds,
    )
    if sent:
        until = datetime.now(UTC) + timedelta(seconds=cfg.sla_seconds)
        print(log_decision_offer(int(first.get("mid")), until))
        return True

    print(log_escalate(o.id))
    return False


__all__ = [
    "DistConfig",
    "fmt_rank_item",
    "log_tick_header",
    "log_decision_offer",
    "log_escalate",
    "has_active_sent_offer",
    "finalize_accepted_if_any",
    "current_round",
    "candidate_rows",
    "send_offer",
    "process_one_order",
]
