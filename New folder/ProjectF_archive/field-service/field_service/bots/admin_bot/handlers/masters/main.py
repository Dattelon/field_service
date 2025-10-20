from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from pathlib import Path
from tempfile import TemporaryDirectory
from aiogram import Bot
from aiogram.types import FSInputFile
from field_service.config import settings as env_settings
from field_service.services.push_notifications import (
    notify_master as push_notify_master,
    NotificationEvent,
)

from field_service.bots.common import FSMTimeoutConfig, FSMTimeoutMiddleware
from field_service.infra.enhanced_logging import (
    log_function_call,
    log_callback_received,
    LoggingContext,
)

from ...core.dto import MasterDetail, MasterListItem, StaffRole, StaffUser
from ...core.filters import StaffRoleFilter
from ...ui.keyboards import back_to_menu
from ...ui.texts.common import (
    NAV_PREV, NAV_NEXT, NAV_BACK, NAV_TO_MENU,
    BTN_OPEN, BTN_APPROVE, BTN_REJECT, BTN_BLOCK, BTN_UNBLOCK,
    BTN_DELETE, BTN_DOCS, BTN_LIMIT, BTN_CONFIRM, BTN_CANCEL
)
from ...utils import get_service

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
    "SHIFT_ON": "✅ На смене",
    "SHIFT_OFF": "❌ Вне смены",
    "BREAK": "☕ Перерыв",
}
GROUP_LABELS = {
    "ok": "✅ Одобренные",
    "mod": "🔍 На модерации",
    "blk": "🚫 Заблокированные",
}

MASTER_GROUP_ORDER = ("ok", "mod", "blk")

logger = logging.getLogger(__name__)
UTC = timezone.utc


@dataclass(slots=True)
class MasterAction:
    prefix: str
    action: str
    master_id: int
    group: str | None = None
    category: str | None = None
    page: int | None = None

    @property
    def mode(self) -> str:
        return "moderation" if self.prefix == "adm:mod" else "masters"


def parse_master_action(data: str) -> MasterAction:
    parts = data.split(":")
    if len(parts) < 3:
        raise ValueError("Invalid callback data")
    prefix = ":".join(parts[:2])
    action = parts[2]
    tail = parts[3:]
    if not tail:
        raise ValueError("Missing master identifier")
    try:
        master_id = int(tail[-1])
    except ValueError as exc:
        raise ValueError("Invalid master identifier") from exc
    group = category = None
    page: int | None = None
    if len(tail) >= 4:
        group = tail[-4]
        category = tail[-3]
        page_str = tail[-2]
        try:
            page = int(page_str)
        except ValueError:
            page = None
    return MasterAction(prefix, action, master_id, group, category, page)


class RejectReasonState(StatesGroup):
    waiting = State()


class ChangeLimitState(StatesGroup):
    waiting = State()


async def debug_callback_middleware(handler, event, data):
    """Middleware    callback   ."""
    if hasattr(event, 'data'):
        logger.info(f"[MASTERS ROUTER] Callback received: {event.data}")
    return await handler(event, data)


router = Router(name="admin_masters")
_timeout_middleware = FSMTimeoutMiddleware(
    FSMTimeoutConfig(timeout=timedelta(minutes=5))
)
router.callback_query.middleware(debug_callback_middleware)
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
        return f"{base} (Перерыв)"
    return base


