with open(r'field_service\bots\admin_bot\handlers\orders\create.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i, line in enumerate(lines, 1):
        if 'prompt_parts.append' in line and 'способ' in line.lower():
            print(f'{i}: {repr(line)}')