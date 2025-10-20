# 🔧 КРИТИЧЕСКАЯ ОТЛАДКА - Очистка кэша Python

## Проблема
Python кэширует скомпилированные файлы `.pyc`, которые могут содержать старый код.

## Решение

### 1. Удалить ВСЕ кэшированные файлы
```powershell
# Из корня field-service
Get-ChildItem -Path . -Include __pycache__ -Recurse -Force | Remove-Item -Force -Recurse
Get-ChildItem -Path . -Include *.pyc -Recurse -Force | Remove-Item -Force
```

### 2. Перезапустить бот с отладкой
```powershell
python -m field_service.bots.admin_bot.main
```

### 3. Проверить логи
При попытке подтвердить комиссию вы должны увидеть:
```
ERROR:...[MIDDLEWARE] Loading superuser from DB for tg_id=332786197
ERROR:...[MIDDLEWARE] Loaded: staff.id=5, staff.tg_id=332786197, staff.role=GLOBAL_ADMIN
ERROR:...[MIDDLEWARE] Setting data['staff'] with id=5
```

**Если увидите `staff.id=0` или `staff.id=None`** — проблема в `get_by_tg_id()`, нужно смотреть services_db.py

---

## Альтернатива: Запуск с флагом -B
```powershell
# Игнорирует все .pyc файлы
python -B -m field_service.bots.admin_bot.main
```

---

**ВЫПОЛНИТЕ ПРЯМО СЕЙЧАС И ПРИШЛИТЕ ЛОГИ!**
