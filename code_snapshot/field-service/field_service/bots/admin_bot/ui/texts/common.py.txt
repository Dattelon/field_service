"""Admin bot text formatting."""
from __future__ import annotations

from typing import Mapping

from ...core.dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    OrderListItem,
)


FSM_TIMEOUT_MESSAGE = "Сессия истекла. Нажмите /start"

COMMISSION_STATUS_LABELS = {
    'WAIT_PAY': 'Ожидает оплаты',
    'REPORTED': 'Проверяется',
    'APPROVED': 'Оплачено',
    'OVERDUE': 'Просрочено',
}

def _category_value(category: object) -> str:
    if isinstance(category, OrderCategory):
        return category.value
    if isinstance(category, str):
        return category
    return ""



