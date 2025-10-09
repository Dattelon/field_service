# ===== ЧАСТЬ 1: Новая версия _show_summary с кнопками редактирования =====

async def _show_summary(event: Message | CallbackQuery, state: FSMContext) -> None:
    """Показывает summary с кнопками редактирования для каждого поля."""
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

    # Кнопки редактирования
    edit_buttons = [
        [InlineKeyboardButton(text="✏️ Изменить ФИО", callback_data="m:onb:edit:name")],
        [InlineKeyboardButton(text="✏️ Изменить телефон", callback_data="m:onb:edit:phone")],
        [InlineKeyboardButton(text="✏️ Изменить город", callback_data="m:onb:edit:city")],
    ]
    
    # Кнопку редактирования районов показываем только если они есть
    if data.get("districts"):
        edit_buttons.append(
            [InlineKeyboardButton(text="✏️ Изменить районы", callback_data="m:onb:edit:districts")]
        )
    
    edit_buttons.extend([
        [InlineKeyboardButton(text="✏️ Изменить автомобиль", callback_data="m:onb:edit:vehicle")],
        [InlineKeyboardButton(text="✏️ Изменить навыки", callback_data="m:onb:edit:skills")],
        [InlineKeyboardButton(text="✏️ Изменить способ выплаты", callback_data="m:onb:edit:payout")],
        [InlineKeyboardButton(text="✏️ Изменить дом-базу", callback_data="m:onb:edit:home_geo")],
        [InlineKeyboardButton(text="✅ Отправить на модерацию", callback_data="m:onboarding:confirm")],
    ])

    keyboard = inline_keyboard(edit_buttons)
    await state.set_state(OnboardingStates.confirm)
    await push_step_message(event, state, "\n".join(lines), keyboard)


# ===== ЧАСТЬ 2: Callback handlers для редактирования =====

@router.callback_query(OnboardingStates.confirm, F.data == "m:onb:edit:name")
async def onboarding_edit_name(callback: CallbackQuery, state: FSMContext) -> None:
    """Переход к редактированию ФИО."""
    await state.update_data(is_editing=True)
    await state.set_state(OnboardingStates.last_name)
    await push_step_message(
        callback,
        state,
        "Введите новую фамилию (от 2 до 230 символов).",
    )
    await callback.answer()


@router.callback_query(OnboardingStates.confirm, F.data == "m:onb:edit:phone")
async def onboarding_edit_phone(callback: CallbackQuery, state: FSMContext) -> None:
    """Переход к редактированию телефона."""
    await state.update_data(is_editing=True)
    await state.set_state(OnboardingStates.phone)
    await push_step_message(
        callback,
        state,
        "Введите новый телефон формата +7XXXXXXXXXX или 8XXXXXXXXXX.",
    )
    await callback.answer()


@router.callback_query(OnboardingStates.confirm, F.data == "m:onb:edit:city")
async def onboarding_edit_city(callback: CallbackQuery, state: FSMContext) -> None:
    """Переход к редактированию города."""
    await state.update_data(is_editing=True)
    await state.set_state(OnboardingStates.city)
    await callback.message.answer(
        "Напишите название города: можно начать вводить и увидеть подсказки."
    )
    await callback.answer()


