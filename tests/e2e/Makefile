# Makefile для удобного запуска E2E тестов

.PHONY: help install test test-critical test-all test-scenario coverage report clean

# По умолчанию показываем help
.DEFAULT_GOAL := help

help: ## Показать справку
	@echo "════════════════════════════════════════════════════════════════"
	@echo "  🧪 E2E TESTS - Makefile Commands"
	@echo "════════════════════════════════════════════════════════════════"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""

install: ## Установить зависимости
	@echo "📦 Установка зависимостей..."
	pip install -r requirements.txt
	@echo "✅ Готово!"

test-critical: ## Запустить только критичные тесты (быстро)
	@echo "🚀 Запуск критичных тестов..."
	pytest -m critical -v --tb=short

test-all: ## Запустить все E2E тесты
	@echo "🚀 Запуск всех E2E тестов..."
	pytest -v --tb=short

test-scenario: ## Запустить конкретный сценарий (make test-scenario SCENARIO=1)
	@echo "🚀 Запуск сценария $(SCENARIO)..."
	pytest test_order_lifecycle_all_scenarios.py::test_scenario_$(SCENARIO)_* -v

test-additional: ## Запустить дополнительные сценарии (5-8)
	@echo "🚀 Запуск дополнительных сценариев..."
	pytest test_additional_scenarios.py -v

test-watch: ## Запуск в режиме наблюдения (перезапуск при изменениях)
	@echo "👀 Режим наблюдения..."
	pytest-watch -v

coverage: ## Запустить тесты с покрытием
	@echo "📊 Анализ покрытия..."
	pytest --cov --cov-report=html --cov-report=term
	@echo ""
	@echo "✅ HTML отчёт: htmlcov/index.html"

report: ## Сгенерировать HTML-отчёт
	@echo "📄 Генерация отчёта..."
	python run_all_tests.py
	@echo "✅ Отчёт: test_report.html"

quick: ## Быстрый старт (интерактивный)
	@echo "🎯 Быстрый старт..."
	python quick_start.py

clean: ## Очистить временные файлы
	@echo "🧹 Очистка..."
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	rm -f test_report.html
	rm -f report.html
	@echo "✅ Очищено!"

format: ## Форматировать код
	@echo "🎨 Форматирование кода..."
	black .
	isort .
	@echo "✅ Готово!"

lint: ## Проверить код
	@echo "🔍 Проверка кода..."
	flake8 .
	mypy . --ignore-missing-imports
	@echo "✅ Готово!"

ci: install test-critical coverage ## Запуск как в CI/CD
	@echo ""
	@echo "════════════════════════════════════════════════════════════════"
	@echo "  ✅ CI/CD проверки пройдены успешно!"
	@echo "════════════════════════════════════════════════════════════════"

# Примеры использования:
# make install          - Установить зависимости
# make test-critical    - Быстрая проверка (критичные тесты)
# make test-all         - Полный прогон всех тестов
# make test-scenario SCENARIO=1  - Запустить сценарий 1
# make coverage         - Тесты + покрытие
# make report           - Сгенерировать HTML отчёт
# make quick            - Интерактивный запуск
# make ci               - Полная CI/CD проверка
