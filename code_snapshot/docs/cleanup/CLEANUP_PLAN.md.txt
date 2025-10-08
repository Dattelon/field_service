# 🗑️ ФАЙЛЫ ДЛЯ УДАЛЕНИЯ

## Категории файлов

---

## ❌ УДАЛИТЬ ОБЯЗАТЕЛЬНО (временные файлы)

### В корне проекта C:\ProjectF:

#### Временные Python скрипты (apply/patch):
- [ ] `apply_orders_patch.py` - временный скрипт применения патча
- [ ] `apply_patch.ps1` - PowerShell скрипт
- [ ] `apply_queue_refactor.py` - применён, больше не нужен
- [ ] `check_queue_refactor.py` - проверочный скрипт
- [ ] `_apply_patch.py` - временный
- [ ] `rewrite_migration.py` - временный
- [ ] `rewrite_services.py` - временный

#### Временные snippet файлы:
- [ ] `approve_snippet.txt` - сниппет кода
- [ ] `block.txt` - сниппет
- [ ] `city_chunk.txt` - сниппет
- [ ] `create_order_block.txt` - сниппет
- [ ] `orders_service_block.txt` - сниппет
- [ ] `snip_fin.txt` - сниппет
- [ ] `temp_queue_backup.txt` - бэкап (если уже применён)
- [ ] `tmp_section.txt` - временный
- [ ] `tmp_section2.txt` - временный
- [ ] `menu_dump.json` - дамп меню

#### Временные утилиты (debugging):
- [ ] `check_fffd.py` - проверка кодировки
- [ ] `check_parse.py` - проверка парсинга
- [ ] `count_strings.py` - подсчёт строк
- [ ] `esc.py` - escape утилита
- [ ] `esc_list.py` - escape list
- [ ] `extract_block.py` - извлечение блоков
- [ ] `findbytes.py` - поиск байтов
- [ ] `inspect_chars.py` - инспекция символов
- [ ] `inspect_line.py` - инспекция строк
- [ ] `readbytes.py` - чтение байтов
- [ ] `replace_block.py` - замена блоков
- [ ] `repr_block.py` - repr блоков
- [ ] `update_dw.py` - обновление DW
- [ ] `write_texts.py` - запись текстов

#### Временные файлы с префиксом tmp/temp/_tmp/__tmp:
- [ ] `tmp_edit_orders.py`
- [ ] `_tmp_fix.py`
- [ ] `_update_admin_imports.py`
- [ ] `__tmp_check.py`
- [ ] `__tmp_codes.py`
- [ ] `__tmp_count.py`
- [ ] `__tmp_patch_notice.py`
- [ ] `__tmp_replace_unicode.py`
- [ ] `__tmp_show_lines.py`

#### Patch файлы (если применены):
- [ ] `mini.patch`
- [ ] `patch.diff`
- [ ] `tmp_handlers_step2.patch`

#### Старые файлы:
- [ ] `TZ(old)` - старая версия

---

### В field-service/:

#### Временные Python скрипты:
- [ ] `collect_files.py` - утилита сбора файлов
- [ ] `collect_files.pyc` - скомпилированный
- [ ] `find_methods.py` - поиск методов
- [ ] `_set_city_tz.py` - установка timezone

#### Временные patch/design файлы:
- [ ] `P0_MODERATION_ACTION_PLAN.md` - перемещён в docs
- [ ] `P0_MODERATION_METHODS.py` - временный метод
- [ ] `P1_QUEUE_SEARCH_PATCH.py` - патч применён
- [ ] `P2_11_BULK_APPROVE_METHOD.py` - метод применён
- [ ] `P2_11_DBFINANCE_PATCH.py` - патч применён
- [ ] `P2_11_SUMMARY.md` - перемещён в docs
- [ ] `P2_BULK_APPROVE_DESIGN.py` - design файл
- [ ] `P2_SCHEDULED_REPORTS_DESIGN.md` - design файл
- [ ] `PATCH_DBMastersService_moderation.py` - патч

#### Diff/patch файлы:
- [ ] `patch1.diff`
- [ ] `patch_export.diff`
- [ ] `temp_patch.diff`

