"""
Tests for structured logging system.

Validates JSON logging for distribution events and candidate rejections.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import pytest

from field_service.infra.structured_logging import (
    DistributionEvent,
    DistributionLogger,
    CandidateRejectionLogger,
    log_distribution_event,
    log_candidate_rejection,
)


class LogCapture:
    """Capture log messages for testing."""
    
    def __init__(self):
        self.messages: list[tuple[str, str]] = []  # (level, message)
    
    def __call__(self, record: logging.LogRecord):
        self.messages.append((record.levelname, record.getMessage()))


@pytest.fixture
def log_capture():
    """Fixture to capture log messages."""
    capture = LogCapture()
    
    # Setup handler for distribution logger
    dist_logger = logging.getLogger("distribution.structured")
    dist_logger.setLevel(logging.DEBUG)
    handler = logging.Handler()
    handler.emit = capture
    dist_logger.addHandler(handler)
    
    # Setup handler for candidates logger
    cand_logger = logging.getLogger("distribution.candidates")
    cand_logger.setLevel(logging.DEBUG)
    cand_handler = logging.Handler()
    cand_handler.emit = capture
    cand_logger.addHandler(cand_handler)
    
    yield capture
    
    # Cleanup
    dist_logger.removeHandler(handler)
    cand_logger.removeHandler(cand_handler)


def test_distribution_logger_basic(log_capture):
    """Test basic distribution event logging."""
    logger = DistributionLogger()
    
    logger.log_event(
        DistributionEvent.TICK_START,
        details={"tick_seconds": 15, "rounds": 2},
    )
    
    assert len(log_capture.messages) == 1
    level, message = log_capture.messages[0]
    assert level == "INFO"
    
    # Parse JSON
    data = json.loads(message)
    assert data["event"] == "tick_start"
    assert "timestamp" in data
    assert data["details"]["tick_seconds"] == 15
    assert data["details"]["rounds"] == 2


def test_distribution_logger_with_order_info(log_capture):
    """Test distribution event logging with order information."""
    logger = DistributionLogger()
    
    logger.log_event(
        DistributionEvent.ROUND_START,
        order_id=123,
        city_id=1,
        district_id=5,
        round_number=1,
        total_rounds=2,
        category="ELECTRICS",
        order_type="NORMAL",
    )
    
    assert len(log_capture.messages) == 1
    level, message = log_capture.messages[0]
    
    data = json.loads(message)
    assert data["event"] == "round_start"
    assert data["order_id"] == 123
    assert data["city_id"] == 1
    assert data["district_id"] == 5
    assert data["round_number"] == 1
    assert data["total_rounds"] == 2
    assert data["category"] == "ELECTRICS"
    assert data["order_type"] == "NORMAL"


def test_distribution_logger_escalation(log_capture):
    """Test escalation event logging."""
    logger = DistributionLogger()
    
    logger.log_event(
        DistributionEvent.ESCALATION_LOGIST,
        order_id=456,
        city_id=2,
        escalated_to="logist",
        reason="no_candidates",
        level="WARNING",
    )
    
    assert len(log_capture.messages) == 1
    level, message = log_capture.messages[0]
    assert level == "WARNING"
    
    data = json.loads(message)
    assert data["event"] == "escalation_logist"
    assert data["order_id"] == 456
    assert data["escalated_to"] == "logist"
    assert data["reason"] == "no_candidates"


def test_candidate_rejection_logger(log_capture):
    """Test candidate rejection logging."""
    logger = CandidateRejectionLogger()
    
    logger.log_rejection(
        order_id=789,
        master_id=101,
        mode="auto",
        rejection_reasons=["shift", "break", "limit"],
        master_details={
            "full_name": "Test Master",
            "city_id": 1,
            "has_vehicle": True,
            "rating": 4.5,
        },
    )
    
    assert len(log_capture.messages) == 1
    level, message = log_capture.messages[0]
    assert level == "INFO"
    
    data = json.loads(message)
    assert data["order_id"] == 789
    assert data["master_id"] == 101
    assert data["mode"] == "auto"
    assert data["rejection_reasons"] == ["shift", "break", "limit"]
    assert data["master_details"]["full_name"] == "Test Master"
    assert data["master_details"]["has_vehicle"] is True
    assert data["master_details"]["rating"] == 4.5


def test_global_log_distribution_event(log_capture):
    """Test global convenience function for distribution logging."""
    log_distribution_event(
        DistributionEvent.OFFER_SENT,
        order_id=999,
        master_id=202,
        round_number=1,
        sla_seconds=120,
    )
    
    assert len(log_capture.messages) == 1
    level, message = log_capture.messages[0]
    
    data = json.loads(message)
    assert data["event"] == "offer_sent"
    assert data["order_id"] == 999
    assert data["master_id"] == 202
    assert data["sla_seconds"] == 120


def test_global_log_candidate_rejection(log_capture):
    """Test global convenience function for candidate rejection logging."""
    log_candidate_rejection(
        order_id=888,
        master_id=303,
        mode="manual",
        rejection_reasons=["verified", "skill"],
        master_details={"rating": 3.2},
    )
    
    assert len(log_capture.messages) == 1
    level, message = log_capture.messages[0]
    
    data = json.loads(message)
    assert data["order_id"] == 888
    assert data["master_id"] == 303
    assert data["mode"] == "manual"
    assert data["rejection_reasons"] == ["verified", "skill"]
    assert data["master_details"]["rating"] == 3.2


def test_json_format_no_none_values(log_capture):
    """Test that None values are excluded from JSON output."""
    log_distribution_event(
        DistributionEvent.ORDER_FETCHED,
        order_id=None,  # Should be excluded
        details={"count": 5},
    )
    
    assert len(log_capture.messages) == 1
    level, message = log_capture.messages[0]
    
    data = json.loads(message)
    assert "order_id" not in data  # None values excluded
    assert data["event"] == "order_fetched"
    assert data["details"]["count"] == 5


def test_timestamp_format(log_capture):
    """Test that timestamps are in ISO format with Z suffix."""
    log_distribution_event(
        DistributionEvent.TICK_START,
        details={},
    )
    
    assert len(log_capture.messages) == 1
    level, message = log_capture.messages[0]
    
    data = json.loads(message)
    timestamp = data["timestamp"]
    
    # Verify ISO format with Z suffix
    assert timestamp.endswith("Z")
    assert "T" in timestamp
    
    # Verify parseable
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
