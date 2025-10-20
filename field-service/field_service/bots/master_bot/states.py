from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class OnboardingStates(StatesGroup):
    pdn = State()
    last_name = State()
    first_name = State()
    middle_name = State()
    phone = State()
    referral_code = State()  # Ввод реферального кода (опционально)
    city = State()
    districts = State()
    vehicle = State()
    skills = State()
    passport = State()
    selfie = State()
    payout_method = State()
    payout_requisites = State()
    payout_sbp_bank = State()  # 🔧 Выбор банка для СБП
    confirm = State()
    home_geo = State()


class FinanceUploadStates(StatesGroup):
    check = State()


class CloseOrderStates(StatesGroup):
    amount = State()
    act = State()
