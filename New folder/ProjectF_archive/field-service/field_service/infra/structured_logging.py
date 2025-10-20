"""
Structured logging system for distribution and candidate selection.

Provides JSON-formatted logging with context, timestamps, and structured data.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, asdict, field

__all__ = [
    "DistributionEvent",
    "DistributionLogger",
    "CandidateRejectionLogger",
    "log_distribution_event",
    "log_candidate_rejection",
]

logger = logging.getLogger("distribution.structured")


class DistributionEvent(str, Enum):
    """Types of distribution events."""
    TICK_START = "tick_start"
    TICK_END = "tick_end"
    ORDER_FETCHED = "order_fetched"
    OFFER_EXPIRED = "offer_expired"
    ROUND_START = "round_start"
    CANDIDATES_FOUND = "candidates_found"
    NO_CANDIDATES = "no_candidates"
    OFFER_SENT = "offer_sent"
    ESCALATION_LOGIST = "escalation_logist"
    ESCALATION_ADMIN = "escalation_admin"
    NOTIFICATION_SENT = "notification_sent"
    DEFERRED_WAKE = "deferred_wake"
    ESCALATION_RESET = "escalation_reset"
    ERROR = "error"
    

@dataclass
class DistributionLogEntry:
    """Structured log entry for distribution events."""
    timestamp: str
    event: str
    order_id: Optional[int] = None
    master_id: Optional[int] = None
    city_id: Optional[int] = None
    district_id: Optional[int] = None
    round_number: Optional[int] = None
    total_rounds: Optional[int] = None
    candidates_count: Optional[int] = None
    sla_seconds: Optional[int] = None
    category: Optional[str] = None
    order_type: Optional[str] = None
    preferred_master_id: Optional[int] = None
    escalated_to: Optional[str] = None
    notification_type: Optional[str] = None
    expires_at: Optional[str] = None
    reason: Optional[str] = None
    search_scope: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    

    def to_json(self) -> str:
        """Convert to JSON string."""
        data = {k: v for k, v in asdict(self).items() if v is not None}
        return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


@dataclass
class CandidateRejectionEntry:
    """Structured log entry for candidate rejection."""
    timestamp: str
    order_id: int
    master_id: int
    mode: str
    rejection_reasons: list[str]
    master_details: dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        data = asdict(self)
        return json.dumps(data, ensure_ascii=False, separators=(',', ':'))


class DistributionLogger:
    """Logger for distribution events with structured JSON output."""
    
    def __init__(self, logger_name: str = "distribution.structured"):
        self.logger = logging.getLogger(logger_name)
    
    def log_event(
        self,
        event: DistributionEvent,
        *,
        order_id: Optional[int] = None,
        master_id: Optional[int] = None,
        city_id: Optional[int] = None,
        district_id: Optional[int] = None,
        round_number: Optional[int] = None,
        total_rounds: Optional[int] = None,
        candidates_count: Optional[int] = None,
        sla_seconds: Optional[int] = None,
        category: Optional[str] = None,
        order_type: Optional[str] = None,
        preferred_master_id: Optional[int] = None,
        escalated_to: Optional[str] = None,
        notification_type: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        reason: Optional[str] = None,
        search_scope: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        level: str = "INFO",
    ) -> None:
        """Log a distribution event with structured data."""
        entry = DistributionLogEntry(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            event=event.value,
            order_id=order_id,
            master_id=master_id,
            city_id=city_id,
            district_id=district_id,
            round_number=round_number,
            total_rounds=total_rounds,
            candidates_count=candidates_count,
            sla_seconds=sla_seconds,
            category=category,
            order_type=order_type,
            preferred_master_id=preferred_master_id,
            escalated_to=escalated_to,
            notification_type=notification_type,
            expires_at=expires_at.isoformat().replace("+00:00", "Z") if expires_at else None,
            reason=reason,
            search_scope=search_scope,
            details=details or {},
        )
        
        json_msg = entry.to_json()
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(json_msg)


class CandidateRejectionLogger:
    """Logger for candidate rejections with detailed reasons."""
    
    def __init__(self, logger_name: str = "distribution.candidates"):
        self.logger = logging.getLogger(logger_name)
    
    def log_rejection(
        self,
        order_id: int,
        master_id: int,
        mode: str,
        rejection_reasons: list[str],
        master_details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log candidate rejection with detailed reasons."""
        entry = CandidateRejectionEntry(
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            order_id=order_id,
            master_id=master_id,
            mode=mode,
            rejection_reasons=rejection_reasons,
            master_details=master_details or {},
        )
        
        json_msg = entry.to_json()
        self.logger.info(json_msg)


# Global instances
_dist_logger = DistributionLogger()
_rejection_logger = CandidateRejectionLogger()


def log_distribution_event(
    event: DistributionEvent,
    **kwargs: Any,
) -> None:
    """
    Log distribution event using global logger.
    
    Convenience function for logging distribution events.
    All kwargs are passed to DistributionLogger.log_event().
    """
    _dist_logger.log_event(event, **kwargs)


def log_candidate_rejection(
    order_id: int,
    master_id: int,
    mode: str,
    rejection_reasons: list[str],
    master_details: Optional[dict[str, Any]] = None,
) -> None:
    """
    Log candidate rejection using global logger.
    
    Convenience function for logging candidate rejections.
    """
    _rejection_logger.log_rejection(
        order_id=order_id,
        master_id=master_id,
        mode=mode,
        rejection_reasons=rejection_reasons,
        master_details=master_details,
    )
