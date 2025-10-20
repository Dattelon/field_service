"""Admin bot text formatting."""
from __future__ import annotations

from typing import Mapping

from field_service.db import OrderCategory
from field_service.bots.common.breadcrumbs import AdminPaths, add_breadcrumbs_to_text

from ...core.dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    OrderListItem,
    OrderCard,
)


def _category_value(category: OrderCategory) -> str:
    """Convert OrderCategory enum to human-readable text."""
    category_labels = {
        OrderCategory.ELECTRICS: "Электрика",
        OrderCategory.PLUMBING: "Сантехника",
        OrderCategory.APPLIANCES: "Бытовая техника",
        OrderCategory.DOORS: "Двери/замки",
        OrderCategory.FURNITURE: "Мебель",
        OrderCategory.WINDOWS: "Окна",
        OrderCategory.RENOVATION: "Ремонт/отделка",
        OrderCategory.OTHER: "Прочее",
    }
    return category_labels.get(category, str(category.value) if hasattr(category, 'value') else str(category))


def order_teaser(order: OrderListItem) -> str:
    district = order.district_name or ""
    slot = f"🕐 Слот: {order.timeslot_local}" if order.timeslot_local else ""
    category = _category_value(order.category)
    return (
        f"#{order.id} 📍 {order.city_name}/{district} 🔧 {category}{slot} 📊 {order.status}"
    )



def order_card(order: OrderCard) -> str:
    district = order.district_name or ""
    slot = order.timeslot_local or ""
    master_line = (
        f"👨‍🔧 Мастер: {order.master_name}" + (f" ({order.master_phone})" if order.master_phone else "")
    ) if order.master_name else "👨‍🔧 Мастер: Не назначен"
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
        f"📦 <b>Заявка #{order.id}</b>",
        f"📍 {address}",
        f"🔧 Категория: {_category_value(order.category)}",
        f"📋 Тип: {order.order_type.value}",
        f"🕐 Слот: {slot}",
        f"📊 Статус: {order.status}",
        f"📅 Создана: {order.created_at_local}",
        f"👤 Клиент: {customer}",
        master_line,
    ]
    
    if order.description:
        lines.append("📝 Описание: " + order.description)
    
    # P1-02: Добавляем временные метки работы
    if order.en_route_at_local and order.working_at_local:
        lines.append(f"🚗 В пути: {order.en_route_at_local}")
    if order.working_at_local and order.payment_at_local:
        lines.append(f"🛠 Работа: {order.working_at_local} → {order.payment_at_local}")
    
    # P1-02: Добавляем отказы
    if order.declined_masters:
        declined_count = len(order.declined_masters)
        lines.append(f"\n❌ <b>Отказались ({declined_count}):</b>")
        for dm in order.declined_masters[:5]:  # Показываем максимум 5
            lines.append(f"  • {dm.master_name} (Р.{dm.round_number}) → {dm.declined_at_local}")
        if declined_count > 5:
            lines.append(f"  ...и ещё {declined_count - 5}")
    
    # P1-20: Добавляем историю статусов
    if order.status_history:
        lines.append(f"\n📜 <b>История статусов:</b>")
        # Показываем последние 5
        for item in order.status_history[-5:]:
            from_status_text = item.from_status or ""
            change_text = f"{from_status_text} → {item.to_status}"
            
            # Иконки для типов актора
            actor_icon = {
                "SYSTEM": "⚙️",
                "ADMIN": "👨‍💼",
                "MASTER": "👨‍🔧",
                "AUTO_DISTRIBUTION": "🤖"
            }.get(item.actor_type, "❓")
            
            # Формируем запись об изменении
            actor_name = item.actor_name or ""
            if actor_name:
                lines.append(f"  {actor_icon} {change_text} → {item.changed_at_local}")
                lines.append(f"    <i>Кто: {actor_name}</i>")
            else:
                lines.append(f"  {actor_icon} {change_text} → {item.changed_at_local}")
            
            # Причина изменения
            if item.reason:
                lines.append(f"    <i>Причина: {item.reason}</i>")
            
            # Дополнительный context (если есть)
            if item.context:
                ctx = item.context
                if "candidates_count" in ctx and "round_number" in ctx:
                    lines.append(f"    <i>Раунд {ctx['round_number']}, кандидатов: {ctx['candidates_count']}</i>")
                elif "method" in ctx:
                    method_text = {
                        "auto_distribution": "Автораспределение",
                        "manual_assign": "Ручное назначение",
                        "admin_override": "Админ вмешался"
                    }.get(ctx["method"], ctx["method"])
                    lines.append(f"    <i>Метод: {method_text}</i>")
    
    # P1-23: Add breadcrumbs navigation
    text = "\n".join(lines)
    breadcrumb_path = AdminPaths.order_card(order.id)
    return add_breadcrumbs_to_text(text, breadcrumb_path)



