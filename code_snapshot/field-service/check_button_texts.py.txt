"""Скрипт для сбора всех текстов кнопок и сообщений в админ-боте."""
import re
from pathlib import Path
from collections import defaultdict

def extract_button_texts_from_file(file_path):
    """Извлекает тексты кнопок из файла."""
    texts = []
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Поиск text= в InlineKeyboardButton
    patterns = [
        r'text=["\']([^"\']+)["\']',  # text="..."
        r'text=f["\']([^"\']+)["\']',  # text=f"..."
        r'\.button\(\s*text=["\']([^"\']+)["\']',  # .button(text="...")
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content)
        texts.extend(matches)
    
    return texts

def extract_test_expectations(file_path):
    """Извлекает ожидаемые тексты из тестов."""
    expectations = []
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Поиск строк-ожиданий в тестах
    patterns = [
        r'assert ["\']([^"\']+)["\'] in',
        r'==\s*["\']([^"\']+)["\']',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, content)
        expectations.extend(matches)
    
    return expectations

def collect_all_texts():
    """Собирает все тексты из админ-бота."""
    base_path = Path('field_service/bots/admin_bot')
    tests_path = Path('tests')
    
    results = {
        'button_texts_by_module': defaultdict(set),
        'test_expectations': defaultdict(set),
        'all_button_texts': set(),
    }
    
    # Клавиатуры
    keyboards_path = base_path / 'ui' / 'keyboards'
    for file in keyboards_path.glob('*.py'):
        if file.name == '__init__.py':
            continue
        texts = extract_button_texts_from_file(file)
        results['button_texts_by_module'][file.stem].update(texts)
        results['all_button_texts'].update(texts)
    
    # Хендлеры
    handlers_path = base_path / 'handlers'
    for file in handlers_path.rglob('*.py'):
        if file.name == '__init__.py':
            continue
        texts = extract_button_texts_from_file(file)
        results['button_texts_by_module'][f"handlers/{file.stem}"].update(texts)
        results['all_button_texts'].update(texts)
    
    # Тесты
    for test_file in tests_path.glob('test_admin_bot_*.py'):
        expectations = extract_test_expectations(test_file)
        results['test_expectations'][test_file.stem].update(expectations)
    
    return results

def main():
    results = collect_all_texts()
    
    output_lines = []
    output_lines.append("=" * 80)
    output_lines.append("АНАЛИЗ ТЕКСТОВ КНОПОК В АДМИН-БОТЕ")
    output_lines.append("=" * 80)
    output_lines.append("")
    
    # Все уникальные тексты кнопок
    output_lines.append("ВСЕ УНИКАЛЬНЫЕ ТЕКСТЫ КНОПОК В КОДЕ:")
    output_lines.append("-" * 80)
    for text in sorted(results['all_button_texts']):
        output_lines.append(f"  - {text}")
    output_lines.append("")
    
    # Детали по модулям
    output_lines.append("=" * 80)
    output_lines.append("ТЕКСТЫ КНОПОК ПО МОДУЛЯМ:")
    output_lines.append("=" * 80)
    for module, texts in sorted(results['button_texts_by_module'].items()):
        output_lines.append(f"\n{module}:")
        for text in sorted(texts):
            output_lines.append(f"  - {text}")
    output_lines.append("")
    
    # Ожидания в тестах
    output_lines.append("=" * 80)
    output_lines.append("ОЖИДАЕМЫЕ СТРОКИ В ТЕСТАХ:")
    output_lines.append("=" * 80)
    for test_file, expectations in sorted(results['test_expectations'].items()):
        output_lines.append(f"\n{test_file}:")
        for exp in sorted(expectations):
            output_lines.append(f"  - {exp}")
    
    # Сохраняем результат
    output_file = Path('button_texts_analysis.txt')
    output_file.write_text('\n'.join(output_lines), encoding='utf-8')
    print(f"Анализ сохранён в {output_file}")
    print(f"Всего найдено уникальных текстов кнопок: {len(results['all_button_texts'])}")

if __name__ == '__main__':
    main()
