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


class OwnerPayEditFSM(StatesGroup):
    field = State()
    value = State()


class SettingsEditFSM(StatesGroup):
    awaiting_value = State()


class StaffCityEditFSM(StatesGroup):
    action = State()


class AccessCodeNewFSM(StatesGroup):
    city_select = State()


class StaffAccessFSM(StatesGroup):
    code = State()
    pdn = State()
    full_name = State()
    phone = State()


class FinanceActionFSM(StatesGroup):
    commission_id = State()
    reject_reason = State()
    approve_amount = State()




class QueueFiltersFSM(StatesGroup):
    master = State()
    date = State()


class QueueActionFSM(StatesGroup):
    cancel_reason = State()


class MasterActionFSM(StatesGroup):
    master_id = State()
    reject_reason = State()
    block_reason = State()
    limit_value = State()




class ReportsExportFSM(StatesGroup):
    awaiting_period = State()


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
    "StaffAccessFSM",
    "ReportsExportFSM",
]
