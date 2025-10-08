"""Compatibility layer exposing admin bot texts under legacy import paths."""
from .ui.texts import *  # noqa: F401,F403

from .ui import texts as _texts

__all__ = getattr(_texts, "__all__", [name for name in globals() if not name.startswith("_")])
