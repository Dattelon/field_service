# 📊 STRUCTURED LOGGING SYSTEM

## Overview

Structured logging system for Field Service distribution and candidate selection. Provides JSON-formatted logs with consistent structure, timestamps, and rich contextual data.

## Key Features

✅ **JSON Format**: All logs in machine-readable JSON format  
✅ **Timestamps**: ISO 8601 format with UTC timezone  
✅ **Event Types**: Enumerated distribution events  
✅ **Rich Context**: Order IDs, master IDs, cities, districts, rounds  
✅ **Detailed Rejections**: Comprehensive candidate rejection reasons  
✅ **Zero Overhead**: Only logs what's necessary

## Architecture

### Core Components

```
field_service/infra/structured_logging.py
├── DistributionEvent         # Event type enum
├── DistributionLogger         # Distribution events logger
├── CandidateRejectionLogger   # Candidate rejection logger
├── log_distribution_event()   # Global convenience function
└── log_candidate_rejection()  # Global convenience function
```

### Integration Points

**distribution_scheduler.py**:
- Tick start/end events
- Order fetching
- Round start
- Candidates found/not found
- Offer sent/expired
- Escalations (logist, admin)
- Deferred wake events

**candidates.py**:
- Master rejection with detailed reasons
```json
{
  "timestamp": "2025-10-06T12:00:01Z",
  "event": "round_start",
  "order_id": 123,
  "city_id": 1,
  "district_id": 5,
  "round_number": 1,
  "total_rounds": 2,
  "category": "ELECTRICS",
  "order_type": "NORMAL",
  "preferred_master_id": null
}
```

**Candidates Found**:
```json
{
  "timestamp": "2025-10-06T12:00:02Z",
  "event": "candidates_found",
  "order_id": 123,
  "city_id": 1,
  "district_id": 5,
  "round_number": 1,
  "candidates_count": 5,
  "master_id": 42,
  "details": {
    "top_master": {
      "mid": 42,
      "car": true,
      "avg_week": 3500.0,
      "rating": 4.8
    }
  }
}
```

**Offer Sent**:
```json
{
  "timestamp": "2025-10-06T12:00:03Z",
  "event": "offer_sent",
  "order_id": 123,
  "master_id": 42,
  "round_number": 1,
  "sla_seconds": 120,
  "expires_at": "2025-10-06T12:02:03Z"
}
```

**No Candidates (Escalation)**:
```json
{
  "timestamp": "2025-10-06T12:00:04Z",
  "event": "no_candidates",
  "order_id": 456,
  "city_id": 2,
  "district_id": null,
  "round_number": 2,
  "candidates_count": 0,
  "search_scope": "citywide",
  "reason": "escalate_to_logist"
}
```

**Escalation to Logist**:
```json
{
  "timestamp": "2025-10-06T12:00:05Z",
  "event": "escalation_logist",
  "order_id": 456,
  "city_id": 2,
  "district_id": null,
  "escalated_to": "logist",
  "reason": "no_candidates",
  "search_scope": "citywide",
  "notification_type": "escalation_logist_notified"
}
```

**Escalation to Admin**:
```json
{
  "timestamp": "2025-10-06T12:10:05Z",
  "event": "escalation_admin",
  "order_id": 456,
  "city_id": 2,
  "district_id": null,
  "escalated_to": "admin",
  "notification_type": "escalation_admin_notified"
}
```

## Candidate Rejection Logs

### Rejection Reasons

- `city`: Wrong city
- `district`: Not in required district
- `skill`: Missing required skill
- `verified`: Master not verified
- `active`: Master is inactive/blocked
- `shift`: Master not on shift
- `break`: Master on break
- `limit`: Active orders limit reached
- `offer`: Already has open offer for this order

### Example Log

```json
{
  "timestamp": "2025-10-06T12:00:02Z",
  "order_id": 123,
  "master_id": 101,
  "mode": "auto",
  "rejection_reasons": ["shift", "break"],
  "master_details": {
    "full_name": "Ivanov Ivan",
    "city_id": 1,
    "has_vehicle": true,
    "avg_week_check": 2500.0,
    "rating": 4.2,
    "is_on_shift": false,
    "on_break": true,
    "is_active": true,
    "verified": true,
    "in_district": true,
    "active_orders": 2,
    "max_active_orders": 5,
    "has_skill": true,
    "has_open_offer": false
  }
}
```

