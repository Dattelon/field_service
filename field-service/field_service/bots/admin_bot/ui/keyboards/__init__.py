"""Admin bot keyboards."""
from .common import main_menu, orders_menu, back_to_menu
from .orders import (
    create_order_mode_keyboard,  # P0-5: Выбор режима создания
    queue_list_keyboard,
    order_card_keyboard,
    queue_cancel_keyboard,
    queue_return_confirm_keyboard,
    assign_menu_keyboard,
    manual_candidates_keyboard,
    manual_confirm_keyboard,
    new_order_city_keyboard,
    new_order_district_keyboard,
    new_order_street_mode_keyboard,
    new_order_street_keyboard,
    new_order_street_manual_keyboard,
    new_order_street_search_keyboard,
    new_order_attachments_keyboard,
    new_order_slot_keyboard,
    new_order_asap_late_keyboard,
    new_order_confirm_keyboard,
)
from .finance import (
    finance_menu,
    finance_segment_keyboard,
    finance_card_actions,
    finance_reject_cancel_keyboard,
    owner_pay_actions_keyboard,
    owner_pay_edit_keyboard,
    finance_grouped_keyboard,  # P1-15
    finance_group_period_keyboard,  # P1-15
)
from .reports import (
    reports_menu_keyboard,
    reports_periods_keyboard,
)
from .settings import (
    settings_menu_keyboard,
    settings_group_keyboard,
    logs_menu_keyboard,
)

__all__ = [
    # Common
    'main_menu',
    'orders_menu',
    'back_to_menu',
    # Orders
    'create_order_mode_keyboard',  # P0-5: Выбор режима создания
    'queue_list_keyboard',
    'order_card_keyboard',
    'queue_cancel_keyboard',
    'queue_return_confirm_keyboard',
    'assign_menu_keyboard',
    'manual_candidates_keyboard',
    'manual_confirm_keyboard',
    'new_order_city_keyboard',
    'new_order_district_keyboard',
    'new_order_street_mode_keyboard',
    'new_order_street_keyboard',
    'new_order_street_manual_keyboard',
    'new_order_street_search_keyboard',
    'new_order_attachments_keyboard',
    'new_order_slot_keyboard',
    'new_order_asap_late_keyboard',
    'new_order_confirm_keyboard',
    # Finance
    'finance_menu',
    'finance_segment_keyboard',
    'finance_card_actions',
    'finance_reject_cancel_keyboard',
    'owner_pay_actions_keyboard',
    'owner_pay_edit_keyboard',
    'finance_grouped_keyboard',  # P1-15
    'finance_group_period_keyboard',  # P1-15
    # Reports
    'reports_menu_keyboard',
    'reports_periods_keyboard',
    # Settings
    'settings_menu_keyboard',
    'settings_group_keyboard',
    'logs_menu_keyboard',
]
