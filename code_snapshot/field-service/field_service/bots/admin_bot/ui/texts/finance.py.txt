"""Admin bot text formatting."""
from __future__ import annotations

from typing import Mapping

from ...core.dto import (
    CommissionDetail,
    CommissionListItem,
    MasterBrief,
    OrderListItem,
)


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



