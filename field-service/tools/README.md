# Tools Directory

Вспомогательные скрипты для работы с проектом.

## 📁 Содержимое

### `collect_code.py` - Сборщик кода проекта

Скрипт для сбора всех кодовых файлов проекта в один файл.

**Возможности:**
- ✅ Автоматический поиск и сбор Python, SQL, конфигурационных файлов
- ✅ Исключение документации, логов, кэша, бинарных файлов
- ✅ Два формата вывода: текст и Markdown
- ✅ Фильтрация по размеру файла
- ✅ Прогресс-индикатор при сборке

**Использование:**

```bash
# Простой запуск (текстовый формат)
python tools/collect_code.py

# Markdown формат
python tools/collect_code.py --format markdown --output code_export.md

# Или через bat-файл (Windows)
tools\collect_code.bat
```

**Параметры:**
- `--output, -o` - Имя выходного файла (по умолчанию: `code_export.txt`)
- `--format, -f` - Формат: `text` или `markdown` (по умолчанию: `text`)
- `--root, -r` - Корневая директория проекта (по умолчанию: автоопределение)

**Примеры:**

```bash
# Экспорт в Markdown с оглавлением
python tools/collect_code.py -f markdown -o project_code.md

# Экспорт конкретной директории
python tools/collect_code.py -r C:\MyProject -o my_code.txt

# Быстрый экспорт для анализа
python tools/collect_code.py -f text -o /tmp/code_snapshot.txt
```

### `collect_code.bat` - Быстрый запуск для Windows

Запускает `collect_code.py` с предустановленными параметрами:
- Формат: Markdown
- Выходной файл: `code_export.md`

**Использование:**
```bash
# Запуск из корня проекта
tools\collect_code.bat
```

---

## ⚙️ Что включается в сборку

### ✅ Включаемые типы файлов:
- `.py` - Python исходники
- `.sql` - SQL скрипты
- `.ini`, `.toml`, `.yaml`, `.yml` - Конфигурационные файлы
- `.json` - JSON данные и конфигурация
- `.env.example` - Шаблоны переменных окружения
- `.sh`, `.bat` - Shell/Batch скрипты
- `.js`, `.html`, `.css` - Web файлы (если есть)

### ❌ Исключаемые типы файлов:
- `.md`, `.txt` - Документация
- `.log` - Логи
- `.png`, `.jpg`, `.gif`, `.svg` - Изображения
- `.pdf`, `.doc`, `.docx` - Документы
- `.zip`, `.tar`, `.gz` - Архивы
- `.pyc`, `.pyo` - Python bytecode
- `.lock` - Lock файлы

### 🚫 Исключаемые директории:
- `__pycache__`, `.mypy_cache`, `.pytest_cache`
- `.git`, `.venv`, `venv`, `env`
- `node_modules`
- `.idea`, `.vscode`
- `dist`, `build`

---

## 🎯 Примеры использования

### 1. Экспорт для ревью кода
```bash
# Создаём читаемый Markdown файл
python tools/collect_code.py -f markdown -o code_review.md

# Отправляем коллегам
# Файл содержит оглавление и подсветку синтаксиса
```

### 2. Бэкап перед большими изменениями
```bash
# Сохраняем текущее состояние
python tools/collect_code.py -o backup_$(date +%Y%m%d).txt

# Храним в отдельной папке
mkdir -p backups
python tools/collect_code.py -o backups/code_$(date +%Y%m%d_%H%M%S).txt
```

### 3. Анализ структуры проекта
```bash
# Экспортируем только для анализа размера
python tools/collect_code.py | tee analysis.log

# Видим:
# - Сколько файлов
# - Общий размер
# - Список обработанных файлов
```

### 4. Подготовка для AI-ассистентов
```bash
# Создаём Markdown для загрузки в Claude/ChatGPT
python tools/collect_code.py -f markdown -o project_for_ai.md

# Результат удобен для анализа:
# - Оглавление для навигации
# - Подсветка синтаксиса
# - Структурированный формат
```

---

## 📊 Пример вывода

```
📂 Сканирование директории: C:\ProjectF\field-service
🔍 Ищем кодовые файлы...

✓ field_service\__init__.py
✓ field_service\config.py
✓ field_service\db\models.py
✓ field_service\db\session.py
✓ field_service\services\distribution_scheduler.py
...

✅ Собрано файлов: 127
📊 Общий размер: 2.45 MB

💾 Сохранение в формате: markdown
✅ Сохранено: code_export.md (2.67 MB)

🎉 Готово!
```

---

## 🔧 Настройка

Если нужно изменить поведение скрипта, отредактируйте константы в начале `collect_code.py`:

```python
# Добавить новые расширения
INCLUDE_EXTENSIONS = {
    '.py',
    '.rs',    # Добавить Rust
    '.go',    # Добавить Go
    # ...
}

# Исключить дополнительные директории
EXCLUDE_DIRS = {
    '__pycache__',
    'my_temp_folder',  # Ваша папка
    # ...
}

# Изменить лимит размера файла
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB вместо 10 MB
```

---

## 🐛 Troubleshooting

### Ошибка: "Python not found"
**Решение:** Установите Python 3.8+ и добавьте в PATH

### Файлы не включаются в сборку
**Причины:**
1. Расширение файла не в списке `INCLUDE_EXTENSIONS`
2. Файл слишком большой (>10 MB)
3. Файл в исключённой директории

**Решение:** Отредактируйте константы в `collect_code.py`

### Кодировка выглядит неправильно
**Решение:** Скрипт использует UTF-8. Убедитесь что:
- Исходные файлы в UTF-8
- Просмотрщик поддерживает UTF-8

---

## 📝 Заметки

- Скрипт безопасен - **только читает** файлы, не модифицирует
- Большие файлы (>10 MB) пропускаются автоматически
- Binary файлы игнорируются
- Скрытые директории (начинаются с `.`) пропускаются (кроме `.github`)

---

## 🚀 TODO

Возможные улучшения:
- [ ] Добавить фильтрацию по git статусу (только tracked файлы)
- [ ] Генерация статистики (строк кода, файлов по типу)
- [ ] Поддержка .gitignore паттернов
- [ ] Сжатие выходного файла
- [ ] Web UI для просмотра
