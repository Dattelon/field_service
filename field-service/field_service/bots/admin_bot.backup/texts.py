from __future__ import annotations

from decimal import Decimal
import html
from typing import Mapping, Sequence

from .dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    OrderCard,
    OrderCategory,
    OrderListItem,
)

FSM_TIMEOUT_MESSAGE = " .  /start"


COMMISSION_STATUS_LABELS = {
    'WAIT_PAY': ' ',
    'REPORTED': '',
    'APPROVED': '',
    'OVERDUE': '',
}


def _category_value(category: object) -> str:
    if isinstance(category, OrderCategory):
        return category.value
    if isinstance(category, str):
        return category
    return ""


def order_teaser(order: OrderListItem) -> str:
    district = order.district_name or ""
    slot = f"  {order.timeslot_local}" if order.timeslot_local else ""
    category = _category_value(order.category)
    return (
        f"#{order.id}  {order.city_name}/{district}  {category}{slot}  {order.status}"
    )


def order_card(order: OrderCard) -> str:
    district = order.district_name or ""
    slot = order.timeslot_local or ""
    master_line = (
        f" {order.master_name}" + (f" ({order.master_phone})" if order.master_phone else "")
    ) if order.master_name else " "
    customer = order.client_name or ""
    if order.client_phone:
        customer += f" ({order.client_phone})"
    address_parts = [order.city_name, district]
    if order.street_name:
        address_parts.append(order.street_name)
    if order.house:
        address_parts.append(str(order.house))
    address = ", ".join(p for p in address_parts if p)
    lines = [
        f" <b> #{order.id}</b>",
        f" {address}",
        f" : {_category_value(order.category)}",
        f" : {order.order_type.value}",
        f" : {slot}",
        f" : {order.status}",
        f" : {order.created_at_local}",
        f" : {customer}",
        master_line,
    ]
    if order.description:
        lines.append(" : " + order.description)
    return "\n".join(lines)


def master_brief_line(master: MasterBrief) -> str:
    available = master.is_on_shift and not master.on_break
    status_icon = "" if available else ""
    car_icon = "" if master.has_car else ""
    parts = [
        f"{status_icon} #{master.id} {master.full_name}",
        f"{master.rating_avg:.1f}",
        f"{master.avg_week_check:.0f}",
    ]
    if master.max_active_orders > 0:
        parts.append(f" {master.active_orders}/{master.max_active_orders}")
    parts.append(car_icon)
    text_block = "  ".join(parts)
    flags = []
    if not master.is_on_shift:
        flags.append(' ')
    elif master.on_break:
        flags.append('')
    if not master.in_district:
        flags.append(' ')
    if master.max_active_orders > 0 and master.active_orders >= master.max_active_orders:
        flags.append('')
    if not master.is_active or not master.verified:
        flags.append('')
    if flags:
        flags_text = '; '.join(flags)
        text_block = f"{text_block}  {flags_text}"
    return text_block
def finance_list_line(item: CommissionListItem) -> str:
    master = item.master_name or ""
    status_label = COMMISSION_STATUS_LABELS.get((item.status or '').upper(), item.status)
    parts = [
        f"#{item.id}",
        f" #{item.order_id}",
        master,
        f"{item.amount:.2f} ",
        status_label,
    ]
    if item.deadline_at_local:
        parts.append(f" {item.deadline_at_local}")
    return "  ".join(parts)


def commission_detail(detail: CommissionDetail) -> str:
    status_label = COMMISSION_STATUS_LABELS.get((detail.status or '').upper(), detail.status)
    master_name = html.escape(detail.master_name) if detail.master_name else ''
    master_phone = html.escape(detail.master_phone) if detail.master_phone else ''
    master_line = f" : {master_name}" + (f" ({master_phone})" if master_phone else '')

    lines = [
        f" <b> #{detail.id}</b>",
        f" : #{detail.order_id}",
        master_line,
        f" : {status_label}",
        f" : {detail.amount:.2f} ",
    ]

    rate = detail.rate or Decimal('0')
    rate_percent = rate * 100 if rate <= 1 else rate
    rate_str = f"{rate_percent:.2f}".rstrip('0').rstrip('.')
    if rate_percent > 0:
        lines.append(f" : {rate_str}%")

    if detail.deadline_at_local:
        lines.append(f" : {html.escape(detail.deadline_at_local)}")
    lines.append(f" : {html.escape(detail.created_at_local)}")
    if detail.paid_reported_at_local:
        lines.append(f"   : {html.escape(detail.paid_reported_at_local)}")
    if detail.paid_approved_at_local:
        lines.append(f" : {html.escape(detail.paid_approved_at_local)}")
    if detail.paid_amount is not None:
        lines.append(f" : {detail.paid_amount:.2f} ")

    if detail.snapshot_methods:
        methods = ', '.join(detail.snapshot_methods)
        lines.append(f"  : {html.escape(methods)}")

    card_last4 = detail.snapshot_data.get('card_last4')
    if card_last4:
        card_info = [f"****{card_last4}"]
        card_holder = detail.snapshot_data.get('card_holder')
        if card_holder:
            card_info.append(html.escape(card_holder))
        card_bank = detail.snapshot_data.get('card_bank')
        if card_bank:
            card_info.append(html.escape(card_bank))
        lines.append(f" : {' / '.join(card_info)}")

    sbp_phone = detail.snapshot_data.get('sbp_phone')
    if sbp_phone:
        sbp_line = f" : {html.escape(sbp_phone)}"
        sbp_bank = detail.snapshot_data.get('sbp_bank')
        if sbp_bank:
            sbp_line += f" ({html.escape(sbp_bank)})"
        lines.append(sbp_line)

    if detail.snapshot_data.get('qr_file_id'):
        lines.append("QR: ")

    other_text = detail.snapshot_data.get('other_text')
    if other_text:
        lines.append(html.escape(other_text))

    comment = detail.snapshot_data.get('comment')
    if comment:
        lines.append(f" : {html.escape(comment)}")

    lines.append(f" : {'' if detail.has_checks else ''}")
    return "\n".join(lines)


def new_order_summary(data: Mapping[str, object]) -> str:
    lines = [" <b> </b>"]
    lines.append(f": {data.get('city_name', '')}")
    lines.append(f": {data.get('district_name', '')}")
    lines.append(f": {data.get('street_name', '')}")
    lines.append(f": {data.get('house', '')}")
    if data.get('apartment'):
        lines.append(f".: {data['apartment']}")
    if data.get('address_comment'):
        lines.append(f"  : {data['address_comment']}")
    lines.append(
        ": "
        + str(data.get('client_name', ''))
        + (f" ({data['client_phone']})" if data.get('client_phone') else "")
    )
    category_obj = data.get('category')
    if isinstance(category_obj, OrderCategory):
        category_fallback = category_obj.value
    else:
        category_fallback = str(category_obj or '')
    lines.append(
        f": {data.get('category_label', category_fallback)}"
    )
    lines.append(f": {data.get('order_type', 'NORMAL')}")
    lines.append(f": {data.get('timeslot_display', '')}")
    if data.get('description'):
        lines.append(": " + str(data['description']))
    if data.get('attachments_count'):
        lines.append(f": {data['attachments_count']}")
    return "\n".join(lines)


__all__ = [
    "commission_detail",
    "finance_list_line",
    "master_brief_line",
    "new_order_summary",
    "order_card",
    "order_teaser",
]
