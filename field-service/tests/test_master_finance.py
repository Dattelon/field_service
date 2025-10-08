from field_service.bots.master_bot.finance import format_pay_snapshot


def test_format_pay_snapshot_empty_returns_blank() -> None:
    assert format_pay_snapshot(None) == ""
    assert format_pay_snapshot({}) == ""


def test_format_pay_snapshot_renders_fields() -> None:
    snapshot = {
        "methods": ["card", "sbp"],
        "card_number_last4": "4321",
        "card_holder": "Ivanov I.I.",
        "card_bank": "T Bank",
        "sbp_phone_masked": "+7*** *** ** 21",
        "comment": "Commission #12",
    }
    text = format_pay_snapshot(snapshot)
    assert "****4321" in text
    assert "Ivanov" in text
    assert "Commission #12" in text
