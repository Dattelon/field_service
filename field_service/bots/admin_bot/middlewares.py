"""Compatibility exports for admin bot middlewares."""
from .core.middlewares import ACCESS_PROMPT, INACTIVE_PROMPT, StaffAccessMiddleware

__all__ = ["ACCESS_PROMPT", "INACTIVE_PROMPT", "StaffAccessMiddleware"]
