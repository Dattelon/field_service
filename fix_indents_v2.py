"""
Скрипт для исправления отступов ТОЛЬКО внутри for order in orders:
"""

file_path = r"C:\ProjectF\field-service\field_service\services\distribution_scheduler.py"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.splitlines(keepends=True)

fixed_lines = []
inside_for_loop = False
for_loop_line_num = 0

for i, line in enumerate(lines):
    line_num = i + 1
    
    # Находим строку "for order in orders:"
    if "for order in orders:" in line and not inside_for_loop:
        inside_for_loop = True
        for_loop_line_num = line_num
        fixed_lines.append(line)
        print(f"[{line_num}] Found 'for order in orders:'")
        continue
    
    # Находим строку "await session.commit()" на уровне функции (_tick_once_impl)
    if inside_for_loop and "await session.commit()" in line:
        # Проверяем отступ - должен быть 4 пробела (уровень функции)
        indent = len(line) - len(line.lstrip())
        if indent == 4:
            inside_for_loop = False
            fixed_lines.append(line)
            print(f"[{line_num}] Found end of for loop at 'await session.commit()'")
            continue
    
    # Внутри for loop - убираем 4 пробела если отступ > 8
    if inside_for_loop:
        if line.strip() and line[0] == ' ':
            indent = len(line) - len(line.lstrip())
            # Убираем 4 пробела только если отступ >= 12 (лишний отступ)
            if indent >= 12:
                fixed_line = line[4:]
                fixed_lines.append(fixed_line)
            else:
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)
    else:
        fixed_lines.append(line)

# Записываем
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print(f"Fixed! Total lines: {len(lines)}")