def _category_label(category: str, skills: list[dict[str, object]]) -> str:
    if not category or category == "all":
        return ""
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
        status_flags.append("🗑️ Удалён")
    if not item.verified:
        status_flags.append("⏳ Не верифицирован")
    if not item.is_active:
        status_flags.append("🚫 Неактивен")
    flags = f" ({', '.join(status_flags)})" if status_flags else ""
    limit_value: str
    if item.max_active_orders:
        limit_value = f"{item.active_orders}/{item.max_active_orders}"
    else:
        limit_value = str(item.active_orders)
    avg_check = f"{item.avg_check:.0f} ₽" if item.avg_check is not None else "—"
    city = item.city_name or "—"
    return (
        f"#{item.id} {item.full_name} • {city} • {skills} • ⭐ {item.rating:.1f} • "
        f"{transport} • {shift}{flags}\n"
        f"📦 Активных: {limit_value}  •  💰 Средний чек: {avg_check}"
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
    selected_ids: set[int] | None = None,  # P1-14:  
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    if prefix == "adm:m":
        active_group = (group or "ok").lower()
        buttons: list[InlineKeyboardButton] = []
        for key in MASTER_GROUP_ORDER:
            label = _group_label(key)
            text_label = label if key != active_group else f"[{label}]"
            buttons.append(
                InlineKeyboardButton(
                    text=text_label,
                    callback_data=f"adm:m:grp:{key}",
                )
            )
        if buttons:
            kb.row(*buttons)

    list_builder = InlineKeyboardBuilder()
    is_moderation = prefix == "adm:mod"
    selected = selected_ids or set()
    
    # P1-14: Чекбоксы для модерации + кнопка открытия
    if is_moderation:
        for item in items:
            is_selected = item.id in selected
            checkbox = "☑️" if is_selected else "⬜"
            list_builder.button(
                text=f"{checkbox} #{item.id}",
                callback_data=f"{prefix}:toggle:{group}:{category}:{page}:{item.id}",
            )
            list_builder.button(
                text=BTN_OPEN,
                callback_data=f"{prefix}:card:{group}:{category}:{page}:{item.id}",
            )
        if items:
            list_builder.adjust(2)  # 2    ( + )
    else:
        #   -   
        for item in items:
            list_builder.button(
                text=f"{BTN_OPEN} #{item.id}",
                callback_data=f"{prefix}:card:{group}:{category}:{page}:{item.id}",
            )
        if items:
            list_builder.adjust(1)
    
    if items:
        kb.attach(list_builder)

    # P1-14: Массовые действия
    if is_moderation and selected:
        bulk_actions = InlineKeyboardBuilder()
        bulk_actions.button(
            text=f"✅ Одобрить все ({len(selected)})",
            callback_data=f"{prefix}:bulk:approve:{group}:{category}:{page}",
        )
        bulk_actions.button(
            text=f"❌ Отклонить все ({len(selected)})",
            callback_data=f"{prefix}:bulk:reject:{group}:{category}:{page}",
        )
        bulk_actions.button(
            text=f"🔄 Снять выделение ({len(selected)})",
            callback_data=f"{prefix}:bulk:clear:{group}:{category}:{page}",
        )
        bulk_actions.adjust(1)
        kb.attach(bulk_actions)

    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(
            text=NAV_PREV,
            callback_data=f"{prefix}:list:{group}:{category}:{page - 1}",
        )
    if has_next:
        nav.button(
            text=NAV_NEXT,
            callback_data=f"{prefix}:list:{group}:{category}:{page + 1}",
        )
    nav_count = 0
    if page > 1:
        nav_count += 1
    if has_next:
        nav_count += 1
    if nav_count:
        nav.adjust(nav_count)
        kb.attach(nav)

    categories = InlineKeyboardBuilder()
    categories.button(text="📋 Все категории", callback_data=f"{prefix}:list:{group}:all:1")
    for skill in skills[:6]:
        skill_id = str(skill.get("id"))
        label = str(skill.get("name") or skill_id)
        if len(label) > 24:
            label = label[:21] + ""
        categories.button(
            text=label,
            callback_data=f"{prefix}:list:{group}:{skill_id}:1",
        )
    categories_count = 1 + min(len(skills), 6)
    if categories_count:
        categories.adjust(min(categories_count, 3))
        kb.attach(categories)

    footer = InlineKeyboardBuilder()
    footer.button(text=NAV_BACK, callback_data="adm:menu")
    footer.button(text=NAV_TO_MENU, callback_data="adm:menu")
    footer.adjust(2)
    kb.attach(footer)

    return kb.as_markup()


def build_card_kb(
    detail: MasterDetail,
    staff: StaffUser,
    *,
    mode: str = "masters",
    prefix: str = "adm:m",
    group: str | None = None,
    category: str | None = None,
    page: int | None = None,
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    manage = _can_manage(staff) and not detail.is_deleted
    group_value = group or ("mod" if mode == "moderation" else "ok")
    category_value = category or "all"
    page_value = page or 1

    def _action_callback(action: str) -> str:
        return f"{prefix}:{action}:{group_value}:{category_value}:{page_value}:{detail.id}"

    if mode == "moderation":
        if manage and not detail.verified:
            kb.button(text=BTN_APPROVE, callback_data=_action_callback("ok"))
        if manage:
            kb.button(text=BTN_REJECT, callback_data=_action_callback("rej"))
        kb.button(text=BTN_DOCS, callback_data=_action_callback("docs"))
        kb.adjust(1)
        kb.row(
            InlineKeyboardButton(
                text=NAV_BACK,
                callback_data=f"{prefix}:list:{group_value}:{category_value}:{page_value}",
            ),
            InlineKeyboardButton(text=NAV_TO_MENU, callback_data="adm:menu"),
        )
        return kb.as_markup()

    if manage and not detail.verified:
        kb.button(text=BTN_APPROVE, callback_data=_action_callback("ok"))
    if manage:
        kb.button(text=BTN_REJECT, callback_data=_action_callback("rej"))
    if manage:
        if detail.is_active and not detail.is_deleted:
            kb.button(text=BTN_BLOCK, callback_data=_action_callback("blk"))
        else:
            kb.button(text=BTN_UNBLOCK, callback_data=_action_callback("unb"))
        kb.button(text=BTN_LIMIT, callback_data=_action_callback("lim"))
    kb.button(text=BTN_DOCS, callback_data=_action_callback("docs"))
    if manage:
        delete_text = (
            BTN_DELETE
            if not (detail.has_orders or detail.has_commissions)
            else f"{BTN_DELETE} ⚠️"
        )
        kb.button(text=delete_text, callback_data=_action_callback("del"))

    kb.adjust(2, 2, 2)
    kb.row(
        InlineKeyboardButton(
            text=NAV_BACK,
            callback_data=f"{prefix}:list:{group_value}:{category_value}:{page_value}",
        ),
        InlineKeyboardButton(text=NAV_TO_MENU, callback_data="adm:menu"),
    )
    return kb.as_markup()


@log_function_call
async def render_master_list(
    bot,
    group: str,
    category: str,
    page: int,
    *,
    staff: StaffUser,
    mode: str = "masters",
    prefix: str = "adm:m",
    selected_ids: set[int] | None = None,  # P1-14:    
) -> tuple[str, InlineKeyboardMarkup, list[MasterListItem], list[dict[str, object]], bool]:
    logger.info(f"[RENDER_MASTER_LIST] Starting: group={group}, category={category}, page={page}, staff_id={staff.id}, mode={mode}")
    
    async with LoggingContext("render_master_list", group=group, category=category, page=page):
        service = _masters_service(bot)
        logger.debug(f"[RENDER_MASTER_LIST] Service obtained: {service}")
        
        logger.info("[RENDER_MASTER_LIST] Fetching active skills...")
        skills = await service.list_active_skills()
        logger.info(f"[RENDER_MASTER_LIST] Got {len(skills)} skills")
        
        city_scope = _city_scope(staff)
        logger.info(f"[RENDER_MASTER_LIST] City scope for staff: {city_scope}")
        
        logger.info("[RENDER_MASTER_LIST] Fetching masters list...")
        items, has_next = await service.list_masters(
            group,
            city_ids=city_scope,
            category=category,
            page=page,
            page_size=PAGE_SIZE,
        )
        logger.info(f"[RENDER_MASTER_LIST] Got {len(items)} masters, has_next={has_next}")
        
        title = "👥 <b>Мастера</b>"
        if mode == "moderation":
            title = "🔍 <b>На модерации</b>"
        group_label = _group_label(group)
        category_label = _category_label(category, skills)
        lines = [
            title,
            f"Группа: {group_label}",
            f"Категория: {category_label}",
            f"Страница: {page}",
        ]
        # P1-14: Показываем количество выбранных
        if selected_ids:
            lines.append(f"✅ Выбрано: {len(selected_ids)}")
        if not items:
            lines.append("Мастеров не найдено.")
        else:
            for item in items:
                lines.append(_format_master_line(item))
        
        logger.info("[RENDER_MASTER_LIST] Building keyboard...")
        markup = build_list_kb(
            group,
            category,
            page,
            items,
            has_next,
            skills,
            prefix=prefix,
            selected_ids=selected_ids,  # P1-14:  
        )
        text_joined = '\n\n'.join(lines)
        logger.info(f"[RENDER_MASTER_LIST] Success: text_length={len(text_joined)}, items_count={len(items)}")
        
        return "\n\n".join(lines), markup, items, skills, has_next


@log_function_call
async def render_master_card(
    bot,
    master_id: int,
    *,
    staff: StaffUser,
    mode: str = "masters",
    prefix: str = "adm:m",
    group: str | None = None,
    category: str | None = None,
    page: int | None = None,
) -> tuple[str, InlineKeyboardMarkup]:
    logger.info(f"[RENDER_MASTER_CARD] Starting: master_id={master_id}, staff_id={staff.id}, mode={mode}")
    
    async with LoggingContext("render_master_card", master_id=master_id):
        service = _masters_service(bot)
        logger.info(f"[RENDER_MASTER_CARD] Fetching master detail for id={master_id}...")
        detail = await service.get_master_detail(master_id)
        
        if not detail:
            logger.warning(f"[RENDER_MASTER_CARD] Master {master_id} not found!")
            return "❌ Мастер не найден.", back_to_menu()
        
        logger.info(f"[RENDER_MASTER_CARD] Got detail: name={detail.full_name}, verified={detail.verified}, active={detail.is_active}")


    status_parts: list[str] = []
    if detail.is_deleted:
        status_parts.append("🗑️ Удалён")
    if not detail.verified:
        status_parts.append("⏳ Не верифицирован")
    if not detail.is_active:
        status_parts.append("🚫 Неактивен")
    if detail.is_blocked:
        status_parts.append("🚫 Заблокирован")
    status_line = ", ".join(status_parts) if status_parts else ""

    avg_check = f"{detail.avg_check:.0f} ₽" if detail.avg_check is not None else "—"
    limit_value = detail.current_limit if detail.current_limit else "—"
    verified_at = detail.verified_at_local or "—"
    status_value = (detail.shift_status or "").upper()
    shift = _shift_label(status_value, status_value == "BREAK")

    lines = [
        f"👤 <b>{detail.full_name}</b> #{detail.id}",
        f"📍 Город: {detail.city_name or '—'}",
        f"📞 Телефон: {detail.phone or '—'}",
        f"⭐ Рейтинг: {detail.rating:.1f}",
        f"🚗 Автомобиль: {'✅' if detail.has_vehicle else '❌'}",
        f"📅 Смена: {shift}",
        f"📦 Активных заказов: {detail.active_orders}",
        f"🔢 Лимит активных: {limit_value}",
        f"💰 Средний чек: {avg_check}",
        f"ℹ️ Статусы: {status_line}",
        f"✅ Верифицирован: {detail.verified}",
        f"📅 Дата верификации: {verified_at}",
    ]
    if detail.referral_code:
        lines.append(f"🎁 Реф. код: {detail.referral_code}")
        try:
            ref_stats = await service.get_master_referral_stats(master_id)
            if ref_stats and ref_stats.get("invited_total", 0) > 0:
                lines.append(
                    f"👥 Приглашено: {ref_stats['invited_total']} "
                    f"(ожидают: {ref_stats['invited_pending']})"
                )
                lines.append(
                    f"💵 Начислено: {ref_stats['rewards_amount']:.2f} ₽ "
                    f"({ref_stats['rewards_count']} нач.)"
                )
        except Exception:
            logger.debug("Failed to load referral stats", exc_info=True)

    if detail.moderation_reason:
        lines.append(f"❌ Причина отклонения: {detail.moderation_reason}")
    if detail.blocked_reason:
        lines.append(f"🚫 Причина блокировки: {detail.blocked_reason}")
    lines.append(
        "🗺️ Районы: " + (", ".join(detail.district_names) or "—")
    )
    lines.append(
        "🛠️ Навыки: " + (", ".join(detail.skill_names) or "—")
    )
    if detail.documents:
        doc_types = ", ".join(filter(None, (doc.document_type for doc in detail.documents)))
        lines.append("📄 Документы: " + (doc_types or "—"))
    lines.append(f"📅 Создан: {detail.created_at_local}")
    lines.append(f"🔄 Обновлён: {detail.updated_at_local}")

    markup = build_card_kb(
        detail,
        staff,
        mode=mode,
        prefix=prefix,
        group=group,
        category=category,
        page=page,
    )
    return "\n".join(lines), markup


async def _refresh_card_message(
    bot,
    chat_id: int,
    message_id: int,
    master_id: int,
    staff: StaffUser,
    *,
    mode: str = "masters",
    prefix: str = "adm:m",
    group: str | None = None,
    category: str | None = None,
    page: int | None = None,
) -> None:
    try:
        text, markup = await render_master_card(
            bot,
            master_id,
            staff=staff,
            mode=mode,
            prefix=prefix,
            group=group,
            category=category,
            page=page,
        )
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=markup,
        )
    except Exception:
        logger.debug("Failed to refresh master card", exc_info=True)


async def refresh_card(
    cq: CallbackQuery,
    master_id: int,
    staff: StaffUser,
    *,
    mode: str | None = None,
    prefix: str = "adm:m",
    group: str | None = None,
    category: str | None = None,
    page: int | None = None,
) -> None:
    if not cq.message:
        return
    text, markup = await render_master_card(
        cq.bot,
        master_id,
        staff=staff,
        mode=mode or ("moderation" if prefix == "adm:mod" else "masters"),
        prefix=prefix,
        group=group,
        category=category,
        page=page,
    )
    await cq.message.edit_text(text, reply_markup=markup)


async def _send_master_event(
    service,
    master_id: int,
    event: NotificationEvent,
    **payload: Any,
) -> None:
    session_factory = getattr(service, "_session_factory", None)
    if session_factory is None:
        return
    try:
        async with session_factory() as session:
            await push_notify_master(
                session,
                master_id=master_id,
                event=event,
                **payload,
            )
            await session.commit()
    except Exception:
        logger.warning(
            "Failed to enqueue push notification %s for master %s",
            event,
            master_id,
            exc_info=True,
        )


async def notify_master_event(
    bot,
    master_id: int,
    event: NotificationEvent,
    **kwargs: Any,
) -> None:
    service = _masters_service(bot)
    await _send_master_event(service, master_id, event, **kwargs)


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
@log_function_call
async def open_group(cq: CallbackQuery, staff: StaffUser) -> None:
    log_callback_received(cq.data, cq.from_user.id)
    logger.info(f"[OPEN_GROUP] Callback data: {cq.data}, User: {cq.from_user.id}, Staff: {staff.id}")
    
    group = cq.data.split(":")[-1]
    logger.info(f"[OPEN_GROUP] Extracted group: {group}")
    
    try:
        logger.info("[OPEN_GROUP] Calling render_master_list...")
        text, markup, *extras = await render_master_list(
            cq.bot,
            group,
            "all",
            1,
            staff=staff,
        )
        logger.info(f"[OPEN_GROUP] Got text (length={len(text)}), has {len(extras)} extras")
        
        if cq.message:
            logger.info(f"[OPEN_GROUP] Editing message {cq.message.message_id} in chat {cq.message.chat.id}")
            await cq.message.edit_text(text, reply_markup=markup)
            logger.info("[OPEN_GROUP] Message edited successfully")
        else:
            logger.warning("[OPEN_GROUP] No message object in callback query!")
        
        await cq.answer()
        logger.info("[OPEN_GROUP] Complete")
        
    except Exception as e:
        logger.error(f"[OPEN_GROUP] Failed with error: {type(e).__name__}: {e}", exc_info=True)
        try:
            await cq.answer("Ошибка при загрузке списка мастеров", show_alert=True)
        except:
            pass
        raise


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
        await cq.answer("Неверный формат номера страницы", show_alert=True)
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
        action = parse_master_action(cq.data)
    except ValueError:
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    text, markup = await render_master_card(
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
    F.data.startswith("adm:m:ok"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def approve_master(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        action = parse_master_action(cq.data)
    except ValueError:
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    master_id = action.master_id
    service = _masters_service(cq.bot)
    if not await service.approve_master(master_id, staff.id):
        await cq.answer("Не удалось одобрить мастера", show_alert=True)
        return
    await _send_master_event(
        service,
        master_id,
        NotificationEvent.MODERATION_APPROVED,
    )
    await notify_master(
        cq.bot,
        master_id,
        "✅ Поздравляем! Ваша анкета одобрена. Теперь вы можете начать работу.",
    )
    await refresh_card(
        cq,
        master_id,
        staff,
        mode=action.mode,
        prefix=action.prefix,
        group=action.group,
        category=action.category,
        page=action.page,
    )
    await cq.answer("Мастер одобрен")


@router.callback_query(
    F.data.startswith("adm:m:rej"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def ask_reject_reason(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    try:
        action = parse_master_action(cq.data)
    except ValueError:
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    await state.set_state(RejectReasonState.waiting)
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
        await cq.message.answer("Введите причину отклонения (до 1200 символов).")
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:m:blk"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def ask_block_reason(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    try:
        action = parse_master_action(cq.data)
    except ValueError:
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    await state.set_state(RejectReasonState.waiting)
    await state.update_data(
        master_id=action.master_id,
        action="block",
        origin_chat_id=cq.message.chat.id if cq.message else None,
        origin_message_id=cq.message.message_id if cq.message else None,
        prefix=action.prefix,
        group=action.group,
        category=action.category,
        page=action.page,
        mode=action.mode,
    )
    if cq.message:
        await cq.message.answer("Введите причину блокировки (до 1200 символов).")
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
        await message.answer("Причина должна содержать от 1 до 200 символов")
        return
    service = _masters_service(message.bot)
    if action == "reject":
        ok = await service.reject_master(master_id, reason=reason, by_staff_id=staff.id)
        if not ok:
            await message.answer("Не удалось отклонить мастера")
            await state.clear()
            return
        await _send_master_event(
            service,
            master_id,
            NotificationEvent.MODERATION_REJECTED,
            reason=reason,
        )
        await notify_master(
            message.bot,
            master_id,
            f"❌ Ваша анкета отклонена. Причина: {reason}",
        )
        await message.answer("Мастер отклонён")
    else:
        ok = await service.block_master(master_id, reason=reason, by_staff_id=staff.id)
        if not ok:
            await message.answer("Не удалось заблокировать мастера")
            await state.clear()
            return
        await _send_master_event(
            service,
            master_id,
            NotificationEvent.ACCOUNT_BLOCKED,
            reason=reason,
        )
        await notify_master(
            message.bot,
            master_id,
            f"🚫 Ваш аккаунт заблокирован. Причина: {reason}",
        )
        await message.answer("Мастер заблокирован")
    if origin_chat_id and origin_message_id:
        await _refresh_card_message(
            message.bot,
            origin_chat_id,
            origin_message_id,
            master_id,
            staff,
            mode=data.get("mode", "masters"),
            prefix=str(data.get("prefix") or "adm:m"),
            group=data.get("group"),
            category=data.get("category"),
            page=data.get("page"),
        )
    await state.clear()


@router.callback_query(
    F.data.startswith("adm:m:unb"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def unblock_master(cq: CallbackQuery, staff: StaffUser) -> None:
    try:
        action = parse_master_action(cq.data)
    except ValueError:
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    master_id = action.master_id
    service = _masters_service(cq.bot)
    if not await service.unblock_master(master_id, by_staff_id=staff.id):
        await cq.answer("Не удалось разблокировать мастера", show_alert=True)
        return
    await _send_master_event(
        service,
        master_id,
        NotificationEvent.ACCOUNT_UNBLOCKED,
    )
    await notify_master(cq.bot, master_id, "✅ Ваш аккаунт разблокирован.")
    await refresh_card(
        cq,
        master_id,
        staff,
        mode=action.mode,
        prefix=action.prefix,
        group=action.group,
        category=action.category,
        page=action.page,
    )
    await cq.answer("Мастер разблокирован")


@router.callback_query(
    F.data.startswith("adm:m:lim"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def ask_limit(cq: CallbackQuery, state: FSMContext, staff: StaffUser) -> None:
    try:
        action = parse_master_action(cq.data)
    except ValueError:
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    await state.set_state(ChangeLimitState.waiting)
    await state.update_data(
        master_id=action.master_id,
        origin_chat_id=cq.message.chat.id if cq.message else None,
        origin_message_id=cq.message.message_id if cq.message else None,
        prefix=action.prefix,
        group=action.group,
        category=action.category,
        page=action.page,
        mode=action.mode,
    )
    if cq.message:
        await cq.message.answer("Введите новый лимит активных заказов (1-20):")
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
        await message.answer("Пожалуйста, введите число от 1 до 20.")
        return
    limit = max(1, min(int(raw_value), 20))
    service = _masters_service(message.bot)
    if not await service.set_master_limit(master_id, limit=limit, by_staff_id=staff.id):
        await message.answer("Не удалось изменить лимит активных заказов")
        await state.clear()
        return
    await _send_master_event(
        service,
        master_id,
        NotificationEvent.LIMIT_CHANGED,
        limit=limit,
    )
    await notify_master(
        message.bot,
        master_id,
        f"ℹ️ Ваш лимит активных заказов изменён: {limit}",
    )
    await message.answer(f"Лимит активных заказов изменён: {limit}")
    if origin_chat_id and origin_message_id:
        await _refresh_card_message(
            message.bot,
            origin_chat_id,
            origin_message_id,
            master_id,
            staff,
            mode=data.get("mode", "masters"),
            prefix=str(data.get("prefix") or "adm:m"),
            group=data.get("group"),
            category=data.get("category"),
            page=data.get("page"),
        )
    await state.clear()


async def _relay_document(current_bot, *, chat_id: int, file_id: str, file_type: str, caption: str = "", filename: str | None = None) -> bool:
    token = getattr(env_settings, 'master_bot_token', None)
    if not token:
        return False
    try:
        async with Bot(token) as source_bot:
            with TemporaryDirectory() as tmpdir:
                # Resolve filename from Telegram file info or fallback by type
                try:
                    info = await source_bot.get_file(file_id)
                    suggested = Path(getattr(info, "file_path", "") or "").name or None
                except Exception:
                    suggested = None
                if not filename and suggested:
                    filename_use = suggested
                elif filename:
                    filename_use = filename
                else:
                    ext = ".jpg" if file_type.upper() == "PHOTO" else (".pdf" if file_type.upper() == "DOCUMENT" else ".bin")
                    filename_use = f"doc{ext}"
                tmp = Path(tmpdir) / filename_use
                await source_bot.download(file_id, destination=tmp)
                if file_type.upper() == "PHOTO":
                    await current_bot.send_photo(chat_id, FSInputFile(tmp, filename=filename_use), caption=caption)
                else:
                    await current_bot.send_document(chat_id, FSInputFile(tmp, filename=filename_use), caption=caption)
        return True
    except Exception:
        logger.warning('Relay via master bot failed', exc_info=True)
        return False


async def _clear_document_messages(bot: Bot, state: FSMContext, chat_id: int) -> None:
    """     ."""
    data = await state.get_data()
    doc_msg_ids = data.get("document_msg_ids", [])
    
    for msg_id in doc_msg_ids:
        try:
            await bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    
    await state.update_data(document_msg_ids=[])


@router.callback_query(
    F.data.startswith("adm:m:docs") | F.data.startswith("adm:mod:docs"),
    StaffRoleFilter(VIEW_ROLES),
)
async def show_documents(cq: CallbackQuery, staff: StaffUser, state: FSMContext) -> None:
    logger.info(f"[DOCS] Handler called for {cq.data}")
    try:
        action = parse_master_action(cq.data)
    except ValueError:
        logger.error(f"[DOCS] Failed to parse action from {cq.data}")
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    master_id = action.master_id
    logger.info(f"[DOCS] Master ID: {master_id}")
    
    try:
        await cq.answer()
    except Exception:
        pass
    
    if cq.message:
        await _clear_document_messages(cq.bot, state, cq.message.chat.id)
    
    service = _masters_service(cq.bot)
    detail = await service.get_master_detail(master_id)
    logger.info(f"[DOCS] Master detail fetched. Has detail: {detail is not None}")
    
    if not detail or not detail.documents:
        logger.info(f"[DOCS] No documents found. detail={detail is not None}, documents={len(detail.documents) if detail else 0}")
        if cq.message:
            await cq.message.answer("Документы мастера не найдены")
        return
    
    logger.info(f"[DOCS] Found {len(detail.documents)} documents")
    chat_id = cq.message.chat.id if cq.message else None
    sent_msg_ids = []
    
    for idx, document in enumerate(detail.documents):
        caption = document.caption or document.document_type or ''
        file_type = (document.file_type or '').upper()
        logger.info(f"[DOCS] Document {idx+1}: type={file_type}, file_id={document.file_id[:20]}...")
        sent_msg = None
        try:
            if file_type == 'PHOTO':
                logger.info(f"[DOCS] Sending photo {idx+1}")
                sent_msg = await cq.message.answer_photo(document.file_id, caption=caption)
            elif file_type == 'DOCUMENT':
                logger.info(f"[DOCS] Sending document {idx+1}")
                sent_msg = await cq.message.answer_document(document.file_id, caption=caption)
            else:
                logger.warning(f"[DOCS] Unknown file type: {document.file_type}")
                sent_msg = await cq.message.answer(f"⚠️ Неизвестный тип файла: {document.file_type}")
            
            #  message_id  
            if sent_msg:
                sent_msg_ids.append(sent_msg.message_id)
                logger.info(f"[DOCS] Document {idx+1} sent successfully")
        except Exception as e:
            logger.error(f"[DOCS] Failed to send document {idx+1} directly: {e}", exc_info=True)
            if chat_id is not None:
                logger.info(f"[DOCS] Trying relay for document {idx+1}")
                ok = await _relay_document(cq.bot, chat_id=chat_id, file_id=document.file_id, file_type=file_type, caption=caption, filename=(document.file_name or None))
                if not ok:
                    logger.warning(f'[DOCS] Relay failed for document {idx+1}', exc_info=True)
                else:
                    logger.info(f"[DOCS] Document {idx+1} sent via relay")
            else:
                logger.warning('[DOCS] No chat_id for relay', exc_info=True)
    
    logger.info(f"[DOCS] Completed. Sent {len(sent_msg_ids)} documents")
    #  message_id   state
    await state.update_data(document_msg_ids=sent_msg_ids)
@router.callback_query(
    F.data.startswith("adm:m:del:") | F.data.startswith("adm:mod:del:"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def delete_master(cq: CallbackQuery, staff: StaffUser) -> None:
    logger.info(f"Delete master initiated: {cq.data}")
    try:
        action = parse_master_action(cq.data)
    except ValueError:
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    master_id = action.master_id
    group_value = action.group or ("mod" if action.mode == "moderation" else "ok")
    category_value = action.category or "all"
    page_value = action.page or 1
    prefix = action.prefix
    confirm_callback = f"{prefix}:delconfirm:{group_value}:{category_value}:{page_value}:{master_id}"
    logger.info(f"Generated delete confirmation callback: {confirm_callback}")
    kb = InlineKeyboardBuilder()
    kb.button(
        text=BTN_CONFIRM,
        callback_data=confirm_callback,
    )
    kb.button(
        text=BTN_CANCEL,
        callback_data=f"{prefix}:card:{group_value}:{category_value}:{page_value}:{master_id}",
    )
    kb.adjust(1)
    if cq.message:
        await cq.message.edit_text(
            "⚠️ Подтвердите удаление мастера?", reply_markup=kb.as_markup()
        )
    await cq.answer()


@router.callback_query(
    F.data.startswith("adm:m:delconfirm") | F.data.startswith("adm:mod:delconfirm"),
    StaffRoleFilter(MANAGE_ROLES),
)
async def perform_delete(cq: CallbackQuery, staff: StaffUser) -> None:
    logger.info(f"Delete confirmation received: {cq.data}")
    try:
        action = parse_master_action(cq.data)
        logger.info(f"Parsed action: master_id={action.master_id}, mode={action.mode}")
    except ValueError as e:
        logger.error(f"Failed to parse action: {e}")
        await cq.answer("Неверные данные действия", show_alert=True)
        return
    
    master_id = action.master_id
    logger.info(f"Calling delete_master for master_id={master_id}, staff_id={staff.id}")
    
    service = _masters_service(cq.bot)
    try:
        success, soft = await service.delete_master(master_id, by_staff_id=staff.id)
        logger.info(f"Delete result: success={success}, soft={soft}")
    except Exception as e:
        logger.error(f"Exception in delete_master: {e}", exc_info=True)
        await cq.answer("Ошибка при удалении мастера", show_alert=True)
        return
    
    if not success:
        logger.warning(f"Delete failed for master_id={master_id}")
        await cq.answer("Не удалось удалить мастера", show_alert=True)
        return
    
    if soft:
        logger.info(f"Soft delete successful for master_id={master_id}")
        await cq.answer("Мастер помечен как удалённый", show_alert=True)
        await refresh_card(
            cq,
            master_id,
            staff,
            mode=action.mode,
            prefix=action.prefix,
            group=action.group,
            category=action.category,
            page=action.page,
        )
    else:
        logger.info(f"Hard delete successful for master_id={master_id}")
        if cq.message:
            await cq.message.edit_text("Мастер удалён из базы данных", reply_markup=back_to_menu())
        await cq.answer("Мастер удалён", show_alert=True)
    
    logger.info(f"Delete handler completed for master_id={master_id}")


#     callback ( adm:m:,  adm:mod:)
@router.callback_query(F.data.startswith("adm:m:"))
async def catch_unhandled_master_callbacks(cq: CallbackQuery) -> None:
    """   callback   ( )."""
    logger.warning(f"[UNHANDLED CALLBACK] Masters router: {cq.data}")
    await cq.answer(f"Необработанное действие '{cq.data}'. Обратитесь к администратору", show_alert=True)


__all__ = [
    "router",
    "render_master_list",
    "render_master_card",
    "build_card_kb",
    "refresh_card",
    "notify_master",
    "notify_master_event",
    "parse_master_action",
    "RejectReasonState",
    "show_documents",
    "_clear_document_messages",
]




