from __future__ import annotations

import math
from typing import Sequence

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ContentType, InlineKeyboardButton, Message
from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db import models as m
from field_service.services import onboarding_service

from ..keyboards import (
    districts_keyboard,
    home_geo_keyboard,
    payout_methods_keyboard,
    pdn_keyboard,
    skills_keyboard,
    vehicle_keyboard,
)
from ..states import OnboardingStates
from ..texts import (
    MASTER_PDN_CONSENT,
    MASTER_PDN_DECLINED,
    ONBOARDING_ALREADY_VERIFIED,
    ONBOARDING_SENT,
    ONBOARDING_SUMMARY_HEADER,
)
from ..utils import clear_step_messages, inline_keyboard, now_utc, push_step_message

router = Router(name="master_onboarding")

DISTRICTS_PER_PAGE = 5
AVAILABLE_PAYOUT_METHODS: tuple[m.PayoutMethod, ...] = (
    m.PayoutMethod.CARD,
    m.PayoutMethod.SBP,
    m.PayoutMethod.YOOMONEY,
    m.PayoutMethod.BANK_ACCOUNT,
)


@router.callback_query(F.data == "m:onboarding:start")
async def onboarding_start(
    callback: CallbackQuery,
    state: FSMContext,
    master: m.masters,
) -> None:
    await callback.answer()  # Отвечаем СРАЗУ, чтобы не было таймаута
    if getattr(master, "verified", False):
        await callback.message.answer(ONBOARDING_ALREADY_VERIFIED)
        return
    await state.clear()
    await state.update_data(step_msg_ids=[], last_step_msg_id=None)
    await state.set_state(OnboardingStates.pdn)
    await push_step_message(
        callback,
        state,
        MASTER_PDN_CONSENT,
        reply_markup=pdn_keyboard(),
    )


