"""
COVERAGE ANALYZER: Анализ покрытия E2E тестами
===============================================

Этот скрипт:
1. Анализирует какие модули/функции покрыты тестами
2. Генерирует детальный отчёт по покрытию
3. Выводит рекомендации что ещё протестировать
"""

import json
from pathlib import Path
from typing import Dict, List, Set
from datetime import datetime


class CoverageAnalyzer:
    """Анализатор покрытия функциональности"""
    
    def __init__(self):
        self.modules = {
            "FSM переходы": {
                "total": 50,
                "covered": set(),
                "states": [
                    "MainMenu", "OrderCreation:awaiting_address",
                    "OrderCreation:awaiting_time", "OrderCreation:awaiting_description",
                    "OrderCompletion:awaiting_amount", "Rating:awaiting_rating",
                    # ... и т.д.
                ]
            },
            "Автораспределение": {
                "total": 20,
                "covered": set(),
                "features": [
                    "Round 1 assignment", "Round 2 assignment",
                    "Escalation to admin", "SLA 120s check",
                    "Priority master selection", "Warranty priority",
                    # ...
                ]
            },
            "БД операции": {
                "total": 100,
                "covered": set(),
                "tables": [
                    "orders", "masters", "clients", "transactions",
                    "ratings", "order_assignment_attempts", "admin_queue",
                    # ...
                ]
            },
            "Финансы": {
                "total": 15,
                "covered": set(),
                "operations": [
                    "Commission 50%", "Commission 60% (overdue)",
                    "Commission 0% (warranty)", "Payout after 3h",
                    "No-show penalty", "Cancellation fee",
                    # ...
                ]
            },
            "Уведомления": {
                "total": 40,
                "covered": set(),
                "types": [
                    "Order created", "Master assigned", "Order completed",
                    "No-show alert", "Dispute notification",
                    # ...
                ]
            },
            "Админ функции": {
                "total": 25,
                "covered": set(),
                "features": [
                    "Queue management", "Manual assignment",
                    "Dispute resolution", "Master moderation",
                    "Financial reports", "Settings management",
                    # ...
                ]
            }
        }
    
    def analyze_test_logs(self, logs: List[Dict]):
        """Анализ логов тестов для определения покрытия"""
        
        for log in logs:
            log_type = log.get('type')
            
            # FSM переходы
            if log_type == 'fsm_transition':
                state = log.get('to')
                self.modules["FSM переходы"]["covered"].add(state)
            
            # БД операции
            elif log_type in ['db_write', 'db_read']:
                table = log.get('table')
                self.modules["БД операции"]["covered"].add(table)
            
            # Системные события (автораспределение)
            elif log_type == 'system_event':
                event = log.get('event', '')
                if 'autoassign' in event.lower() or 'round' in event.lower():
                    self.modules["Автораспределение"]["covered"].add(event)
            
            # Уведомления
            elif log_type == 'message_sent':
                text = log.get('text', '')
                if 'заказ' in text.lower():
                    self.modules["Уведомления"]["covered"].add("Order notification")
    
    def calculate_coverage(self) -> Dict[str, float]:
        """Расчёт процента покрытия по каждому модулю"""
        
        coverage = {}
        
        for module_name, module_data in self.modules.items():
            total = module_data['total']
            covered_count = len(module_data['covered'])
            
            # Примерный расчёт (можно улучшить)
            percentage = min(100, (covered_count / total * 100) if total > 0 else 0)
            coverage[module_name] = round(percentage, 2)
        
        return coverage
    
    def generate_report(self, output_file: str = "coverage_report.md"):
        """Генерация Markdown отчёта"""
        
        coverage = self.calculate_coverage()
        total_coverage = sum(coverage.values()) / len(coverage)
        
        report = f"""# 📊 E2E Coverage Report

**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Общее покрытие:** {total_coverage:.2f}%

---

## Покрытие по модулям

| Модуль | Покрытие | Прогресс |
|--------|----------|----------|
"""
        
        for module_name, percent in sorted(coverage.items(), key=lambda x: x[1], reverse=True):
            bar_length = int(percent / 2)  # 50 символов = 100%
            bar = "█" * bar_length + "░" * (50 - bar_length)
            
            status = "✅" if percent >= 80 else "⚠️" if percent >= 60 else "❌"
            
            report += f"| {status} {module_name} | {percent}% | `{bar}` |\n"
        
        report += f"""
---

## Детальный анализ

"""
        
        for module_name, module_data in self.modules.items():
            percent = coverage[module_name]
            covered = module_data['covered']
            
            report += f"""### {module_name} ({percent}%)

**Покрыто:** {len(covered)} элементов

**Примеры покрытых элементов:**
"""
            for item in list(covered)[:5]:
                report += f"- ✅ {item}\n"
            
            report += "\n"
        
        report += """
---

## Рекомендации

### ✅ Хорошо покрыто (>80%)
"""
        
        for module_name, percent in coverage.items():
            if percent >= 80:
                report += f"- **{module_name}**: {percent}% - Отлично!\n"
        
        report += """
### ⚠️ Требует внимания (60-80%)
"""
        
        for module_name, percent in coverage.items():
            if 60 <= percent < 80:
                report += f"- **{module_name}**: {percent}% - Добавить тесты\n"
        
        report += """
### ❌ Низкое покрытие (<60%)
"""
        
        for module_name, percent in coverage.items():
            if percent < 60:
                report += f"- **{module_name}**: {percent}% - **Критично!** Нужны тесты\n"
        
        report += """
---

## Следующие шаги

1. Добавить тесты для модулей с покрытием <80%
2. Покрыть граничные случаи
3. Добавить нагрузочные тесты
4. Протестировать обработку ошибок

---

*Сгенерировано автоматически скриптом coverage_analyzer.py*
"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        return output_file
    
    def print_summary(self):
        """Вывод краткой статистики в консоль"""
        
        coverage = self.calculate_coverage()
        total = sum(coverage.values()) / len(coverage)
        
        print("\n" + "="*80)
        print("📊 COVERAGE SUMMARY")
        print("="*80 + "\n")
        
        print(f"Общее покрытие: {total:.2f}%\n")
        
        for module_name, percent in sorted(coverage.items(), key=lambda x: x[1], reverse=True):
            bar = "█" * int(percent / 2) + "░" * (50 - int(percent / 2))
            status = "✅" if percent >= 80 else "⚠️" if percent >= 60 else "❌"
            print(f"{status} {module_name:25} [{bar}] {percent:5.1f}%")
        
        print("\n" + "="*80)


def analyze_from_test_results(results_file: str = "test_results.json"):
    """Анализ из файла результатов тестов"""
    
    analyzer = CoverageAnalyzer()
    
    if Path(results_file).exists():
        with open(results_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        # Анализируем логи из результатов
        for result in results:
            if result.get('status') == 'PASS':
                logs = result.get('logs', [])
                analyzer.analyze_test_logs(logs)
    
    # Выводим в консоль
    analyzer.print_summary()
    
    # Генерируем отчёт
    report_file = analyzer.generate_report()
    print(f"\n📄 Детальный отчёт сохранён: {report_file}\n")
    
    return analyzer


if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║   📊 COVERAGE ANALYZER                                               ║
║   Анализ покрытия E2E тестами                                        ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
""")
    
    analyzer = analyze_from_test_results()
    
    print("""
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║   ✅ АНАЛИЗ ЗАВЕРШЁН                                                 ║
║                                                                       ║
║   Следующие шаги:                                                    ║
║   1. Откройте coverage_report.md                                     ║
║   2. Добавьте тесты для модулей с низким покрытием                   ║
║   3. Перезапустите анализ после добавления тестов                    ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
""")
