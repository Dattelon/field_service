from pathlib import Path
p = Path('field-service/field_service/bots/admin_bot/handlers.py')
raw = p.read_text(encoding='utf-8', errors='ignore')
fixed = raw.encode('cp1251', 'ignore').decode('utf-8', 'ignore')
print('before_has_R=', 'Р' in raw)
print('after_has_R=', 'Р' in fixed)
if fixed != raw:
    p.write_text(fixed, encoding='utf-8', newline='\n')
    print('rewritten')
else:
    print('nochange')
