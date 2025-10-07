from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Iterable, Mapping

from field_service.db import models as m

# Onboarding flow texts (missing constants used by handlers)
ONBOARDING_ALREADY_VERIFIED = "Вы уже верифицированы."
ONBOARDING_SENT = "Заявка отправлена на модерацию."
ONBOARDING_SUMMARY_HEADER = "Проверьте данные анкеты:"

MASTER_PDN_CONSENT = (
    "Согласие на обработку персональных данных.",
    "Я разрешаю Field Service обрабатывать мои ФИО, телефон и сведения о заказах для заключения договора и организации работы.",
    "Я ознакомлен с тем, что могу отозвать согласие, написав в поддержку сервиса.",
)

MASTER_PDN_DECLINED = (
    "Вы отказались от обработки персональных данных. Мы не сможем продолжить регистрацию.",
)

START_NOT_APPROVED = (
    "Добро пожаловать в Field Service! Ваша анкета отправлена на модерацию.",
    "Мы сообщим, как только проверим данные. Пока вы можете дополнить профиль и ознакомиться с требованиями.",
)

START_BLOCKED = (
    "Ваш аккаунт заблокирован.",
    "Если это ошибка, свяжитесь с поддержкой или администратором сервиса.",
)

START_APPROVED = (
    "Рады видеть вас на смене! Вы можете включить смену, брать заявки и управлять финансами.",
)

FSM_TIMEOUT_MESSAGE = "Сессия истекла. Нажмите /start"

MAIN_MENU_BUTTONS = {
    "shift_on": "🟢 Включить смену",
    "shift_break": "☕ Перерыв 2 часа",
    "shift_break_end": "🟢 Включить смену",
    "shift_off": "🔴 Выключить смену",
    "new_orders": "🆕 Новые заказы",
    "active_order": "📦 Активный заказ",
    "finance": "💳 Финансы",
    "referral": "🎁 Реферальная программа",
    "knowledge": "📚 База знаний",
    "start_onboarding": "Заполнить анкету",
}

ORDER_STATUS_TITLES: Mapping[m.OrderStatus, str] = {
    m.OrderStatus.ASSIGNED: "Назначено мастеру",
    m.OrderStatus.EN_ROUTE: "Мастер в пути",
    m.OrderStatus.WORKING: "Мастер работает",
    m.OrderStatus.PAYMENT: "Ожидает подтверждения оплаты",
    m.OrderStatus.CLOSED: "Заказ закрыт",
    m.OrderStatus.DEFERRED: "Заказ отложен",
    m.OrderStatus.GUARANTEE: "Гарантийный визит",
    m.OrderStatus.CANCELED: "Заказ отменён",
    m.OrderStatus.CREATED: "Создан",
    m.OrderStatus.SEARCHING: "Идёт поиск мастера",
}

SHIFT_MESSAGES = {
    "started": "Смена начата.",
    "finished": "Смена завершена.",
    "break_started": "Перерыв 2 часа начат.",
    "break_finished": "Вы вернулись на смену.",
    "inactive": "Смена не активна.",
    "not_break": "Сейчас не перерыв.",
    "blocked": "Смена недоступна: аккаунт заблокирован.",
    "pending": "Профиль на модерации. Дождитесь одобрения.",
}

OFFERS_EMPTY = "Нет новых предложений"
OFFERS_REFRESH_BUTTON = "🔄 Обновить"
OFFERS_HEADER_TEMPLATE = "<b>🆕 Новые заказы</b>\nСтраница {page}/{pages} • всего: {total}"


def _escape(value: str | None) -> str:
    return html.escape(value or "—")


def offer_line(order_id: int, city: str, district: str | None, category: str, timeslot: str | None) -> str:
    district_part = f", {_escape(district)}" if district else ""
    slot = _escape(timeslot or "сегодня/ASAP")
    return f"#{order_id} • {_escape(city)}{district_part} • {_escape(category)} • {slot}"


def offer_card(
    *,
    order_id: int,
    city: str,
    district: str | None,
    street: str | None,
    house: str | None,
    timeslot: str | None,
    category: str,
    description: str | None,
) -> str:
    address_parts: list[str] = [
        _escape(city),
    ]
    if district:
        address_parts.append(_escape(district))
    if street:
        address_parts.append(_escape(street))
    if house:
        address_parts.append(_escape(str(house)))
    address = ", ".join(address_parts)
    description_text = _escape(description.strip() if description else "—")
    slot = _escape(timeslot or "—")
    lines = [
        f"<b>Заявка #{order_id}</b>",
        f"📍 Адрес: {address}",
        f"🗓 Слот: {slot}",
        f"🛠 Категория: {_escape(category)}",
        f"💬 Описание: {description_text}",
    ]
    return "\n".join(lines)


