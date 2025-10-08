from pathlib import Path
import re
p=Path('field-service/field_service/bots/admin_bot/handlers.py')
s=p.read_text(encoding='utf-8')

def replace_block(pattern_start, pattern_end, new_block):
    global s
    m1=re.search(pattern_start,s,flags=re.M)
    if not m1:
        return False
    m2=re.search(pattern_end,s[m1.start():],flags=re.M)
    if not m2:
        return False
    start=m1.start()
    end=m1.start()+m2.end()
    s=s[:start]+new_block+s[end:]
    return True

# FINANCE_SEGMENT_TITLES
replace_block(r'^FINANCE_SEGMENT_TITLES\s*=.*?$','^\}\s*$', 'FINANCE_SEGMENT_TITLES = {\n    "aw": "Ожидают оплаты",\n    "pd": "Оплаченные",\n    "ov": "Просроченные",\n}\n')
# STAFF_* constants
a=re.sub(r'^STAFF_CODE_PROMPT\s*=.*$', 'STAFF_CODE_PROMPT = "Введите код доступа, который выдали администраторы."', s, flags=re.M)
s=a
s=re.sub(r'^STAFF_CODE_ERROR\s*=.*$', 'STAFF_CODE_ERROR = "Код не найден / истёк / уже использован / вам недоступен."', s, flags=re.M)
replace_block(r'^STAFF_PDN_TEXT\s*=\s*\(.*?$','^\)\s*$', 'STAFF_PDN_TEXT = (\n    "Согласие на обработку персональных данных.\\n"\n    "Согласие включает обработку ФИО, телефона и данных о заказах для допуска к работе и обеспечения безопасности сервиса. "\n    "Отправьте \\\"Согласен\\\" для продолжения или \\\"Не согласен\\\" для отмены."\n)\n')
# CATEGORY_CHOICES
s=re.sub(r'^CATEGORY_CHOICES:.*?^\]$', 'CATEGORY_CHOICES: list[tuple[OrderCategory, str]] = [\n    (OrderCategory.ELECTRICS, "Электрика"),\n    (OrderCategory.PLUMBING, "Сантехника"),\n    (OrderCategory.APPLIANCES, "Бытовая техника"),\n    (OrderCategory.WINDOWS, "Окна"),\n    (OrderCategory.HANDYMAN, "Универсал"),\n    (OrderCategory.ROADSIDE, "Автопомощь"),\n]\n', s, flags=re.M|re.S)
# REPORT_DEFINITIONS
s=re.sub(r'^REPORT_DEFINITIONS:.*?^\}$', 'REPORT_DEFINITIONS: dict[str, tuple[str, Any, str]] = {\n    "orders": ("заказы", export_service.export_orders, "Orders"),\n    "commissions": ("комиссии", export_service.export_commissions, "Commissions"),\n    "ref_rewards": ("реферальные начисления", export_service.export_referral_rewards, "Referral rewards"),\n}\n', s, flags=re.M|re.S)
# ASAP line fix
s=re.sub(r'ASAP.*19:30.*13\?', 'ASAP позже 19:30. Выбрать завтра 10–13?', s)

p.write_text(s, encoding='utf-8')
print('done')