def master_brief_line(master: MasterBrief) -> str:
    available = master.is_on_shift and not master.on_break
    status_icon = "✅" if available else "❌"
    car_icon = "🚗" if master.has_car else "🚶"
    parts = [
        f"{status_icon} #{master.id} {master.full_name}",
        f"⭐{master.rating_avg:.1f}",
        f"💰{master.avg_week_check:.0f}₽",
    ]
    if master.max_active_orders > 0:
        parts.append(f"📊 {master.active_orders}/{master.max_active_orders}")
    parts.append(car_icon)
    text_block = "  ".join(parts)
    flags = []
    if not master.is_on_shift:
        flags.append('🚫 Не на смене')
    elif master.on_break:
        flags.append('☕ На перерыве')
    if not master.in_district:
        flags.append('📍 Не в районе')
    if master.max_active_orders > 0 and master.active_orders >= master.max_active_orders:
        flags.append('⚠️ Перегружен')
    if not master.is_active or not master.verified:
        flags.append('❌ Заблокирован')
    if flags:
        flags_text = '; '.join(flags)
        text_block = f"{text_block}  ⚠️ {flags_text}"
    return text_block

def new_order_summary(data: Mapping[str, object]) -> str:
    lines = ["📋 <b>Новая заявка</b>"]
    lines.append(f"🏙 Город: {data.get('city_name', '')}")
    lines.append(f"🗺 Район: {data.get('district_name', '')}")
    lines.append(f"🛣 Улица: {data.get('street_name', '')}")
    lines.append(f"🏠 Дом: {data.get('house', '')}")
    if data.get('apartment'):
        lines.append(f"🚪 Кв.: {data['apartment']}")
    if data.get('address_comment'):
        lines.append(f"💬 Комментарий адреса: {data['address_comment']}")
    lines.append(
        "👤 Клиент: "
        + str(data.get('client_name', ''))
        + (f" ({data['client_phone']})" if data.get('client_phone') else "")
    )
    category_obj = data.get('category')
    if isinstance(category_obj, OrderCategory):
        category_fallback = category_obj.value
    else:
        category_fallback = str(category_obj or '')
    lines.append(
        f"🔧 Категория: {data.get('category_label', category_fallback)}"
    )
    lines.append(f"📋 Тип: {data.get('order_type', 'NORMAL')}")
    lines.append(f"🕐 Слот: {data.get('timeslot_display', '')}")
    if data.get('description'):
        lines.append("📝 Описание: " + str(data['description']))
    if data.get('attachments_count'):
        lines.append(f"📎 Вложений: {data['attachments_count']}")
    
    # P1-23: Add breadcrumbs navigation
    text = "\n".join(lines)
    breadcrumb_path = AdminPaths.ORDERS_CREATE
    return add_breadcrumbs_to_text(text, breadcrumb_path)


__all__ = [
    "commission_detail",
    "finance_list_line",
    "master_brief_line",
    "new_order_summary",
    "order_card",
    "order_teaser",
]
