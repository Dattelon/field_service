"""Compatibility layer exposing admin bot keyboards under legacy import paths."""
from .ui.keyboards import *  # noqa: F401,F403

# Re-export the public keyboard factory functions for older imports.
from .ui import keyboards as _keyboards

__all__ = getattr(_keyboards, "__all__", [])
