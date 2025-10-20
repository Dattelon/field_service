"""Патч для исправления ошибок в orders.py"""
import re

FILE_PATH = r"C:\ProjectF\field-service\field_service\bots\master_bot\handlers\orders.py"

def main():
    # Читаем файл
    with open(FILE_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Исправление 1: Сохранение master_id перед commit...")
    # 1. Добавляем сохранение master_id перед попыткой записи метрик
    content = content.replace(
        '    # ✅ STEP 4.1: Запись метрик распределения (ДО commit, но ошибки игнорируются)\n    _log.info("offer_accept: starting distribution_metrics recording for order=%s", order_id)\n    try:',
        '    # ✅ STEP 4.1: Запись метрик распределения (ДО commit, но ошибки игнорируются)\n    _log.info("offer_accept: starting distribution_metrics recording for order=%s", order_id)\n    \n    # 🔧 BUGFIX: Сохраняем master_id ДО коммита (чтобы избежать MissingGreenlet после commit)\n    master_id_for_metrics = master.id\n    \n    try:'
    )
    
    print("Исправление 2: Конвертация Enum в строку для category...")
    # 2. Исправляем передачу category (Enum → string)
    content = content.replace(
        '                    category=order_row.category,  # BUGFIX: Pass enum directly, not string',
        '                    category=order_row.category.value if hasattr(order_row.category, \'value\') else str(order_row.category),'
    )
    
    print("Исправление 3: Конвертация Enum в строку для order_type...")
    # 3. Исправляем передачу order_type (Enum → string)
    content = content.replace(
        '                    order_type=order_row.type,  # BUGFIX: Pass enum directly, not string',
        '                    order_type=order_row.type.value if hasattr(order_row.type, \'value\') else str(order_row.type),'
    )
    
    print("Исправление 4: Использование master_id_for_metrics...")
    # 4. Заменяем все master.id на master_id_for_metrics в блоке метрик
    content = re.sub(
        r'(insert\(m\.distribution_metrics\)\.values\(\s+order_id=order_id,\s+)master_id=master\.id,',
        r'\1master_id=master_id_for_metrics,',
        content
    )
    
    content = re.sub(
        r'preferred_master_used=\(master\.id == order_row\.preferred_master_id\)',
        r'preferred_master_used=(master_id_for_metrics == order_row.preferred_master_id)',
        content
    )
    
    content = re.sub(
        r'"distribution_metrics recorded: order=%s master=%s round=%s candidates=%s time=%ss",\s+order_id, master\.id,',
        r'"distribution_metrics recorded: order=%s master=%s round=%s candidates=%s time=%ss",\n                order_id, master_id_for_metrics,',
        content
    )
    
    print("Исправление 5: Добавление session.refresh(master) после commit...")
    # 5. Заменяем комментарий и добавляем refresh
    content = content.replace(
        '''    # ✅ BUGFIX: Сбрасываем кэш SQLAlchemy после commit
    # Без этого _render_offers будет читать устаревшие данные из кэша
    # BUGFIX: SQLAlchemy automatically refreshes data after commit
    # No need for expire_all() - it breaks async context''',
        '''    # 🔧 BUGFIX: После commit обновляем объект master из БД (вместо expire_all)
    # session.expire_all() приводит к MissingGreenlet ошибке при доступе к master.id
    _log.info("offer_accept: refreshing master after commit, master_id=%s", master_id_for_metrics)
    await session.refresh(master)
    _log.info("offer_accept: master refreshed successfully")'''
    )
    
    # Записываем обратно
    with open(FILE_PATH, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Файл успешно исправлен: {FILE_PATH}")
    print("\nВсе исправления применены:")
    print("  1. Сохранение master_id перед commit")
    print("  2. Конвертация category Enum → string")
    print("  3. Конвертация order_type Enum → string")
    print("  4. Использование master_id_for_metrics вместо master.id")
    print("  5. Добавление await session.refresh(master) после commit")

if __name__ == "__main__":
    main()
