"""Admin bot staff management text formatting."""
from __future__ import annotations

from field_service.db import StaffRole


# ============================================================================
# РАЗДЕЛ "ПЕРСОНАЛ" (ТЗ v1.1 §13.6)
# ============================================================================

STAFF_MENU = """
🔐 <b>Доступ и персонал</b>

Управление администраторами и логистами:
• Глобальные администраторы - без ограничений
• Городские администраторы - модерация и финансы в выбранных городах
• Логисты - работа с очередью в своих городах

Выберите действие:
"""

STAFF_LIST_TEMPLATE = """
👥 <b>{role_name}</b>

Всего сотрудников: {total}
Активных: {active}

{staff_list}
"""

STAFF_CARD_TEMPLATE = """
👤 <b>Сотрудник #{staff_id}</b>

ФИО: {full_name}
Телефон: {phone}
Роль: {role_display}
Города: {cities_list}
Статус: {status}
Создан: {created_at}

Telegram ID: <code>{tg_id}</code>
"""

CREATE_STAFF_ACCESS = """
➕ <b>Создать доступ</b>

Выберите роль для нового сотрудника:

• <b>Глобальный администратор</b> - полный доступ
• <b>Городской администратор</b> - модерация и финансы в выбранных городах
• <b>Логист</b> - только очередь и назначение в выбранных городах
"""

SELECT_CITIES_FOR_STAFF = """
🏙 <b>Выбор городов</b>

Для роли: {role_display}

Выбрано городов: {selected_count}
{selected_cities}

Выберите города из списка (максимум 5 на странице):
"""

ACCESS_CODE_CREATED = """
✅ <b>Код доступа создан</b>

Роль: {role_display}
Города: {cities_list}

<b>Код для регистрации:</b>
<code>{access_code}</code>

Передайте этот код сотруднику для входа в бот.
Код действителен до первого использования.
"""

STAFF_DEACTIVATED = """
🚫 <b>Сотрудник деактивирован</b>

{full_name} больше не имеет доступа к системе.
"""

STAFF_CITIES_UPDATED = """
✅ <b>Города обновлены</b>

Сотрудник: {full_name}
Новый список городов: {cities_list}
"""

CONFIRM_STAFF_DEACTIVATE = """
⚠️ <b>Подтверждение деактивации</b>

Вы уверены, что хотите деактивировать сотрудника?

{full_name}
Роль: {role_display}
Города: {cities_list}

После деактивации доступ будет закрыт немедленно.
"""

CODE_REVOKED = """
✅ <b>Код отозван</b>

Код доступа успешно отозван и больше не может быть использован.
"""

STAFF_NOT_FOUND = """
❌ Сотрудник не найден или был удалён.
"""

ACCESS_CODE_NOT_FOUND = """
❌ Код доступа не найден или уже использован.
"""

NO_STAFF_IN_CATEGORY = """
ℹ️ В этой категории пока нет сотрудников.
"""

NO_CODES_ISSUED = """
ℹ️ Нет выданных кодов доступа.
"""


def role_display_name(role: StaffRole) -> str:
    """Человекочитаемое название роли."""
    role_names = {
        StaffRole.GLOBAL_ADMIN: "Глобальный администратор",
        StaffRole.CITY_ADMIN: "Городской администратор",
        StaffRole.LOGIST: "Логист",
    }
    return role_names.get(role, str(role.value))


def staff_brief_line(staff_id: int, full_name: str, role: StaffRole, cities: list[str], is_active: bool) -> str:
    """Краткая строка о сотруднике для списка."""
    status_icon = "✅" if is_active else "❌"
    role_name = role_display_name(role)
    
    cities_text = ", ".join(cities) if cities else "Все города"
    
    return f"{status_icon} #{staff_id} {full_name} | {role_name} | {cities_text}"


def access_code_line(code: str, role: StaffRole, cities: list[str], created_at: str, is_used: bool, is_revoked: bool) -> str:
    """Строка с информацией о коде доступа."""
    if is_revoked:
        status = "🚫 Отозван"
    elif is_used:
        status = "✅ Использован"
    else:
        status = "⏳ Активен"
    
    role_name = role_display_name(role)
    cities_text = ", ".join(cities) if cities else "Все города"
    
    return f"<code>{code}</code> | {role_name} | {cities_text} | {status} | {created_at}"


__all__ = [
    "STAFF_MENU",
    "STAFF_LIST_TEMPLATE",
    "STAFF_CARD_TEMPLATE",
    "CREATE_STAFF_ACCESS",
    "SELECT_CITIES_FOR_STAFF",
    "ACCESS_CODE_CREATED",
    "STAFF_DEACTIVATED",
    "STAFF_CITIES_UPDATED",
    "CONFIRM_STAFF_DEACTIVATE",
    "CODE_REVOKED",
    "STAFF_NOT_FOUND",
    "ACCESS_CODE_NOT_FOUND",
    "NO_STAFF_IN_CATEGORY",
    "NO_CODES_ISSUED",
    "role_display_name",
    "staff_brief_line",
    "access_code_line",
]