## Usage

### In Distribution Scheduler

```python
from field_service.infra.structured_logging import (
    DistributionEvent,
    log_distribution_event,
)

# Log tick start
log_distribution_event(
    DistributionEvent.TICK_START,
    details={"tick_seconds": 15, "rounds": 2}
)

# Log round start
log_distribution_event(
    DistributionEvent.ROUND_START,
    order_id=order.id,
    city_id=order.city_id,
    district_id=order.district_id,
    round_number=next_round,
    total_rounds=cfg.rounds,
    category=order.category,
)

# Log offer sent
log_distribution_event(
    DistributionEvent.OFFER_SENT,
    order_id=order.id,
    master_id=master_id,
    round_number=round_number,
    sla_seconds=120,
    expires_at=until,
)

# Log escalation with warning level
log_distribution_event(
    DistributionEvent.ESCALATION_LOGIST,
    order_id=order.id,
    city_id=order.city_id,
    escalated_to="logist",
    reason="no_candidates",
    level="WARNING",
)
```

### In Candidate Selection

```python
from field_service.infra.structured_logging import log_candidate_rejection

# Log rejection with detailed reasons
log_candidate_rejection(
    order_id=order_id,
    master_id=master_id,
    mode="auto",
    rejection_reasons=["shift", "break", "limit"],
    master_details={
        "full_name": master.full_name,
        "city_id": master.city_id,
        "has_vehicle": master.has_vehicle,
        "rating": master.rating,
        "active_orders": active_count,
        "max_active_orders": max_limit,
    },
)
```

## Log Analysis

### Parsing Logs

```python
import json

# Read structured log
with open("distribution.log") as f:
    for line in f:
        try:
            event = json.loads(line)
            if event["event"] == "escalation_logist":
                print(f"Order {event['order_id']} escalated: {event['reason']}")
        except json.JSONDecodeError:
            pass  # Skip non-JSON lines
```

### Common Analysis Queries

**Find all escalations in last hour**:
```bash
cat distribution.log | grep -E '"event":"escalation_' | \
  jq 'select(.timestamp > "2025-10-06T11:00:00Z")'
```

**Count rejections by reason**:
```bash
cat distribution.log | grep '"rejection_reasons"' | \
  jq -r '.rejection_reasons[]' | sort | uniq -c | sort -rn
```

**Average candidates per order**:
```bash
cat distribution.log | grep '"candidates_found"' | \
  jq '.candidates_count' | awk '{sum+=$1; count++} END {print sum/count}'
```

**Orders with no candidates**:
```bash
cat distribution.log | grep '"no_candidates"' | \
  jq '{order: .order_id, city: .city_id, district: .district_id, scope: .search_scope}'
```

**Escalation timeline for order**:
```bash
ORDER_ID=123
cat distribution.log | grep -E "\"order_id\":$ORDER_ID" | \
  jq '{time: .timestamp, event: .event, reason: .reason}'
```

## Performance

### Log Volume Estimates


- **Tick Start**: 1 log per tick (every 15s = 4/min)
- **Orders Fetched**: 1 log per tick
- **Round Start**: 1 log per order per round (2-20/min typical)
- **Candidates Found/None**: 1 log per order per round
- **Offer Sent**: 1 log per successful offer (5-15/min typical)
- **Candidate Rejection**: 10-50 logs per order (depends on master count)
- **Escalations**: 1-5 logs per hour (rare events)

**Estimated daily volume**: 50,000 - 200,000 log lines

### Log Size

- Average distribution event: ~200 bytes
- Average rejection event: ~400 bytes
- Daily storage: ~50 MB - 200 MB

## Configuration

### Logger Setup

```python
import logging

# Configure distribution logger
dist_logger = logging.getLogger("distribution.structured")
dist_logger.setLevel(logging.INFO)

# Configure candidates logger
cand_logger = logging.getLogger("distribution.candidates")
cand_logger.setLevel(logging.INFO)

# Add file handler
handler = logging.FileHandler("distribution_structured.log")
handler.setFormatter(logging.Formatter("%(message)s"))
dist_logger.addHandler(handler)
cand_logger.addHandler(handler)
```

