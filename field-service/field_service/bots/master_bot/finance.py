from __future__ import annotations

from typing import Iterable, Optional, Sequence

from .utils import escape_html

PAYMENT_METHOD_LABELS: dict[str, str] = {
    "card": "💳 Карта",
    "sbp": "СБП",
    "cash": "Наличные",
}


def _format_methods(methods: Iterable[object]) -> str:
    titles: list[str] = []
    for item in methods:
        item_str = str(item)
        if not item_str:
            continue
        label = PAYMENT_METHOD_LABELS.get(item_str, item_str)
        titles.append(escape_html(label))
    return ", ".join(titles)


def format_pay_snapshot(snapshot: Optional[dict]) -> str:
    if not snapshot or not isinstance(snapshot, dict):
        return ""

    lines: list[str] = []

    methods: Sequence[object] | None = snapshot.get("methods")  # type: ignore[assignment]
    if methods:
        method_titles = _format_methods(methods)
        if method_titles:
            lines.append(f"Способы оплаты: {method_titles}")

    card_last4 = snapshot.get("card_number_last4")
    if card_last4:
        card_line = f"Карта ****{escape_html(str(card_last4))}"
        extra: list[str] = []
        card_holder = snapshot.get("card_holder")
        if card_holder:
            extra.append(escape_html(str(card_holder)))
        card_bank = snapshot.get("card_bank")
        if card_bank:
            extra.append(escape_html(str(card_bank)))
        if extra:
            card_line += " (" + ", ".join(extra) + ")"
        lines.append(card_line)

    sbp_phone = snapshot.get("sbp_phone_masked")
    if sbp_phone:
        sbp_line = f"Телефон для СБП: {escape_html(str(sbp_phone))}"
        sbp_bank = snapshot.get("sbp_bank")
        if sbp_bank:
            sbp_line += f" ({escape_html(str(sbp_bank))})"
        lines.append(sbp_line)

    if snapshot.get("sbp_qr_file_id"):
        lines.append("QR-код доступен ниже.")

    other_text = snapshot.get("other_text")
    if other_text:
        other_text_safe = escape_html(str(other_text))
        lines.extend(other_text_safe.splitlines() or [other_text_safe])

    comment = snapshot.get("comment")
    if comment:
        comment_safe = escape_html(str(comment))
        lines.append(f"Комментарий к оплате: {comment_safe}")

    return "\n".join(lines)
