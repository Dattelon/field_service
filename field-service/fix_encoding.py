#!/usr/bin/env python3
"""Скрипт для исправления битой кириллицы в Python файлах."""
import re
from pathlib import Path

# Маппинг битых строк → правильные строки
FIXES = {
    # master_bot/finance.py
    '"card": " "': '"card": "Карта"',
    '"sbp": ""': '"sbp": "СБП"',
    '"cash": ""': '"cash": "Наличные"',
    'f" : {method_titles}"': 'f"Способ оплаты: {method_titles}"',
    'f" ****{card_last4}"': 'f"Карта ****{card_last4}"',
    'f"  : {sbp_phone}"': 'f"СБП тел: {sbp_phone}"',
    '"QR-  ."': '"QR-код прилагается."',
    'f"  : {comment}"': 'f"Комментарий для перевода: {comment}"',
    
    # master_bot/handlers/statistics.py
    '"<b> </b>"': '"<b>📊 Статистика мастера</b>"',
    'f": <b> :</b> {completed_count}"': 'f"Завершено заказов: <b>всего:</b> {completed_count}"',
    'f" : <b>{avg_rating:.1f}</b>"': 'f"Средняя оценка: <b>{avg_rating:.1f}</b>"',
    'f"  : <b>{response_time_str}</b>"': 'f"Среднее время отклика: <b>{response_time_str}</b>"',
    'f" : <b> :</b> {month_count}"': 'f"Текущий месяц: <b>заказов:</b> {month_count}"',
    '"   ,    !"': '"Добро пожаловать, начните брать заказы!"',
    'f" !  10   {10 - completed_count}."': 'f"Отличный старт! До 10 заказов осталось {10 - completed_count}."',
    'f" !  50   {50 - completed_count}."': 'f"Так держать! До 50 заказов осталось {50 - completed_count}."',
    'f" !  100   {100 - completed_count}."': 'f"Молодец! До 100 заказов осталось {100 - completed_count}."',
    '" !     !"': '"Профессионал! Вы выполнили более сотни заказов!"',
    
    # admin_bot/handlers/system/reports.py
    'f"   : {exc}"': 'f"❌ Ошибка при генерации: {exc}"',
    
    # admin_bot/handlers/system/settings.py  
    '"  "': '"⚠️ Неверный формат времени"',
    
    # admin_bot/handlers/orders/queue.py
    '"  "': '"ℹ️ История статусов"',
    '"  "': '"ℹ️ История статусов"',  # 3 раза встречается
    
    # admin_bot/handlers/staff/access_codes.py
    '"  "': '"⚠️ Код уже использован"',
    
    # admin_bot/handlers/masters/moderation.py
    '"  "': '"⚠️ Мастер не найден"',
    
    # admin_bot/handlers/finance/main.py  
    '"  "': '"⚠️ Недостаточно прав"',
    'f"  #{commission_id}\\n"': 'f"💳 Комиссия #{commission_id}\\n"',
    '"  :"': '"Оплачена:"',
    '"  :"': '"Сумма оплаты:"',
    '" ?"': '"Подтвердить оплату?"',
    
    # Паттерны для пагинации (повторяющиеся)
    ' : ': ': ',  # убираем лишние пробелы вокруг двоеточия в срезах
}

def fix_file(file_path: Path) -> bool:
    """Исправить битую кириллицу в файле.
    
    Returns:
        True если файл был изменен
    """
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content
        
        # Применяем все замены
        for broken, fixed in FIXES.items():
            content = content.replace(broken, fixed)
        
        if content != original:
            # Проверяем синтаксис перед сохранением
            try:
                compile(content, str(file_path), 'exec')
            except SyntaxError as e:
                print(f"❌ Синтаксическая ошибка в {file_path}: {e}")
                return False
            
            file_path.write_text(content, encoding='utf-8')
            return True
        return False
    except Exception as e:
        print(f"❌ Ошибка при обработке {file_path}: {e}")
        return False

def main():
    """Найти и исправить все Python файлы с битой кириллицей."""
    base_dir = Path(__file__).parent / 'field_service' / 'bots'
    
    py_files = list(base_dir.rglob('*.py'))
    print(f"Найдено {len(py_files)} Python файлов")
    
    fixed_count = 0
    for py_file in py_files:
        if fix_file(py_file):
            print(f"✅ Исправлен: {py_file.relative_to(base_dir)}")
            fixed_count += 1
    
    print(f"\n{'='*50}")
    print(f"Исправлено файлов: {fixed_count}")
    print(f"{'='*50}")

if __name__ == '__main__':
    main()
