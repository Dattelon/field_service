from __future__ import annotations

from typing import Iterable, Optional, Sequence

PAYMENT_METHOD_LABELS: dict[str, str] = {
    "card": "Карта",
    "sbp": "СБП",
    "cash": "Наличные",
}


def _format_methods(methods: Iterable[object]) -> str:
    titles = [PAYMENT_METHOD_LABELS.get(str(item), str(item)) for item in methods if str(item)]
    return ", ".join(titles)


def format_pay_snapshot(snapshot: Optional[dict]) -> str:
    if not snapshot or not isinstance(snapshot, dict):
        return ""

    lines: list[str] = []

    methods: Sequence[object] | None = snapshot.get("methods")  # type: ignore[assignment]
    if methods:
        method_titles = _format_methods(methods)
        if method_titles:
            lines.append(f"Способ оплаты: {method_titles}")

    card_last4 = snapshot.get("card_number_last4")
    if card_last4:
        card_line = f"Карта ****{card_last4}"
        extra: list[str] = []
        card_holder = snapshot.get("card_holder")
        if card_holder:
            extra.append(str(card_holder))
        card_bank = snapshot.get("card_bank")
        if card_bank:
            extra.append(str(card_bank))
        if extra:
            card_line += " (" + ", ".join(extra) + ")"
        lines.append(card_line)

    sbp_phone = snapshot.get("sbp_phone_masked")
    if sbp_phone:
        sbp_line = f"СБП тел: {sbp_phone}"
        sbp_bank = snapshot.get("sbp_bank")
        if sbp_bank:
            sbp_line += f" ({sbp_bank})"
        lines.append(sbp_line)

    if snapshot.get("sbp_qr_file_id"):
        lines.append("QR-код прилагается.")

    other_text = snapshot.get("other_text")
    if other_text:
        lines.append(str(other_text))

    comment = snapshot.get("comment")
    if comment:
        lines.append(f"Комментарий для перевода: {comment}")

    return "\n".join(lines)
