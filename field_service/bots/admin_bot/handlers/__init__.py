# field_service/bots/admin_bot/handlers/__init__.py
"""
Модули обработчиков админ-бота.

Структура:
- menu.py: Главное меню, навигация, регистрация через access code
- logs.py: Просмотр и управление логами
- helpers.py: Общие функции и хелперы
- (handlers.py в корне остаётся для остальных обработчиков до полной миграции)
"""
from aiogram import Router

from .common.menu import router as menu_router
from .system.logs import router as logs_router
from .orders import router as orders_router
from .system.settings import router as settings_router
from .system.reports import router as reports_router  # P2-08: Отчёты
# from .staff.access_codes import router as staff_access_router  # DEPRECATED: Коды доступа больше не используются
from .staff.management import router as staff_management_router  # CR-2025-10-04: Управление персоналом


def create_combined_router() -> Router:
    """Объединяет все роутеры модулей handlers в один."""
    combined = Router(name="admin_handlers_combined")
    # combined.include_router(staff_access_router)  # DEPRECATED: Коды доступа больше не используются
    combined.include_router(staff_management_router)  # CR-2025-10-04: Управление персоналом
    combined.include_router(menu_router)
    combined.include_router(logs_router)
    combined.include_router(orders_router)
    combined.include_router(settings_router)
    combined.include_router(reports_router)
    return combined


__all__ = [
    "create_combined_router",
    "menu_router",
    "logs_router",
    "orders_router",
    "settings_router",
    "reports_router",  # P2-08
    # "staff_access_router",  # DEPRECATED: Коды доступа больше не используются
    "staff_management_router",  # CR-2025-10-04
]
