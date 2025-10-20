"""Совместимость с прежним API слоя БД админ-бота."""

from .services import (  # noqa: F401
    DBDistributionService,
    DBFinanceService,
    DBMastersService,
    DBOrdersService,
    DBSettingsService,
    DBStaffService,
    AccessCodeError,
    _StaffAccess,
    _load_staff_access,
)
from .services._common import PAYMENT_METHOD_LABELS  # noqa: F401

__all__ = [
    "DBDistributionService",
    "DBFinanceService",
    "DBMastersService",
    "DBOrdersService",
    "DBSettingsService",
    "DBStaffService",
    "AccessCodeError",
    "_StaffAccess",
    "_load_staff_access",
    "PAYMENT_METHOD_LABELS",
]
