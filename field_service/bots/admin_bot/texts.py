from __future__ import annotations

from decimal import Decimal
import html
from typing import Mapping, Sequence

from .dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    OrderCard,
    OrderListItem,
)

COMMISSION_STATUS_LABELS = {
    'WAIT_PAY': 'Ожидает оплаты',
    'REPORTED': 'На проверке',
    'APPROVED': 'Оплачена',
    'OVERDUE': 'Просрочена',
}


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
    available = master.is_on_shift and not master.on_break
    status_icon = "✅" if available else "❌"
    car_icon = "🚗" if master.has_car else "🚶"
    parts = [
        f"{status_icon} #{master.id} {master.full_name}",
        f"⭐{master.rating_avg:.1f}",
        f"₽{master.avg_week_check:.0f}",
    ]
    if master.max_active_orders > 0:
        parts.append(f"актив {master.active_orders}/{master.max_active_orders}")
    parts.append(car_icon)
    text_block = " • ".join(parts)
    flags = []
    if not master.is_on_shift:
        flags.append('смена выкл')
    elif master.on_break:
        flags.append('перерыв')
    if not master.in_district:
        flags.append('другой район')
    if master.max_active_orders > 0 and master.active_orders >= master.max_active_orders:
        flags.append('лимит')
    if not master.is_active or not master.verified:
        flags.append('недоступен')
    if flags:
        flags_text = '; '.join(flags)
        text_block = f"{text_block} • {flags_text}"
    return text_block
def finance_list_line(item: CommissionListItem) -> str:
    master = item.master_name or "—"
    status_label = COMMISSION_STATUS_LABELS.get((item.status or '').upper(), item.status)
    parts = [
        f"#{item.id}",
        f"заказ #{item.order_id}",
        master,
        f"{item.amount:.2f} ₽",
        status_label,
    ]
    if item.deadline_at_local:
        parts.append(f"до {item.deadline_at_local}")
    return " · ".join(parts)


def commission_detail(detail: CommissionDetail) -> str:
    status_label = COMMISSION_STATUS_LABELS.get((detail.status or '').upper(), detail.status)
    master_name = html.escape(detail.master_name) if detail.master_name else '—'
    master_phone = html.escape(detail.master_phone) if detail.master_phone else ''
    master_line = f"Мастер: {master_name}" + (f" ({master_phone})" if master_phone else '')

    lines = [
        f"💳 <b>Комиссия #{detail.id}</b>",
        f"Заказ: #{detail.order_id}",
        master_line,
        f"Статус: {status_label}",
        f"Сумма: {detail.amount:.2f} ₽",
    ]

    rate = detail.rate or Decimal('0')
    rate_percent = rate * 100 if rate <= 1 else rate
    rate_str = f"{rate_percent:.2f}".rstrip('0').rstrip('.')
    if rate_percent > 0:
        lines.append(f"Ставка: {rate_str}%")

    if detail.deadline_at_local:
        lines.append(f"Дедлайн: {html.escape(detail.deadline_at_local)}")
    lines.append(f"Создана: {html.escape(detail.created_at_local)}")
    if detail.paid_reported_at_local:
        lines.append(f"Сообщена оплата: {html.escape(detail.paid_reported_at_local)}")
    if detail.paid_approved_at_local:
        lines.append(f"Подтверждена: {html.escape(detail.paid_approved_at_local)}")
    if detail.paid_amount is not None:
        lines.append(f"Оплачено фактически: {detail.paid_amount:.2f} ₽")

    if detail.snapshot_methods:
        methods = ', '.join(detail.snapshot_methods)
        lines.append(f"Способы оплаты: {html.escape(methods)}")

    card_last4 = detail.snapshot_data.get('card_last4')
    if card_last4:
        card_info = [f"••••{card_last4}"]
        card_holder = detail.snapshot_data.get('card_holder')
        if card_holder:
            card_info.append(html.escape(card_holder))
        card_bank = detail.snapshot_data.get('card_bank')
        if card_bank:
            card_info.append(html.escape(card_bank))
        lines.append(f"Карта: {' / '.join(card_info)}")

    sbp_phone = detail.snapshot_data.get('sbp_phone')
    if sbp_phone:
        sbp_line = f"СБП: {html.escape(sbp_phone)}"
        sbp_bank = detail.snapshot_data.get('sbp_bank')
        if sbp_bank:
            sbp_line += f" ({html.escape(sbp_bank)})"
        lines.append(sbp_line)

    if detail.snapshot_data.get('qr_file_id'):
        lines.append("QR: загружен в системе")

    other_text = detail.snapshot_data.get('other_text')
    if other_text:
        lines.append(html.escape(other_text))

    comment = detail.snapshot_data.get('comment')
    if comment:
        lines.append(f"Комментарий к платежу: {html.escape(comment)}")

    lines.append(f"Чеки: {'есть' if detail.has_checks else 'нет'}")
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
    lines.append(f"Слот: {data.get('timeslot_display', '—')}")
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
