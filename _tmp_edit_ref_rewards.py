from pathlib import Path

path = Path('field_service/db/models.py')
lines = path.read_text(encoding='utf-8').splitlines()
out = []
i = 0
quote = '"'
replaced = False
while i < len(lines):
    line = lines[i]
    if not replaced and line.strip() == '__table_args__ = (':
        out.extend([
            '    __table_args__ = (',
            '        UniqueConstraint(',
            f'            {quote}commission_id{quote},',
            f'            {quote}level{quote},',
            f'            name={quote}uq_referral_rewards__commission_level{quote},',
            '        ),',
            f'        Index({quote}ix_ref_rewards__referrer_status{quote}, {quote}referrer_id{quote}, {quote}status{quote}),',
            f'        Index({quote}ix_ref_rewards__referrer_created{quote}, {quote}referrer_id{quote}, {quote}created_at{quote}),',
            '    )',
        ])
        replaced = True
        i += 1
        while i < len(lines) and not lines[i].startswith('    )'):
            i += 1
        if i < len(lines) and lines[i].startswith('    )'):
            i += 1
        continue
    out.append(line)
    i += 1

if not replaced:
    raise SystemExit('expected snippet not found')
path.write_text('\n'.join(out) + '\n', encoding='utf-8')
