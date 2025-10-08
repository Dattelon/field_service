from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class NewOrderFSM(StatesGroup):
    city = State()
    district = State()
    street_mode = State()
    street_search = State()
    street_manual = State()
    house = State()
    apartment = State()
    address_comment = State()
    client_name = State()
    client_phone = State()
    category = State()
    description = State()
    order_type = State()
    slot = State()
    slot_custom_date = State()
    slot_custom_time = State()
    attachments = State()
    confirm = State()
    confirm_deferred = State()  # ⚠️ Подтверждение создания в нерабочее время


class OwnerPayEditFSM(StatesGroup):
    field = State()
    value = State()


class SettingsEditFSM(StatesGroup):
    awaiting_value = State()


class StaffCityEditFSM(StatesGroup):
    action = State()


class AccessCodeNewFSM(StatesGroup):
    city_select = State()


# DEPRECATED: Коды доступа больше не используются
# class StaffAccessFSM(StatesGroup):
#     code = State()
#     pdn = State()
#     full_name = State()
#     phone = State()


class FinanceActionFSM(StatesGroup):
    commission_id = State()
    reject_reason = State()
    approve_amount = State()
    bulk_approve_period = State()  # P2-11: Массовое одобрение




class QueueFiltersFSM(StatesGroup):
    master = State()
    date = State()


class QueueActionFSM(StatesGroup):
    cancel_reason = State()
    search_by_id = State()  # P1-9: Поиск заказа по ID


class MasterActionFSM(StatesGroup):
    master_id = State()
    reject_reason = State()
    block_reason = State()
    limit_value = State()




class ReportsExportFSM(StatesGroup):
    awaiting_period = State()


class StaffAddFSM(StatesGroup):
    """FSM для добавления персонала по ID/username."""
    role_select = State()
    user_input = State()
    city_select = State()
    confirm = State()


class StaffEditFSM(StatesGroup):
    """FSM для редактирования персонала."""
    role_select = State()
    city_select = State()
    confirm = State()


__all__ = [
    "QueueFiltersFSM",
    "QueueActionFSM",
    "AccessCodeNewFSM",
    "FinanceActionFSM",
    "MasterActionFSM",
    "NewOrderFSM",
    "OwnerPayEditFSM",
    "SettingsEditFSM",
    "StaffCityEditFSM",
    # "StaffAccessFSM",  # DEPRECATED: Коды доступа больше не используются
    "ReportsExportFSM",
    "StaffAddFSM",
    "StaffEditFSM",
]
