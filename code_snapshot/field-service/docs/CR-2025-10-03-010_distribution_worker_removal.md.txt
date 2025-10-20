# CR-2025-10-03-010: Migration from distribution_worker to distribution_scheduler

**Date:** 2025-10-03  
**Status:** ✅ COMPLETED  
**Type:** Legacy Code Removal / Test Migration

---

## 📋 Summary

Removed legacy `distribution_worker.py` and migrated all tests to use the modern `distribution_scheduler.py` implementation.

## 🎯 Motivation

- `distribution_worker.py` - legacy standalone worker with basic functionality
- `distribution_scheduler.py` - modern implementation with:
  - ✅ Advisory locks (prevents duplicate processing)
  - ✅ DEFERRED order wake-up automation  
  - ✅ Telegram push notifications for admins
  - ✅ Detailed logging and reports
  - ✅ Better architecture and error handling

Production was already using `distribution_scheduler` exclusively via `admin_bot/main.py`.

## 📊 Changes Made

### 1. Updated Tests (`tests/test_distribution_scheduler.py`)

**Before:**
```python
from field_service.services import distribution_worker

cfg = distribution_worker.DistConfig(...)
await distribution_worker.process_one_order(session, cfg, order)
await distribution_worker._maybe_escalate_admin(session, cfg, order)
```

**After:**
```python
from field_service.services import distribution_scheduler

cfg = distribution_scheduler.DistConfig(...)
await distribution_scheduler.tick_once(cfg, bot=None, alerts_chat_id=None)
```

**Key improvements:**
- Tests now use public API (`tick_once`) instead of internal functions
- More integration-focused (tests real behavior)
- Removed mocking of internal implementation details
- Added new tests for config loading and offer sending

### 2. Removed Legacy File

**Deprecated:**
- `field_service/services/distribution_worker.py` → `.deprecated`

**Reason:** 
- Not imported anywhere in production code
- Only used in tests (now migrated)
- Scheduler provides all functionality + more

## 🧪 Testing

**New test suite covers:**

1. ✅ `test_wakeup_promotes_at_start` - DEFERRED → SEARCHING transition
2. ✅ `test_wakeup_notices_only_once` - Deduplication of wakeup logs
3. ✅ `test_wakeup_uses_city_timezone` - City-specific timezone handling
4. ✅ `test_distribution_escalates_when_no_candidates` - Logist escalation
5. ✅ `test_distribution_sends_offer_when_candidates_exist` - Offer creation
6. ✅ `test_distribution_config_loads_from_settings` - Config loading

**Run tests:**
```bash
pytest tests/test_distribution_scheduler.py -v
```

## ⚠️ Breaking Changes

**None** - production code already using `distribution_scheduler`.

## 🔄 Rollback Plan

If issues arise:
```bash
# Restore deprecated file
mv field_service/services/distribution_worker.py.deprecated \
   field_service/services/distribution_worker.py

# Revert test changes
git checkout HEAD tests/test_distribution_scheduler.py
```

## ✅ Verification Checklist

- [x] Production using `distribution_scheduler` (confirmed in `admin_bot/main.py`)
- [x] Tests updated and passing
- [x] No imports of `distribution_worker` remain in codebase
- [x] Legacy file deprecated (not deleted - safe fallback)
- [x] Documentation created

## 📈 Impact

- **Code Quality:** ✅ Removed 800+ lines of legacy code
- **Maintainability:** ✅ Single source of truth for distribution logic  
- **Test Quality:** ✅ More robust integration tests
- **Production:** ✅ No changes (already using scheduler)

## 🔗 Related

- Original comparison document in Project Knowledge
- `distribution_scheduler.py` implementation
- `admin_bot/main.py` - production usage
