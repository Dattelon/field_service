"""
Временный скрипт для исправления отступов в distribution_scheduler.py
"""

file_path = r"C:\ProjectF\field-service\field_service\services\distribution_scheduler.py"

# Читаем файл
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим строку "for order in orders:" (примерно строка 771)
# И до "await session.commit()" (примерно строка 1022)
# Убираем 4 лишних пробела с каждой строки в этом диапазоне

fixed_lines = []
inside_for_loop = False
for_loop_indent = 0

for i, line in enumerate(lines):
    line_num = i + 1
    
    # Начало блока
    if "for order in orders:" in line and line_num >= 770:
        inside_for_loop = True
        for_loop_indent = len(line) - len(line.lstrip())
        fixed_lines.append(line)
        print(f"[{line_num}] Начало for loop, базовый отступ: {for_loop_indent}")
        continue
    
    # Конец блока - найдена строка "await session.commit()" на уровне for loop
    if inside_for_loop and "await session.commit()" in line:
        # Проверяем что это на правильном уровне (8 пробелов = уровень функции _tick_once_impl)
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= for_loop_indent:
            inside_for_loop = False
            fixed_lines.append(line)
            print(f"[{line_num}] Конец for loop")
            continue
    
    # Внутри блока - убираем 4 лишних пробела
    if inside_for_loop:
        # Если строка не пустая и начинается с пробелов
        if line.strip() and line[0] == ' ':
            current_indent = len(line) - len(line.lstrip())
            # Убираем 4 пробела только если отступ больше базового
            if current_indent > for_loop_indent:
                fixed_line = line[4:]  # Убираем 4 пробела
                fixed_lines.append(fixed_line)
                if line_num <= 780 or line_num >= 1015:  # Логируем начало и конец
                    print(f"[{line_num}] Исправлен отступ: {current_indent} -> {current_indent-4}")
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    else:
        fixed_lines.append(line)

# Записываем исправленный файл
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print(f"\n✅ Исправлено! Всего строк: {len(lines)}")
