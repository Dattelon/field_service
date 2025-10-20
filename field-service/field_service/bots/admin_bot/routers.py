"""Совместимость с прежним модулем роутеров админ-бота."""

from .handlers.masters import main as admin_masters  # noqa: F401

__all__ = ["admin_masters"]