#### Временные test файлы:
- [ ] `temp_message_answer.py`
- [ ] `temp_simulate_close.py`
- [ ] `temp_simulate_close2.py`
- [ ] `temp_simulate_close3.py`

#### Snapshot:
- [ ] `project_snapshot.txt` - можно удалить, если не актуален

---

## ⚠️ ПРОВЕРИТЬ ПЕРЕД УДАЛЕНИЕМ

### В корне проекта:
- [ ] `.local/` - локальная папка (проверить содержимое)
- [ ] `.pytest_cache/` - кэш pytest (можно удалить)
- [ ] `.ruff_cache/` - кэш ruff (можно удалить)

### В field-service/:
- [ ] `.mypy_cache/` - кэш mypy (можно удалить)
- [ ] `.pytest_cache/` - кэш pytest (можно удалить)
- [ ] `.ruff_cache/` - кэш ruff (можно удалить)
- [ ] `__pycache__/` - кэш Python (можно удалить, но регенерируется)

---

## ✅ ОСТАВИТЬ (важные файлы)

### В корне проекта:
- [x] `MASTER_PLAN_v1.3.md` - главный план
- [x] `README.md` - описание проекта
- [x] `docs/` - вся документация
- [x] `field-service/` - основной проект
- [x] `tools/` - утилиты (проверить содержимое)
- [x] `.gitignore`, `.git`, `.vscode` - git и IDE настройки

### В field-service/:
- [x] `.env`, `.env.example` - конфигурация
- [x] `.editorconfig`, `.gitattributes`, `.gitignore` - настройки
- [x] `.pre-commit-config.yaml` - pre-commit хуки
- [x] `alembic/`, `alembic.ini` - миграции БД
- [x] `docker-compose.yml` - Docker конфиг
- [x] `field_service/` - исходный код
- [x] `mypy.ini`, `pytest.ini` - конфиги тестов
- [x] `README.md`, `CHANGELOG.md` - документация
- [x] `requirements.txt` - зависимости
- [x] `scripts/`, `tests/`, `tools/`, `ops/` - важные папки
- [x] `UAT_CHECKLIST.md` - чеклист

---

## 📊 СТАТИСТИКА

### Для удаления:
- **Корень проекта:** ~43 файла
- **field-service/:** ~17 файлов
- **Итого:** ~60 файлов

### Можно удалить кэш:
- `.pytest_cache/` (2 папки)
- `.ruff_cache/` (2 папки)
- `.mypy_cache/` (1 папка)
- `__pycache__/` (много папок)

---

## 🚀 КОМАНДЫ ДЛЯ УДАЛЕНИЯ

### PowerShell (Windows):

```powershell
# В корне проекта
cd C:\ProjectF

# Удалить временные Python скрипты
Remove-Item apply_orders_patch.py, apply_patch.ps1, apply_queue_refactor.py -Force
Remove-Item check_queue_refactor.py, _apply_patch.py, rewrite_migration.py, rewrite_services.py -Force

# Удалить сниппеты
Remove-Item approve_snippet.txt, block.txt, city_chunk.txt, create_order_block.txt -Force
Remove-Item orders_service_block.txt, snip_fin.txt, temp_queue_backup.txt -Force
Remove-Item tmp_section.txt, tmp_section2.txt, menu_dump.json -Force

# Удалить утилиты debugging
Remove-Item check_fffd.py, check_parse.py, count_strings.py, esc.py, esc_list.py -Force
Remove-Item extract_block.py, findbytes.py, inspect_chars.py, inspect_line.py -Force
Remove-Item readbytes.py, replace_block.py, repr_block.py, update_dw.py, write_texts.py -Force

# Удалить tmp файлы
Remove-Item tmp_edit_orders.py, _tmp_fix.py, _update_admin_imports.py -Force
Remove-Item __tmp_*.py -Force

# Удалить patch файлы
Remove-Item mini.patch, patch.diff, tmp_handlers_step2.patch -Force

# Удалить старые
Remove-Item "TZ(old)" -Force

# В field-service
cd field-service

# Удалить временные скрипты
Remove-Item collect_files.py, collect_files.pyc, find_methods.py, _set_city_tz.py -Force

# Удалить patch/design файлы
Remove-Item P0_MODERATION_ACTION_PLAN.md, P0_MODERATION_METHODS.py -Force
Remove-Item P1_QUEUE_SEARCH_PATCH.py, P2_11_BULK_APPROVE_METHOD.py -Force
Remove-Item P2_11_DBFINANCE_PATCH.py, P2_11_SUMMARY.md -Force
Remove-Item P2_BULK_APPROVE_DESIGN.py, P2_SCHEDULED_REPORTS_DESIGN.md -Force
Remove-Item PATCH_DBMastersService_moderation.py -Force

# Удалить diff файлы
Remove-Item patch1.diff, patch_export.diff, temp_patch.diff -Force

# Удалить temp test файлы
Remove-Item temp_message_answer.py, temp_simulate_close*.py -Force

# Удалить snapshot (если не нужен)
Remove-Item project_snapshot.txt -Force

# Удалить кэши (опционально)
Remove-Item -Recurse -Force .pytest_cache, .ruff_cache, .mypy_cache -ErrorAction SilentlyContinue
```