@router.callback_query(OnboardingStates.confirm, F.data == "m:onb:edit:districts")
async def onboarding_edit_districts(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Переход к редактированию районов."""
    data = await state.get_data()
    city_id = data.get("city_id")
    if not city_id:
        await callback.answer("Сначала выберите город.", show_alert=True)
        return
    
    await state.update_data(is_editing=True)
    districts = await _load_districts(session, city_id)
    if not districts:
        await callback.answer("В этом городе нет районов для выбора.", show_alert=True)
        return
    
    selected = set(data.get("district_ids", []))
    await state.update_data(districts=districts, district_page=1)
    await state.set_state(OnboardingStates.districts)
    keyboard = _build_district_keyboard(districts, selected, page=1)
    await push_step_message(
        callback,
        state,
        "Выберите районы работы (можно несколько).",
        keyboard,
    )
    await callback.answer()
# ===== ЧАСТЬ 3: Остальные callback handlers для редактирования =====

@router.callback_query(OnboardingStates.confirm, F.data == "m:onb:edit:vehicle")
async def onboarding_edit_vehicle(callback: CallbackQuery, state: FSMContext) -> None:
    """Переход к редактированию наличия автомобиля."""
    await state.update_data(is_editing=True)
    await state.set_state(OnboardingStates.vehicle)
    await push_step_message(
        callback,
        state,
        "Есть ли у вас автомобиль?",
        vehicle_keyboard(),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.confirm, F.data == "m:onb:edit:skills")
async def onboarding_edit_skills(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    """Переход к редактированию навыков."""
    await state.update_data(is_editing=True)
    
    # Загружаем навыки заново
    stmt = select(m.skills).where(m.skills.is_active.is_(True)).order_by(m.skills.name.asc())
    skills = (await session.execute(stmt)).scalars().all()
    skills_data = [{"id": skill.id, "name": skill.name} for skill in skills]
    
    data = await state.get_data()
    selected = set(data.get("skill_ids", []))
    
    await state.update_data(skills=skills_data)
    await state.set_state(OnboardingStates.skills)
    keyboard = _build_skills_keyboard(skills_data, selected)
    await push_step_message(
        callback, 
        state, 
        "Выберите ваши навыки (можно несколько).", 
        keyboard
    )
    await callback.answer()


@router.callback_query(OnboardingStates.confirm, F.data == "m:onb:edit:payout")
async def onboarding_edit_payout(callback: CallbackQuery, state: FSMContext) -> None:
    """Переход к редактированию способа выплаты."""
    await state.update_data(is_editing=True)
    await state.set_state(OnboardingStates.payout_method)
    await push_step_message(
        callback,
        state,
        "Выберите способ выплаты.",
        payout_methods_keyboard(AVAILABLE_PAYOUT_METHODS),
    )
    await callback.answer()


@router.callback_query(OnboardingStates.confirm, F.data == "m:onb:edit:home_geo")
async def onboarding_edit_home_geo(callback: CallbackQuery, state: FSMContext) -> None:
    """Переход к редактированию домашней геолокации."""
    await state.update_data(is_editing=True)
    await state.set_state(OnboardingStates.home_geo)
    await push_step_message(
        callback,
        state,
        "Укажите домашнюю геолокацию (необязательно) или пропустите этот шаг.",
        home_geo_keyboard(),
    )
    await callback.answer()


# ===== ЧАСТЬ 4: Модификация существующих handlers =====
# Добавляем проверку is_editing в конце каждого handler'а

# Пример для onboarding_phone:
@router.message(OnboardingStates.phone)
async def onboarding_phone(message: Message, state: FSMContext) -> None:
    try:
        phone = onboarding_service.normalize_phone(message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(phone=phone)
    
    # НОВОЕ: Проверка флага редактирования
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)  # Сбрасываем флаг
        await _show_summary(message, state)
        return
    
    # Обычный flow
    await state.set_state(OnboardingStates.city)
    await message.answer(
        "Напишите название города: можно начать вводить и увидеть подсказки."
    )


# Пример для onboarding_first_name:
@router.message(OnboardingStates.first_name)
async def onboarding_first_name(message: Message, state: FSMContext) -> None:
    try:
        first_name = onboarding_service.validate_name_part(message.text or "")
    except onboarding_service.ValidationError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(first_name=first_name)
    
    # НОВОЕ: Проверка флага редактирования
    data = await state.get_data()
    if data.get("is_editing"):
        # При редактировании ФИО нужно пройти все 3 поля
        await state.set_state(OnboardingStates.middle_name)
        await push_step_message(
            message,
            state,
            "Введите ваше отчество или прочерк-минус, если его нет.",
        )
        return
    
    # Обычный flow
    await state.set_state(OnboardingStates.middle_name)
    await push_step_message(
        message,
        state,
        "Введите ваше отчество или прочерк-минус, если его нет.",
    )


# Пример для onboarding_middle_name:
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
    
    # НОВОЕ: Проверка флага редактирования
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await _show_summary(message, state)
        return
    
    # Обычный flow
    await state.set_state(OnboardingStates.phone)
    await push_step_message(
        message,
        state,
        "Введите ваш телефон формата +7XXXXXXXXXX или 8XXXXXXXXXX.",
    )
# ===== ЧАСТЬ 5: Модификации для city, districts, vehicle, skills =====

# onboarding_city_pick - выбор города
@router.callback_query(OnboardingStates.city, F.data.startswith("m:onboarding:city:"))
async def onboarding_city_pick(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    city_id = int(callback.data.split(":")[-1])
    data = await state.get_data()
    option_lookup = {item["id"]: item["name"] for item in data.get("city_options", [])}
    if city_id not in option_lookup:
        await callback.answer("Город устарел. Выберите снова.", show_alert=True)
        return
    city_name = option_lookup[city_id]
    
    # НОВОЕ: При смене города в режиме редактирования сбрасываем районы
    is_editing = data.get("is_editing", False)
    if is_editing:
        await state.update_data(city_id=city_id, city_name=city_name, district_ids=[])
    else:
        await state.update_data(city_id=city_id, city_name=city_name, district_ids=[])

    districts = await _load_districts(session, city_id)
    if not districts:
        # Нет районов в городе
        if is_editing:
            await state.update_data(is_editing=False, districts=[])
            await _show_summary(callback.message, state)
            await callback.answer("Город изменён. В этом городе нет районов.")
            return
        else:
            # Обычный flow
            await state.set_state(OnboardingStates.vehicle)
            await push_step_message(
                callback,
                state,
                "Есть ли у вас автомобиль?",
                vehicle_keyboard(),
            )
            await callback.answer()
            return

    await state.update_data(districts=districts, district_page=1, district_ids=[])
    await state.set_state(OnboardingStates.districts)
    keyboard = _build_district_keyboard(districts, set(), page=1)
    await push_step_message(
        callback,
        state,
        "Выберите районы работы (можно несколько). При смене города старые районы сброшены.",
        keyboard,
    )
    await callback.answer()


# onboarding_districts_done - завершение выбора районов
@router.callback_query(OnboardingStates.districts, F.data == "m:onboarding:districts_done")
async def onboarding_districts_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = data.get("district_ids", [])
    if not selected:
        await callback.answer("Выберите хотя бы один район.", show_alert=True)
        return
    
    # НОВОЕ: Проверка флага редактирования
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await _show_summary(callback.message, state)
        await callback.answer("Районы обновлены")
        return
    
    # Обычный flow
    await state.set_state(OnboardingStates.vehicle)
    await push_step_message(
        callback,
        state,
        "Есть ли у вас автомобиль?",
        vehicle_keyboard(),
    )
    await callback.answer()


# onboarding_vehicle_yes/no - выбор автомобиля
@router.callback_query(OnboardingStates.vehicle, F.data == "m:onboarding:vehicle_yes")
async def onboarding_vehicle_yes(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.update_data(has_vehicle=True)
    
    # НОВОЕ: Проверка флага редактирования
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await _show_summary(callback.message, state)
        await callback.answer("Автомобиль обновлён")
        return
    
    # Обычный flow
    await _start_skills(callback, state, session)
    await callback.answer()


@router.callback_query(OnboardingStates.vehicle, F.data == "m:onboarding:vehicle_no")
async def onboarding_vehicle_no(
    callback: CallbackQuery,
    state: FSMContext,
    session: AsyncSession,
) -> None:
    await state.update_data(has_vehicle=False)
    
    # НОВОЕ: Проверка флага редактирования
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await _show_summary(callback.message, state)
        await callback.answer("Автомобиль обновлён")
        return
    
    # Обычный flow
    await _start_skills(callback, state, session)
    await callback.answer()


# onboarding_skills_done - завершение выбора навыков
@router.callback_query(OnboardingStates.skills, F.data == "m:onboarding:skills_done")
async def onboarding_skills_done(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    if not data.get("skill_ids"):
        await callback.answer("Выберите хотя бы один навык.", show_alert=True)
        return
    
    # НОВОЕ: Проверка флага редактирования
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await _show_summary(callback.message, state)
        await callback.answer("Навыки обновлены")
        return
    
    # Обычный flow
    await state.set_state(OnboardingStates.passport)
    await push_step_message(
        callback,
        state,
        "Загрузите фото или PDF паспорта (разворот с фото).",
    )
    await callback.answer()
# ===== ЧАСТЬ 6: Модификации для payout и home_geo =====

# onboarding_payout_requisites - ввод реквизитов выплаты
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
    
    # НОВОЕ: Проверка флага редактирования
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await _show_summary(message, state)
        return
    
    # Обычный flow
    await state.set_state(OnboardingStates.home_geo)
    await push_step_message(
        message,
        state,
        "Укажите домашнюю геолокацию (необязательно) или пропустите этот шаг.",
        home_geo_keyboard(),
    )


# onboarding_home_geo_skip - пропуск геолокации
@router.callback_query(OnboardingStates.home_geo, F.data == "m:onboarding:home_geo_skip")
async def onboarding_home_geo_skip(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(home_lat=None, home_lon=None)
    
    # НОВОЕ: Проверка флага редактирования
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
        await callback.answer("Геолокация сброшена")
    
    await _show_summary(callback.message, state)
    await callback.answer()


# onboarding_home_geo_location - геолокация через кнопку
@router.message(OnboardingStates.home_geo, F.content_type == ContentType.LOCATION)
async def onboarding_home_geo_location(message: Message, state: FSMContext) -> None:
    location = message.location
    await state.update_data(home_lat=location.latitude, home_lon=location.longitude)
    
    # НОВОЕ: Проверка флага редактирования
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
    
    await _show_summary(message, state)


# onboarding_home_geo_text - геолокация текстом
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
    
    # НОВОЕ: Проверка флага редактирования
    data = await state.get_data()
    if data.get("is_editing"):
        await state.update_data(is_editing=False)
    
    await _show_summary(message, state)


# ===== ИТОГОВЫЙ СПИСОК ИЗМЕНЕНИЙ =====

"""
SUMMARY OF CHANGES:
===================

1. _show_summary() - добавлены кнопки редактирования для всех полей

2. Новые callback handlers для редактирования:
   - m:onb:edit:name
   - m:onb:edit:phone
   - m:onb:edit:city
   - m:onb:edit:districts
   - m:onb:edit:vehicle
   - m:onb:edit:skills
   - m:onb:edit:payout
   - m:onb:edit:home_geo

3. Модифицированы существующие handlers:
   - onboarding_phone
   - onboarding_first_name
   - onboarding_middle_name
   - onboarding_city_pick
   - onboarding_districts_done
   - onboarding_vehicle_yes/no
   - onboarding_skills_done
   - onboarding_payout_requisites
   - onboarding_home_geo_skip/location/text

4. Логика is_editing флага:
   - Устанавливается в True при нажатии кнопки редактирования
   - Проверяется в конце каждого handler'а
   - Сбрасывается в False после возврата к summary
   
5. Особенности:
   - При редактировании города сбрасываются районы
   - При редактировании ФИО нужно пройти все 3 поля
   - Файлы (паспорт, селфи) не редактируются (слишком сложно)

TESTING CHECKLIST:
==================
✅ Редактирование ФИО (3 поля последовательно)
✅ Редактирование телефона
✅ Редактирование города (проверка сброса районов)
✅ Редактирование районов
✅ Редактирование автомобиля
✅ Редактирование навыков
✅ Редактирование способа выплаты
✅ Редактирование/сброс геолокации
✅ Возврат к summary после каждого редактирования
✅ Отправка анкеты после редактирования
"""
