"""Breadcrumbs navigation utility for both bots.

Provides hierarchical navigation path display for better UX.

Example:
    >>> build_breadcrumbs([" ", "", "", " #123"])
    "  >  >  >  #123"
"""
from __future__ import annotations

from typing import Sequence


def build_breadcrumbs(path: Sequence[str], separator: str = " > ") -> str:
    """Build breadcrumb navigation string from path components.
    
    Args:
        path: Sequence of navigation items from root to current
        separator: String to use between items (default: " > ")
        
    Returns:
        Formatted breadcrumb string
        
    Example:
        >>> build_breadcrumbs(["Main", "Orders", "Queue"])
        "Main > Orders > Queue"
    """
    if not path:
        return ""
    return separator.join(path)


def format_breadcrumb_header(breadcrumbs: str) -> str:
    """Format breadcrumbs as a message header.
    
    Args:
        breadcrumbs: Breadcrumb string from build_breadcrumbs()
        
    Returns:
        Formatted header with breadcrumbs in gray text
        
    Example:
        >>> format_breadcrumb_header("Main > Orders")
        "<i>Main > Orders</i>\\n"
    """
    if not breadcrumbs:
        return ""
    # Use italic gray text for subtle breadcrumbs
    return f"<i>{breadcrumbs}</i>\n"


# Navigation paths for Admin Bot
class AdminPaths:
    """Predefined navigation paths for admin bot."""
    
    MAIN = [" "]
    
    # Orders section
    ORDERS = MAIN + [""]
    ORDERS_QUEUE = ORDERS + [""]
    ORDERS_CREATE = ORDERS + [" "]
    ORDERS_QUICK_CREATE = ORDERS + [" "]
    
    # Masters section
    MASTERS = MAIN + [""]
    MASTERS_MODERATION = MASTERS + [""]
    MASTERS_LIST = MASTERS + [" "]
    
    # Finance section
    FINANCE = MAIN + [""]
    FINANCE_COMMISSIONS = FINANCE + [""]
    
    # Staff section
    STAFF = MAIN + [""]
    STAFF_MANAGEMENT = STAFF + [""]
    STAFF_ACCESS_CODES = STAFF + [" "]
    
    # System section
    SYSTEM = MAIN + [""]
    SYSTEM_REPORTS = SYSTEM + [""]
    SYSTEM_SETTINGS = SYSTEM + [""]
    SYSTEM_LOGS = SYSTEM + [""]
    
    @staticmethod
    def order_card(order_id: int) -> list[str]:
        """Build path for order card."""
        return AdminPaths.ORDERS_QUEUE + [f" #{order_id}"]
    
    @staticmethod
    def master_card(master_name: str) -> list[str]:
        """Build path for master card."""
        return AdminPaths.MASTERS_LIST + [master_name]


# Navigation paths for Master Bot
class MasterPaths:
    """Predefined navigation paths for master bot."""
    
    MAIN = [" "]
    
    # Orders section
    NEW_ORDERS = MAIN + [" "]
    ACTIVE_ORDERS = MAIN + [" "]
    ACTIVE_ORDER = MAIN + [" "]  #    
    HISTORY = MAIN + [" "]
    
    # Finance section
    FINANCE = MAIN + [""]
    FINANCE_COMMISSIONS = FINANCE + [""]
    
    # Other sections
    REFERRAL = MAIN + [" "]
    STATISTICS = MAIN + [" "]
    KNOWLEDGE = MAIN + [" "]
    
    # Shift management
    SHIFT = MAIN + [" "]
    
    # Onboarding
    ONBOARDING = [""]
    
    @staticmethod
    def offer_card(order_id: int) -> list[str]:
        """Build path for offer card."""
        return MasterPaths.NEW_ORDERS + [f" #{order_id}"]
    
    @staticmethod
    def active_order_card(order_id: int) -> list[str]:
        """Build path for active order card."""
        return MasterPaths.ACTIVE_ORDERS + [f" #{order_id}"]
    
    @staticmethod
    def history_order_card(order_id: int) -> list[str]:
        """Build path for history order card."""
        return MasterPaths.HISTORY + [f" #{order_id}"]
    
    @staticmethod
    def commission_card(commission_id: int) -> list[str]:
        """Build path for commission card."""
        return MasterPaths.FINANCE_COMMISSIONS + [f" #{commission_id}"]


# Helper functions for common use cases
def add_breadcrumbs_to_text(text: str, path: Sequence[str]) -> str:
    """Add breadcrumbs header to existing text.
    
    Args:
        text: Original message text
        path: Navigation path for breadcrumbs
        
    Returns:
        Text with breadcrumbs prepended
        
    Example:
        >>> add_breadcrumbs_to_text("Order #123", ["Main", "Orders", "Queue"])
        "<i>Main > Orders > Queue</i>\\nOrder #123"
    """
    breadcrumbs = build_breadcrumbs(path)
    header = format_breadcrumb_header(breadcrumbs)
    return f"{header}{text}"
