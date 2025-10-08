"""Legacy service entry points retained for backwards compatibility.

The original admin bot exposed database service classes directly from a
``services_db`` module.  The implementation has since moved into the
``services`` package, but several tests – and, potentially, third-party
integrations – still import the old module.  This shim simply re-exports the
new implementations so existing imports continue to work.
"""
from .services._common import PAYMENT_METHOD_LABELS
from .services.distribution import DBDistributionService
from .services.finance import DBFinanceService
from .services.masters import DBMastersService
from .services.orders import DBOrdersService
from .services.settings import DBSettingsService
from .services.staff import AccessCodeError, DBStaffService

__all__ = [
    "PAYMENT_METHOD_LABELS",
    "DBDistributionService",
    "DBFinanceService",
    "DBMastersService",
    "DBOrdersService",
    "DBSettingsService",
    "DBStaffService",
    "AccessCodeError",
]
