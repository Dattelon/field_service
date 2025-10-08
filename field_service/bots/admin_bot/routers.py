"""Compatibility shims for legacy router imports."""
from .handlers.masters import main as admin_masters

__all__ = ["admin_masters"]