### Log Rotation

```python
from logging.handlers import RotatingFileHandler

# Rotate at 100 MB, keep 10 files
handler = RotatingFileHandler(
    "distribution_structured.log",
    maxBytes=100 * 1024 * 1024,  # 100 MB
    backupCount=10,
)
```

## Integration with Monitoring

### Elasticsearch/Kibana

```json
PUT /distribution-logs
{
  "mappings": {
    "properties": {
      "timestamp": {"type": "date"},
      "event": {"type": "keyword"},
      "order_id": {"type": "integer"},
      "master_id": {"type": "integer"},
      "city_id": {"type": "integer"},
      "district_id": {"type": "integer"},
      "round_number": {"type": "integer"},
      "candidates_count": {"type": "integer"},
      "reason": {"type": "keyword"},
      "rejection_reasons": {"type": "keyword"}
    }
  }
}
```

### Grafana Queries

**Escalation Rate**:
```sql
SELECT 
  COUNT(*) as escalations,
  reason
FROM distribution_logs
WHERE event IN ('escalation_logist', 'escalation_admin')
  AND timestamp > NOW() - INTERVAL '1 hour'
GROUP BY reason
```

**Average Assignment Time**:
```sql
WITH offers AS (
  SELECT order_id, MIN(timestamp) as first_offer
  FROM distribution_logs
  WHERE event = 'offer_sent'
  GROUP BY order_id
),
starts AS (
  SELECT order_id, MIN(timestamp) as first_round
  FROM distribution_logs
  WHERE event = 'round_start'
  GROUP BY order_id
)
SELECT 
  AVG(EXTRACT(EPOCH FROM (o.first_offer - s.first_round))) as avg_seconds
FROM offers o
JOIN starts s ON s.order_id = o.order_id
WHERE o.first_offer > NOW() - INTERVAL '1 hour'
```

## Debugging

### Common Issues

**Missing logs**:
- Check logger level: `logging.getLogger("distribution.structured").level`
- Verify handler attached: `logger.handlers`
- Check file permissions

**Malformed JSON**:
- Ensure no `print()` statements mixing with structured logs
- Use separate loggers for human-readable and JSON logs

**High volume**:
- Filter candidate rejections: set `distribution.candidates` to WARNING
- Reduce tick frequency
- Archive old logs more frequently

### Testing

```bash
# Run structured logging tests
cd C:\ProjectF\field-service
$env:PYTHONIOENCODING='utf-8'
pytest tests/test_structured_logging.py -v -s
```

## Benefits

✅ **Machine-Readable**: Easy parsing with jq, Python, or log aggregators  
✅ **Consistent Structure**: All events follow same format  
✅ **Rich Context**: Every event has full order/master/city context  
✅ **Time-Series Analysis**: ISO timestamps for chronological analysis  
✅ **Debugging**: Detailed rejection reasons for troubleshooting  
✅ **Monitoring**: Real-time alerts on escalations  
✅ **Analytics**: Historical analysis of distribution performance

## Comparison: Before vs After

### Before (Plain Text)
```
[dist] order=123 city=1 district=5 round=1/2 candidates=5 top_mid=42
[candidates] order=123 master=101 mode=auto rejected: shift, break
```

**Problems**:
- Hard to parse programmatically
- Missing context (timestamps, full metadata)
- No standard format
- Difficult to aggregate

### After (Structured JSON)
```json
{"timestamp":"2025-10-06T12:00:01Z","event":"candidates_found","order_id":123,"city_id":1,"district_id":5,"round_number":1,"candidates_count":5,"master_id":42}
{"timestamp":"2025-10-06T12:00:02Z","order_id":123,"master_id":101,"mode":"auto","rejection_reasons":["shift","break"],"master_details":{"rating":4.2}}
```

**Benefits**:
- One-line JSON per event
- Easy parsing: `jq '.order_id'`
- Full context preserved
- Standard format for all systems

## See Also

- [Distribution Metrics](DISTRIBUTION_METRICS.md) - Quantitative metrics
- [Distribution Scheduler](../field_service/services/distribution_scheduler.py) - Main logic
- [Candidates Selection](../field_service/services/candidates.py) - Master filtering
