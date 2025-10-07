"""Admin bot keyboards."""
from __future__ import annotations

from typing import Mapping, Sequence, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ...core.dto import CommissionDetail, StaffUser, StaffRole


def main_menu(staff: StaffUser) -> InlineKeyboardMarkup:
    """Главное меню с учётом ролей и доступов.
    
    GLOBAL_ADMIN: полный доступ ко всем функциям
    CITY_ADMIN: управление заказами, мастерами, финансами в своих городах
    LOGIST: только просмотр эскалированных заказов в очереди и логов
    """
    kb = InlineKeyboardBuilder()
    
    # Очередь доступна всем (с разными фильтрами по ролям)
    kb.button(text="📦 Заявки", callback_data="adm:orders_menu")
    
    # Создание заказов: GLOBAL_ADMIN и CITY_ADMIN
    if staff.role in {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}:
        kb.button(text="➕ Новый заказ", callback_data="adm:new")
    
    # Мастера и Модерация: GLOBAL_ADMIN и CITY_ADMIN
    if staff.role in {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}:
        kb.button(text="👷 Мастера", callback_data="adm:m:grp:ok")
        kb.button(text="🛠 Модерация", callback_data="adm:mod:list:1")
    
    # Финансы: GLOBAL_ADMIN и CITY_ADMIN
    if staff.role in {StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}:
        kb.button(text="💰 Финансы", callback_data="adm:f")
    
    # Отчёты: только GLOBAL_ADMIN
    if staff.role is StaffRole.GLOBAL_ADMIN:
        kb.button(text="📊 Отчёты", callback_data="adm:r")
    
    # Настройки: только GLOBAL_ADMIN
    if staff.role is StaffRole.GLOBAL_ADMIN:
        kb.button(text="⚙️ Настройки", callback_data="adm:s")
    
    # Персонал: только GLOBAL_ADMIN
    if staff.role is StaffRole.GLOBAL_ADMIN:
        kb.button(text="👤 Персонал и доступ", callback_data="adm:staff:menu")
    
    # Логи доступны всем
    kb.button(text="🧾 Логи", callback_data="adm:l")
    
    # Адаптивная раскладка: по 2 кнопки в ряд
    kb.adjust(2)
    
    return kb.as_markup()




def orders_menu(staff: StaffUser, counts: Mapping[str, int]) -> InlineKeyboardMarkup:
    """Меню раздела "Заявки" c счётчиками."""
    kb = InlineKeyboardBuilder()

    kb.button(text="🔍 Поиск по ID", callback_data="adm:q:search")
    kb.button(text="🔧 Фильтры", callback_data="adm:q:flt")

    queue_count = int(counts.get('queue', 0))
    guarantee_count = int(counts.get('guarantee', 0))
    closed_count = int(counts.get('closed', 0))

    kb.button(
        text=f"📋 Очередь ({queue_count})",
        callback_data="adm:orders:queue:1",
    )
    kb.button(
        text=f"🛡 На гарантии ({guarantee_count})",
        callback_data="adm:orders:warranty:1",
    )
    kb.button(
        text=f"✅ Закрытые ({closed_count})",
        callback_data="adm:orders:closed:1",
    )

    kb.button(text="🏠 В меню", callback_data="adm:menu")
    kb.adjust(2, 1, 1, 1, 1)
    return kb.as_markup()




def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Назад в меню", callback_data="adm:menu")
    return kb.as_markup()



