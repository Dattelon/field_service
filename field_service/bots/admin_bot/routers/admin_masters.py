from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from field_service.bots.common import FSMTimeoutConfig, FSMTimeoutMiddleware

from ..dto import MasterDetail, MasterListItem, StaffRole, StaffUser
from ..filters import StaffRoleFilter
from ..keyboards import back_to_menu
from ..utils import get_service

PAGE_SIZE = 10
VIEW_ROLES = {
    StaffRole.GLOBAL_ADMIN,
    StaffRole.CITY_ADMIN,
    StaffRole.LOGIST,
}
MANAGE_ROLES = {
    StaffRole.GLOBAL_ADMIN,
    StaffRole.CITY_ADMIN,
}
SHIFT_LABELS = {
    "SHIFT_ON": "На смене",
    "SHIFT_OFF": "Не на смене",
    "BREAK": "Перерыв",
}
GROUP_LABELS = {
    "ok": "Одобренные",
    "mod": "На модерации",
    "blk": "Неактивные",
}

logger = logging.getLogger(__name__)
UTC = timezone.utc


class RejectReasonState(StatesGroup):
    waiting = State()


class ChangeLimitState(StatesGroup):
    waiting = State()


router = Router(name="admin_masters")
_timeout_middleware = FSMTimeoutMiddleware(
    FSMTimeoutConfig(timeout=timedelta(minutes=5))
)
router.callback_query.middleware(_timeout_middleware)
router.message.middleware(_timeout_middleware)


def _masters_service(bot):
    return get_service(bot, "masters_service")


def _can_manage(staff: StaffUser) -> bool:
    return staff.role in MANAGE_ROLES


def _city_scope(staff: StaffUser) -> Optional[Iterable[int]]:
    if staff.role is StaffRole.GLOBAL_ADMIN:
        return None
    return list(staff.city_ids)


def _group_label(group: str) -> str:
    return GROUP_LABELS.get(group.lower(), group)


def _shift_label(status: str, on_break: bool) -> str:
    status_key = (status or "").upper()
    base = SHIFT_LABELS.get(status_key, status_key or "UNKNOWN")
    if on_break:
        return f"{base} (перерыв)"
    return base


def _category_label(category: str, skills: list[dict[str, object]]) -> str:
    if not category or category == "all":
        return "Все"
    lookup: dict[str, str] = {}
    for item in skills:
        code = str(item.get("code") or "").lower()
        name = str(item.get("name") or item.get("id"))
        lookup[str(item.get("id"))] = name
        if code:
            lookup[code] = name
    return lookup.get(category.lower(), category)


def _format_master_line(item: MasterListItem) -> str:
    skills = ", ".join(item.skills) if item.skills else "—"
    transport = "🚗" if item.has_vehicle else "🚶"
    on_break = item.on_break or item.shift_status.upper() == "BREAK"
    shift = _shift_label(item.shift_status, on_break)
    status_flags: list[str] = []
    if item.is_deleted:
        status_flags.append("удален")
    if not item.verified:
        status_flags.append("не проверен")
    if not item.is_active:
        status_flags.append("не активен")
    flags = f" ({', '.join(status_flags)})" if status_flags else ""
    limit_value: str
    if item.max_active_orders:
        limit_value = f"{item.active_orders}/{item.max_active_orders}"
    else:
        limit_value = str(item.active_orders)
    avg_check = f"{item.avg_check:.0f} ₽" if item.avg_check is not None else "—"
    city = item.city_name or "—"
    return (
        f"#{item.id} {item.full_name} • {city} • {skills} • {item.rating:.1f} ★ • "
        f"{transport} • {shift}{flags}\n"
        f"Активные заказы: {limit_value} • Средний чек: {avg_check}"
    )


