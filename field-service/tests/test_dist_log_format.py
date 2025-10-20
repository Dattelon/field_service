from types import SimpleNamespace

from field_service.services.distribution_worker import (
    fmt_rank_item,
    log_decision_offer,
    log_tick_header,
)


def test_log_tick_header_contains_required_keys() -> None:
    row = SimpleNamespace(
        id=123,
        city_id=1,
        district_id=None,
        category="ELECTRICS",
        status="SEARCHING",
    )
    header = log_tick_header(row, 1, 2, 120, 3)

    assert header.startswith("[dist] order=123 city=1")
    assert "district=-" in header
    assert "cat=ELECTRICS" in header
    assert "type=NORMAL" in header
    assert "round=1/2" in header
    assert "sla=120s" in header
    assert "candidates=3" in header


def test_fmt_rank_item_and_decision_format() -> None:
    item = fmt_rank_item(
        {
            "mid": 10,
            "car": True,
            "avg_week": 5,
            "rating": 4.2,
            "rnd": 0.33,
            "shift": False,
        }
    )
    # Minimal shape checks
    assert "mid=10" in item
    assert "shift=off" in item
    assert "car=1" in item
    assert "avg_week=5" in item
    assert "rating=4.2" in item
    assert "rnd(0.33)" in item

    # Decision string should contain mid and an ISO timestamp
    decision = log_decision_offer(10, __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    assert decision.startswith("decision=offer mid=10 until=")

