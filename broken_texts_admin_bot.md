# Битые/отсутствующие строки в админ-боте

## C:\ProjectF\field-service\field_service\bots\admin_bot\ui\texts\common.py
- Строка 41: `def _category_value(category: object) -> str:` - функция не завершена
- Строка 44-47: Импорты отсутствуют (OrderCategory)

## C:\ProjectF\field-service\field_service\bots\admin_bot\ui\texts\finance.py
- Строка 2-11: Импорты html, Decimal отсутствуют
- Строка 27: `COMMISSION_STATUS_LABELS` - не определена в этом файле
- Строка 40-109: Множественные битые эмодзи/иконки в тексте:
  - ` : {master_name}` (строка 42)
  - ` <b> #{detail.id}</b>` (строка 46)
  - ` : #{detail.order_id}` (строка 47)
  - ` : {status_label}` (строка 50)
  - ` : {detail.amount:.2f} ` (строка 51)
  - ` : {rate_str}%` (строка 57)
  - ` : {html.escape(detail.deadline_at_local)}` (строка 60)
  - ` : {html.escape(detail.created_at_local)}` (строка 61)
  - `   : {html.escape(detail.paid_reported_at_local)}` (строка 63)
  - ` : {html.escape(detail.paid_approved_at_local)}` (строка 65)
  - ` : {detail.paid_amount:.2f} ` (строка 67)
  - `  : {html.escape(methods)}` (строка 71)
  - ` : {' / '.join(card_info)}` (строка 80)
  - ` : {html.escape(sbp_phone)}` (строка 84)
  - ` : {html.escape(other_text)}` (строка 94)
  - ` : {html.escape(comment)}` (строка 97)
  - ` : {'' if detail.has_checks else ''}` (строка 99)

## C:\ProjectF\field-service\field_service\bots\admin_bot\handlers\orders\queue.py
- Строка 254: `type_label = order.type if not is_guarantee else f"{order.type} ()"` - пустые скобки
- Строка 282: `is_deferred = status == 'DEFERRED'  #   ` - битый комментарий
- Строка 283: `#  BUGFIX:   ` - битый комментарий
- Строка 1193-1199: Множественные битые эмодзи в master search:
  - `lines = [f" <b> : {len(masters)}</b>\n"]`
  - `lines.append(f" #{master.id} {full_name} ({master.phone or ''})")`
  - `nav_builder.button(text="Назад к заказу", callback_data=f"adm:q:card:{order_id}")`
  - `nav_builder.button(text="Главное меню", callback_data="adm:menu")`
- Строки 1222-1285: Битые эмодзи в order display:
  - `lines = [f" <b>  #{master_id} {full_name}</b>"]`
  - `f"    {order.client_name or ''}"`
  - `f"    {order.status.value...}`
  - `nav_builder.button(text="🔍 Новый поиск"...)`
  - Multiple status emojis (строки 1237-1243)

## C:\ProjectF\field-service\field_service\bots\admin_bot\handlers\finance\main.py
- Строки 105-150: Множественные битые эмодзи и текст:
  - `lines.append("<b> </b>")` (строка 113)
  - `block.append("<b> </b>")` (строка 137)
  - `block.append(f": {html.escape(card_number)}")` (строки 139-142)
  - `block.append("<b></b>")` (строка 152)
  - `block.append(f": {html.escape(phone)}")` (строки 154-156)
  - `block.append("QR-: " + ("" if qr else ""))` (строка 158)
- Строка 203: `raise ValueErro` - опечатка в названии исключения
- Файл обрезан - требуется полная проверка

## Общие проблемы:
1. Отсутствие импортов (html, Decimal, OrderCategory)
2. Битые emoji/иконки по всему коду
3. Незавершённые функции
4. Опечатки в названиях классов исключений
5. Пустые строки вместо текста labels

## Рекомендации:
1. Проверить кодировку файлов (должна быть UTF-8)
2. Восстановить все emoji из исходных файлов
3. Добавить недостающие импорты
4. Исправить опечатки
5. Завершить все незавершённые функции
