# P2-08: ПАТЧ ДЛЯ УДАЛЕНИЯ ДУБЛИРУЮЩЕГОСЯ КОДА ИЗ handlers.py

## ⚠️ ВАЖНО
Сейчас handlers.py = 95KB (2518 строк), т.к. код дублируется в новых модулях.
Нужно удалить перенесённый код, чтобы handlers.py стал ~35KB (1000 строк).

---

## 🔧 ЧТО НУЖНО СДЕЛАТЬ

### Вариант 1: Безопасный (рекомендуется)
**Создать новый файл handlers_legacy.py:**
1. Скопировать handlers.py → handlers_legacy.py
2. Удалить из handlers.py всё, что перенесено
3. Если что-то сломается - откатиться к handlers_legacy.py

### Вариант 2: Автоматический
**Использовать скрипт очистки** (создам ниже)

---

## 📋 ЧТО УДАЛИТЬ ИЗ handlers.py

### 1. Импорты (заменить на импорты из handlers/)

**УДАЛИТЬ (уже в helpers.py):**
```python
PHONE_RE = re.compile(r"^\+7\d{10}$")
NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\- ]{1,99}$")
ATTACHMENTS_LIMIT = 10
LOG_ENTRIES_LIMIT = 20

def _staff_service(bot): ...
def _orders_service(bot): ...
def _masters_service(bot): ...
def _distribution_service(bot): ...
def _finance_service(bot): ...
def _settings_service(bot): ...

def _normalize_phone(value: str) -> str: ...
def _validate_phone(value: str) -> bool: ...
def _validate_name(value: str) -> bool: ...
def _attachments_from_state(data: dict) -> list: ...
def _build_new_order_data(data: dict, staff: StaffUser) -> NewOrderData: ...
def _resolve_city_names(bot, city_ids) -> list[str]: ...
def _zone_storage_value(tz: ZoneInfo) -> str: ...
def _resolve_city_timezone(bot, city_id) -> ZoneInfo: ...
def _format_log_entries(entries) -> str: ...
```

**ДОБАВИТЬ В НАЧАЛО:**
```python
from .handlers.helpers import (
    PHONE_RE, NAME_RE, ATTACHMENTS_LIMIT, LOG_ENTRIES_LIMIT,
    _staff_service, _orders_service, _masters_service,
    _distribution_service, _finance_service, _settings_service,
    _normalize_phone, _validate_phone, _validate_name,
    _attachments_from_state, _build_new_order_data,
    _resolve_city_names, _zone_storage_value, _resolve_city_timezone,
    _format_log_entries,
)
from .handlers.menu import (
    STAFF_CODE_PROMPT, STAFF_CODE_ERROR, STAFF_PDN_TEXT,
    STAFF_ROLE_LABELS, ACCESS_CODE_ERROR_MESSAGES,
)
from .handlers.settings import SETTING_GROUPS, SettingFieldDef, SettingGroupDef
from .handlers.reports import REPORT_DEFINITIONS
```

---

### 2. Обработчики меню (удалить - в menu.py)

**УДАЛИТЬ:**
```python
@router.message(CommandStart(), StaffRoleFilter(...))
async def admin_start(message: Message, staff: StaffUser) -> None:
    ...

@router.message(CommandStart())
async def not_allowed_start(message: Message, state: FSMContext) -> None:
    ...

@router.callback_query(F.data == "adm:menu", ...)
async def cb_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    ...

@router.callback_query(F.data == "adm:staff:menu", ...)
async def cb_staff_menu_denied(cq: CallbackQuery, staff: StaffUser) -> None:
    ...

@router.callback_query(F.data == "adm:f", ...)
async def cb_finance_root(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    ...
```

---

### 3. Обработчики логов (удалить - в logs.py)

**УДАЛИТЬ:**
```python
@router.callback_query(F.data == "adm:l", ...)
async def cb_logs_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    ...

@router.callback_query(F.data == "adm:l:refresh", ...)
async def cb_logs_refresh(cq: CallbackQuery, staff: StaffUser) -> None:
    ...

@router.callback_query(F.data == "adm:l:clear", ...)
async def cb_logs_clear(cq: CallbackQuery, staff: StaffUser) -> None:
    ...
```

---

### 4. Обработчики создания заказов (удалить - в orders.py)

