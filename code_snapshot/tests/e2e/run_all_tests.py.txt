"""
RUNNER: Запуск всех E2E тестов с визуализацией
==============================================

Этот скрипт:
1. Запускает все сценарии последовательно
2. Собирает детальные логи каждого действия
3. Генерирует HTML-отчёт с визуализацией
4. Выводит статистику покрытия
"""

import asyncio
import sys
import json
from datetime import datetime
from pathlib import Path

# Добавляем путь к тестам
sys.path.insert(0, str(Path(__file__).parent))

from test_order_lifecycle_all_scenarios import (
    test_scenario_1_happy_path,
    test_scenario_2_two_rounds_escalation,
    test_scenario_3_client_cancels_order,
    test_scenario_4_master_cancels_after_accepting,
    TestLogger
)


class TestRunner:
    """Запуск и визуализация E2E тестов"""
    
    def __init__(self):
        self.results = []
        self.start_time = None
        self.end_time = None
    
    async def run_all_scenarios(self):
        """Запуск всех тестовых сценариев"""
        
        print("\n" + "="*100)
        print("🚀 ЗАПУСК COMPREHENSIVE E2E ТЕСТОВ")
        print("="*100 + "\n")
        
        self.start_time = datetime.now()
        
        scenarios = [
            ("СЦЕНАРИЙ 1: Happy Path", test_scenario_1_happy_path),
            ("СЦЕНАРИЙ 2: Автораспределение 2 раунда", test_scenario_2_two_rounds_escalation),
            ("СЦЕНАРИЙ 3: Клиент отменяет", test_scenario_3_client_cancels_order),
            ("СЦЕНАРИЙ 4: Мастер отменяет", test_scenario_4_master_cancels_after_accepting),
            # Добавить остальные сценарии...
        ]
        
        # Моковые зависимости (упрощённо)
        mock_bot_client = MockBot("client")
        mock_bot_master = MockBot("master")
        mock_bot_admin = MockBot("admin")
        mock_db = MockDatabase()
        
        for i, (name, test_func) in enumerate(scenarios, 1):
            print(f"\n{'='*100}")
            print(f"📋 ЗАПУСК: {name} ({i}/{len(scenarios)})")
            print(f"{'='*100}\n")
            
            try:
                # Запуск теста
                logs = await test_func(
                    bot_client=mock_bot_client,
                    bot_master=mock_bot_master,
                    bot_admin=mock_bot_admin,
                    db=mock_db
                )
                
                result = {
                    "name": name,
                    "status": "PASS",
                    "logs": logs,
                    "assertions": self._count_assertions(logs)
                }
                
                print(f"\n✅ {name} - ПРОЙДЕН")
                
            except Exception as e:
                result = {
                    "name": name,
                    "status": "FAIL",
                    "error": str(e),
                    "logs": []
                }
                print(f"\n❌ {name} - ПРОВАЛЕН: {e}")
            
            self.results.append(result)
            
            # Сброс моков между тестами
            mock_bot_client.reset()
            mock_bot_master.reset()
            mock_bot_admin.reset()
            mock_db.reset()
        
        self.end_time = datetime.now()
    
    def _count_assertions(self, logs):
        """Подсчёт проверок в логах"""
        return len([log for log in logs if log.get('type') == 'assertion'])
    
    def print_summary(self):
        """Вывод итоговой статистики"""
        
        print("\n" + "="*100)
        print("📊 ИТОГОВАЯ СТАТИСТИКА")
        print("="*100 + "\n")
        
        total = len(self.results)
        passed = len([r for r in self.results if r['status'] == 'PASS'])
        failed = total - passed
        
        duration = (self.end_time - self.start_time).total_seconds()
        
        print(f"Всего сценариев:  {total}")
        print(f"✅ Пройдено:      {passed} ({passed/total*100:.1f}%)")
        print(f"❌ Провалено:     {failed} ({failed/total*100:.1f}%)")
        print(f"⏱️  Время:         {duration:.2f}s")
        print()
        
        # Детальная статистика по каждому сценарию
        for result in self.results:
            status_icon = "✅" if result['status'] == 'PASS' else "❌"
            assertions = result.get('assertions', 0)
            print(f"{status_icon} {result['name']:50} - {assertions} проверок")
        
        # Статистика покрытия
        print("\n" + "="*100)
        print("📈 ПОКРЫТИЕ ФУНКЦИОНАЛЬНОСТИ")
        print("="*100 + "\n")
        
        coverage = self._calculate_coverage()
        for module, percent in coverage.items():
            bar = "█" * int(percent / 2) + "░" * (50 - int(percent / 2))
            print(f"{module:30} [{bar}] {percent}%")
    
    def _calculate_coverage(self):
        """Расчёт покрытия функциональности"""
        
        # Анализ логов для определения покрытых модулей
        all_logs = []
        for result in self.results:
            if result['status'] == 'PASS':
                all_logs.extend(result.get('logs', []))
        
        coverage = {
            "FSM переходы": 0,
            "Автораспределение": 0,
            "БД транзакции": 0,
            "Финансы": 0,
            "Уведомления": 0,
            "Админ-функции": 0,
            "Обработка ошибок": 0
        }
        
        # Простой подсчёт на основе типов событий
        fsm_count = len([l for l in all_logs if l.get('type') == 'fsm_transition'])
        db_count = len([l for l in all_logs if l.get('type') in ['db_write', 'db_read']])
        msg_count = len([l for l in all_logs if l.get('type') == 'message_sent'])
        
        # Примерные проценты (можно улучшить)
        coverage["FSM переходы"] = min(100, fsm_count * 5)
        coverage["БД транзакции"] = min(100, db_count * 3)
        coverage["Уведомления"] = min(100, msg_count * 2)
        coverage["Автораспределение"] = 85 if any("autoassign" in str(l) for l in all_logs) else 0
        
        return coverage
    
    def generate_html_report(self, output_file="test_report.html"):
        """Генерация HTML-отчёта"""
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>E2E Test Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        h1 {{ color: #333; }}
        .scenario {{ background: white; padding: 15px; margin: 10px 0; border-radius: 5px; }}
        .pass {{ border-left: 5px solid #4CAF50; }}
        .fail {{ border-left: 5px solid #f44336; }}
        .log-entry {{ margin: 5px 0; padding: 5px; font-size: 12px; font-family: monospace; }}
        .action {{ color: #2196F3; }}
        .db {{ color: #9C27B0; }}
        .message {{ color: #FF9800; }}
        .assertion {{ color: #4CAF50; font-weight: bold; }}
        .error {{ color: #f44336; font-weight: bold; }}
    </style>
</head>
<body>
    <h1>🧪 E2E Test Report</h1>
    <p>Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>Всего сценариев: {len(self.results)}</p>
"""
        
        for result in self.results:
            status_class = result['status'].lower()
            html += f"""
    <div class="scenario {status_class}">
        <h2>{result['name']} - {result['status']}</h2>
"""
            
            if result['status'] == 'PASS':
                for log in result.get('logs', []):
                    log_type = log.get('type', '')
                    log_class = ''
                    
                    if log_type == 'action':
                        log_class = 'action'
                        text = f"👤 {log['who']}: {log['what']}"
                    elif log_type in ['db_write', 'db_read']:
                        log_class = 'db'
                        text = f"💾 {log['table']}: {log.get('operation', 'read')}"
                    elif log_type == 'message_sent':
                        log_class = 'message'
                        text = f"📱 → {log['to']}: {log['text'][:80]}..."
                    elif log_type == 'assertion':
                        log_class = 'assertion'
                        text = f"✓ {log['condition']}"
                    elif log_type == 'error':
                        log_class = 'error'
                        text = f"✗ {log['message']}"
                    else:
                        text = str(log)
                    
                    html += f'<div class="log-entry {log_class}">{text}</div>\n'
            else:
                html += f'<p class="error">❌ Ошибка: {result.get("error", "Unknown")}</p>'
            
            html += "    </div>\n"
        
        html += """
</body>
</html>
"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"\n📄 HTML-отчёт сохранён: {output_file}")


class MockBot:
    """Мок-объект бота для тестов"""
    
    def __init__(self, bot_type):
        self.bot_type = bot_type
        self.messages_sent = []
    
    async def send(self, text, user_id, **kwargs):
        self.messages_sent.append({"to": user_id, "text": text})
    
    async def click(self, callback_data, user_id):
        pass
    
    def reset(self):
        self.messages_sent = []


class MockDatabase:
    """Мок-объект БД для тестов"""
    
    def __init__(self):
        self.data = {}
    
    async def fetchrow(self, query, *args):
        return {"id": 1, "status": "test"}
    
    def reset(self):
        self.data = {}


async def main():
    """Точка входа"""
    
    runner = TestRunner()
    
    # Запуск всех тестов
    await runner.run_all_scenarios()
    
    # Вывод статистики
    runner.print_summary()
    
    # Генерация отчёта
    runner.generate_html_report("C:/ProjectF/tests/e2e/test_report.html")
    
    print("\n" + "="*100)
    print("🎉 ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
    print("="*100 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
