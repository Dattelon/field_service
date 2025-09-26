*** Begin Patch
*** Update File: field_service/services/distribution_worker.py
@@
-async def _max_active_limit_for(session: AsyncSession) -> int:
-    #  
-    return await _get_int_setting(session, "max_active_orders", 1)
+async def _max_active_limit_for(session: AsyncSession) -> int:
+    """Return the global default max active orders (fallback 5)."""
+    value = await _get_int_setting(session, "max_active_orders", 5)
+    # Safety guard: at least 1 active order allowed.
+    return max(1, int(value))
@@
 async def _mark_logist_escalation(
     session: Optional[AsyncSession],
     order: Any,
     reason_suffix: str,
 ) -> None:
@@
-        await _append_history(session, order, f"{ESC_REASON_LOGIST}:{reason_suffix}")
-        print(log_escalate(order.id))
+        await _append_history(session, order, f"{ESC_REASON_LOGIST}:{reason_suffix}")
+        message = log_escalate(order.id)
+        print(message)
+        try:
+            live_log.push("dist", message, level="WARN")
+        except Exception:
+            pass
@@
-        await _append_history(session, order, ESC_REASON_ADMIN)
-        print(log_escalate_admin(order.id))
+        await _append_history(session, order, ESC_REASON_ADMIN)
+        message = log_escalate_admin(order.id)
+        print(message)
+        try:
+            live_log.push("dist", message, level="WARN")
+        except Exception:
+            pass
@@
-def log_skip_no_district(order_id: int) -> str:
-    return f"[dist] order={order_id} skip_auto: no_district  escalate=logist_now"
+def log_skip_no_district(order_id: int) -> str:
+    return f"[dist] order={order_id} skip_auto: no_district  escalate=logist_now"
@@
 async def autoblock_guarantee_timeouts(session: AsyncSession) -> int:
@@
-        UPDATE masters SET is_blocked=TRUE, blocked_at=NOW(), blocked_reason='guarantee_refusal'
+        UPDATE masters
+           SET is_blocked = TRUE,
+               is_active = FALSE,
+               blocked_at = NOW(),
+               blocked_reason = 'guarantee_refusal'
@@
 async def autoblock_guarantee_declines(session: AsyncSession) -> int:
@@
-        UPDATE masters
-           SET is_blocked = TRUE,
-               blocked_at = NOW(),
-               blocked_reason = 'guarantee_refusal'
+        UPDATE masters
+           SET is_blocked = TRUE,
+               is_active = FALSE,
+               blocked_at = NOW(),
+               blocked_reason = 'guarantee_refusal'
@@
 async def fetch_orders_batch(session: AsyncSession, limit: int = 100) -> Sequence[Any]:
@@
-        SELECT id, city_id, district_id, preferred_master_id, status, category, order_type, dist_escalated_logist_at, dist_escalated_admin_at
+        SELECT id,
+               city_id,
+               district_id,
+               preferred_master_id,
+               status,
+               category,
+               order_type,
+               dist_escalated_logist_at,
+               dist_escalated_admin_at,
+               no_district
@@
 async def process_one_order(
     session: Optional[AsyncSession], cfg: DistConfig, o: Any
 ) -> None:
     await _maybe_escalate_admin(session, cfg, o)
 
-    if getattr(o, "district_id", None) is None:
-        await _mark_logist_escalation(session, o, "no_district")
-        await _maybe_escalate_admin(session, cfg, o)
+    district_missing = getattr(o, "district_id", None) is None
+    no_district_flag = bool(getattr(o, "no_district", False))
+    if district_missing or no_district_flag:
+        message = log_skip_no_district(o.id)
+        print(message)
+        try:
+            live_log.push("dist", message, level="WARN")
+        except Exception:
+            pass
+        await _mark_logist_escalation(session, o, "no_district")
+        await _maybe_escalate_admin(session, cfg, o)
         return
@@
     skill_code = _skill_code_for_category(category)
     if skill_code is None:
-        print(log_skip_no_category(o.id, category))
+        message = log_skip_no_category(o.id, category)
+        print(message)
+        try:
+            live_log.push("dist", message, level="WARN")
+        except Exception:
+            pass
         return
@@
-    header = log_tick_header(o, next_round, cfg.rounds, cfg.sla_seconds, len(cand))
-    print(header)
+    header = log_tick_header(o, next_round, cfg.rounds, cfg.sla_seconds, len(cand))
+    print(header)
+    try:
+        live_log.push("dist", header)
+    except Exception:
+        pass
     if cand:
         top = cand[:10]
         ranked = ", ".join(
@@
-        print("ranked=[\n  " + ranked + "\n]")
+        ranked_block = "ranked=[\n  " + ranked + "\n]"
+        print(ranked_block)
+        try:
+            live_log.push("dist", ranked_block)
+        except Exception:
+            pass
 
         first = cand[0]
         await _reset_escalations(session, o)
         ok = await send_offer(
             session, o.id, int(first["mid"]), next_round, cfg.sla_seconds
         )
         if ok:
             until = _now() + timedelta(seconds=cfg.sla_seconds)
-            print(log_decision_offer(int(first["mid"]), until))
+            decision = log_decision_offer(int(first["mid"]), until)
+            print(decision)
+            try:
+                live_log.push("dist", decision)
+            except Exception:
+                pass
         else:
             print(
                 f"[dist] order={o.id} race_conflict: offer exists for mid={first['mid']}"
             )
     else:
*** End Patch
