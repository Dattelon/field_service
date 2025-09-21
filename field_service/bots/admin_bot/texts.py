from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

from .dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    OrderCard,
    OrderListItem,
)


def order_teaser(order: OrderListItem) -> str:
    district = order.district_name or "—"
    slot = f" • {order.timeslot_local}" if order.timeslot_local else ""
    category = order.category or "—"
    return (
        f"#{order.id} · {order.city_name}/{district} · {category}{slot} · {order.status}"
    )


def order_card(order: OrderCard) -> str:
    district = order.district_name or "—"
    slot = order.timeslot_local or "—"
    master_line = (
        f"👷 {order.master_name}" + (f" ({order.master_phone})" if order.master_phone else "")
    ) if order.master_name else "👷 —"
    customer = order.client_name or "—"
    if order.client_phone:
        customer += f" ({order.client_phone})"
    address_parts = [order.city_name, district]
    if order.street_name:
        address_parts.append(order.street_name)
    if order.house:
        address_parts.append(str(order.house))
    address = ", ".join(p for p in address_parts if p)
    lines = [
        f"📄 <b>Заявка #{order.id}</b>",
        f"📍 {address}",
        f"Категория: {order.category or '—'}",
        f"Тип: {order.order_type.value}",
        f"Слот: {slot}",
        f"Статус: {order.status}",
        f"Создана: {order.created_at_local}",
        f"Клиент: {customer}",
        master_line,
    ]
    if order.description:
        lines.append("Описание: " + order.description)
    return "\n".join(lines)


def master_brief_line(master: MasterBrief) -> str:
    car = "🚗" if master.has_car else "🚶"
    shift = "🟢" if master.is_on_shift else "🔴"
    base = f"#{master.id} {master.full_name} {car} {shift}"
    stats = f"avg₽={master.avg_week_check:.0f} · ⭐ {master.rating_avg:.1f}"
    flags = []
    if not master.is_active or not master.verified:
        flags.append("❗не допущен")
    if not master.in_district:
        flags.append("⚠ вне района")
    return f"{base} · {stats}" + (" · " + ", ".join(flags) if flags else "")


def finance_list_line(item: CommissionListItem) -> str:
    deadline = item.deadline_at_local or "—"
    master = item.master_name or "—"
    return (
        f"#{item.id} · заказ #{item.order_id} · {master} · {item.amount:.2f} ₽ · до {deadline}"
    )


def commission_detail(detail: CommissionDetail) -> str:
    lines = [
        f"💳 <b>Комиссия #{detail.id}</b>",
        f"Заказ: #{detail.order_id}",
        f"Мастер: {detail.master_name or '—'}" + (f" ({detail.master_phone})" if detail.master_phone else ""),
        f"Статус: {detail.status}",
        f"Сумма: {detail.amount:.2f} ₽", 
        f"Ставка: {detail.rate:.2f}"
    ]
    if detail.deadline_at_local:
        lines.append(f"Дедлайн: {detail.deadline_at_local}")
    lines.append(f"Создана: {detail.created_at_local}")
    if detail.paid_reported_at_local:
        lines.append(f"Сообщена оплата: {detail.paid_reported_at_local}")
    if detail.paid_approved_at_local:
        lines.append(f"Подтверждена: {detail.paid_approved_at_local}")
    if detail.paid_amount is not None:
        lines.append(f"Оплачено фактически: {detail.paid_amount:.2f} ₽")
    if detail.snapshot_methods:
        lines.append("Методы оплаты: " + ", ".join(detail.snapshot_methods))
    for key, value in detail.snapshot_data.items():
        if value:
            lines.append(f"{key}: {value}")
    lines.append(f"Чеки: {'да' if detail.has_checks else 'нет'}")
    return "\n".join(lines)


def new_order_summary(data: Mapping[str, object]) -> str:
    lines = ["📝 <b>Новая заявка</b>"]
    lines.append(f"Город: {data.get('city_name', '—')}")
    lines.append(f"Район: {data.get('district_name', '—')}")
    lines.append(f"Улица: {data.get('street_name', '—')}")
    lines.append(f"Дом: {data.get('house', '—')}")
    if data.get('apartment'):
        lines.append(f"Квартира: {data['apartment']}")
    if data.get('address_comment'):
        lines.append(f"Комментарий: {data['address_comment']}")
    lines.append(
        "Клиент: "
        + str(data.get('client_name', '—'))
        + (f" ({data['client_phone']})" if data.get('client_phone') else "")
    )
    lines.append(f"Категория: {data.get('category_label', data.get('category', '—'))}")
    lines.append(f"Тип заявки: {data.get('order_type', 'NORMAL')}")
    lines.append(f"Слот: {data.get('slot_label_display', '—')}")
    if data.get('description'):
        lines.append("Описание: " + str(data['description']))
    if data.get('attachments_count'):
        lines.append(f"Вложений: {data['attachments_count']}")
    return "\n".join(lines)


__all__ = [
    "commission_detail",
    "finance_list_line",
    "master_brief_line",
    "new_order_summary",
    "order_card",
    "order_teaser",
]