def build_list_kb(
    group: str,
    category: str,
    page: int,
    items: list[MasterListItem],
    has_next: bool,
    skills: list[dict[str, object]],
    *,
    prefix: str = "adm:m",
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for item in items:
        kb.button(text=f"Открыть #{item.id}", callback_data=f"{prefix}:card:{item.id}")
    if items:
        kb.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(
            text="◀️ Назад",
            callback_data=f"{prefix}:list:{group}:{category}:{page - 1}",
        )
    if has_next:
        nav.button(
            text="▶️ Вперёд",
            callback_data=f"{prefix}:list:{group}:{category}:{page + 1}",
        )
    if nav.buttons:
        nav.adjust(len(nav.buttons))
        kb.attach(nav)

    categories = InlineKeyboardBuilder()
    categories.button(text="Все", callback_data=f"{prefix}:list:{group}:all:1")
    for skill in skills[:6]:
        skill_id = str(skill.get("id"))
        label = str(skill.get("name") or skill_id)
        if len(label) > 24:
            label = label[:21] + "…"
        categories.button(
            text=label,
            callback_data=f"{prefix}:list:{group}:{skill_id}:1",
        )
    if categories.buttons:
        categories.adjust(min(len(categories.buttons), 3))
        kb.attach(categories)

    kb.button(text="⬅️ В меню", callback_data="adm:menu")
    kb.adjust(1)
    return kb.as_markup()


def build_card_kb(
    detail: MasterDetail,
    staff: StaffUser,
    *,
    mode: str = "masters",
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    manage = _can_manage(staff) and not detail.is_deleted

    if manage and not detail.verified:
        kb.button(text="✅ Одобрить", callback_data=f"adm:m:ok:{detail.id}")
    if manage:
        kb.button(text="❌ Отклонить", callback_data=f"adm:m:rej:{detail.id}")
    if manage:
        if detail.is_active and not detail.is_deleted:
            kb.button(text="🚫 Заблокировать", callback_data=f"adm:m:blk:{detail.id}")
        else:
            kb.button(text="✅ Разблокировать", callback_data=f"adm:m:unb:{detail.id}")
        kb.button(text="🎯 Изм. лимит", callback_data=f"adm:m:lim:{detail.id}")
    kb.button(text="📄 Документы", callback_data=f"adm:m:docs:{detail.id}")
    if manage:
        delete_text = (
            "🗑 Удалить"
            if not (detail.has_orders or detail.has_commissions)
            else "🧹 Мягкое удаление"
        )
        kb.button(text=delete_text, callback_data=f"adm:m:del:{detail.id}")

    kb.button(text="⬅️ К списку", callback_data=f"adm:m:grp:ok")
    kb.adjust(2, 2, 1)

    if mode == "moderation":
        kb = InlineKeyboardBuilder()
        if manage and not detail.verified:
            kb.button(text="✅ Одобрить", callback_data=f"adm:mod:ok:{detail.id}")
        if manage:
            kb.button(text="❌ Отклонить", callback_data=f"adm:mod:rej:{detail.id}")
        kb.button(text="📄 Документы", callback_data=f"adm:mod:docs:{detail.id}")
        kb.button(text="⬅️ К списку", callback_data="adm:mod:list:1")
        kb.adjust(1)
        return kb.as_markup()

    return kb.as_markup()


async def render_master_list(
    bot,
    group: str,
    category: str,
    page: int,
    *,
    staff: StaffUser,
    mode: str = "masters",
    prefix: str = "adm:m",
) -> tuple[str, InlineKeyboardMarkup, list[MasterListItem], list[dict[str, object]], bool]:
    service = _masters_service(bot)
    skills = await service.list_active_skills()
    items, has_next = await service.list_masters(
        group,
        city_ids=_city_scope(staff),
        category=category,
        page=page,
        page_size=PAGE_SIZE,
    )
    title = "👷 <b>Мастера</b>"
    if mode == "moderation":
        title = "🛠 <b>Модерация мастеров</b>"
    group_label = _group_label(group)
    category_label = _category_label(category, skills)
    lines = [
        title,
        f"Группа: {group_label}",
        f"Категория: {category_label}",
        f"Страница: {page}",
    ]
    if not items:
        lines.append("Список пуст.")
    else:
        for item in items:
            lines.append(_format_master_line(item))
    markup = build_list_kb(
        group,
        category,
        page,
        items,
        has_next,
        skills,
        prefix=prefix,
    )
    return "\n\n".join(lines), markup, items, skills, has_next


async def render_master_card(
    bot,
    master_id: int,
    *,
    staff: StaffUser,
    mode: str = "masters",
) -> tuple[str, InlineKeyboardMarkup]:
    service = _masters_service(bot)
    detail = await service.get_master_detail(master_id)
    if not detail:
        return "Мастер не найден или удалён.", back_to_menu()

    status_parts: list[str] = []
    if detail.is_deleted:
        status_parts.append("удалён")
    if not detail.verified:
        status_parts.append("не проверен")
    if not detail.is_active:
        status_parts.append("не активен")
    if detail.is_blocked:
        status_parts.append("заблокирован")
    status_line = ", ".join(status_parts) if status_parts else "активен"

    avg_check = f"{detail.avg_check:.0f} ₽" if detail.avg_check is not None else "—"
    limit_value = detail.current_limit if detail.current_limit else "—"
    verified_at = detail.verified_at_local or "—"
    status_value = (detail.shift_status or "").upper()
    shift = _shift_label(status_value, status_value == "BREAK")

    lines = [
        f"👷 <b>{detail.full_name}</b> #{detail.id}",
        f"📍 Город: {detail.city_name or '—'}",
        f"📞 Телефон: {detail.phone or '—'}",
        f"⭐️ Рейтинг: {detail.rating:.1f}",
        f"🚗 Транспорт: {'Авто' if detail.has_vehicle else 'Пеший'}",
        f"🕒 Смена: {shift}",
        f"📊 Активные заказы: {detail.active_orders}",
        f"🎯 Лимит: {limit_value}",
        f"💰 Средний чек: {avg_check}",
        f"📎 Статус: {status_line}",
        f"✅ Проверен: {detail.verified}",
        f"📅 Дата проверки: {verified_at}",
    ]
    if detail.moderation_reason:
        lines.append(f"📝 Причина: {detail.moderation_reason}")
    if detail.blocked_reason:
        lines.append(f"🚫 Блокировка: {detail.blocked_reason}")
    lines.append(
        "🏙 Районы: " + (", ".join(detail.district_names) or "—")
    )
    lines.append(
        "🛠 Навыки: " + (", ".join(detail.skill_names) or "—")
    )
    if detail.documents:
        doc_types = ", ".join(filter(None, (doc.document_type for doc in detail.documents)))
        lines.append("📄 Документы: " + (doc_types or "доступны"))
    lines.append(f"📅 Создан: {detail.created_at_local}")
    lines.append(f"🆙 Обновлён: {detail.updated_at_local}")

    markup = build_card_kb(detail, staff, mode=mode)
    return "\n".join(lines), markup


async def _refresh_card_message(
    bot,
    chat_id: int,
    message_id: int,
    master_id: int,
    staff: StaffUser,
    *,
    mode: str = "masters",
) -> None:
    try:
        text, markup = await render_master_card(
            bot,
            master_id,
            staff=staff,
            mode=mode,
        )
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=markup,
        )
    except Exception:
        logger.debug("Failed to refresh master card", exc_info=True)


async def refresh_card(cq: CallbackQuery, master_id: int, staff: StaffUser) -> None:
    if not cq.message:
        return
    text, markup = await render_master_card(
        cq.bot,
        master_id,
        staff=staff,
    )
    await cq.message.edit_text(text, reply_markup=markup)


async def notify_master(bot, master_id: int, message: str) -> None:
    try:
        service = _masters_service(bot)
        await service.enqueue_master_notification(master_id, message)
    except Exception:
        logger.warning("Failed to enqueue master notification", exc_info=True)


@router.callback_query(
    F.data.startswith("adm:m:grp:"),
    StaffRoleFilter(VIEW_ROLES),
)
async def open_group(cq: CallbackQuery, staff: StaffUser) -> None:
    group = cq.data.split(":")[-1]
    text, markup, *_ = await render_master_list(
        cq.bot,
        group,
        "all",
        1,
        staff=staff,
    )
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:m:list:"),
    StaffRoleFilter(VIEW_ROLES),
)
async def list_page(cq: CallbackQuery, staff: StaffUser) -> None:
    parts = cq.data.split(":")
    try:
        _, _, _, group, category, page = parts
        page_num = max(1, int(page))
    except (ValueError, IndexError):
        await cq.answer("Некорректный запрос", show_alert=True)
        return
    text, markup, *_ = await render_master_list(
        cq.bot,
        group,
        category,
        page_num,
        staff=staff,
    )
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:m:card:"),
    StaffRoleFilter(VIEW_ROLES),
)
async def master_card(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    text, markup = await render_master_card(cq.bot, master_id, staff=staff)
    if cq.message:
        await cq.message.edit_text(text, reply_markup=markup)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:m:ok"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def approve_master(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    service = _masters_service(cq.bot)
    if not await service.approve_master(master_id, staff.id):
        await cq.answer("Не удалось обновить статус", show_alert=True)
        return
    await notify_master(
        cq.bot,
        master_id,
        "Анкета одобрена. Вам доступна смена.",
    )
    await refresh_card(cq, master_id, staff)
    await cq.answer("Мастер одобрен")


@router.callback_query(
    F.data.startswith("adm:m:rej"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def ask_reject_reason(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    await state.set_state(RejectReasonState.waiting)
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
    F.data.startswith("adm:m:blk"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def ask_block_reason(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    await state.set_state(RejectReasonState.waiting)
    await state.update_data(
        master_id=master_id,
        action="block",
        origin_chat_id=cq.message.chat.id if cq.message else None,
        origin_message_id=cq.message.message_id if cq.message else None,
    )
    if cq.message:
        await cq.message.answer("Укажите причину блокировки (1–200 символов).")
    await cq.answer()


@router.message(
    StateFilter(RejectReasonState.waiting),
    StaffRoleFilter(MANAGE_ROLES),
)
async def process_reason(message: Message, state: FSMContext, staff: StaffUser) -> None:
    data = await state.get_data()
    master_id = int(data.get("master_id", 0))
    action = data.get("action")
    origin_chat_id = data.get("origin_chat_id")
    origin_message_id = data.get("origin_message_id")
    reason = (message.text or "").strip()
    if not 1 <= len(reason) <= 200:
        await message.answer("Причина должна быть от 1 до 200 символов.")
        return
    service = _masters_service(message.bot)
    if action == "reject":
        ok = await service.reject_master(master_id, reason=reason, by_staff_id=staff.id)
        if not ok:
            await message.answer("Не удалось отклонить мастера.")
            await state.clear()
            return
        await notify_master(
            message.bot,
            master_id,
            f"Анкета отклонена. Причина: {reason}",
        )
        await message.answer("Анкета отклонена.")
    else:
        ok = await service.block_master(master_id, reason=reason, by_staff_id=staff.id)
        if not ok:
            await message.answer("Не удалось заблокировать мастера.")
            await state.clear()
            return
        await notify_master(
            message.bot,
            master_id,
            f"Ваш аккаунт заблокирован. Причина: {reason}",
        )
        await message.answer("Мастер заблокирован.")
    if origin_chat_id and origin_message_id:
        await _refresh_card_message(
            message.bot,
            origin_chat_id,
            origin_message_id,
            master_id,
            staff,
        )
    await state.clear()


@router.callback_query(
    F.data.startswith("adm:m:unb"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def unblock_master(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    service = _masters_service(cq.bot)
    if not await service.unblock_master(master_id, by_staff_id=staff.id):
        await cq.answer("Не удалось разблокировать", show_alert=True)
        return
    await notify_master(cq.bot, master_id, "Ваш аккаунт разблокирован.")
    await refresh_card(cq, master_id, staff)
    await cq.answer("Разблокирован")


@router.callback_query(
    F.data.startswith("adm:m:lim"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def ask_limit(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    await state.set_state(ChangeLimitState.waiting)
    await state.update_data(
        master_id=master_id,
        origin_chat_id=cq.message.chat.id if cq.message else None,
        origin_message_id=cq.message.message_id if cq.message else None,
    )
    if cq.message:
        await cq.message.answer("Введите лимит активных заказов (1–20):")
    await cq.answer()


@router.message(
    StateFilter(ChangeLimitState.waiting),
    StaffRoleFilter(MANAGE_ROLES),
)
async def change_limit(message: Message, state: FSMContext, staff: StaffUser) -> None:
    data = await state.get_data()
    master_id = int(data.get("master_id", 0))
    origin_chat_id = data.get("origin_chat_id")
    origin_message_id = data.get("origin_message_id")
    raw_value = (message.text or "").strip()
    if not raw_value.isdigit():
        await message.answer("Введите число от 1 до 20.")
        return
    limit = max(1, min(int(raw_value), 20))
    service = _masters_service(message.bot)
    if not await service.set_master_limit(master_id, limit=limit, by_staff_id=staff.id):
        await message.answer("Не удалось обновить лимит.")
        await state.clear()
        return
    await notify_master(
        message.bot,
        master_id,
        f"Ваш лимит активных заказов обновлён: {limit}",
    )
    await message.answer(f"Лимит обновлён: {limit}")
    if origin_chat_id and origin_message_id:
        await _refresh_card_message(
            message.bot,
            origin_chat_id,
            origin_message_id,
            master_id,
            staff,
        )
    await state.clear()


@router.callback_query(
    F.data.startswith("adm:m:docs"),
    StaffRoleFilter(VIEW_ROLES),
)
async def show_documents(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    service = _masters_service(cq.bot)
    detail = await service.get_master_detail(master_id)
    if not detail or not detail.documents:
        await cq.answer("Документы отсутствуют", show_alert=True)
        return
    for document in detail.documents:
        caption = document.caption or document.document_type or ""
        file_type = (document.file_type or "").upper()
        try:
            if file_type == "PHOTO":
                await cq.message.answer_photo(document.file_id, caption=caption)
            elif file_type == "DOCUMENT":
                await cq.message.answer_document(document.file_id, caption=caption)
            else:
                await cq.message.answer(
                    f"Недопустимый формат документа: {document.file_type}"
                )
        except Exception:
            logger.warning("Failed to send document", exc_info=True)
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:m:del"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def delete_master(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Подтвердить",
        callback_data=f"adm:m:delconfirm:{master_id}",
    )
    kb.button(text="⬅️ Назад", callback_data=f"adm:m:card:{master_id}")
    if cq.message:
        await cq.message.edit_text(
            "Точно удалить мастера?", reply_markup=kb.as_markup()
        )
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:m:delconfirm"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def perform_delete(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        master_id = int(cq.data.split(":")[-1])
    except ValueError:
        await cq.answer("Некорректный идентификатор", show_alert=True)
        return
    service = _masters_service(cq.bot)
    success, soft = await service.delete_master(master_id, by_staff_id=staff.id)
    if not success:
        await cq.answer("Не удалось удалить", show_alert=True)
        return
    if soft:
        await cq.answer("Профиль помечен как удалён", show_alert=True)
        await refresh_card(cq, master_id, staff)
    else:
        if cq.message:
            await cq.message.edit_text("Профиль удалён окончательно.", reply_markup=back_to_menu())
        await cq.answer("Профиль удалён", show_alert=True)


__all__ = [
    "router",
    "render_master_list",
    "render_master_card",
    "build_card_kb",
    "refresh_card",
    "notify_master",
    "RejectReasonState",
]
