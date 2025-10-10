import os
import asyncio
import logging
from datetime import datetime
from functools import wraps
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from dotenv import load_dotenv
import paramiko

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
SERVER_HOST = os.getenv("SERVER_HOST")
SERVER_USER = os.getenv("SERVER_USER")
SERVER_PASSWORD = os.getenv("SERVER_PASSWORD")
PROJECT_PATH = "/opt/field-service"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# SSH клиент
def ssh_execute(command: str, timeout: int = 30) -> tuple[str, int]:
    """Выполнить команду на сервере через SSH"""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(SERVER_HOST, username=SERVER_USER, password=SERVER_PASSWORD, timeout=10)
        
        stdin, stdout, stderr = ssh.exec_command(command, timeout=timeout)
        output = stdout.read().decode('utf-8', errors='ignore')
        error = stderr.read().decode('utf-8', errors='ignore')
        exit_code = stdout.channel.recv_exit_status()
        
        ssh.close()
        
        result = output + error if error else output
        return result.strip(), exit_code
    except Exception as e:
        return f"❌ SSH Error: {str(e)}", 1

# Проверка доступа (ИСПРАВЛЕНО - добавлен @wraps)
def check_admin(func):
    @wraps(func)
    async def wrapper(message_or_callback, **kwargs):
        user_id = message_or_callback.from_user.id
        if user_id != ADMIN_ID:
            if isinstance(message_or_callback, Message):
                await message_or_callback.answer("❌ Access denied")
            else:
                await message_or_callback.answer("❌ Access denied", show_alert=True)
            return
        return await func(message_or_callback, **kwargs)
    return wrapper

# Главное меню
def main_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton(text="📊 Статус", callback_data="status"),
            InlineKeyboardButton(text="📋 Логи", callback_data="logs")
        ],
        [
            InlineKeyboardButton(text="▶️ Запустить", callback_data="start"),
            InlineKeyboardButton(text="⏸️ Остановить", callback_data="stop")
        ],
        [
            InlineKeyboardButton(text="🔄 Перезапустить", callback_data="restart"),
            InlineKeyboardButton(text="🏥 Здоровье", callback_data="health")
        ],
        [
            InlineKeyboardButton(text="🚀 Деплой", callback_data="deploy_confirm"),
        ],
        [
            InlineKeyboardButton(text="🔄 Git Pull + Деплой", callback_data="git_deploy_confirm"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Меню деплоя
def deploy_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="⚠️ Подтвердить деплой", callback_data="deploy_execute")],
        [InlineKeyboardButton(text="« Назад", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Меню Git деплоя
def git_deploy_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(text="⚠️ Подтвердить Git Pull + Деплой", callback_data="git_deploy_execute")],
        [InlineKeyboardButton(text="« Назад", callback_data="menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# Команда /start
@dp.message(Command("start"))
@check_admin
async def cmd_start(message: Message, **kwargs):
    await message.answer(
        "🤖 <b>Field Service Control Bot</b>\n\n"
        "Управление ботами на продакшн сервере:\n"
        f"📍 Сервер: {SERVER_HOST}\n"
        f"📁 Проект: {PROJECT_PATH}\n\n"
        "Выберите действие:",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )

# Обработчик кнопок
@dp.callback_query(F.data == "menu")
@check_admin
async def show_menu(callback: CallbackQuery, **kwargs):
    await callback.message.edit_text(
        "🤖 <b>Field Service Control Bot</b>\n\n"
        "Выберите действие:",
        reply_markup=main_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

# Статус
@dp.callback_query(F.data == "status")
@check_admin
async def show_status(callback: CallbackQuery, **kwargs):
    await callback.answer("⏳ Получаю статус...")
    
    cmd = f"cd {PROJECT_PATH} && docker compose ps --format json"
    output, _ = ssh_execute(cmd)
    
    # Парсим статус
    status_text = "📊 <b>Статус контейнеров:</b>\n\n"
    
    try:
        import json
        containers = [json.loads(line) for line in output.strip().split('\n') if line]
        for c in containers:
            name = c.get('Service', 'unknown')
            state = c.get('State', 'unknown')
            emoji = "✅" if state == "running" else "❌"
            status_text += f"{emoji} <code>{name}</code>: {state}\n"
    except:
        status_text += f"<pre>{output[:500]}</pre>"
    
    await callback.message.edit_text(
        status_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="status")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )

# Логи
@dp.callback_query(F.data == "logs")
@check_admin
async def show_logs_menu(callback: CallbackQuery, **kwargs):
    keyboard = [
        [
            InlineKeyboardButton(text="Admin Bot", callback_data="logs_admin"),
            InlineKeyboardButton(text="Master Bot", callback_data="logs_master")
        ],
        [InlineKeyboardButton(text="« Назад", callback_data="menu")]
    ]
    await callback.message.edit_text(
        "📋 <b>Логи ботов</b>\n\nВыберите бота:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("logs_"))
@check_admin
async def show_logs(callback: CallbackQuery, **kwargs):
    service = callback.data.split("_")[1]
    await callback.answer(f"⏳ Загружаю логи {service}-bot...")
    
    cmd = f"cd {PROJECT_PATH} && docker compose logs {service}-bot --tail=30"
    output, _ = ssh_execute(cmd, timeout=15)
    
    # Обрезаем если слишком длинный
    if len(output) > 3500:
        output = output[-3500:]
    
    await callback.message.edit_text(
        f"📋 <b>Логи {service}-bot (последние 30 строк):</b>\n\n"
        f"<pre>{output}</pre>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data=f"logs_{service}")],
            [InlineKeyboardButton(text="« Назад", callback_data="logs")]
        ]),
        parse_mode="HTML"
    )

# Запуск
@dp.callback_query(F.data == "start")
@check_admin
async def start_bots(callback: CallbackQuery, **kwargs):
    await callback.answer("⏳ Запускаю боты...")
    
    cmd = f"cd {PROJECT_PATH} && docker compose up -d admin-bot master-bot"
    output, exit_code = ssh_execute(cmd, timeout=30)
    
    emoji = "✅" if exit_code == 0 else "❌"
    await callback.message.edit_text(
        f"{emoji} <b>Запуск ботов</b>\n\n<pre>{output[:1000]}</pre>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Проверить статус", callback_data="status")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )

# Остановка
@dp.callback_query(F.data == "stop")
@check_admin
async def stop_bots(callback: CallbackQuery, **kwargs):
    await callback.answer("⏳ Останавливаю боты...")
    
    cmd = f"cd {PROJECT_PATH} && docker compose stop admin-bot master-bot"
    output, exit_code = ssh_execute(cmd, timeout=30)
    
    emoji = "✅" if exit_code == 0 else "❌"
    await callback.message.edit_text(
        f"{emoji} <b>Остановка ботов</b>\n\n<pre>{output[:1000]}</pre>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Проверить статус", callback_data="status")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )

