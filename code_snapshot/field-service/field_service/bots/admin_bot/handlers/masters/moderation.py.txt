from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ...core.dto import StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...core.states import ModerationBulkFSM  # P1-14:   
from ...utils import get_service
from . import main as admin_masters
from field_service.services.push_notifications import NotificationEvent

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


async def _get_selected_ids(state: FSMContext) -> set[int]:
    """P1-14:   master_ids  state."""
    data = await state.get_data()
    return set(data.get("selected_master_ids", []))


@router.callback_query(
    F.data == "adm:mod:list",
    StaffRoleFilter(MOD_VIEW_ROLES),
)
@router.callback_query(
    F.data.startswith("adm:mod:list:"),
    StaffRoleFilter(MOD_VIEW_ROLES),
)
async def moderation_list(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    #      
    if cq.message:
        await admin_masters._clear_document_messages(cq.bot, state, cq.message.chat.id)
    
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
    
    # P1-14:   
    selected_ids = await _get_selected_ids(state)
    
    text, markup, *_ = await admin_masters.render_master_list(
        cq.bot,
        group,
        category,
        page,
        staff=staff,
        mode="moderation",
        prefix="adm:mod",
        selected_ids=selected_ids,  # P1-14:  
    )
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:mod:card:"),
    StaffRoleFilter(MOD_VIEW_ROLES),
)
async def moderation_card(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    #     
    if cq.message:
        await admin_masters._clear_document_messages(cq.bot, state, cq.message.chat.id)
    
    try:
        action = admin_masters.parse_master_action(cq.data)
    except ValueError:
        await cq.answer(" ", show_alert=True)
        return
    text, markup = await admin_masters.render_master_card(
        cq.bot,
        action.master_id,
        staff=staff,
        mode=action.mode,
        prefix=action.prefix,
        group=action.group,
        category=action.category,
        page=action.page,
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
        action = admin_masters.parse_master_action(cq.data)
    except ValueError:
        await cq.answer(" ", show_alert=True)
        return
    master_id = action.master_id
    service = _masters_service(cq.bot)
    by_id = staff.id
    if by_id == 0:
        try:
            staff_service = get_service(cq.bot, "staff_service", required=False)
            if staff_service and cq.from_user:
                resolved = await staff_service.get_by_tg_id(cq.from_user.id)
                if resolved:
                    by_id = resolved.id
        except Exception:
            pass
    if not await service.approve_master(master_id, by_id):
        await cq.answer("  ", show_alert=True)
        return
    await admin_masters.notify_master_event(
        cq.bot,
        master_id,
        NotificationEvent.MODERATION_APPROVED,
    )
    await admin_masters.notify_master(
        cq.bot,
        master_id,
        " .   .",
    )
    await admin_masters.refresh_card(
        cq,
        master_id,
        staff,
        mode=action.mode,
        prefix=action.prefix,
        group=action.group,
        category=action.category,
        page=action.page,
    )
    await cq.answer("")


@router.callback_query(
    F.data.startswith("adm:mod:rej"),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def moderation_reject(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    try:
        action = admin_masters.parse_master_action(cq.data)
    except ValueError:
        await cq.answer(" ", show_alert=True)
        return
    await state.set_state(admin_masters.RejectReasonState.waiting)
    await state.update_data(
        master_id=action.master_id,
        action="reject",
        origin_chat_id=cq.message.chat.id if cq.message else None,
        origin_message_id=cq.message.message_id if cq.message else None,
        prefix=action.prefix,
        group=action.group,
        category=action.category,
        page=action.page,
        mode=action.mode,
    )
    if cq.message:
        await cq.message.answer("   (1200 ).")
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:mod:docs"),
    StaffRoleFilter(MOD_VIEW_ROLES),
)
async def moderation_docs(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    # reuse master handler for docs
    await admin_masters.show_documents(cq, staff, state)


@router.callback_query(
    F.data.startswith("adm:mod:del"),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def disable_delete(cq: CallbackQuery, staff: StaffUser) -> None:
    await cq.answer("   ", show_alert=True)


# ========================================
# P1-14:   
# ========================================


@router.callback_query(
    F.data.startswith("adm:mod:toggle:"),
    StaffRoleFilter(MOD_VIEW_ROLES),
)
async def bulk_toggle_master(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-14:    ()."""
    parts = cq.data.split(":")
    if len(parts) < 6:
        await cq.answer(" ", show_alert=True)
        return
    
    try:
        _, _, _, group, category, page_str, master_id_str = parts[:7]
        page = max(1, int(page_str))
        master_id = int(master_id_str)
    except (ValueError, IndexError):
        await cq.answer(" ", show_alert=True)
        return
    
    #   
    data = await state.get_data()
    selected = set(data.get("selected_master_ids", []))
    
    # 
    if master_id in selected:
        selected.remove(master_id)
        action_text = ""
    else:
        selected.add(master_id)
        action_text = ""
    
    # 
    await state.update_data(selected_master_ids=list(selected))
    
    #  
    text, markup, *_ = await admin_masters.render_master_list(
        cq.bot,
        group,
        category,
        page,
        staff=staff,
        mode="moderation",
        prefix="adm:mod",
        selected_ids=selected,
    )
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    await cq.answer(f"{action_text} #{master_id}")


@router.callback_query(
    F.data.startswith("adm:mod:bulk:clear:"),
    StaffRoleFilter(MOD_VIEW_ROLES),
)
async def bulk_clear_selection(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-14:    ."""
    parts = cq.data.split(":")
    if len(parts) < 6:
        await cq.answer(" ", show_alert=True)
        return
    
    try:
        _, _, _, _, group, category, page_str = parts[:7]
        page = max(1, int(page_str))
    except (ValueError, IndexError):
        await cq.answer(" ", show_alert=True)
        return
    
    #  
    await state.update_data(selected_master_ids=[])
    
    #  
    text, markup, *_ = await admin_masters.render_master_list(
        cq.bot,
        group,
        category,
        page,
        staff=staff,
        mode="moderation",
        prefix="adm:mod",
        selected_ids=set(),
    )
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    await cq.answer(" ")


@router.callback_query(
    F.data.startswith("adm:mod:bulk:approve:"),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def bulk_approve_ask_confirm(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-14:     ."""
    parts = cq.data.split(":")
    if len(parts) < 6:
        await cq.answer(" ", show_alert=True)
        return
    
    try:
        _, _, _, _, group, category, page_str = parts[:7]
        page = max(1, int(page_str))
    except (ValueError, IndexError):
        await cq.answer(" ", show_alert=True)
        return
    
    #  
    selected = await _get_selected_ids(state)
    if not selected:
        await cq.answer("    ", show_alert=True)
        return
    
    #  
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    
    kb = InlineKeyboardBuilder()
    kb.button(
        text=f" ,  ({len(selected)})",
        callback_data=f"adm:mod:bulk:approve:confirm:{group}:{category}:{page}",
    )
    kb.button(
        text=" ",
        callback_data=f"adm:mod:list:{group}:{category}:{page}",
    )
    kb.adjust(1)
    
    if cq.message:
        await cq.message.edit_text(
            f" <b>  </b>\n\n"
            f" ,    <b>{len(selected)}</b> ?\n\n"
            f"       .",
            reply_markup=kb.as_markup(),
        )
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:mod:bulk:approve:confirm:"),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def bulk_approve_confirmed(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-14:    ."""
    parts = cq.data.split(":")
    if len(parts) < 7:
        await cq.answer(" ", show_alert=True)
        return
    
    try:
        _, _, _, _, _, group, category, page_str = parts[:8]
        page = max(1, int(page_str))
    except (ValueError, IndexError):
        await cq.answer(" ", show_alert=True)
        return
    
    #  
    selected = await _get_selected_ids(state)
    if not selected:
        await cq.answer("    ", show_alert=True)
        return
    
    #  
    if cq.message:
        await cq.message.edit_text(f"  {len(selected)} ...")
    
    service = _masters_service(cq.bot)
    by_id = staff.id
    if by_id == 0:
        try:
            staff_service = get_service(cq.bot, "staff_service", required=False)
            if staff_service and cq.from_user:
                resolved = await staff_service.get_by_tg_id(cq.from_user.id)
                if resolved:
                    by_id = resolved.id
        except Exception:
            pass
    
    #   
    success_count = 0
    for master_id in selected:
        try:
            if await service.approve_master(master_id, by_id):
                success_count += 1
                #  
                await admin_masters.notify_master_event(
                    cq.bot,
                    master_id,
                    NotificationEvent.MODERATION_APPROVED,
                )
                await admin_masters.notify_master(
                    cq.bot,
                    master_id,
                    " .   .",
                )
        except Exception:
            pass
    
    #  
    await state.update_data(selected_master_ids=[])
    
    #  
    text, markup, *_ = await admin_masters.render_master_list(
        cq.bot,
        group,
        category,
        page,
        staff=staff,
        mode="moderation",
        prefix="adm:mod",
        selected_ids=set(),
    )
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    
    await cq.answer(f" : {success_count}  {len(selected)}", show_alert=True)


@router.callback_query(
    F.data.startswith("adm:mod:bulk:reject:"),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def bulk_reject_ask_reason(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    """P1-14:     ."""
    parts = cq.data.split(":")
    if len(parts) < 6:
        await cq.answer(" ", show_alert=True)
        return
    
    try:
        _, _, _, _, group, category, page_str = parts[:7]
        page = max(1, int(page_str))
    except (ValueError, IndexError):
        await cq.answer(" ", show_alert=True)
        return
    
    #  
    selected = await _get_selected_ids(state)
    if not selected:
        await cq.answer("    ", show_alert=True)
        return
    
    #   FSM  
    await state.set_state(ModerationBulkFSM.reject_reason)
    await state.update_data(
        bulk_group=group,
        bulk_category=category,
        bulk_page=page,
        origin_chat_id=cq.message.chat.id if cq.message else None,
        origin_message_id=cq.message.message_id if cq.message else None,
    )
    
    if cq.message:
        await cq.message.answer(
            f"    {len(selected)}  (1200 ):"
        )
    await cq.answer()


@router.message(
    StateFilter(ModerationBulkFSM.reject_reason),
    StaffRoleFilter(MOD_MANAGE_ROLES),
)
async def bulk_reject_process(message: Message, staff: StaffUser, state: FSMContext) -> None:
    """P1-14:    ."""
    reason = (message.text or "").strip()
    if not 1 <= len(reason) <= 200:
        await message.answer("    1  200 .")
        return
    
    data = await state.get_data()
    selected = set(data.get("selected_master_ids", []))
    if not selected:
        await message.answer("    .")
        await state.clear()
        return
    
    group = data.get("bulk_group", "mod")
    category = data.get("bulk_category", "all")
    page = data.get("bulk_page", 1)
    origin_chat_id = data.get("origin_chat_id")
    origin_message_id = data.get("origin_message_id")
    
    service = _masters_service(message.bot)
    
    #   
    success_count = 0
    for master_id in selected:
        try:
            if await service.reject_master(master_id, reason=reason, by_staff_id=staff.id):
                success_count += 1
                #  
                await admin_masters.notify_master_event(
                    message.bot,
                    master_id,
                    NotificationEvent.MODERATION_REJECTED,
                    reason=reason,
                )
                await admin_masters.notify_master(
                    message.bot,
                    master_id,
                    f" . : {reason}",
                )
        except Exception:
            pass
    
    await message.answer(f": {success_count}  {len(selected)}")
    
    #    FSM
    await state.update_data(selected_master_ids=[])
    await state.clear()
    
    #     
    if origin_chat_id and origin_message_id:
        try:
            text, markup, *_ = await admin_masters.render_master_list(
                message.bot,
                group,
                category,
                page,
                staff=staff,
                mode="moderation",
                prefix="adm:mod",
                selected_ids=set(),
            )
            await message.bot.edit_message_text(
                text,
                chat_id=origin_chat_id,
                message_id=origin_message_id,
                reply_markup=markup,
            )
        except Exception:
            pass


__all__ = ["router"]