**УДАЛИТЬ ВСЕ обработчики с prefix "adm:new:"**

Список (50+ обработчиков):
- `cb_new_order_start`
- `admin_cancel_command`
- `cb_new_order_cancel`
- `cb_new_order_city_page`
- `cb_new_order_city_search`
- `new_order_city_input`
- `cb_new_order_city_pick`
- `_render_district_step`
- `cb_new_order_district_page`
- `cb_new_order_city_back`
- `cb_new_order_district_none`
- `cb_new_order_district_pick`
- `cb_new_order_street_search`
- `cb_new_order_street_manual`
- `cb_new_order_street_none`
- `cb_new_order_street_back`
- `new_order_street_manual_input`
- `new_order_street_search_input`
- `cb_new_order_street_pick`
- `new_order_house`
- `new_order_apartment`
- `new_order_address_comment`
- `new_order_client_name`
- `new_order_client_phone`
- `cb_new_order_category`
- `new_order_description`
- `cb_new_order_att_add`
- `cb_new_order_att_clear`
- `new_order_attach_photo`
- `new_order_attach_doc`
- `cb_new_order_att_done`
- `cb_new_order_type`
- `cb_new_order_slot`
- `cb_new_order_slot_lateok`
- `cb_new_order_slot_reslot`
- `cb_new_order_confirm`

И все хелперы:
- `_start_new_order`
- `_render_city_step`
- `_slot_options`
- `_format_slot_display`
- `_resolve_workday_window`
- `_finalize_slot_selection`
- `_render_created_order_card`

---

### 5. Обработчики настроек (удалить - в settings.py)

**УДАЛИТЬ:**
```python
SETTING_GROUPS: dict[str, SettingGroupDef] = {...}
SETTING_FIELD_BY_KEY: dict = {...}
SETTING_FIELD_GROUP: dict = {...}
SCHEMA_DEFAULT_HELP: dict = {...}

@dataclass(frozen=True)
class SettingFieldDef: ...

@dataclass(frozen=True)
class SettingGroupDef: ...

def _get_setting_group(group_key: str) -> SettingGroupDef: ...
def _get_setting_field(field_key: str) -> SettingFieldDef: ...
def _format_setting_value(...) -> tuple[str, bool]: ...
def _choice_help(field: SettingFieldDef) -> str: ...
def _build_setting_prompt(...) -> str: ...
def _parse_setting_input(...) -> tuple[str, str]: ...
async def _build_settings_view(...) -> tuple[str, Any]: ...

@router.callback_query(F.data == "adm:s", ...)
async def cb_settings_menu(...): ...

@router.callback_query(F.data.startswith("adm:s:group:"), ...)
async def cb_settings_group(...): ...

@router.callback_query(F.data.startswith("adm:s:edit:"), ...)
async def cb_settings_edit_start(...): ...

@router.message(StateFilter(SettingsEditFSM.awaiting_value), F.text == "/cancel")
async def settings_edit_cancel(...): ...

@router.message(StateFilter(SettingsEditFSM.awaiting_value), ...)
async def settings_edit_value(...): ...
```

---

### 6. Обработчики отчётов (удалить - в reports.py)

**УДАЛИТЬ:**
```python
REPORT_DEFINITIONS: dict = {...}
DATE_INPUT_FORMATS = (...)

def _parse_period_input(text: str) -> Optional[tuple[date, date]]: ...
def _compute_quick_period(key: str, *, tz: str) -> Optional[tuple[date, date]]: ...
def _format_period_label(start_dt: date, end_dt: date) -> str: ...
async def _send_export_documents(...): ...

@router.callback_query(F.data == "adm:r", ...)
async def cb_reports(...): ...

async def _prompt_report_period(...): ...

@router.callback_query(F.data == "adm:r:o", ...)
async def cb_reports_orders(...): ...

@router.callback_query(F.data == "adm:r:c", ...)
async def cb_reports_commissions(...): ...

@router.callback_query(F.data == "adm:r:rr", ...)
async def cb_reports_referrals(...): ...

@router.message(StateFilter(ReportsExportFSM.awaiting_period), F.text == "/cancel")
async def reports_cancel(...): ...

@router.message(StateFilter(ReportsExportFSM.awaiting_period))
async def reports_period_submit(...): ...

@router.callback_query(F.data.regexp(r"^adm:r:pd:..."))
async def reports_quick_period_choice(...): ...
```