# Перезапуск
@dp.callback_query(F.data == "restart")
@check_admin
async def restart_bots(callback: CallbackQuery, **kwargs):
    await callback.answer("⏳ Перезапускаю боты...")
    
    cmd = f"cd {PROJECT_PATH} && docker compose restart admin-bot master-bot"
    output, exit_code = ssh_execute(cmd, timeout=45)
    
    emoji = "✅" if exit_code == 0 else "❌"
    await callback.message.edit_text(
        f"{emoji} <b>Перезапуск ботов</b>\n\n<pre>{output[:1000]}</pre>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Проверить статус", callback_data="status")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )

# Здоровье
@dp.callback_query(F.data == "health")
@check_admin
async def show_health(callback: CallbackQuery, **kwargs):
    await callback.answer("⏳ Проверяю здоровье...")
    
    commands = {
        "Containers": f"cd {PROJECT_PATH} && docker compose ps",
        "Disk": "df -h | grep -E '(Filesystem|/dev/)' | head -3",
        "Memory": "free -h | head -2",
        "Heartbeat": f"cd {PROJECT_PATH} && docker compose logs --since 5m | grep 'alive' | tail -3"
    }
    
    health_text = "🏥 <b>Здоровье сервера:</b>\n\n"
    
    for name, cmd in commands.items():
        output, _ = ssh_execute(cmd, timeout=10)
        health_text += f"<b>{name}:</b>\n<pre>{output[:300]}</pre>\n\n"
    
    if len(health_text) > 3500:
        health_text = health_text[:3500] + "..."
    
    await callback.message.edit_text(
        health_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="health")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )

