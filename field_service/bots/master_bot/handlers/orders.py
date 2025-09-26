from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ContentType, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import and_, func, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.config import settings
from field_service.services import time_service
from field_service.services.commission_service import CommissionService

from ..states import CloseOrderStates
from ..utils import escape_html, inline_keyboard, normalize_money, now_utc

router = Router(name="master_orders")

OFFERS_PAGE_SIZE = 5
ACTIVE_STATUSES: tuple[m.OrderStatus, ...] = (
    m.OrderStatus.ASSIGNED,
    m.OrderStatus.EN_ROUTE,
    m.OrderStatus.WORKING,
    m.OrderStatus.PAYMENT,
)



def _timeslot_text(
    start_utc: datetime | None,
    end_utc: datetime | None,
    tz_value: str | None = None,
) -> Optional[str]:
    tz = time_service.resolve_timezone(tz_value or settings.timezone)
    return time_service.format_timeslot_local(start_utc, end_utc, tz=tz)


@router.callback_query(F.data == "m:new")
async def offers_root(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    await _render_offers(callback, session, master, page=1)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:new:(\d+)$"))
async def offers_page(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    page = int(callback.data.rsplit(":", 1)[-1])
    await _render_offers(callback, session, master, page=page)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:new:card:(\d+)(?::(\d+))?$"))
async def offers_card(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    parts = callback.data.split(":")
    order_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    await _render_offer_card(callback, session, master, order_id, page)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:new:acc:(\d+)(?::(\d+))?$"))
async def offer_accept(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    parts = callback.data.split(":")
    order_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    if master.is_blocked:
        await callback.answer("Доступ запрещён: вы заблокированы.", show_alert=True)
        return

    limit = await _get_active_limit(session, master)
    active_orders = await _count_active_orders(session, master.id)
    if limit and active_orders >= limit:
        await callback.answer("Превышен лимит активных заказов.", show_alert=True)
        return

    updated = await session.execute(
        update(m.orders)
        .where(
            and_(
                m.orders.id == order_id,
                m.orders.assigned_master_id.is_(None),
                m.orders.status.in_(
                    (m.OrderStatus.CREATED, m.OrderStatus.SEARCHING, m.OrderStatus.GUARANTEE)
                ),
            )
        )
        .values(
            assigned_master_id=master.id,
            status=m.OrderStatus.ASSIGNED,
            updated_at=func.now(),
        )
        .returning(m.orders.id)
    )
    if not updated.first():
        await callback.answer("Заказ уже принят другим мастером.", show_alert=True)
        return

    await session.execute(
        update(m.offers)
        .where((m.offers.order_id == order_id) & (m.offers.master_id == master.id))
        .values(state=m.OfferState.ACCEPTED, responded_at=func.now())
    )
    await session.execute(
        insert(m.order_status_history).values(
            order_id=order_id,
            from_status=m.OrderStatus.SEARCHING,
            to_status=m.OrderStatus.ASSIGNED,
            changed_by_master_id=master.id,
            reason="accepted_by_master",
        )
    )
    await session.commit()

    await callback.answer("Заказ принят.")
    await _render_offers(callback, session, master, page=page)


@router.callback_query(F.data.regexp(r"^m:new:dec:(\d+)(?::(\d+))?$"))
async def offer_decline(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    parts = callback.data.split(":")
    order_id = int(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1

    await session.execute(
        update(m.offers)
        .where((m.offers.order_id == order_id) & (m.offers.master_id == master.id))
        .values(state=m.OfferState.DECLINED, responded_at=func.now())
    )
    await session.commit()

    await callback.answer("Оффер отклонён.")
    await _render_offers(callback, session, master, page=page)


@router.callback_query(F.data == "m:act")
async def active_order_entry(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    await _render_active_order(callback, session, master, order_id=None)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:act:card:(\d+)$"))
async def active_order_card(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    await _render_active_order(callback, session, master, order_id=order_id)
    await callback.answer()


@router.callback_query(F.data.regexp(r"^m:act:enr:(\d+)$"))
async def active_set_enroute(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    changed = await _update_order_status(
        session,
        master.id,
        order_id,
        expected=m.OrderStatus.ASSIGNED,
        new=m.OrderStatus.EN_ROUTE,
        reason="master_en_route",
    )
    if not changed:
        await callback.answer("Не удалось изменить статус.", show_alert=True)
        return
    await callback.answer("Статус обновлён.")
    await _render_active_order(callback, session, master, order_id=order_id)


@router.callback_query(F.data.regexp(r"^m:act:wrk:(\d+)$"))
async def active_set_working(
    callback: CallbackQuery,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    changed = await _update_order_status(
        session,
        master.id,
        order_id,
        expected=m.OrderStatus.EN_ROUTE,
        new=m.OrderStatus.WORKING,
        reason="master_working",
    )
    if not changed:
        await callback.answer("Не удалось изменить статус.", show_alert=True)
        return
    await callback.answer("Статус обновлён.")
    await _render_active_order(callback, session, master, order_id=order_id)


@router.callback_query(F.data.regexp(r"^m:act:cls:(\d+)$"))
async def active_close_start(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    order_id = int(callback.data.split(":")[-1])
    order = await session.get(m.orders, order_id)
    if order is None or order.assigned_master_id != master.id:
        await callback.answer("Заказ не найден.", show_alert=True)
        return
    if order.status != m.OrderStatus.WORKING:
        await callback.answer("Переведите заказ в статус «Работаю» перед закрытием.", show_alert=True)
        return

    await state.update_data(close_order_id=order_id)
    if order.order_type == m.OrderType.GUARANTEE:
        await state.update_data(close_order_amount=str(Decimal("0")))
        await state.set_state(CloseOrderStates.act)
        await callback.message.answer("Загрузите акт (фото или PDF).")
    else:
        await state.set_state(CloseOrderStates.amount)
        await callback.message.answer("Введите итоговую сумму, например 3500 или 4999.99.")
    await callback.answer()


@router.message(CloseOrderStates.amount)
async def active_close_amount(message: Message, state: FSMContext) -> None:
    amount = normalize_money(message.text or "")
    if amount is None:
        await message.answer("Неверный формат суммы. Пример: 3500 или 4999.99.")
        return
    await state.update_data(close_order_amount=str(amount))
    await state.set_state(CloseOrderStates.act)
    await message.answer("Загрузите акт (фото или PDF).")


@router.message(
    CloseOrderStates.act,
    F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}),
)
async def active_close_act(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    data = await state.get_data()
    order_id = int(data.get("close_order_id"))
    amount = Decimal(str(data.get("close_order_amount", "0")))

    order = await session.get(m.orders, order_id)
    if order is None or order.assigned_master_id != master.id:
        await message.answer("Заказ не найден или уже закрыт.")
        await state.clear()
        return
    if order.status != m.OrderStatus.WORKING:
        await message.answer("Заказ должен быть в статусе «Работаю».")
        await state.clear()
        return

    file_id = message.photo[-1].file_id if message.photo else message.document.file_id
    file_type = (
        m.AttachmentFileType.PHOTO if message.photo else m.AttachmentFileType.DOCUMENT
    )
    session.add(
        m.attachments(
            entity_type=m.AttachmentEntity.ORDER,
            entity_id=order_id,
            file_type=file_type,
            file_id=file_id,
            uploaded_by_master_id=master.id,
        )
    )

    is_guarantee = order.order_type == m.OrderType.GUARANTEE
    order.updated_at = now_utc()
    order.version = (order.version or 0) + 1

    if is_guarantee:
        order.total_sum = Decimal("0")
        order.status = m.OrderStatus.CLOSED
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.WORKING,
                to_status=m.OrderStatus.CLOSED,
                changed_by_master_id=master.id,
                reason="guarantee_completed",
            )
        )
    else:
        order.total_sum = amount
        order.status = m.OrderStatus.PAYMENT
        await session.execute(
            insert(m.order_status_history).values(
                order_id=order_id,
                from_status=m.OrderStatus.WORKING,
                to_status=m.OrderStatus.PAYMENT,
                changed_by_master_id=master.id,
                reason="master_uploaded_act",
            )
        )
        await CommissionService(session).create_for_order(order_id)

    await session.commit()
    await state.clear()

    if is_guarantee:
        await message.answer(f"Заказ #{order_id} закрыт как гарантийный.")
    else:
        await message.answer(f"Заказ #{order_id} закрыт. Итог: {amount:.2f} ₽")
    await _render_active_order(message, session, master, order_id=order_id)


@router.message(CloseOrderStates.act)
async def active_close_act_invalid(message: Message) -> None:
    await message.answer("Пожалуйста, загрузите акт в виде фото или PDF.")


async def _render_offers(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    *,
    page: int,
) -> None:
    offers = await _load_offers(session, master.id)
    if not offers:
        keyboard = inline_keyboard([[InlineKeyboardButton(text="Обновить", callback_data="m:new")]])
        await _respond(event, "Нет новых офферов.", keyboard)
        return

    total = len(offers)
    pages = max(1, math.ceil(total / OFFERS_PAGE_SIZE))
    page = max(1, min(page, pages))
    start = (page - 1) * OFFERS_PAGE_SIZE
    chunk = offers[start : start + OFFERS_PAGE_SIZE]

    lines = ["<b>Новые офферы</b>"]
    keyboard_rows: list[list[InlineKeyboardButton]] = []
    for item in chunk:
        order_id = item.order_id
        city = escape_html(item.city or "N/A")
        district = f" / {escape_html(item.district)}" if item.district else ""
        category = item.category.value if isinstance(item.category, m.OrderCategory) else str(item.category or "N/A")
        lines.append(f"#{order_id} - {city}{district} - {category}")
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=f"#{order_id} - {category}",
                    callback_data=f"m:new:card:{order_id}:{page}",
                )
            ]
        )

    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="<", callback_data=f"m:new:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="m:new"))
    if page < pages:
        nav.append(InlineKeyboardButton(text=">", callback_data=f"m:new:{page + 1}"))
    if nav:
        keyboard_rows.append(nav)

    keyboard = inline_keyboard(keyboard_rows)
    await _respond(event, "\n".join(lines), keyboard)


async def _render_offer_card(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    order_id: int,
    page: int,
) -> None:
    row = await _load_offer_detail(session, master.id, order_id)
    if row is None:
        await _respond(event, "????? ??????????.", None)
        return

    order = row.order
    city = escape_html(row.city or "N/A")
    district = escape_html(row.district) if row.district else None
    street = escape_html(row.street) if row.street else None

    lines = [f"<b>????? #{order.id}</b>", f"?????: {city}"]
    if district:
        lines.append(f"?????: {district}")
    if street or order.house:
        parts = [street or "", escape_html(order.house or "")]
        lines.append(f"?????: {' '.join(p for p in parts if p).strip() or 'N/A'}")
    slot_text = _timeslot_text(order.timeslot_start_utc, order.timeslot_end_utc, getattr(row, 'city_tz', None))
    if slot_text:
        lines.append(f"????: {escape_html(slot_text)}")
    category = order.category.value if isinstance(order.category, m.OrderCategory) else order.category
    lines.append(f"?????????: {category or 'N/A'}")
    if order.description:
        lines.extend(["", escape_html(order.description)])

    keyboard = inline_keyboard(
        [
            [
                InlineKeyboardButton(text="?????", callback_data=f"m:new:acc:{order.id}:{page}"),
                InlineKeyboardButton(text="??????????", callback_data=f"m:new:dec:{order.id}:{page}"),
            ],
            [InlineKeyboardButton(text="?????", callback_data=f"m:new:{page}")],
        ]
    )
    await _respond(event, "\n".join(lines), keyboard)


async def _render_active_order(
    event: Message | CallbackQuery,
    session: AsyncSession,
    master: m.masters,
    order_id: int | None,
) -> None:
    row = await _load_active_order(session, master.id, order_id)
    if row is None:
        await _respond(event, "? ??? ??? ???????? ???????.", None)
        return

    order = row.order
    text_lines = [f"<b>????? #{order.id}</b>", f"??????: {order.status.value}"]
    text_lines.append(f"?????: {escape_html(row.city or 'N/A')}")
    if row.district:
        text_lines.append(f"?????: {escape_html(row.district)}")
    if row.street or order.house:
        parts = [escape_html(row.street or ''), escape_html(order.house or '')]
        text_lines.append(f"?????: {' '.join(p for p in parts if p).strip() or 'N/A'}")
    slot_text = _timeslot_text(order.timeslot_start_utc, order.timeslot_end_utc, getattr(row, 'city_tz', None))
    if slot_text:
        text_lines.append(f"????: {escape_html(slot_text)}")

    if order.status in {m.OrderStatus.ASSIGNED, m.OrderStatus.EN_ROUTE, m.OrderStatus.WORKING, m.OrderStatus.PAYMENT}:
        text_lines.append(f"??????: {escape_html(order.client_name or 'N/A')}")
        text_lines.append(f"???????: {escape_html(order.client_phone or 'N/A')}")

    if order.description:
        text_lines.extend(["", escape_html(order.description)])

    keyboard_rows: list[list[InlineKeyboardButton]] = []
    if order.status == m.OrderStatus.ASSIGNED:
        keyboard_rows.append([
            InlineKeyboardButton(text="? ????", callback_data=f"m:act:enr:{order.id}"),
        ])
    if order.status == m.OrderStatus.EN_ROUTE:
        keyboard_rows.append([
            InlineKeyboardButton(text="???????", callback_data=f"m:act:wrk:{order.id}"),
        ])
    if order.status == m.OrderStatus.WORKING:
        keyboard_rows.append([
            InlineKeyboardButton(text="???????", callback_data=f"m:act:cls:{order.id}"),
        ])
    keyboard_rows.append([
        InlineKeyboardButton(text="?????", callback_data="m:menu"),
    ])
    keyboard = inline_keyboard(keyboard_rows)

    await _respond(event, "\n".join(text_lines), keyboard)


async def _update_order_status(
    session: AsyncSession,
    master_id: int,
    order_id: int,
    *,
    expected: m.OrderStatus,
    new: m.OrderStatus,
    reason: str,
) -> bool:
    updated = await session.execute(
        update(m.orders)
        .where(
            and_(
                m.orders.id == order_id,
                m.orders.assigned_master_id == master_id,
                m.orders.status == expected,
            )
        )
        .values(status=new, updated_at=func.now())
        .returning(m.orders.id)
    )
    if not updated.first():
        await session.rollback()
        return False
    await session.execute(
        insert(m.order_status_history).values(
            order_id=order_id,
            from_status=expected,
            to_status=new,
            changed_by_master_id=master_id,
            reason=reason,
        )
    )
    await session.commit()
    return True


async def _load_offers(session: AsyncSession, master_id: int) -> list[SimpleNamespace]:
    stmt = (
        select(
            m.offers.order_id,
            m.cities.name.label("city"),
            m.districts.name.label("district"),
            m.orders.category,
            m.cities.timezone.label("city_tz"),
            m.orders.timeslot_start_utc,
            m.orders.timeslot_end_utc,
        )
        .join(m.orders, m.orders.id == m.offers.order_id)
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .where(
            m.offers.master_id == master_id,
            m.offers.state.in_((m.OfferState.SENT, m.OfferState.VIEWED)),
        )
        .order_by(m.offers.sent_at.desc(), m.offers.order_id.desc())
    )
    result = await session.execute(stmt)
    rows = []
    for row in result:
        rows.append(
            SimpleNamespace(
                order_id=row.order_id,
                city=row.city,
                district=row.district,
                category=row.category,
                city_tz=row.city_tz,
                timeslot_start=row.timeslot_start_utc,
                timeslot_end=row.timeslot_end_utc,
                timeslot_text=_timeslot_text(row.timeslot_start_utc, row.timeslot_end_utc, row.city_tz),
            )
        )
    return rows


async def _load_offer_detail(
    session: AsyncSession,
    master_id: int,
    order_id: int,
) -> SimpleNamespace | None:
    stmt = (
        select(
            m.orders,
            m.cities.name.label("city"),
            m.cities.timezone.label("city_tz"),
            m.districts.name.label("district"),
            m.streets.name.label("street"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .outerjoin(m.streets, m.streets.id == m.orders.street_id)
        .join(m.offers, and_(m.offers.order_id == m.orders.id, m.offers.master_id == master_id))
        .where(m.orders.id == order_id)
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    return SimpleNamespace(order=row.orders, city=row.city, city_tz=row.city_tz, district=row.district, street=row.street)


async def _load_active_order(
    session: AsyncSession,
    master_id: int,
    order_id: int | None,
) -> SimpleNamespace | None:
    stmt = (
        select(
            m.orders,
            m.cities.name.label("city"),
            m.cities.timezone.label("city_tz"),
            m.districts.name.label("district"),
            m.streets.name.label("street"),
        )
        .join(m.cities, m.cities.id == m.orders.city_id)
        .outerjoin(m.districts, m.districts.id == m.orders.district_id)
        .outerjoin(m.streets, m.streets.id == m.orders.street_id)
        .where(
            m.orders.assigned_master_id == master_id,
            m.orders.status.in_(ACTIVE_STATUSES),
        )
        .order_by(m.orders.updated_at.desc(), m.orders.id.desc())
    )
    if order_id is not None:
        stmt = stmt.where(m.orders.id == order_id)
    row = (await session.execute(stmt)).first()
    if not row:
        return None
    return SimpleNamespace(order=row.orders, city=row.city, city_tz=row.city_tz, district=row.district, street=row.street)


async def _get_active_limit(session: AsyncSession, master: m.masters) -> int:
    if master.max_active_orders_override is not None and master.max_active_orders_override > 0:
        return master.max_active_orders_override
    value = (
        await session.execute(
            select(m.settings.value).where(m.settings.key == "max_active_orders")
        )
    ).scalar_one_or_none()
    try:
        return int(value) if value is not None else 5
    except (TypeError, ValueError):
        return 5


async def _count_active_orders(session: AsyncSession, master_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(m.orders)
        .where(
            m.orders.assigned_master_id == master_id,
            m.orders.status.in_(ACTIVE_STATUSES),
        )
    )
    return int((await session.execute(stmt)).scalar_one())


async def _respond(
    event: Message | CallbackQuery,
    text: str,
    keyboard: InlineKeyboardMarkup | None,
) -> None:
    if isinstance(event, CallbackQuery) and event.message:
        try:
            await event.message.edit_text(text, reply_markup=keyboard)
            return
        except TelegramBadRequest:
            await event.message.answer(text, reply_markup=keyboard)
            return
    if isinstance(event, Message):
        await event.answer(text, reply_markup=keyboard)
    elif isinstance(event, CallbackQuery) and event.message:
        await event.message.answer(text, reply_markup=keyboard)
