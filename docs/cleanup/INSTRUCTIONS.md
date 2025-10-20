# 🗑️ УДАЛЕНИЕ ВРЕМЕННЫХ ФАЙЛОВ - ИНСТРУКЦИЯ

## ⚡ Быстрый старт

### Вариант 1: Python (рекомендуется)
```bash
cd C:\ProjectF
python cleanup_temp_files.py
```

### Вариант 2: PowerShell
```powershell
cd C:\ProjectF
.\cleanup_temp_files.ps1
```

---

## 📋 Что будет удалено

### Из корня проекта (~43 файла):
- ✅ Временные Python скрипты (apply_*, check_*, rewrite_*, etc.)
- ✅ Сниппеты кода (*.txt)
- ✅ Утилиты отладки (inspect_*, find_*, etc.)
- ✅ Временные файлы (tmp_*, _tmp_*, __tmp_*)
- ✅ Patch файлы (*.patch, *.diff)
- ✅ Старые файлы (TZ(old))

### Из field-service/ (~17 файлов):
- ✅ Временные скрипты (collect_files.py, find_methods.py, etc.)
- ✅ Patch/design файлы (P0_*, P1_*, P2_*, PATCH_*)
- ✅ Diff файлы (*.diff)
- ✅ Временные тесты (temp_simulate_close*.py)
- ✅ Снапшоты (project_snapshot.txt)

**Итого:** ~60 файлов

---

## ⚠️ Важно!

### Перед удалением:
1. ✅ Убедитесь что патчи применены
2. ✅ Сделайте backup (если нужен):
   ```bash
   git commit -am "backup before cleanup"
   ```

### После удаления:
1. ✅ Проверьте что проект работает:
   ```bash
   cd field-service
   pytest
   ```

2. ✅ Сделайте commit:
   ```bash
   git add -A
   git commit -m "chore: cleanup temporary files"
   ```

---

## 🔍 Что НЕ будет удалено

### Важные файлы остаются:
- ✅ `MASTER_PLAN_v1.3.md` - главный план
- ✅ `README.md` - описание проекта
- ✅ `docs/` - вся документация
- ✅ `field-service/` - исходный код
- ✅ `tools/` - утилиты
- ✅ `.git`, `.gitignore`, `.vscode` - настройки

---

## 📊 Ожидаемый результат

### До:
```
C:\ProjectF/
├── 📄 43 временных файла
├── 📁 docs/
├── 📁 field-service/
│   └── 📄 17 временных файлов
└── ...
```

### После:
```
C:\ProjectF/
├── 📄 MASTER_PLAN_v1.3.md
├── 📄 README.md
├── 📄 CLEANUP_PLAN.md (можно удалить после)
├── 📁 docs/ (организованная документация)
├── 📁 field-service/ (чистый проект)
└── 📁 tools/
```

---

## 🚀 Дополнительная очистка (опционально)

### Удалить кэши:
```powershell
# PowerShell
Remove-Item -Recurse -Force .pytest_cache, .ruff_cache, .mypy_cache -ErrorAction SilentlyContinue
cd field-service
Remove-Item -Recurse -Force .pytest_cache, .ruff_cache, .mypy_cache, __pycache__ -ErrorAction SilentlyContinue
```

```bash
# Bash
rm -rf .pytest_cache .ruff_cache
cd field-service
rm -rf .pytest_cache .ruff_cache .mypy_cache
find . -type d -name __pycache__ -exec rm -rf {} +
```

---

## ❓ Что делать если ошибка

### Файл не найден:
✅ Нормально - файл уже удалён или не существовал

### Ошибка доступа:
❌ Закройте программы использующие файл (IDE, редакторы)

### Ошибка удаления:
❌ Проверьте права доступа, запустите от администратора

---

## 📝 После очистки

1. ✅ Проект станет чище (~60 файлов меньше)
2. ✅ Легче найти нужные файлы
3. ✅ Меньше мусора в git status
4. ✅ Быстрее работа IDE

---

**Создано:** 03.10.2025  
**Автор:** Claude (Anthropic)

**Готов удалять? Запустите:**
- `python cleanup_temp_files.py` (Python)
- `.\cleanup_temp_files.ps1` (PowerShell)