@router.callback_query(OnboardingStates.pdn, F.data == "m:onboarding:pdn_accept")
async def onboarding_pdn_accept(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(OnboardingStates.last_name)
    await push_step_message(
        callback,
        state,
        "Введите вашу фамилию (от 2 до 230 символов).",
    )


@router.callback_query(OnboardingStates.pdn, F.data == "m:onboarding:pdn_decline")
async def onboarding_pdn_decline(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await clear_step_messages(callback.message.bot, state, callback.message.chat.id)
    await state.clear()
    await callback.message.answer(MASTER_PDN_DECLINED)


@router.message(OnboardingStates.last_name)
async def onboarding_last_name(message: Message, state: FSMContext) -> None:
    try:
        last_name = onboarding_service.validate_name_part(message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(last_name=last_name)
    await state.set_state(OnboardingStates.first_name)
    await push_step_message(
        message,
        state,
        "Введите ваше имя (от 2 до 230 символов).",
    )


@router.message(OnboardingStates.first_name)
async def onboarding_first_name(message: Message, state: FSMContext) -> None:
    try:
        first_name = onboarding_service.validate_name_part(message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(first_name=first_name)
    await state.set_state(OnboardingStates.middle_name)
    await push_step_message(
        message,
        state,
        "Введите ваше отчество или прочерк-минус, если его нет.",
    )


@router.message(OnboardingStates.middle_name)
async def onboarding_middle_name(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw and raw not in {"-", ""}:
        try:
            middle_name = onboarding_service.validate_name_part(raw)
        except onboarding_service.ValidationError as exc:
            await message.answer(str(exc))
            return
        await state.update_data(middle_name=middle_name)
    else:
        await state.update_data(middle_name=None)
    await state.set_state(OnboardingStates.phone)
    await push_step_message(
        message,
        state,
        "Введите ваш телефон формата +7XXXXXXXXXX или 8XXXXXXXXXX.",
    )


@router.message(OnboardingStates.phone)
async def onboarding_phone(message: Message, state: FSMContext) -> None:
    try:
        phone = onboarding_service.normalize_phone(message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(phone=phone)
    await state.set_state(OnboardingStates.city)
    await message.answer(
        "Напишите название города: можно начать вводить и увидеть подсказки."
    )


@router.message(OnboardingStates.city)
async def onboarding_city_lookup(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    query = (message.text or "").strip()
    if not query:
        await message.answer("Введите название города.")
        return
    pattern = f"%{query.lower()}%"
    stmt = (
        select(m.cities)
        .where(func.lower(m.cities.name).like(pattern))
        .where(m.cities.is_active.is_(True))
        .order_by(m.cities.name.asc())
        .limit(12)
    )
    cities = (await session.execute(stmt)).scalars().all()
    if not cities:
        await message.answer("Город не найден. Попробуйте ещё раз.")
        return
    options = [
        [InlineKeyboardButton(text=city.name, callback_data=f"m:onboarding:city:{city.id}")]
        for city in cities
    ]
    await state.update_data(
        city_options=[{"id": city.id, "name": city.name} for city in cities]
    )
    await push_step_message(message, state, "Выберите ваш город:", inline_keyboard(options))


@router.callback_query(OnboardingStates.city, F.data.startswith("m:onboarding:city:"))
async def onboarding_city_pick(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    city_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    option_lookup = {item["id"]: item["name"] for item in data.get("city_options", [])}
    if city_id not in option_lookup:
        await callback.message.answer("Город устарел. Выберите снова.")
        return
    city_name = option_lookup[city_id]
    await state.update_data(city_id=city_id, city_name=city_name, district_ids=[])

    districts = await _load_districts(session, city_id)
    if not districts:
        await state.set_state(OnboardingStates.vehicle)
        await push_step_message(
            callback,
            state,
            "Есть ли у вас автомобиль?",
            vehicle_keyboard(),
        )
        return

    await state.update_data(districts=districts, district_page=1, district_ids=[])
    await state.set_state(OnboardingStates.districts)
    keyboard = _build_district_keyboard(districts, set(), page=1)
    await push_step_message(
        callback,
        state,
        "Выберите районы работы (можно несколько).",
        keyboard,
    )


@router.callback_query(OnboardingStates.districts, F.data.startswith("m:onboarding:districts_page:"))
async def onboarding_district_page(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    tail = callback.data.split(":")[-1]
    if tail == "noop":
        await callback.answer()
        return
    await callback.answer()
    page = int(tail)
    data = await state.get_data()
    districts = data.get("districts", [])
    selected = set(data.get("district_ids", []))
    keyboard = _build_district_keyboard(districts, selected, page=page)
    await state.update_data(district_page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except TelegramBadRequest:
        pass


@router.callback_query(OnboardingStates.districts, F.data.startswith("m:onboarding:district:"))
async def onboarding_district_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    district_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    districts = data.get("districts", [])
    known_ids = {item["id"] for item in districts}
    if district_id not in known_ids:
        await callback.message.answer("Район не найден.")
        return
    selected = set(data.get("district_ids", []))
    if district_id in selected:
        selected.remove(district_id)
    else:
        selected.add(district_id)
    await state.update_data(district_ids=list(sorted(selected)))
    page = data.get("district_page", 1)
    keyboard = _build_district_keyboard(districts, selected, page=page)
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except TelegramBadRequest:
        pass


@router.callback_query(OnboardingStates.districts, F.data == "m:onboarding:districts_done")
async def onboarding_districts_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = data.get("district_ids", [])
    if not selected:
        await callback.answer("Выберите хотя бы один район.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(OnboardingStates.vehicle)
    await push_step_message(
        callback,
        state,
        "Есть ли у вас автомобиль?",
        vehicle_keyboard(),
    )


@router.callback_query(OnboardingStates.vehicle, F.data == "m:onboarding:vehicle_yes")
async def onboarding_vehicle_yes(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await state.update_data(has_vehicle=True)
    await _start_skills(callback, state, session)


@router.callback_query(OnboardingStates.vehicle, F.data == "m:onboarding:vehicle_no")
async def onboarding_vehicle_no(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await callback.answer()
    await state.update_data(has_vehicle=False)
    await _start_skills(callback, state, session)


async def _start_skills(
    event: Message | CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    stmt = select(m.skills).where(m.skills.is_active.is_(True)).order_by(m.skills.name.asc())
    skills = (await session.execute(stmt)).scalars().all()
    skills_data = [{"id": skill.id, "name": skill.name} for skill in skills]
    await state.update_data(skills=skills_data, skill_ids=[])
    keyboard = _build_skills_keyboard(skills_data, set())
    await state.set_state(OnboardingStates.skills)
    await push_step_message(event, state, "Выберите ваши навыки (можно несколько).", keyboard)


@router.callback_query(OnboardingStates.skills, F.data.startswith("m:onboarding:skill:"))
async def onboarding_skill_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    skill_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    skills = data.get("skills", [])
    known_ids = {item["id"] for item in skills}
    if skill_id not in known_ids:
        await callback.message.answer("Навык не найден.")
        return
    selected = set(data.get("skill_ids", []))
    if skill_id in selected:
        selected.remove(skill_id)
    else:
        selected.add(skill_id)
    await state.update_data(skill_ids=list(sorted(selected)))
    keyboard = _build_skills_keyboard(skills, selected)
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except TelegramBadRequest:
        pass


@router.callback_query(OnboardingStates.skills, F.data == "m:onboarding:skills_done")
async def onboarding_skills_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("skill_ids"):
        await callback.answer("Выберите хотя бы один навык.", show_alert=True)
        return
    await callback.answer()
    await state.set_state(OnboardingStates.passport)
    await push_step_message(
        callback,
        state,
        "Загрузите фото или PDF паспорта (разворот с фото).",
    )


@router.message(OnboardingStates.passport, F.content_type.in_({ContentType.PHOTO, ContentType.DOCUMENT}))
async def onboarding_passport_file(message: Message, state: FSMContext) -> None:
    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "PHOTO"
    else:
        file_id = message.document.file_id
        file_type = "DOCUMENT"
    await state.update_data(passport_file={"file_id": file_id, "file_type": file_type})
    await state.set_state(OnboardingStates.selfie)
    await push_step_message(message, state, "Теперь загрузите селфи с паспортом (видно лицо).")


@router.message(OnboardingStates.passport)
async def onboarding_passport_invalid(message: Message) -> None:
    await message.answer("Нужно фото или PDF-документ.")


@router.message(OnboardingStates.selfie, F.content_type == ContentType.PHOTO)
async def onboarding_selfie_file(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(selfie_file={"file_id": file_id, "file_type": "PHOTO"})
    await state.set_state(OnboardingStates.payout_method)
    await push_step_message(
        message,
        state,
        "Выберите способ выплаты.",
        payout_methods_keyboard(AVAILABLE_PAYOUT_METHODS),
    )


@router.message(OnboardingStates.selfie)
async def onboarding_selfie_invalid(message: Message) -> None:
    await message.answer("Нужна фотография (селфи).")


@router.callback_query(OnboardingStates.payout_method, F.data.startswith("m:onboarding:payout:"))
async def onboarding_payout_method(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    code = callback.data.split(":")[-1].upper()
    try:
        method = m.PayoutMethod[code]
    except KeyError:
        await callback.message.answer("Способ не найден.")
        return
    await state.update_data(payout_method=method.value)
    await state.set_state(OnboardingStates.payout_requisites)
    await push_step_message(callback, state, _payout_prompt(method))


@router.message(OnboardingStates.payout_requisites)
async def onboarding_payout_requisites(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    method_value = data.get("payout_method")
    if not method_value:
        await message.answer("Сначала выберите способ выплаты.")
        return
    try:
        payout = onboarding_service.validate_payout(method_value, message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(payout_method=payout.method.value, payout_payload=payout.payload)
    await state.set_state(OnboardingStates.home_geo)
    await push_step_message(
        message,
        state,
        "Укажите домашнюю геолокацию (необязательно) или пропустите этот шаг.",
        home_geo_keyboard(),
    )


@router.callback_query(OnboardingStates.home_geo, F.data == "m:onboarding:home_geo_share")
async def onboarding_home_geo_share(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        "Нажмите кнопку прикрепления в Telegram и выберите геолокацию, "
        "либо отправьте координаты текстом: 55.75580, 37.61730."
    )


@router.callback_query(OnboardingStates.home_geo, F.data == "m:onboarding:home_geo_skip")
async def onboarding_home_geo_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.update_data(home_lat=None, home_lon=None)
    await _show_summary(callback.message, state)


@router.message(OnboardingStates.home_geo, F.content_type == ContentType.LOCATION)
async def onboarding_home_geo_location(message: Message, state: FSMContext) -> None:
    location = message.location
    await state.update_data(home_lat=location.latitude, home_lon=location.longitude)
    await _show_summary(message, state)


@router.message(OnboardingStates.home_geo, F.content_type == ContentType.TEXT)
async def onboarding_home_geo_text(message: Message, state: FSMContext) -> None:
    text_value = (message.text or "").strip()
    if "," not in text_value:
        await message.answer("Формат координат: широта, долгота. Например: 55.75580, 37.61730.")
        return
    lat_part, lon_part = [part.strip() for part in text_value.split(",", 1)]
    try:
        latitude = float(lat_part)
        longitude = float(lon_part)
    except ValueError:
        await message.answer("Неверный формат. Попробуйте снова.")
        return
    await state.update_data(home_lat=latitude, home_lon=longitude)
    await _show_summary(message, state)


@router.message(OnboardingStates.home_geo)
async def onboarding_home_geo_other(message: Message) -> None:
    await message.answer("Отправьте геолокацию или координаты.")


async def _show_summary(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    full_name = " ".join(
        part for part in [data.get("last_name"), data.get("first_name"), data.get("middle_name")] if part
    )
    district_names = [
        item["name"]
        for item in data.get("districts", [])
        if item["id"] in set(data.get("district_ids", []))
    ]
    skill_names = [
        item["name"]
        for item in data.get("skills", [])
        if item["id"] in set(data.get("skill_ids", []))
    ]
    payout_method = data.get("payout_method")
    payout_payload = data.get("payout_payload", {})
    lines = [
        ONBOARDING_SUMMARY_HEADER,
        f"ФИО: {full_name or '—'}",
        f"Телефон: {data.get('phone', '')}",
        f"Город: {data.get('city_name', '')}",
        f"Районы: {', '.join(district_names) if district_names else '—'}",
        f"Автомобиль: {'Да' if data.get('has_vehicle') else 'Нет'}",
        f"Навыки: {', '.join(skill_names) if skill_names else '—'}",
        f"Способ выплаты: {_format_payout_summary(payout_method, payout_payload)}",
    ]
    if data.get("home_lat") is not None and data.get("home_lon") is not None:
        lines.append(f"Дом-база: {data['home_lat']:.5f}, {data['home_lon']:.5f}")
    else:
        lines.append("Дом-база: не указана")

    keyboard = inline_keyboard(
        [[InlineKeyboardButton(text="✅ Отправить", callback_data="m:onboarding:confirm")]]
    )
    await state.set_state(OnboardingStates.confirm)
    await push_step_message(event, state, "\n".join(lines), keyboard)


@router.callback_query(OnboardingStates.confirm, F.data == "m:onboarding:confirm")
async def onboarding_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    await callback.answer("Анкета отправлена на модерацию.")
    data = await state.get_data()
    required_keys = [
        "last_name",
        "first_name",
        "phone",
        "city_id",
        "district_ids",
        "skill_ids",
        "passport_file",
        "selfie_file",
        "payout_method",
        "payout_payload",
    ]
    if any(key not in data or not data[key] for key in required_keys):
        await callback.message.answer("Не все данные заполнены. Начните анкету заново.")
        return

    full_name = " ".join(
        part for part in [data.get("last_name"), data.get("first_name"), data.get("middle_name")] if part
    )
    master.full_name = full_name
    master.phone = data["phone"]
    master.city_id = data["city_id"]
    master.has_vehicle = bool(data.get("has_vehicle"))
    master.pdn_accepted_at = now_utc()
    master.verified = False
    master.is_active = False
    master.is_on_shift = False
    master.shift_status = m.ShiftStatus.SHIFT_OFF
    master.break_until = None
    master.moderation_status = m.ModerationStatus.PENDING

    payout_method = m.PayoutMethod(data["payout_method"])
    master.payout_method = payout_method
    master.payout_data = data.get("payout_payload", {})

    if data.get("home_lat") is not None and data.get("home_lon") is not None:
        master.home_latitude = data["home_lat"]
        master.home_longitude = data["home_lon"]
    else:
        master.home_latitude = None
        master.home_longitude = None

    passport_info = data.get("passport_file", {})
    selfie_info = data.get("selfie_file", {})

    await session.execute(
        delete(m.master_districts).where(m.master_districts.master_id == master.id)
    )
    district_values = [
        {"master_id": master.id, "district_id": district_id}
        for district_id in set(data.get("district_ids", []))
    ]
    if district_values:
        await session.execute(insert(m.master_districts), district_values)

    await session.execute(
        delete(m.master_skills).where(m.master_skills.master_id == master.id)
    )
    skill_values = [
        {"master_id": master.id, "skill_id": skill_id}
        for skill_id in set(data.get("skill_ids", []))
    ]
    if skill_values:
        await session.execute(insert(m.master_skills), skill_values)

    await session.execute(
        delete(m.attachments)
        .where(m.attachments.entity_type == m.AttachmentEntity.MASTER)
        .where(m.attachments.entity_id == master.id)
    )
    attachments: list[m.attachments] = []
    if passport_info:
        attachments.append(
            m.attachments(
                entity_type=m.AttachmentEntity.MASTER,
                entity_id=master.id,
                file_type=m.AttachmentFileType[passport_info["file_type"]],
                file_id=passport_info["file_id"],
                document_type="passport",
                uploaded_by_master_id=master.id,
            )
        )
    if selfie_info:
        attachments.append(
            m.attachments(
                entity_type=m.AttachmentEntity.MASTER,
                entity_id=master.id,
                file_type=m.AttachmentFileType[selfie_info["file_type"]],
                file_id=selfie_info["file_id"],
                document_type="selfie",
                uploaded_by_master_id=master.id,
            )
        )
    session.add_all(attachments)

    access_code = data.get("access_code") or {}
    if access_code:
        code_id = access_code.get("id")
        source = access_code.get("source")
        if source == "master" and code_id:
            code = await session.get(m.master_invite_codes, code_id)
            if code:
                await onboarding_service.mark_code_used(session, code, master.id)
        elif source == "staff" and code_id:
            staff_code = await session.get(m.staff_access_codes, code_id)
            if staff_code:
                staff_code.used_at = now_utc()
                staff_code.is_revoked = True

    await session.commit()

    await clear_step_messages(callback.message.bot, state, callback.message.chat.id)
    await state.clear()
    await callback.message.answer(ONBOARDING_SENT)


async def _load_districts(session: AsyncSession, city_id: int) -> list[dict[str, int | str]]:
    stmt = (
        select(m.districts)
        .where(m.districts.city_id == city_id)
        .order_by(m.districts.name.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [{"id": row.id, "name": row.name} for row in rows]


def _build_district_keyboard(
    districts: Sequence[dict[str, int | str]],
    selected_ids: Sequence[int],
    page: int,
):
    pages = max(1, math.ceil(len(districts) / DISTRICTS_PER_PAGE))
    page = max(1, min(page, pages))
    start = (page - 1) * DISTRICTS_PER_PAGE
    chunk = districts[start : start + DISTRICTS_PER_PAGE]
    selected = set(selected_ids)
    options = [(item['id'], item['name'], item['id'] in selected) for item in chunk]
    return districts_keyboard(options=options, page=page, total_pages=pages)


def _build_skills_keyboard(
    skills: Sequence[dict[str, int | str]],
    selected_ids: Sequence[int],
):
    selected = set(selected_ids)
    options = [(item['id'], item['name'], item['id'] in selected) for item in skills]
    return skills_keyboard(options)


def _payout_prompt(method: m.PayoutMethod) -> str:
    if method is m.PayoutMethod.CARD:
        return "Введите номер карты (1619 или 16 цифр без пробелов)."
    if method is m.PayoutMethod.SBP:
        return "Введите телефон, привязанный к СБП (формат +7XXXXXXXXXX или 8XXXXXXXXXX)."
    if method is m.PayoutMethod.YOOMONEY:
        return "Введите номер счёта (email или кошелёк из 11 цифр)."
    if method is m.PayoutMethod.BANK_ACCOUNT:
        return "Введите номер счета (10/12), БИК (9) и корреспондентский счёт (20) через пробел."
    return "Введите платёжные реквизиты."


def _format_payout_summary(method_value: str | None, payload: dict | None) -> str:
    if not method_value:
        return ''
    try:
        method = m.PayoutMethod(method_value)
    except ValueError:
        return method_value
    payload = payload or {}
    if method is m.PayoutMethod.CARD:
        number = payload.get('card_number', '')
        digits = ''.join(ch for ch in number if ch.isdigit())
        last4 = digits[-4:] if digits else ''
        return f"Карта *{last4}" if last4 else "Карта"
    if method is m.PayoutMethod.SBP:
        phone = payload.get('sbp_phone', '')
        return f"СБП {phone}".strip() or "СБП"
    if method is m.PayoutMethod.YOOMONEY:
        account = payload.get('account', '')
        return f"ЮMoney {account}".strip() or "ЮMoney"
    if method is m.PayoutMethod.BANK_ACCOUNT:
        account = payload.get('account_number', '')
        last4 = account[-4:] if account else ''
        return f"Банк счёт *{last4}" if last4 else "Банк счёт"
    return method.value



