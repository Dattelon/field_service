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

# Шаги онбординга для прогресс-бара
ONBOARDING_STEPS = [
    "ПДн",           # 1
    "Фамилия",       # 2
    "Имя",           # 3
    "Отчество",      # 4
    "Телефон",       # 5
    "Реф. код",      # 6
    "Город",         # 7
    "Районы",        # 8
    "Авто",          # 9
    "Навыки",        # 10
    "Паспорт",       # 11
    "Селфи",         # 12
    "Выплаты",       # 13
    "Реквизиты",     # 14
    "Геолокация",    # 15
    "Подтверждение", # 16
]

def _progress_bar(current_step: int, total_steps: int = 16) -> str:
    """Генерирует прогресс-бар для онбординга."""
    filled = "▓"
    empty = "░"
    bar_length = 10
    filled_count = int(bar_length * current_step / total_steps)
    empty_count = bar_length - filled_count
    bar = filled * filled_count + empty * empty_count
    percent = int(100 * current_step / total_steps)
    step_name = ONBOARDING_STEPS[current_step - 1] if 0 < current_step <= len(ONBOARDING_STEPS) else ""
    return f"📋 Шаг {current_step}/{total_steps}: {step_name}\n{bar} {percent}%\n"


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
    text = _progress_bar(1) + "\n" + MASTER_PDN_CONSENT
    await push_step_message(
        callback,
        state,
        text,
        reply_markup=pdn_keyboard(),
    )


