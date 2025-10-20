"""Комбинированные роутеры и совместимость с прежним API обработчиков."""

from aiogram import Router

from .common.menu import router as menu_router
from .orders import router as orders_router
from .orders.create import (  # noqa: F401
    _start_new_order,
    _render_created_order_card,
    cb_new_order_att_add,
    cb_new_order_att_clear,
    cb_new_order_att_done,
    cb_new_order_cancel,
    cb_new_order_category,
    cb_new_order_city_back,
    cb_new_order_city_page,
    cb_new_order_city_pick,
    cb_new_order_city_search,
    cb_new_order_confirm,
    cb_new_order_district_none,
    cb_new_order_district_page,
    cb_new_order_district_pick,
    cb_new_order_force_confirm,
    cb_new_order_full_mode,
    cb_new_order_slot,
    cb_new_order_slot_lateok,
    cb_new_order_slot_reslot,
    cb_new_order_start,
    cb_new_order_street_back,
    cb_new_order_street_manual,
    cb_new_order_street_none,
    cb_new_order_street_pick,
    cb_new_order_street_search,
    cb_new_order_type,
    new_order_address_comment,
    new_order_apartment,
    new_order_attach_doc,
    new_order_attach_photo,
    new_order_city_input,
    new_order_client_name,
    new_order_client_phone,
    new_order_description,
    new_order_house,
    new_order_street_manual_input,
    new_order_street_search_input,
)
from .staff.management import router as staff_management_router
from .system.logs import router as logs_router
from .system.reports import router as reports_router
from .system.settings import router as settings_router


def create_combined_router() -> Router:
    """Собрать все роутеры админ-бота в один экземпляр."""
    combined = Router(name="admin_handlers_combined")
    combined.include_router(staff_management_router)
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
    "reports_router",
    "staff_management_router",
    "_start_new_order",
    "_render_created_order_card",
    "cb_new_order_att_add",
    "cb_new_order_att_clear",
    "cb_new_order_att_done",
    "cb_new_order_cancel",
    "cb_new_order_category",
    "cb_new_order_city_back",
    "cb_new_order_city_page",
    "cb_new_order_city_pick",
    "cb_new_order_city_search",
    "cb_new_order_confirm",
    "cb_new_order_district_none",
    "cb_new_order_district_page",
    "cb_new_order_district_pick",
    "cb_new_order_force_confirm",
    "cb_new_order_full_mode",
    "cb_new_order_slot",
    "cb_new_order_slot_lateok",
    "cb_new_order_slot_reslot",
    "cb_new_order_start",
    "cb_new_order_street_back",
    "cb_new_order_street_manual",
    "cb_new_order_street_none",
    "cb_new_order_street_pick",
    "cb_new_order_street_search",
    "cb_new_order_type",
    "new_order_address_comment",
    "new_order_apartment",
    "new_order_attach_doc",
    "new_order_attach_photo",
    "new_order_city_input",
    "new_order_client_name",
    "new_order_client_phone",
    "new_order_description",
    "new_order_house",
    "new_order_street_manual_input",
    "new_order_street_search_input",
]
