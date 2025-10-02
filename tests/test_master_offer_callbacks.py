import pytest

from field_service.bots.master_bot.handlers import orders


def test_parse_offer_callback_payload_basic() -> None:
    assert orders._parse_offer_callback_payload("m:new:card:42", "card") == (42, 1)


def test_parse_offer_callback_payload_with_page() -> None:
    assert orders._parse_offer_callback_payload("m:new:acc:10:3", "acc") == (10, 3)


def test_parse_offer_callback_payload_invalid_page_defaults_to_one() -> None:
    assert orders._parse_offer_callback_payload("m:new:dec:77:0", "dec") == (77, 1)
    assert orders._parse_offer_callback_payload("m:new:dec:77:notanint", "dec") == (77, 1)


def test_parse_offer_callback_payload_rejects_wrong_action() -> None:
    with pytest.raises(ValueError):
        orders._parse_offer_callback_payload("m:new:card:5:2", "acc")


def test_parse_offer_callback_payload_rejects_bad_prefix() -> None:
    with pytest.raises(ValueError):
        orders._parse_offer_callback_payload("m:other:card:5", "card")


def test_parse_offer_callback_payload_rejects_non_numeric_order() -> None:
    with pytest.raises(ValueError):
        orders._parse_offer_callback_payload("m:new:card:abc", "card")
