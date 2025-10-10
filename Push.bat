@echo off
chcp 65001 > nul
echo ========================================
echo   Git Push to GitHub (main)
echo ========================================
echo.

REM Работаем из корневой директории проекта
cd /d C:\ProjectF

echo [1/4] Checking Git status...
git status
echo.

echo [2/4] Adding all changes...
git add .
echo.

echo [3/4] Creating commit...
set /p commit_msg="Enter commit message (or press Enter for auto): "

if "%commit_msg%"=="" (
    set commit_msg=update: auto commit %date% %time%
)

git commit -m "%commit_msg%"
echo.

echo [4/4] Pushing to GitHub (main)...
git push origin main
echo.

if %errorlevel% equ 0 (
    echo ========================================
    echo   SUCCESS! Changes pushed to GitHub
    echo ========================================
) else (
    echo ========================================
    echo   ERROR! Push failed
    echo ========================================
)

echo.
echo Press any key to close...
pause > nul
