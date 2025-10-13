"""Structured logging helpers for order creation and assignment flows."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _stringify(value: Any) -> str:
    """Return a safe string representation for log fields."""
    if value is None:
        return "N/A"
    raw = getattr(value, "value", None)
    if raw is not None:
        return str(raw)
    return str(value)


def generate_request_id() -> str:
    """Return a short unique identifier for correlating log records."""
    return f"req_{uuid.uuid4().hex[:12]}"


def log_order_creation_start(
    *,
    request_id: str,
    staff_id: Optional[int],
    city_id: int,
    category: Any,
    initial_status: Any,
) -> None:
    """Log the beginning of the order creation workflow."""
    logger.info(
        "[CREATE_ORDER_START] request_id=%s | staff_id=%s | city_id=%s | "
        "category=%s | initial_status=%s",
        request_id,
        staff_id,
        city_id,
        _stringify(category),
        _stringify(initial_status),
    )


def log_order_created(
    *,
    request_id: str,
    order_id: int,
    status: Any,
    staff_id: Optional[int],
    tx_id: Optional[str] = None,
) -> None:
    """Log the successful completion of order creation."""
    logger.info(
        "[CREATE_ORDER_SUCCESS] request_id=%s | order_id=%s | status=%s | "
        "staff_id=%s | tx_id=%s",
        request_id,
        order_id,
        _stringify(status),
        staff_id,
        tx_id or "N/A",
    )


def log_order_creation_error(
    *,
    request_id: str,
    error: str,
    staff_id: Optional[int],
) -> None:
    """Log an unexpected failure during order creation."""
    logger.error(
        "[CREATE_ORDER_ERROR] request_id=%s | staff_id=%s | error=%s",
        request_id,
        staff_id,
        error,
    )


def log_assign_start(
    *,
    request_id: str,
    order_id: int,
    master_id: Optional[int],
    staff_id: Optional[int],
    callback_data: Optional[str],
    current_status: Any,
) -> None:
    """Log the start of the assignment flow triggered by an actor."""
    logger.info(
        "[ASSIGN_START] request_id=%s | order_id=%s | master_id=%s | staff_id=%s | "
        "callback_data=%s | current_status=%s",
        request_id,
        order_id,
        master_id,
        staff_id,
        callback_data or "N/A",
        _stringify(current_status),
    )


def log_assign_attempt(
    *,
    request_id: str,
    order_id: int,
    old_status: Any,
    new_status: Any,
    master_id: Optional[int],
    staff_id: Optional[int],
    actor: str,
) -> None:
    """Log the attempt to update the order state to ASSIGNED."""
    logger.info(
        "[ASSIGN_ATTEMPT] request_id=%s | order_id=%s | old_status=%s -> new_status=%s | "
        "master_id=%s | staff_id=%s | actor=%s",
        request_id,
        order_id,
        _stringify(old_status),
        _stringify(new_status),
        master_id,
        staff_id,
        actor,
    )


def log_assign_sql_result(
    *,
    request_id: str,
    order_id: int,
    rows_affected: int,
    operation: str,
) -> None:
    """Log the outcome of SQL side-effects performed during assignment."""
    logger.info(
        "[ASSIGN_SQL] request_id=%s | order_id=%s | operation=%s | rows_affected=%s",
        request_id,
        order_id,
        operation,
        rows_affected,
    )


def log_assign_success(
    *,
    request_id: str,
    order_id: int,
    master_id: int,
    old_status: Any,
    new_status: Any,
    staff_id: Optional[int],
    tx_id: Optional[str] = None,
) -> None:
    """Log a successful assignment transition."""
    logger.info(
        "[ASSIGN_SUCCESS] request_id=%s | order_id=%s | master_id=%s | %s -> %s | "
        "staff_id=%s | tx_id=%s",
        request_id,
        order_id,
        master_id,
        _stringify(old_status),
        _stringify(new_status),
        staff_id,
        tx_id or "N/A",
    )


def log_assign_error(
    *,
    request_id: str,
    order_id: int,
    error: str,
    staff_id: Optional[int],
    callback_data: Optional[str],
) -> None:
    """Log a failure that prevented assignment completion."""
    logger.error(
        "[ASSIGN_ERROR] request_id=%s | order_id=%s | staff_id=%s | callback_data=%s | error=%s",
        request_id,
        order_id,
        staff_id,
        callback_data or "N/A",
        error,
    )


def log_callback_handler_entry(
    *,
    handler_name: str,
    callback_data: str,
    staff_id: int,
    request_id: str,
) -> None:
    """Log entering a callback handler that drives assignment logic."""
    logger.info(
        "[CALLBACK_ENTRY] handler=%s | request_id=%s | staff_id=%s | callback_data=%s",
        handler_name,
        request_id,
        staff_id,
        callback_data,
    )


def log_callback_handler_exit(
    *,
    handler_name: str,
    request_id: str,
    success: bool,
    result: Optional[str] = None,
) -> None:
    """Log the exit of a callback handler with its outcome."""
    logger.info(
        "[CALLBACK_EXIT] handler=%s | request_id=%s | success=%s | result=%s",
        handler_name,
        request_id,
        success,
        result or "N/A",
    )
