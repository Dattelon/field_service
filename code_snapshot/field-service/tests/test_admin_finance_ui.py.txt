from decimal import Decimal

from field_service.bots.admin_bot.dto import CommissionAttachment, CommissionDetail
from field_service.bots.admin_bot.keyboards import finance_card_actions


def _build_detail(status: str) -> CommissionDetail:
    return CommissionDetail(
        id=1,
        order_id=101,
        master_id=55,
        master_name=" ",
        master_phone="+79991234567",
        status=status,
        amount=Decimal("1500.00"),
        rate=Decimal("0.50"),
        deadline_at_local="2025-09-10 18:00",
        created_at_local="2025-09-10 15:00",
        paid_reported_at_local=None,
        paid_approved_at_local=None,
        paid_amount=None,
        has_checks=True,
        snapshot_methods=("card",),
        snapshot_data={
            "card_last4": "9876",
            "card_holder": " ..",
            "card_bank": "-",
            "sbp_phone": None,
            "sbp_bank": None,
            "other_text": None,
            "comment": None,
            "qr_file_id": None,
        },
        attachments=(
            CommissionAttachment(
                id=10,
                file_type="PHOTO",
                file_id="file-id",
                file_name=None,
                caption=None,
            ),
        ),
    )


def test_finance_card_actions_contains_expected_buttons() -> None:
    detail = _build_detail("WAIT_PAY")
    markup = finance_card_actions(detail, "aw", 2)
    values = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert f"adm:f:cm:open:{detail.id}" in values
    assert f"adm:f:cm:ok:{detail.id}" in values
    assert f"adm:f:cm:rej:{detail.id}" in values
    assert f"adm:f:cm:blk:{detail.id}" in values
    assert f"adm:f:aw:2" in values


def test_finance_card_actions_hides_reject_when_overdue() -> None:
    detail = _build_detail("OVERDUE")
    markup = finance_card_actions(detail, "ov", 1)
    values = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert f"adm:f:cm:ok:{detail.id}" in values
    assert f"adm:f:cm:rej:{detail.id}" not in values
