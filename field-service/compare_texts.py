"""Сверка текстов кнопок/сообщений между кодом и тестами."""
import re
from pathlib import Path

# Ключевые тексты, проверяемые в тестах
TEST_EXPECTATIONS = {
    'test_admin_bot_new_order.py': [
        'Выберите способ распределения',
        'adm:q:as:auto:',
        'adm:q:as:man:',
    ],
    'test_admin_bot_queue_card.py': [
        'Вложения: 0',
        'Вложения: {len',
        'Мастер: пока не назначен',
        'Описание',
        'adm:q:att:',
        'adm:q:as:',
    ],
    'test_admin_bot_queue_list.py': [
        'Список пуст',
        'adm:q:flt',
        'adm:q:list:',
    ],
}

def check_text_in_code(text, code_files):
    """Проверяет наличие текста в коде."""
    found_in = []
    for file_path in code_files:
        try:
            content = file_path.read_text(encoding='utf-8')
            if text in content:
                found_in.append(file_path.name)
        except Exception as e:
            pass
    return found_in

def main():
    # Файлы кода админ-бота
    admin_bot_path = Path('field_service/bots/admin_bot')
    code_files = list(admin_bot_path.rglob('*.py'))
    
    results = []
    results.append("=" * 100)
    results.append("СВЕРКА ТЕКСТОВ: КОД vs ТЕСТЫ")
    results.append("=" * 100)
    results.append("")
    
    all_ok = True
    
    for test_file, expected_texts in TEST_EXPECTATIONS.items():
        results.append(f"\n[TEST] {test_file}")
        results.append("-" * 100)
        
        for text in expected_texts:
            found_in = check_text_in_code(text, code_files)
            
            if found_in:
                status = "[OK]"
                details = f"      Найдено в: {', '.join(found_in)}"
            else:
                status = "[FAIL]"
                details = "      НЕ НАЙДЕНО В КОДЕ!"
                all_ok = False
            
            results.append(f"  {status} '{text}'")
            results.append(details)
    
    results.append("")
    results.append("=" * 100)
    if all_ok:
        results.append("[SUCCESS] ВСЕ ТЕКСТЫ ИЗ ТЕСТОВ НАЙДЕНЫ В КОДЕ")
    else:
        results.append("[ERROR] ОБНАРУЖЕНЫ НЕСООТВЕТСТВИЯ - ТРЕБУЮТСЯ ПРАВКИ")
    results.append("=" * 100)
    
    output = '\n'.join(results)
    
    # Сохраняем результат
    output_file = Path('texts_comparison.txt')
    output_file.write_text(output, encoding='utf-8')
    print(f"Результат сохранен в {output_file}")
    
    # Выводим сокращённый результат
    if all_ok:
        print("[SUCCESS] Все тексты найдены")
    else:
        print("[ERROR] Обнаружены несоответствия")
        for test_file, expected_texts in TEST_EXPECTATIONS.items():
            for text in expected_texts:
                found_in = check_text_in_code(text, code_files)
                if not found_in:
                    print(f"  MISSING: '{text}' в {test_file}")

if __name__ == '__main__':
    main()
