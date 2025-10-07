# ⚡ БЫСТРЫЙ СТАРТ HOTFIX

## Одна команда для исправления:

```powershell
# 1. Обновить роль в БД
Get-Content scripts/update_global_admin.sql | docker exec -i field-service-postgres-1 psql -U fs_user -d field_service

# 2. Перезапустить бот (Ctrl+C, затем):
python -m field_service.bots.admin_bot.main
```

## Проверка:
Открыть бот → 💰 Финансы → Комиссию → ✅ Подтвердить

Должно работать БЕЗ ошибок! ✅

---

## Если что-то пошло не так:

### Ошибка: "Superuser не зарегистрирован"
```sql
-- Проверить наличие записи
SELECT id, tg_user_id, role FROM staff_users WHERE tg_user_id = 332786197;

-- Если пусто - создать вручную
INSERT INTO staff_users (tg_user_id, full_name, role, is_active, commission_requisites)
VALUES (332786197, 'Superuser', 'GLOBAL_ADMIN', true, '{}'::jsonb);
```

### Ошибка FK-constraint всё ещё есть
```sql
-- Убедиться, что роль обновлена
SELECT id, tg_user_id, full_name, role FROM staff_users WHERE tg_user_id = 332786197;
-- Должно показать role = 'GLOBAL_ADMIN'
```

### Middleware не загружает staff
- Перезапустите бот полностью (Ctrl+C → заново)
- Проверьте .env: `ADMIN_BOT_SUPERUSERS=332786197`

---

**Время применения: < 1 минуты** ⏱️
