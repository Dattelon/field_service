# P2-08: ИНСТРУКЦИИ ПО УДАЛЕНИЮ ДУБЛИРУЮЩЕГОСЯ КОДА ИЗ handlers.py

## ЧТО УДАЛИТЬ:

### 1. Импорты (обновить)
Заменить:
```python
from .utils import get_service
```
На:
```python
from .utils import get_service
from .handlers.helpers import (
    _staff_service,
    _orders_service,
    _masters_service,
    _distribution_service,
    _finance_service,
    _settings_service,
    _normalize_phone,
    _validate_phone,
    _validate_name,
    _attachments_from_state,
    _build_new_order_data,
    _resolve_city_names,
    _zone_storage_value,
    _resolve_city_timezone,
    _format_log_entries,
    PHONE_RE,
    NAME_RE,
    ATTACHMENTS_LIMIT,
    LOG_ENTRIES_LIMIT,
    EMPTY_PLACEHOLDER,
)
from .handlers.menu import (
    STAFF_CODE_PROMPT,
    STAFF_CODE_ERROR,
    STAFF_PDN_TEXT,
    STAFF_ROLE_LABELS,
    ACCESS_CODE_ERROR_MESSAGES,
)
```

### 2. Удалить константы (уже в menu.py)
- `STAFF_CODE_PROMPT`
- `STAFF_CODE_ERROR`
- `STAFF_PDN_TEXT`
- `STAFF_ROLE_LABELS`
- `ACCESS_CODE_ERROR_MESSAGES`

### 3. Удалить константы (уже в helpers.py)
- `PHONE_RE = re.compile(...)`
- `NAME_RE = re.compile(...)`
- `ATTACHMENTS_LIMIT = 10`
- `LOG_ENTRIES_LIMIT = 20`

### 4. Удалить функции сервисов (уже в helpers.py)
```python
def _staff_service(bot):
    return get_service(bot, "staff_service")

def _orders_service(bot):
    return get_service(bot, "orders_service")

# ... все остальные _*_service функции
```

### 5. Удалить функции валидации (уже в helpers.py)
```python
def _normalize_phone(value: str) -> str:
    ...

def _validate_phone(value: str) -> bool:
    ...

def _validate_name(value: str) -> bool:
    ...
```

### 6. Удалить хелперы (уже в helpers.py)
```python
def _attachments_from_state(data: dict) -> list[dict[str, Any]]:
    ...

def _build_new_order_data(data: dict, staff: StaffUser) -> NewOrderData:
    ...

async def _resolve_city_names(bot, city_ids: Sequence[int]) -> list[str]:
    ...

def _zone_storage_value(tz: ZoneInfo) -> str:
    ...

async def _resolve_city_timezone(bot: Bot, city_id: Optional[int]) -> ZoneInfo:
    ...

def _format_log_entries(entries: Sequence[live_log.LiveLogEntry]) -> str:
    ...
```

### 7. Удалить обработчики меню (уже в menu.py)
```python
@router.message(CommandStart(), StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}))
async def admin_start(message: Message, staff: StaffUser) -> None:
    ...

@router.message(CommandStart())
async def not_allowed_start(message: Message, state: FSMContext) -> None:
    ...

@router.callback_query(
    F.data == "adm:menu",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    ...

@router.callback_query(
    F.data == "adm:staff:menu",
    StaffRoleFilter({StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_staff_menu_denied(cq: CallbackQuery, staff: StaffUser) -> None:
    ...

@router.callback_query(
    F.data == "adm:f",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN}),
)
async def cb_finance_root(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    ...
```

### 8. Удалить обработчики логов (уже в logs.py)
```python
@router.callback_query(
    F.data == "adm:l",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_logs_menu(cq: CallbackQuery, staff: StaffUser) -> None:
    ...

@router.callback_query(
    F.data == "adm:l:refresh",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN, StaffRole.CITY_ADMIN, StaffRole.LOGIST}),
)
async def cb_logs_refresh(cq: CallbackQuery, staff: StaffUser) -> None:
    ...

@router.callback_query(
    F.data == "adm:l:clear",
    StaffRoleFilter({StaffRole.GLOBAL_ADMIN}),
)
async def cb_logs_clear(cq: CallbackQuery, staff: StaffUser) -> None:
    ...
```

### 9. Удалить дублирующиеся константы в конце файла
В конце handlers.py есть блок с переопределением констант:
```python
# -------- Final overrides to fix mojibake in constants --------
FINANCE_SEGMENT_TITLES = {...}
STAFF_CODE_PROMPT = "..."
STAFF_CODE_ERROR = "..."
...
```
Этот блок можно оставить для обратной совместимости, но импортировать из menu.py

## ИТОГОВАЯ ЭКОНОМИЯ:
- ~200 строк кода удалено
- handlers.py: 3000 → 2800 строк
- Улучшена читаемость и модульность

## СЛЕДУЮЩИЕ ШАГИ:
После этого можно продолжить разбиение:
- reports.py (экспорт отчётов)
- settings.py (настройки)
- orders.py (создание заказов)
