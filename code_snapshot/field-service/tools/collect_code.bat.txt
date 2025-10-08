@echo off
REM Скрипт для сбора всех кодовых файлов проекта
REM Запускается из корня проекта: tools\collect_code.bat

echo ========================================
echo   Project Code Collector
echo ========================================
echo.

REM Проверка наличия Python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Please install Python 3.8+
    pause
    exit /b 1
)

echo [INFO] Running code collector...
echo.

REM Запуск скрипта с параметрами по умолчанию
python tools\collect_code.py --format markdown --output code_export.md

if %errorlevel% equ 0 (
    echo.
    echo ========================================
    echo   SUCCESS! Code exported to:
    echo   code_export.md
    echo ========================================
) else (
    echo.
    echo ========================================
    echo   ERROR: Collection failed!
    echo ========================================
)

echo.
pause