### Bash (Linux/Mac):

```bash
# В корне проекта
cd /path/to/ProjectF

# Удалить временные файлы
rm -f apply_orders_patch.py apply_patch.ps1 apply_queue_refactor.py
rm -f check_queue_refactor.py _apply_patch.py rewrite_migration.py rewrite_services.py
rm -f approve_snippet.txt block.txt city_chunk.txt create_order_block.txt
rm -f orders_service_block.txt snip_fin.txt temp_queue_backup.txt
rm -f tmp_section.txt tmp_section2.txt menu_dump.json
rm -f check_fffd.py check_parse.py count_strings.py esc.py esc_list.py
rm -f extract_block.py findbytes.py inspect_chars.py inspect_line.py
rm -f readbytes.py replace_block.py repr_block.py update_dw.py write_texts.py
rm -f tmp_edit_orders.py _tmp_fix.py _update_admin_imports.py
rm -f __tmp_*.py
rm -f mini.patch patch.diff tmp_handlers_step2.patch
rm -f "TZ(old)"

# В field-service
cd field-service
rm -f collect_files.py collect_files.pyc find_methods.py _set_city_tz.py
rm -f P0_MODERATION_ACTION_PLAN.md P0_MODERATION_METHODS.py
rm -f P1_QUEUE_SEARCH_PATCH.py P2_11_BULK_APPROVE_METHOD.py
rm -f P2_11_DBFINANCE_PATCH.py P2_11_SUMMARY.md
rm -f P2_BULK_APPROVE_DESIGN.py P2_SCHEDULED_REPORTS_DESIGN.md
rm -f PATCH_DBMastersService_moderation.py
rm -f patch1.diff patch_export.diff temp_patch.diff
rm -f temp_message_answer.py temp_simulate_close*.py
rm -f project_snapshot.txt

# Удалить кэши
rm -rf .pytest_cache .ruff_cache .mypy_cache
```

---

## ⚡ БЫСТРОЕ УДАЛЕНИЕ (осторожно!)

Если уверены, что все временные файлы можно удалить:

```powershell
# PowerShell - удалить всё из списка одной командой
cd C:\ProjectF
Get-Content cleanup_list.txt | ForEach-Object { Remove-Item $_ -Force -ErrorAction SilentlyContinue }
```

---

## 📋 РЕКОМЕНДАЦИИ

1. **Перед удалением:**
   - Сделать commit текущего состояния
   - Создать бэкап важных файлов
   - Проверить что патчи действительно применены

2. **После удаления:**
   - Запустить тесты: `pytest`
   - Проверить что проект работает
   - Сделать commit: `git add -A && git commit -m "chore: cleanup temporary files"`

3. **Кэши:**
   - Можно удалять безопасно (регенерируются)
   - Добавить в `.gitignore` если ещё не добавлены

---

**Создано:** 03.10.2025  
**Автор:** Claude (Anthropic)

**Продолжаю с удалением?**
