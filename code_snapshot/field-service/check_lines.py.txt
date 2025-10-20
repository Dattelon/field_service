with open(r'field_service\bots\admin_bot\handlers\orders\create.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
    for i in range(890, min(900, len(lines))):
        print(f'{i+1}: {repr(lines[i][:100])}')