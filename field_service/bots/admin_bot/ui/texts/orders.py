"""Admin bot text formatting."""
from __future__ import annotations

from typing import Mapping

from ...core.dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    OrderListItem,
)


def order_teaser(order: OrderListItem) -> str:
    district = order.district_name or ""
    slot = f" ⏰ {order.timeslot_local}" if order.timeslot_local else ""
    category = _category_value(order.category)
    return (
        f"#{order.id} • {order.city_name}/{district} • {category}{slot} • {order.status}"
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
        f"🧾 <b>Заказ #{order.id}</b>",
        f"📍 {address}",
        f"🔧 Категория: {_category_value(order.category)}",
        f"📦 Тип: {order.order_type.value}",
        f"⏰ Слот: {slot}",
        f"📌 Статус: {order.status}",
        f"🗓 Создан: {order.created_at_local}",
        f"👤 Клиент: {customer}",
        master_line,
    ]
    if order.description:
        lines.append("📝 Описание: " + order.description)
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

def new_order_summary(data: Mapping[str, object]) -> str:
    lines = ["🆕 <b>Новый заказ</b>"]
    lines.append(f"Город: {data.get('city_name', '')}")
    lines.append(f"Район: {data.get('district_name', '')}")
    lines.append(f"Улица: {data.get('street_name', '')}")
    lines.append(f"Дом: {data.get('house', '')}")
    if data.get('apartment'):
        lines.append(f"Кв.: {data['apartment']}")
    if data.get('address_comment'):
        lines.append(f"Комментарий к адресу: {data['address_comment']}")
    lines.append(
        "Клиент: "
        + str(data.get('client_name', ''))
        + (f" ({data['client_phone']})" if data.get('client_phone') else "")
    )
    category_obj = data.get('category')
    if isinstance(category_obj, OrderCategory):
        category_fallback = category_obj.value
    else:
        category_fallback = str(category_obj or '')
    lines.append(
        f"Категория: {data.get('category_label', category_fallback)}"
    )
    lines.append(f"Тип: {data.get('order_type', 'NORMAL')}")
    lines.append(f"Слот: {data.get('timeslot_display', '')}")
    if data.get('description'):
        lines.append("Описание: " + str(data['description']))
    if data.get('attachments_count'):
        lines.append(f"Вложения: {data['attachments_count']}")
    return "\n".join(lines)


__all__ = [
    "commission_detail",
    "finance_list_line",
    "master_brief_line",
    "new_order_summary",
    "order_card",
    "order_teaser",
]


