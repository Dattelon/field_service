from __future__ import annotations

from typing import Iterable, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from field_service.db import models as m

from .texts import MAIN_MENU_BUTTONS
from .utils import inline_keyboard


def start_onboarding_keyboard() -> InlineKeyboardMarkup:
    return inline_keyboard(
        [
            [
                InlineKeyboardButton(
                    text=MAIN_MENU_BUTTONS["start_onboarding"],
                    callback_data="m:onboarding:start",
                )
            ]
        ]
    )


def pdn_keyboard() -> InlineKeyboardMarkup:
    return inline_keyboard(
        [
            [InlineKeyboardButton(text="Согласен", callback_data="m:onboarding:pdn_accept")],
            [InlineKeyboardButton(text="Не согласен", callback_data="m:onboarding:pdn_decline")],
        ]
    )


def vehicle_keyboard() -> InlineKeyboardMarkup:
    return inline_keyboard(
        [
            [InlineKeyboardButton(text="Есть авто", callback_data="m:onboarding:vehicle_yes")],
            [InlineKeyboardButton(text="Нет авто", callback_data="m:onboarding:vehicle_no")],
        ]
    )


def districts_keyboard(
    *,
    options: Sequence[tuple[int, str, bool]],
    page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for district_id, title, selected in options:
        label = ("✅ " if selected else "▫️ ") + title
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"m:onboarding:district:{district_id}")]
        )

    controls: list[InlineKeyboardButton] = []
    if total_pages > 1:
        if page > 1:
            controls.append(
                InlineKeyboardButton(text="‹ Назад", callback_data=f"m:onboarding:districts_page:{page - 1}")
            )
        controls.append(
            InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="m:onboarding:districts_page:noop")
        )
        if page < total_pages:
            controls.append(
                InlineKeyboardButton(text="Вперёд ›", callback_data=f"m:onboarding:districts_page:{page + 1}")
            )
    controls.append(InlineKeyboardButton(text="Готово", callback_data="m:onboarding:districts_done"))
    if controls:
        rows.append(controls)
    return inline_keyboard(rows)


def skills_keyboard(skills: Sequence[tuple[int, str, bool]]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for skill_id, title, selected in skills:
        label = ("✅ " if selected else "▫️ ") + title
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"m:onboarding:skill:{skill_id}")]
        )
    rows.append([InlineKeyboardButton(text="Готово", callback_data="m:onboarding:skills_done")])
    return inline_keyboard(rows)


def payout_methods_keyboard(methods: Iterable[m.PayoutMethod]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for method in methods:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_method_title(method),
                    callback_data=f"m:onboarding:payout:{method.value.lower()}",
                )
            ]
        )
    return inline_keyboard(rows)


def home_geo_keyboard() -> InlineKeyboardMarkup:
    return inline_keyboard(
        [
        [InlineKeyboardButton(text="Отправить геопозицию", callback_data="m:onboarding:home_geo_share")],
        [InlineKeyboardButton(text="Пропустить", callback_data="m:onboarding:home_geo_skip")],
        ]
    )


def main_menu_keyboard(master: m.masters) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if getattr(master, "verified", False):
        shift_status = getattr(master, "shift_status", m.ShiftStatus.SHIFT_OFF)
        if shift_status is m.ShiftStatus.SHIFT_OFF:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=MAIN_MENU_BUTTONS["shift_on"],
                        callback_data="m:sh:on",
                    )
                ]
            )
        elif shift_status is m.ShiftStatus.SHIFT_ON:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=MAIN_MENU_BUTTONS["shift_break"],
                        callback_data="m:sh:brk",
                    )
                ]
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=MAIN_MENU_BUTTONS["shift_off"],
                        callback_data="m:sh:off",
                    )
                ]
            )
        elif shift_status is m.ShiftStatus.BREAK:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=MAIN_MENU_BUTTONS["shift_break_end"],
                        callback_data="m:sh:brk:ok",
                    )
                ]
            )
            rows.append(
                [
                    InlineKeyboardButton(
                        text=MAIN_MENU_BUTTONS["shift_off"],
                        callback_data="m:sh:off",
                    )
                ]
            )
        rows.append(
            [
                InlineKeyboardButton(
                    text=MAIN_MENU_BUTTONS["new_orders"],
                    callback_data="m:new",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=MAIN_MENU_BUTTONS["active_order"],
                    callback_data="m:act",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=MAIN_MENU_BUTTONS["finance"],
                    callback_data="m:fin",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=MAIN_MENU_BUTTONS["referral"],
                    callback_data="m:rf",
                )
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=MAIN_MENU_BUTTONS["knowledge"],
                    callback_data="m:kb",
                )
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=MAIN_MENU_BUTTONS["start_onboarding"],
                    callback_data="m:onboarding:start",
                )
            ]
        )
    return inline_keyboard(rows)


def _method_title(method: m.PayoutMethod) -> str:
    mapping = {
        m.PayoutMethod.CARD: "Банковская карта",
        m.PayoutMethod.SBP: "СБП",
        m.PayoutMethod.YOOMONEY: "ЮMoney",
        m.PayoutMethod.BANK_ACCOUNT: "Банковский счёт",
    }
    return mapping.get(method, method.value.title())