@dataclass(slots=True)
class ActiveOrderCard:
    order_id: int
    city: str
    district: str | None
    street: str | None
    house: str | None
    timeslot: str | None
    status: m.OrderStatus
    category: str | None = None

    def lines(self) -> list[str]:
        address_parts: list[str] = [_escape(self.city)]
        if self.district:
            address_parts.append(_escape(self.district))
        if self.street:
            address_parts.append(_escape(self.street))
        if self.house:
            address_parts.append(_escape(str(self.house)))
        address = ", ".join(address_parts)
        status_title = _escape(ORDER_STATUS_TITLES.get(self.status, self.status.value))
        slot = _escape(self.timeslot or "—")
        lines = [
            f"<b>📦 Активный заказ #{self.order_id}</b>",
            f"📍 Адрес: {address}",
            f"🗓 Слот: {slot}",
            f"🔁 Текущий статус: {status_title}",
        ]
        if self.category:
            lines.insert(3, f"🛠 Категория: {_escape(self.category)}")
        return lines


ACTIVE_STATUS_ACTIONS: Mapping[m.OrderStatus, tuple[str, str]] = {
    m.OrderStatus.ASSIGNED: ("🚗 В пути", "m:act:enr"),
    m.OrderStatus.EN_ROUTE: ("🛠 На месте", "m:act:wrk"),
    m.OrderStatus.WORKING: ("🧾 Закрыть", "m:act:cls"),
}

CLOSE_AMOUNT_PROMPT = "Введите сумму по заказу (например, 3500 или 4999.99)."
CLOSE_AMOUNT_ERROR = "Некорректная сумма. Введите целое число или число с двумя знаками после точки."
CLOSE_ACT_PROMPT = "Отправьте акт (фото или PDF одним файлом)."
CLOSE_SUCCESS_TEMPLATE = "Заказ #{order_id} закрыт. Спасибо за работу!"
CLOSE_PAYMENT_TEMPLATE = "Заказ #{order_id} отправлен на оплату. Сумма: {amount:.2f} ₽"
CLOSE_DOCUMENT_RECEIVED = "Документ получен. Проверим и сообщим о результате."
CLOSE_DOCUMENT_ERROR = "Нужен один файл: фото или PDF. Попробуйте ещё раз."

# Сообщение после успешного закрытия заказа
CLOSE_NEXT_STEPS = (
    "✅ <b>Заказ #{order_id} закрыт!</b>\n"
    "Сумма: {amount:.2f} ₽\n\n"
    "📋 <b>Что дальше:</b>\n"
    "1️⃣ Переведите комиссию администратору\n"
    "2️⃣ Дождитесь подтверждения оплаты\n"
    "3️⃣ После одобрения комиссия будет зачислена\n\n"
    "💳 Следить за статусом можно в разделе <b>Финансы</b>\n\n"
    "Спасибо за работу! 🎉"
)

CLOSE_GUARANTEE_SUCCESS = (
    "✅ <b>Гарантийный заказ #{order_id} закрыт!</b>\n\n"
    "Документ получен и отправлен на проверку.\n\n"
    "Спасибо за работу! 🎉"
)

OFFER_NOT_FOUND = "Заявка не найдена. Возможно, её уже приняли другим мастером."
NAV_BACK = "⬅️ Назад"
NAV_MENU = "🏠 Меню"
NO_ACTIVE_ORDERS = "Сейчас нет активных заказов."

# P0-4: Функция для генерации сообщения о блокировке с причиной
def alert_account_blocked(reason: str | None = None) -> str:
    """Генерирует сообщение о блокировке аккаунта с указанием причины."""
    base_text = "⛔️ Ваш аккаунт заблокирован."
    if reason:
        return f"{base_text}\n\n<b>Причина:</b> {html.escape(reason)}\n\nОбратитесь в поддержку для разблокировки."
    return f"{base_text}\n\nОбратитесь в поддержку для подробностей."

# Для обратной совместимости
ALERT_ACCOUNT_BLOCKED = alert_account_blocked()

ALERT_LIMIT_REACHED = "Достигнут лимит активных заказов. Завершите текущие, чтобы брать новые."
ALERT_ALREADY_TAKEN = "Упс, заказ уже забрали другим мастером"
ALERT_ACCEPT_SUCCESS = "Заявка принята. Удачи в работе!"
ALERT_DECLINE_SUCCESS = "Предложение скрыто."
ALERT_EN_ROUTE_FAIL = "Не удалось перевести заказ в статус «В пути». Обновите карточку и попробуйте снова."
ALERT_EN_ROUTE_SUCCESS = "Отметили, что вы в пути."
ALERT_WORKING_FAIL = "Не удалось отметить начало работы. Обновите карточку и попробуйте снова."
ALERT_WORKING_SUCCESS = "Отметили, что вы уже на месте."
ALERT_CLOSE_NOT_FOUND = "Заказ не найден. Начните закрытие заново."
ALERT_CLOSE_STATUS = "Статус заказа изменился. Попробуйте снова из активного заказа."
ALERT_CLOSE_NOT_ALLOWED = "Сейчас нельзя закрыть этот заказ. Проверьте статус."
ALERT_ORDER_NOT_FOUND = "Заказ не найден."

REFERRAL_EMPTY = "Пока нет начислений по реферальной программе."
FINANCE_EMPTY = "Комиссии не найдены."
