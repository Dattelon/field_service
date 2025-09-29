from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from ..dto import StaffRole, StaffUser
from ..filters import StaffRoleFilter
from ..utils import get_service
from . import admin_masters

router = Router(name="admin_moderation")

MOD_VIEW_ROLES = {
    StaffRole.GLOBAL_ADMIN,
    StaffRole.CITY_ADMIN,
    StaffRole.LOGIST,
}
MOD_MANAGE_ROLES = {
    StaffRole.GLOBAL_ADMIN,
    StaffRole.CITY_ADMIN,
}


def _masters_service(bot):
    return get_service(bot, "masters_service")


@router.callback_query(
    F.data == "adm:mod:list",
    StaffRoleFilter(MOD_VIEW_ROLES),
)
@router.callback_query(
    F.data.startswith("adm:mod:list:"),
    StaffRoleFilter(MOD_VIEW_ROLES),
)
async def moderation_list(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    group = "mod"
    category = "all"
    page = 1
    if len(parts) >= 6:
        _, _, _, group, category, page_str = parts[:6]
        try:
            page = max(1, int(page_str))
        except ValueError:
            page = 1
    elif len(parts) >= 4:
        try:
            page = max(1, int(parts[-1]))
        except ValueError:
            page = 1
    text, markup, *_ = await admin_masters.render_master_list(
        cq.bot,
        group,
        category,
        page,
        staff=staff,
        mode="moderation",
        prefix="adm:mod",
    )
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:mod:card:"),
    StaffRoleFilter(MOD_VIEW_ROLES),
)
async def moderation_card(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    text, markup = await admin_masters.render_master_card(
        cq.bot,
        master_id,
        staff=staff,
        mode="moderation",
    )
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:mod:ok"),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def moderation_approve(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    service = _masters_service(cq.bot)
    if not await service.approve_master(master_id, staff.id):
        await cq.answer("Не удалось одобрить", show_alert=True)
        return
    await admin_masters.notify_master(
        cq.bot,
        master_id,
        "Анкета одобрена. Вам доступна смена.",
    )
    await admin_masters.refresh_card(cq, master_id, staff)
    await cq.answer("Одобрено")


@router.callback_query(
    F.data.startswith("adm:mod:rej"),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def moderation_reject(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    await state.set_state(admin_masters.RejectReasonState.waiting)
    await state.update_data(
        master_id=master_id,
        action="reject",
        origin_chat_id=cq.message.chat.id if cq.message else None,
        origin_message_id=cq.message.message_id if cq.message else None,
    )
    if cq.message:
        await cq.message.answer("Укажите причину отклонения (1–200 символов).")
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:mod:docs"),
    StaffRoleFilter(MOD_VIEW_ROLES),
)
async def moderation_docs(cq: CallbackQuery, staff: StaffUser) -> None:
    # reuse master handler for docs
    await admin_masters.show_documents(cq, staff)


@router.callback_query(
    F.data.startswith("adm:mod:del"),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def disable_delete(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.answer("Удаление недоступно из модерации", show_alert=True)


__all__ = ["router"]
