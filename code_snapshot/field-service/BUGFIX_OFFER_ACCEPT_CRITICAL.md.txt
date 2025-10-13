# 🔴 CRITICAL BUGFIX: Offer Accept Errors

## Дата: 2025-10-13
## Статус: КРИТИЧНО - бот падает при принятии заказа

---

## Проблемы из логов

### 1. Ошибка типа данных в distribution_metrics
```
column "category" is of type ordercategory but expression is of type character varying
```

**Где**: `field_service/bots/master_bot/handlers/orders.py` строки 383-384

**Причина**: Конвертируем enum в строку `.value`, но БД ожидает сам enum

### 2. Ошибка greenlet_spawn
```
greenlet_spawn has not been called; can't call await_only() here
```

**Где**: `field_service/bots/master_bot/handlers/orders.py` строка 481

**Причина**: После `session.expire_all()` сессия теряет async контекст при попытке загрузить данные в `_render_active_order`

---

## Исправления

### FIX 1: Передавать enum, а не строку (строки 383-384)

```python
# ❌ НЕПРАВИЛЬНО - передаём строку вместо enum
category=order_row.category.value if hasattr(order_row.category, 'value') else str(order_row.category),
order_type=order_row.type.value if hasattr(order_row.type, 'value') else str(order_row.type),

# ✅ ПРАВИЛЬНО - передаём сам enum
category=order_row.category,  # Передаём enum напрямую
order_type=order_row.type,     # Передаём enum напрямую
```

### FIX 2: Убрать session.expire_all() (строка 407)

```python
# ❌ НЕПРАВИЛЬНО - expire_all() ломает async контекст
session.expire_all()
_log.info("offer_accept: session cache expired for order=%s", order_id)

# ✅ ПРАВИЛЬНО - не нужен expire_all(), данные свежие после commit
# SQLAlchemy автоматически обновит данные при следующем SELECT
_log.info("offer_accept: transaction committed successfully for order=%s", order_id)
```

---

## Применение патча

```powershell
# Применить изменения
python C:\ProjectF\field-service\apply_offer_accept_fix.py

# Перезапустить master-bot на сервере
$pass = ConvertTo-SecureString "owo?8x-YA@vRN*" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("root", $pass)
$s = New-SSHSession -ComputerName 217.199.254.27 -Credential $cred -AcceptKey

# Копируем исправленный файл
scp C:\ProjectF\field-service\field_service\bots\master_bot\handlers\orders.py root@217.199.254.27:/opt/field-service/field_service/bots/master_bot/handlers/

# Перезапускаем контейнер
Invoke-SSHCommand -SessionId $s.SessionId -Command "cd /opt/field-service && docker compose restart master-bot"

Remove-SSHSession -SessionId $s.SessionId
```

---

## Проверка

```powershell
# Проверить логи после перезапуска
docker logs --tail 50 field-service-master-bot-1 2>&1 | grep -E "(ERROR|distribution_metrics|greenlet)"
```

Ошибки должны исчезнуть.