@router.callback_query(OnboardingStates.pdn, F.data == "m:onboarding:pdn_accept")
async def onboarding_pdn_accept(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.set_state(OnboardingStates.last_name)
    text = _progress_bar(2) + "\nВведите вашу фамилию (от 2 до 230 символов)."
    await push_step_message(callback, state, text)


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
    text = _progress_bar(3) + "\nВведите ваше имя (от 2 до 230 символов)."
    await push_step_message(message, state, text)


@router.message(OnboardingStates.first_name)
async def onboarding_first_name(message: Message, state: FSMContext) -> None:
    try:
        first_name = onboarding_service.validate_name_part(message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(first_name=first_name)
    await state.set_state(OnboardingStates.middle_name)
    text = _progress_bar(4) + "\nВведите ваше отчество или прочерк-минус, если его нет."
    await push_step_message(message, state, text)


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
    text = _progress_bar(5) + "\nВведите ваш телефон формата +7XXXXXXXXXX или 8XXXXXXXXXX."
    await push_step_message(message, state, text)


@router.message(OnboardingStates.phone)
async def onboarding_phone(message: Message, state: FSMContext) -> None:
    try:
        phone = onboarding_service.normalize_phone(message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(phone=phone)
    await state.set_state(OnboardingStates.referral_code)
    text = (
        _progress_bar(6) + "\n\n"
        "📨 <b>Реферальный код</b>\n\n"
        "Если у вас есть реферальный код от другого мастера, введите его.\n"
        "Это даст бонусы вам обоим!\n\n"
        "Если кода нет — нажмите «Пропустить»."
    )
    keyboard = inline_keyboard([
        [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="m:onb:ref:skip")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="m:cancel")],
    ])
    await push_step_message(message, state, text, reply_markup=keyboard)


@router.callback_query(OnboardingStates.referral_code, F.data == "m:onb:ref:skip")
async def onboarding_referral_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer("Пропущено")
    await state.update_data(referral_code=None, referrer_id=None)
    await state.set_state(OnboardingStates.city)
    text = _progress_bar(7) + "\nНапишите название города: можно начать вводить и увидеть подсказки."
    await push_step_message(callback, state, text)


@router.message(OnboardingStates.referral_code)
async def onboarding_referral_code(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    master: m.masters,
) -> None:
    code_input = (message.text or "").strip().upper()

    # Валидация формата (8 символов, буквы/цифры)
    if not code_input or len(code_input) != 8 or not code_input.isalnum():
        await message.answer(
            "❌ Неверный формат кода.\n"
            "Код должен содержать ровно 8 символов (буквы и цифры).\n\n"
            "Попробуйте ещё раз или нажмите «Пропустить»."
        )
        return

    # Проверка существования кода
    result = await session.execute(
        select(m.masters.id, m.masters.full_name)
        .where(m.masters.referral_code == code_input)
    )
    referrer = result.one_or_none()

    if not referrer:
        await message.answer(
            "❌ Код не найден.\n"
            "Проверьте правильность ввода или нажмите «Пропустить»."
        )
        return

    referrer_id, referrer_name = referrer

    # Проверка на самореферал
    if referrer_id == master.id:
        await message.answer(
            "❌ Нельзя использовать свой собственный код!\n"
            "Введите код другого мастера или нажмите «Пропустить»."
        )
        return

    # Сохраняем код
    await state.update_data(referral_code=code_input, referrer_id=referrer_id)
    await message.answer(
        f"✅ Код принят!\n"
        f"Вас пригласил: {referrer_name or 'Мастер #' + str(referrer_id)}"
    )

    # Переход к городу
    await state.set_state(OnboardingStates.city)
    text = _progress_bar(7) + "\nНапишите название города: можно начать вводить и увидеть подсказки."
    await push_step_message(message, state, text)


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
        text = _progress_bar(9) + "\nЕсть ли у вас автомобиль?"
        await push_step_message(callback, state, text, vehicle_keyboard())
        return

    await state.update_data(districts=districts, district_page=1, district_ids=[])
    await state.set_state(OnboardingStates.districts)
    keyboard = _build_district_keyboard(districts, set(), page=1)
    text = _progress_bar(8) + "\nВыберите районы работы (можно несколько)."
    await push_step_message(callback, state, text, keyboard)


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
    text = _progress_bar(9) + "\nЕсть ли у вас автомобиль?"
    await push_step_message(callback, state, text, vehicle_keyboard())


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
    text = _progress_bar(10) + "\nВыберите ваши навыки (можно несколько)."
    await push_step_message(event, state, text, keyboard)


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
    text = _progress_bar(11) + "\nЗагрузите фото или PDF паспорта (разворот с фото)."
    await push_step_message(callback, state, text)


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
    text = _progress_bar(12) + "\nТеперь загрузите селфи с паспортом (видно лицо)."
    await push_step_message(message, state, text)


@router.message(OnboardingStates.passport)
async def onboarding_passport_invalid(message: Message) -> None:
    await message.answer("Нужно фото или PDF-документ.")


@router.message(OnboardingStates.selfie, F.content_type == ContentType.PHOTO)
async def onboarding_selfie_file(message: Message, state: FSMContext) -> None:
    file_id = message.photo[-1].file_id
    await state.update_data(selfie_file={"file_id": file_id, "file_type": "PHOTO"})
    await state.set_state(OnboardingStates.payout_method)
    text = _progress_bar(13) + "\nВыберите способ выплаты."
    await push_step_message(
        message,
        state,
        text,
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
    text = _progress_bar(14) + "\n" + _payout_prompt(method)
    await push_step_message(callback, state, text)


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
    text = _progress_bar(15) + "\nУкажите домашнюю геолокацию (необязательно) или пропустите этот шаг."
    await push_step_message(
        message,
        state,
        text,
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

    text = _progress_bar(16) + "\n" + ONBOARDING_SUMMARY_HEADER + "\n"
    lines = [
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
    await push_step_message(event, state, text + "\n".join(lines), keyboard)


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

    # Обработка реферального кода
    referral_code = data.get("referral_code")
    referrer_id = data.get("referrer_id")
    if referral_code and referrer_id:
        # Обновляем referred_by_master_id в мастере
        master.referred_by_master_id = referrer_id

        # Создаём запись в referrals (для уровня 1)
        # Проверяем, нет ли уже записи
        existing = await session.execute(
            select(m.referrals.id).where(m.referrals.master_id == master.id)
        )
        if existing.scalar_one_or_none() is None:
            referral_entry = m.referrals(
                master_id=master.id,
                referrer_id=referrer_id
            )
            session.add(referral_entry)

            # Отправляем уведомление рефереру о новом реферале
            from field_service.services import push_notifications
            await push_notifications.notify_master(
                session,
                master_id=referrer_id,
                event=push_notifications.NotificationEvent.REFERRAL_REGISTERED,
                referred_name=full_name,
            )

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



