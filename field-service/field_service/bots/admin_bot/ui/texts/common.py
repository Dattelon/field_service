"""Admin bot text formatting."""
from __future__ import annotations

from typing import Mapping

from field_service.db import OrderCategory

from ...core.dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    OrderListItem,
)


FSM_TIMEOUT_MESSAGE = "Сессия истекла. Нажмите /start"

COMMISSION_STATUS_LABELS = {
    'WAIT_PAY': 'Ожидает оплаты',
    'REPORTED': 'Проверяется',
    'APPROVED': 'Оплачено',
    'OVERDUE': 'Просрочено',
}

# ============================================================================
# КОНСТАНТЫ ТЕКСТОВ КНОПОК
# ============================================================================

# --- Навигация ---
NAV_PREV = "◀️ Назад"
NAV_NEXT = "Вперёд ▶️"
NAV_BACK = "◀️ Назад"
NAV_TO_MENU = "🏠 Меню"
NAV_MAIN_MENU = "🏠 Главное меню"

# --- Общие действия ---
BTN_CONFIRM = "✅ Подтвердить"
BTN_CONFIRM_YES = "✅ Да"
BTN_CANCEL = "❌ Отмена"
BTN_OPEN = "👁️ Открыть"
BTN_SAVE = "💾 Сохранить"
BTN_EDIT = "✏️ Изменить"
BTN_DELETE = "🗑 Удалить"
BTN_SEARCH = "🔎 Поиск"
BTN_FILTERS = "🔍 Фильтры"
BTN_RESET = "❌ Сбросить"
BTN_DONE = "✅ Готово"

# --- Назначение заказов ---
BTN_ASSIGN = "✅ Назначить"
BTN_ASSIGN_NOW = "✅ Назначить сейчас"
BTN_ASSIGN_AUTO = "🤖 Автоматом"
BTN_ASSIGN_MANUAL = "👤 Вручную"

# --- Модерация и управление мастерами ---
BTN_APPROVE = "✅ Одобрить"
BTN_APPROVE_ALL = "☑️ Одобрить всех"
BTN_REJECT = "❌ Отклонить"
BTN_BLOCK = "🚫 Заблокировать"
BTN_UNBLOCK = "🔓 Разблокировать"
BTN_DOCS = "📄 Документы"
BTN_LIMIT = "⚙️ Лимит активных"

# --- Финансы ---
FIN_AWAITING = "⏳ Ожидают"
FIN_PAID = "✅ Оплаченные"
FIN_OVERDUE = "🚫 Просроченные"
FIN_GROUPED = "📊 Сгруппировать"
FIN_UNGROUPED = "📋 Список"
FIN_CHECKS = "📎 Чеки"
FIN_APPROVE = "✅ Подтвердить"
FIN_REJECT = "❌ Отклонить"
FIN_BLOCK_MASTER = "🚫 Блок мастера"
FIN_SETTINGS = "⚙️ Реквизиты"
FIN_EDIT_SETTINGS = "✏️ Изменить"
FIN_BROADCAST = "📢 Разослать всем"

# --- Очередь заказов ---
QUEUE_LIST = "📋 Список"
QUEUE_SEARCH = "🔎 Поиск"
QUEUE_SHOW_ALL = "📋 Показать всё"

# --- Персонал ---
STAFF_SELECT_ALL = "☑️ Выбрать все"
STAFF_DESELECT_ALL = "⬜ Снять все"

# --- Отчёты ---
REPORT_ORDERS = "📋 Заказы"
REPORT_COMMISSIONS = "💰 Комиссии"
REPORT_REFERRALS = "🤝 Рефералка"


def _category_value(category: object) -> str:
    """Convert OrderCategory enum to human-readable text."""
    if isinstance(category, OrderCategory):
        category_labels = {
            OrderCategory.ELECTRICS: "Электрика",
            OrderCategory.PLUMBING: "Сантехника",
            OrderCategory.APPLIANCES: "Бытовая техника",
            OrderCategory.DOORS: "Двери/замки",
            OrderCategory.FURNITURE: "Мебель",
            OrderCategory.WINDOWS: "Окна",
            OrderCategory.RENOVATION: "Ремонт/отделка",
            OrderCategory.OTHER: "Прочее",
        }
        return category_labels.get(category, str(category.value))
    if isinstance(category, str):
        return category
    return ""
