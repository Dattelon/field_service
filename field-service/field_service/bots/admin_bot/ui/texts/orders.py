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
        OrderCategory.ELECTRICS: "",
        OrderCategory.PLUMBING: "",
        OrderCategory.APPLIANCES: " ",
        OrderCategory.DOORS: "/",
        OrderCategory.FURNITURE: "",
        OrderCategory.WINDOWS: "",
        OrderCategory.RENOVATION: "/",
        OrderCategory.OTHER: "",
    }
    return category_labels.get(category, str(category.value) if hasattr(category, 'value') else str(category))


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
        f" : {order.master_name}" + (f" ({order.master_phone})" if order.master_phone else "")
    ) if order.master_name else " : "
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
    
    # P1-02:      
    if order.en_route_at_local and order.working_at_local:
        lines.append(f"  : {order.en_route_at_local}")
    if order.working_at_local and order.payment_at_local:
        lines.append(f" : {order.working_at_local}  {order.payment_at_local}")
    
    # P1-02:  
    if order.declined_masters:
        declined_count = len(order.declined_masters)
        lines.append(f"\n <b> ({declined_count}):</b>")
        for dm in order.declined_masters[:5]:  #   5
            lines.append(f"   {dm.master_name} (.{dm.round_number})  {dm.declined_at_local}")
        if declined_count > 5:
            lines.append(f"  ...   {declined_count - 5}")
    
    # P1-20:     
    if order.status_history:
        lines.append(f"\n <b> :</b>")
        #   5 
        for item in order.status_history[-5:]:
            from_status_text = item.from_status or ""
            change_text = f"{from_status_text}  {item.to_status}"
            
            #  
            actor_icon = {
                "SYSTEM": "",
                "ADMIN": "",
                "MASTER": "",
                "AUTO_DISTRIBUTION": ""
            }.get(item.actor_type, "")
            
            #    
            actor_name = item.actor_name or ""
            if actor_name:
                lines.append(f"  {actor_icon} {change_text}  {item.changed_at_local}")
                lines.append(f"    <i>: {actor_name}</i>")
            else:
                lines.append(f"  {actor_icon} {change_text}  {item.changed_at_local}")
            
            # 
            if item.reason:
                lines.append(f"    <i>: {item.reason}</i>")
            
            #    context (   )
            if item.context:
                ctx = item.context
                if "candidates_count" in ctx and "round_number" in ctx:
                    lines.append(f"    <i> {ctx['round_number']}, : {ctx['candidates_count']}</i>")
                elif "method" in ctx:
                    method_text = {
                        "auto_distribution": "",
                        "manual_assign": " ",
                        "admin_override": " "
                    }.get(ctx["method"], ctx["method"])
                    lines.append(f"    <i>: {method_text}</i>")
    
    # P1-23: Add breadcrumbs navigation
    text = "\n".join(lines)
    breadcrumb_path = AdminPaths.order_card(order.id)
    return add_breadcrumbs_to_text(text, breadcrumb_path)



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


