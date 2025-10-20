# ✅ СКРИПТ СБОРА КОДА СОЗДАН

## 📦 Что создано

### Основные файлы:
1. **`tools/collect_code.py`** - Основной скрипт (300+ строк)
2. **`tools/collect_code.bat`** - Windows launcher для быстрого запуска
3. **`tools/README.md`** - Полная документация с примерами
4. **`tools/QUICKSTART.txt`** - Краткая шпаргалка
5. **`tools/collect_code.config.example.toml`** - Пример конфигурации

---

## 🚀 КАК ИСПОЛЬЗОВАТЬ

### Windows (самый простой способ):
```bash
# Перейти в корень проекта
cd C:\ProjectF\field-service

# Запустить bat-файл
tools\collect_code.bat

# Результат: code_export.md
```

### Python (универсальный способ):
```bash
# Текстовый формат
python tools/collect_code.py

# Markdown формат (рекомендуется)
python tools/collect_code.py --format markdown -o my_code.md

# Из другой директории
python tools/collect_code.py --root C:\ProjectF\field-service
```

---

## 🎯 ЧТО ВКЛЮЧАЕТСЯ

### ✅ Включаемые файлы:
- **`.py`** - Python исходники
- **`.sql`** - SQL скрипты  
- **`.ini`, `.toml`, `.yaml`, `.yml`** - Конфигурационные файлы
- **`.json`** - JSON данные
- **`.sh`, `.bat`** - Shell/Batch скрипты
- **`.js`, `.html`, `.css`** - Web файлы (если есть)

### ❌ Исключаемые файлы:
- **`.md`, `.txt`** - Документация
- **`.log`** - Логи
- **`.png`, `.jpg`, `.gif`** - Изображения
- **`.pyc`, `.pyo`** - Python bytecode
- **`.zip`, `.tar`, `.gz`** - Архивы

### 🚫 Исключаемые директории:
- `__pycache__`, `.mypy_cache`, `.pytest_cache`
- `.git`, `.venv`, `venv`
- `node_modules`
- `.idea`, `.vscode`
- `dist`, `build`

---

## 📊 ПРИМЕР РЕЗУЛЬТАТА

После запуска вы увидите:

```
📂 Сканирование директории: C:\ProjectF\field-service
🔍 Ищем кодовые файлы...

✓ field_service\__init__.py
✓ field_service\config.py
✓ field_service\db\models.py
✓ field_service\db\session.py
✓ field_service\services\distribution_scheduler.py
✓ field_service\bots\admin_bot\main.py
... (ещё ~120 файлов)

✅ Собрано файлов: 127
📊 Общий размер: 2.45 MB

💾 Сохранение в формате: markdown
✅ Сохранено: code_export.md (2.67 MB)

🎉 Готово!
```

**Результат:** Файл `code_export.md` с:
- Оглавлением для навигации
- Подсветкой синтаксиса
- Всем кодом проекта в одном месте

---

## 💡 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ

### 1. Для AI-ассистента (Claude/GPT):
```bash
python tools/collect_code.py -f markdown -o for_claude.md
# Загружаете for_claude.md в Claude для анализа кода
```

### 2. Бэкап перед большими изменениями:
```bash
python tools/collect_code.py -o backup_20250103.txt
```

### 3. Code review для команды:
```bash
python tools/collect_code.py -f markdown -o code_review.md
# Отправляете code_review.md коллегам
```

### 4. Документация структуры проекта:
```bash
python tools/collect_code.py -f markdown
# Используете как справочник по проекту
```

---

## ⚙️ НАСТРОЙКА

Если нужно изменить поведение:

### Вариант 1: Редактировать константы в скрипте
Откройте `tools/collect_code.py` и измените:
```python
# Добавить новые расширения
INCLUDE_EXTENSIONS = {
    '.py',
    '.rs',    # Добавить Rust
    # ...
}

# Изменить лимит размера
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB
```

### Вариант 2: Конфигурационный файл (TODO)
```bash
# Скопировать пример
cp tools/collect_code.config.example.toml tools/collect_code.config.toml

# Отредактировать
nano tools/collect_code.config.toml
```

---

## 🎨 ФОРМАТЫ ВЫВОДА

### TEXT FORMAT:
```
================================================================================
FILE: field_service/config.py
================================================================================

from pydantic import BaseSettings
...
```

### MARKDOWN FORMAT:
```markdown
## field_service/config.py

```python
from pydantic import BaseSettings
...
```
```

---

## 🔧 ПАРАМЕТРЫ КОМАНДНОЙ СТРОКИ

```
--output, -o FILE     Имя выходного файла (default: code_export.txt)
--format, -f FORMAT   Формат: text или markdown (default: text)
--root, -r PATH       Корневая директория проекта (default: auto)
```

---

## 📈 СТАТИСТИКА ПРОЕКТА

Примерные цифры для вашего проекта:
- **~127 Python файлов**
- **~15 SQL файлов**
- **~10 конфигурационных файлов**
- **Общий размер: ~2.5 MB**
- **Результат экспорта: ~2.7 MB** (с форматированием)

---

## 🐛 TROUBLESHOOTING

### Проблема: "Python not found"
**Решение:** 
```bash
# Проверьте установку Python
python --version

# Должно быть Python 3.8+
```

### Проблема: Файлы не включаются
**Причины:**
1. Расширение не в `INCLUDE_EXTENSIONS`
2. Файл слишком большой (>10 MB)
3. Файл в исключённой директории

**Решение:** Отредактируйте константы в начале `collect_code.py`

### Проблема: Кодировка неправильная
**Решение:** Скрипт использует UTF-8. Убедитесь что исходные файлы в UTF-8

---

## 📚 ДОПОЛНИТЕЛЬНАЯ ИНФОРМАЦИЯ

- **Полная документация:** `tools/README.md`
- **Быстрый старт:** `tools/QUICKSTART.txt`
- **Пример конфига:** `tools/collect_code.config.example.toml`

---

## ✅ ГОТОВО К ИСПОЛЬЗОВАНИЮ!

```bash
# ЗАПУСТИТЕ ПРЯМО СЕЙЧАС:
cd C:\ProjectF\field-service
tools\collect_code.bat

# ИЛИ:
python tools/collect_code.py --format markdown

# РЕЗУЛЬТАТ:
# code_export.md - весь ваш код в одном файле! 🎉
```

---

## 🎉 ПРЕИМУЩЕСТВА

✅ **Быстро** - собирает код за секунды  
✅ **Умно** - исключает мусор автоматически  
✅ **Гибко** - настраивается под ваши нужды  
✅ **Удобно** - два формата вывода  
✅ **Безопасно** - только читает, не модифицирует  

**Наслаждайтесь! 🚀**

---

**Осталось токенов: ~115,000 / 190,000**