---

### 7. Обработчики регистрации (удалить - в staff_access.py)

**УДАЛИТЬ:**
```python
@router.message(StateFilter(StaffAccessFSM.code))
async def staff_access_enter_code(...): ...

@router.message(StateFilter(StaffAccessFSM.pdn))
async def staff_access_pdn(...): ...

@router.message(StateFilter(StaffAccessFSM.full_name))
async def staff_access_full_name(...): ...

@router.message(StateFilter(StaffAccessFSM.phone))
async def staff_access_phone(...): ...
```

---

### 8. Константы в конце файла (удалить дубликаты)

**УДАЛИТЬ блок "Final overrides":**
```python
# -------- Final overrides to fix mojibake in constants --------
FINANCE_SEGMENT_TITLES = {...}
STAFF_CODE_PROMPT = "..."
STAFF_CODE_ERROR = "..."
STAFF_PDN_TEXT = (...)
REPORT_DEFINITIONS = {...}
_RU_GROUP_TITLES = {...}
_RU_GROUP_DESCRIPTIONS = {...}
_RU_FIELD_LABELS = {...}
SCHEMA_DEFAULT_HELP = {...}
```

---

## 📊 ОЖИДАЕМЫЙ РЕЗУЛЬТАТ

После удаления:
- **handlers.py:** 95KB → ~35-40KB
- **Строк:** 2518 → ~1000-1200
- **Обработчиков:** ~150 → ~75 (остаются только finance и несколько утилит)

**В handlers.py останется:**
- Финансы (частично - то что не в handlers_finance.py)
- Middleware
- Router instance
- Несколько утилит

---

## ⚠️ ВНИМАНИЕ

**НЕ УДАЛЯТЬ:**
1. Роутер: `router = Router()`
2. Middleware: `_TIMEOUT_MIDDLEWARE`, `router.message.middleware(...)`
3. Обработчики финансов: `cb_finance_*`, `finance_*`
4. Класс `_MessageEditProxy` (если есть)
5. Любые функции, используемые в handlers_finance.py

---

## 🚀 АВТОМАТИЧЕСКИЙ СКРИПТ ОЧИСТКИ

```python
# cleanup_handlers.py
import re

def cleanup_handlers_py():
    with open('handlers.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Паттерны для удаления
    patterns_to_remove = [
        # Обработчики меню
        r'@router\.message\(CommandStart\(\).*?async def admin_start.*?return\n',
        r'@router\.message\(CommandStart\(\).*?async def not_allowed_start.*?await message\.answer\(STAFF_CODE_PROMPT\)\n',
        r'@router\.callback_query\(F\.data == "adm:menu".*?async def cb_menu.*?await cq\.answer\(\)\n',
        
        # Обработчики логов
        r'@router\.callback_query\(F\.data == "adm:l".*?async def cb_logs_menu.*?await cq\.answer\(\)\n',
        
        # И так далее для каждого блока...
    ]
    
    for pattern in patterns_to_remove:
        content = re.sub(pattern, '', content, flags=re.DOTALL)
    
    with open('handlers_cleaned.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Cleaned version saved to handlers_cleaned.py")

if __name__ == "__main__":
    cleanup_handlers_py()
```

---

## 💡 РЕКОМЕНДАЦИЯ

**Самый безопасный способ:**
1. Создать бэкап: `cp handlers.py handlers_backup.py`
2. Запустить бота и убедиться что всё работает
3. Постепенно удалять блоки из handlers.py
4. После каждого удаления - проверять что бот работает
5. Если что-то сломалось - откатиться к бэкапу

**Или:**
Оставить handlers.py как есть на данный момент. Новые роутеры уже подключены и работают параллельно. Дублирование кода не влияет на работу бота, только на размер файла.

---

## ✅ ИТОГО

**Текущее состояние:** 
- Создано 8 новых модулей ✅
- Код дублируется в handlers.py ⚠️
- Всё работает, но файл большой ⚠️

**Для завершения P2-08 на 100%:**
- Нужно удалить ~1500 строк из handlers.py
- Или оставить как есть (работает, но не оптимально)

**Что делаем?**