# Деплой - подтверждение
@dp.callback_query(F.data == "deploy_confirm")
@check_admin
async def deploy_confirm(callback: CallbackQuery, **kwargs):
    await callback.message.edit_text(
        "🚀 <b>Деплой на продакшн</b>\n\n"
        "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        "Это запустит полный деплой:\n"
        "• Создание бэкапа БД\n"
        "• Загрузка нового кода\n"
        "• Сборка Docker образов\n"
        "• Применение миграций\n"
        "• Перезапуск ботов\n\n"
        "Это займёт 3-5 минут.\n\n"
        "Продолжить?",
        reply_markup=deploy_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

# Деплой - выполнение
@dp.callback_query(F.data == "deploy_execute")
@check_admin
async def deploy_execute(callback: CallbackQuery, **kwargs):
    await callback.answer()
    await callback.message.edit_text(
        "🚀 <b>Запускаю деплой...</b>\n\n"
        "⏳ Это займёт несколько минут.\n"
        "Пожалуйста, подождите...",
        parse_mode="HTML"
    )
    
    deploy_steps = [
        ("Создание бэкапа", "/usr/local/bin/field-service-backup.sh daily"),
        ("Проверка статуса", f"cd {PROJECT_PATH} && docker compose ps"),
        ("Сборка образов", f"cd {PROJECT_PATH} && docker compose build"),
        ("Применение миграций", f"cd {PROJECT_PATH} && docker compose run --rm admin-bot alembic upgrade head"),
        ("Перезапуск", f"cd {PROJECT_PATH} && docker compose up -d --no-deps admin-bot master-bot"),
    ]
    
    result_text = "🚀 <b>Результат деплоя:</b>\n\n"
    
    for step_name, cmd in deploy_steps:
        result_text += f"⏳ {step_name}...\n"
        await callback.message.edit_text(result_text, parse_mode="HTML")
        
        timeout = 300 if "build" in cmd.lower() else 120
        output, exit_code = ssh_execute(cmd, timeout=timeout)
        
        emoji = "✅" if exit_code == 0 else "❌"
        result_text = result_text.replace(f"⏳ {step_name}...", f"{emoji} {step_name}")
        
        if exit_code != 0:
            result_text += f"\n\n❌ <b>Ошибка:</b>\n<pre>{output[:500]}</pre>"
            break
    
    result_text += "\n\n"
    result_text += "✅ Деплой завершён!" if exit_code == 0 else "❌ Деплой завершился с ошибками"
    
    await callback.message.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Проверить статус", callback_data="status")],
            [InlineKeyboardButton(text="📋 Посмотреть логи", callback_data="logs")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )

# Git Деплой - подтверждение
@dp.callback_query(F.data == "git_deploy_confirm")
@check_admin
async def git_deploy_confirm(callback: CallbackQuery, **kwargs):
    await callback.message.edit_text(
        "🔄 <b>Git Pull + Деплой на продакшн</b>\n\n"
        "⚠️ <b>ВНИМАНИЕ!</b>\n\n"
        "Это запустит полный деплой с обновлением из GitHub:\n"
        "• Git pull (получение последнего кода)\n"
        "• Создание бэкапа БД\n"
        "• Сборка Docker образов\n"
        "• Применение миграций\n"
        "• Перезапуск ботов\n\n"
        "Это займёт 3-5 минут.\n\n"
        "Продолжить?",
        reply_markup=git_deploy_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

# Git Деплой - выполнение
@dp.callback_query(F.data == "git_deploy_execute")
@check_admin
async def git_deploy_execute(callback: CallbackQuery, **kwargs):
    await callback.answer()
    await callback.message.edit_text(
        "🔄 <b>Запускаю Git Pull + Деплой...</b>\n\n"
        "⏳ Это займёт несколько минут.\n"
        "Пожалуйста, подождите...",
        parse_mode="HTML"
    )
    
    deploy_steps = [
        ("Git Pull", f"cd {PROJECT_PATH} && git fetch origin main && git reset --hard origin/main"),
        ("Восстановление .env", f"cp /tmp/field-service.env.backup {PROJECT_PATH}/.env"),
        ("Создание бэкапа", "/usr/local/bin/field-service-backup.sh daily"),
        ("Проверка статуса", f"cd {PROJECT_PATH} && docker compose ps"),
        ("Сборка образов", f"cd {PROJECT_PATH} && docker compose build"),
        ("Применение миграций", f"cd {PROJECT_PATH} && docker compose run --rm admin-bot alembic upgrade head"),
        ("Перезапуск", f"cd {PROJECT_PATH} && docker compose up -d --no-deps admin-bot master-bot"),
    ]
    
    result_text = "🔄 <b>Результат Git Pull + Деплоя:</b>\n\n"
    
    for step_name, cmd in deploy_steps:
        result_text += f"⏳ {step_name}...\n"
        await callback.message.edit_text(result_text, parse_mode="HTML")
        
        timeout = 300 if "build" in cmd.lower() else 120
        output, exit_code = ssh_execute(cmd, timeout=timeout)
        
        emoji = "✅" if exit_code == 0 else "❌"
        result_text = result_text.replace(f"⏳ {step_name}...", f"{emoji} {step_name}")
        
        if exit_code != 0:
            result_text += f"\n\n❌ <b>Ошибка:</b>\n<pre>{output[:500]}</pre>"
            break
    
    result_text += "\n\n"
    result_text += "✅ Git Pull + Деплой завершён!" if exit_code == 0 else "❌ Деплой завершился с ошибками"
    
    await callback.message.edit_text(
        result_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Проверить статус", callback_data="status")],
            [InlineKeyboardButton(text="📋 Посмотреть логи", callback_data="logs")],
            [InlineKeyboardButton(text="« Назад", callback_data="menu")]
        ]),
        parse_mode="HTML"
    )

# Запуск бота
async def main():
    logger.info("🤖 Control Bot starting...")
    logger.info(f"👤 Admin ID: {ADMIN_ID}")
    logger.info(f"🖥️ Server: {SERVER_HOST}")
    logger.info(f"📁 Project: {PROJECT_PATH}")
    
    try:
        logger.info("Initializing bot and dispatcher...")
        logger.info(f"Bot token: {BOT_TOKEN[:20]}...")
        
        # Проверяем что бот валидный
        bot_info = await bot.get_me()
        logger.info(f"✅ Bot connected: @{bot_info.username} ({bot_info.first_name})")
        
        logger.info("Starting polling...")
        await dp.start_polling(bot, skip_updates=True)
        
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        logger.info("=" * 50)
        logger.info("CONTROL BOT INITIALIZING")
        logger.info("=" * 50)
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
