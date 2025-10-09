"""
Helper функции для E2E тестирования
"""
from .master_helpers import (
    create_master_via_onboarding,
    change_master_status,
    accept_offer,
    decline_offer,
    start_work,
    complete_work,
)

from .order_helpers import (
    create_order_via_admin,
    wait_for_offer,
    get_order_status,
    cancel_order,
)

from .admin_helpers import (
    assign_order_manually,
    moderate_master,
    approve_master,
    decline_master,
)

__all__ = [
    # Master helpers
    'create_master_via_onboarding',
    'change_master_status',
    'accept_offer',
    'decline_offer',
    'start_work',
    'complete_work',
    
    # Order helpers
    'create_order_via_admin',
    'wait_for_offer',
    'get_order_status',
    'cancel_order',
    
    # Admin helpers
    'assign_order_manually',
    'moderate_master',
    'approve_master',
    'decline_master',
]
