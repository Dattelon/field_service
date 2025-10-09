"""
Тесты для P1-13: Retry функциональность при ошибках

Проверяем:
1. RetryContext - сохранение/загрузка контекста
2. RetryMiddleware - перехват ошибок и показ UI
3. Retry handlers - обработка кнопок "Повторить" и "Отменить"
4. Лимит попыток (MAX_ATTEMPTS = 3)
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message, User, Chat

from field_service.bots.common.retry_context import (
    RetryContext,
    save_retry_context,
    load_retry_context,
    clear_retry_context,
)
from field_service.bots.common.retry_handler import retry_router
from field_service.bots.common.retry_middleware import RetryMiddleware


pytestmark = pytest.mark.asyncio


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def user():
    """Мок пользователя"""
    return User(id=123, is_bot=False, first_name="Test")


@pytest.fixture
def chat():
    """Мок чата"""
    return Chat(id=456, type="private")


@pytest.fixture
def message():
    """Мок сообщения"""
    msg = MagicMock()
    msg.message_id = 789
    msg.chat = MagicMock()
    msg.chat.id = 456
    msg.from_user = MagicMock()
    msg.from_user.id = 123
    msg.edit_text = AsyncMock()
    msg.answer = AsyncMock()
    return msg


@pytest.fixture
def callback(message):
    """Мок callback query"""
    # Используем spec=CallbackQuery чтобы isinstance работал
    from aiogram.types import CallbackQuery
    cb = MagicMock(spec=CallbackQuery)
    cb.id = "test_callback"
    cb.from_user = MagicMock()
    cb.from_user.id = 123
    cb.chat_instance = "test_instance"
    cb.data = "test:action"
    cb.message = message
    cb.answer = AsyncMock()
    cb.bot = MagicMock()
    return cb


@pytest.fixture
async def state():
    """FSM state для тестов"""
    storage = MemoryStorage()
    return FSMContext(
        storage=storage,
        key=MagicMock(
            user_id=123,
            chat_id=456,
            bot_id=789,
        ),
    )


# ============================================================================
# Тесты RetryContext
# ============================================================================

async def test_retry_context_creation():
    """Проверка создания RetryContext"""
    ctx = RetryContext(
        callback_data="test:action",
        timestamp=datetime.now(timezone.utc),
        attempt=1,
        user_id=123,
        chat_id=456,
        message_id=789,
    )
    
    assert ctx.callback_data == "test:action"
    assert ctx.attempt == 1
    assert ctx.user_id == 123
    assert ctx.can_retry() is True


async def test_retry_context_max_attempts():
    """Проверка лимита попыток"""
    ctx = RetryContext(
        callback_data="test:action",
        timestamp=datetime.now(timezone.utc),
        attempt=3,  # MAX_ATTEMPTS
        user_id=123,
        chat_id=456,
        message_id=789,
    )
    
    assert ctx.can_retry() is False


async def test_retry_context_serialization():
    """Проверка сериализации/десериализации"""
    original = RetryContext(
        callback_data="test:action",
        timestamp=datetime.now(timezone.utc),
        attempt=1,
        user_id=123,
        chat_id=456,
        message_id=789,
    )
    
    # Сериализация
    data = original.to_dict()
    assert isinstance(data, dict)
    assert data["callback_data"] == "test:action"
    
    # Десериализация
    restored = RetryContext.from_dict(data)
    assert restored.callback_data == original.callback_data
    assert restored.attempt == original.attempt
    assert restored.user_id == original.user_id


async def test_save_and_load_retry_context(state):
    """Проверка сохранения и загрузки контекста в FSM"""
    # Сохраняем
    await save_retry_context(
        state=state,
        callback_data="test:action",
        user_id=123,
        chat_id=456,
        message_id=789,
        attempt=1,
    )
    
    # Загружаем
    ctx = await load_retry_context(state)
    assert ctx is not None
    assert ctx.callback_data == "test:action"
    assert ctx.attempt == 1
    assert ctx.user_id == 123


async def test_clear_retry_context(state):
    """Проверка очистки контекста"""
    # Сохраняем
    await save_retry_context(
        state=state,
        callback_data="test:action",
        user_id=123,
        chat_id=456,
        message_id=789,
        attempt=1,
    )
    
    # Очищаем
    await clear_retry_context(state)
    
    # Проверяем что контекста больше нет
    ctx = await load_retry_context(state)
    assert ctx is None


# ============================================================================
# Тесты RetryMiddleware
# ============================================================================

async def test_retry_middleware_disabled(callback, state):
    """Проверка что middleware не вмешивается когда выключен"""
    middleware = RetryMiddleware(enabled=False)
    
    # Создаём handler который падает с ошибкой
    async def failing_handler(event, data):
        raise ValueError("Test error")
    
    # Вызываем middleware
    data = {"state": state}
    
    # Должно пробросить исключение т.к. middleware выключен
    with pytest.raises(ValueError):
        await middleware(failing_handler, callback, data)


async def test_retry_middleware_catches_error(callback, state):
    """Проверка что middleware перехватывает ошибки"""
    middleware = RetryMiddleware(enabled=True)
    
    # Создаём handler который падает с ошибкой
    async def failing_handler(event, data):
        raise ValueError("Test error")
    
    # Вызываем middleware
    data = {"state": state}
    result = await middleware(failing_handler, callback, data)
    
    # Middleware должен вернуть None (ошибка перехвачена, не проброшена)
    assert result is None
    
    # Должно сохраниться в state
    ctx = await load_retry_context(state)
    assert ctx is not None
    assert ctx.callback_data == "test:action"
    assert ctx.attempt == 1


async def test_retry_middleware_shows_error_ui(callback, state):
    """Проверка что middleware показывает UI с кнопками"""
    middleware = RetryMiddleware(enabled=True)
    
    # Создаём handler который падает с ошибкой
    async def failing_handler(event, data):
        raise ValueError("Test error")
    
    # Вызываем middleware
    data = {"state": state}
    await middleware(failing_handler, callback, data)
    
    # Проверяем что вызвался edit_text или answer
    assert callback.message.edit_text.called or callback.message.answer.called
    
    # Проверяем текст сообщения - должно быть "Не удалось выполнить действие"
    if callback.message.edit_text.called:
        call_kwargs = callback.message.edit_text.call_args.kwargs
        assert "Не удалось выполнить действие" in call_kwargs["text"]
    else:
        call_kwargs = callback.message.answer.call_args.kwargs
        assert "Не удалось выполнить действие" in call_kwargs["text"]


# ============================================================================
# Тесты Retry Handlers
# ============================================================================

async def test_retry_execute_no_context(callback, state):
    """Проверка retry:execute без сохранённого контекста"""
    callback.data = "retry:execute"
    
    # Находим handler
    handler = None
    for route in retry_router.callback_query.handlers:
        if hasattr(route.callback, "__name__") and route.callback.__name__ == "retry_execute":
            handler = route.callback
            break
    
    assert handler is not None
    
    # Вызываем handler
    await handler(callback, state)
    
    # Должен показать ошибку - callback.answer с позиционным аргументом
    callback.answer.assert_called_once()
    # Первый позиционный аргумент - это текст
    call_args = callback.answer.call_args
    assert len(call_args.args) > 0
    assert "Не удалось загрузить контекст" in call_args.args[0]


async def test_retry_execute_max_attempts_exceeded(callback, state):
    """Проверка retry:execute при превышении лимита попыток"""
    # Сохраняем контекст с MAX_ATTEMPTS попытками
    await save_retry_context(
        state=state,
        callback_data="original:action",
        user_id=123,
        chat_id=456,
        message_id=789,
        attempt=3,  # MAX_ATTEMPTS
    )
    
    callback.data = "retry:execute"
    
    # Находим handler
    handler = None
    for route in retry_router.callback_query.handlers:
        if hasattr(route.callback, "__name__") and route.callback.__name__ == "retry_execute":
            handler = route.callback
            break
    
    # Вызываем handler
    await handler(callback, state)
    
    # Должен показать ошибку о превышении лимита
    callback.answer.assert_called_once()
    call_args = callback.answer.call_args
    assert len(call_args.args) > 0
    assert "Превышено максимальное количество попыток" in call_args.args[0]


async def test_retry_cancel(callback, state):
    """Проверка retry:cancel"""
    # Сохраняем контекст
    await save_retry_context(
        state=state,
        callback_data="test:action",
        user_id=123,
        chat_id=456,
        message_id=789,
        attempt=1,
    )
    
    callback.data = "retry:cancel"
    
    # Находим handler
    handler = None
    for route in retry_router.callback_query.handlers:
        if hasattr(route.callback, "__name__") and route.callback.__name__ == "retry_cancel":
            handler = route.callback
            break
    
    assert handler is not None
    
    # Вызываем handler
    await handler(callback, state)
    
    # Должен очистить контекст
    ctx = await load_retry_context(state)
    assert ctx is None
    
    # Должен показать сообщение
    callback.message.edit_text.assert_called_once()
    assert "Действие отменено" in callback.message.edit_text.call_args[1]["text"]


# ============================================================================
# Интеграционные тесты
# ============================================================================

async def test_full_retry_flow(callback, state):
    """Интеграционный тест: ошибка -> retry -> успех"""
    middleware = RetryMiddleware(enabled=True)
    
    # Первая попытка - падает
    call_count = 0
    
    async def sometimes_failing_handler(event, data):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("First attempt failed")
        # Вторая попытка успешна
        return "success"
    
    # Первый вызов - ошибка, middleware перехватит и вернёт None
    data = {"state": state}
    result = await middleware(sometimes_failing_handler, callback, data)
    assert result is None  # Middleware перехватил ошибку
    assert call_count == 1
    
    # Проверяем что контекст сохранён
    ctx = await load_retry_context(state)
    assert ctx is not None
    assert ctx.attempt == 1
    
    # Увеличиваем счётчик попыток
    await save_retry_context(
        state=state,
        callback_data=ctx.callback_data,
        user_id=ctx.user_id,
        chat_id=ctx.chat_id,
        message_id=ctx.message_id,
        attempt=ctx.attempt + 1,
    )
    
    # Вторая попытка - успех
    result = await middleware(sometimes_failing_handler, callback, data)
    assert result == "success"
    assert call_count == 2


async def test_retry_context_increments_attempts(state):
    """Проверка что attempt увеличивается при каждом retry"""
    # Сохраняем начальный контекст
    await save_retry_context(
        state=state,
        callback_data="test:action",
        user_id=123,
        chat_id=456,
        message_id=789,
        attempt=1,
    )
    
    # Загружаем и увеличиваем
    ctx = await load_retry_context(state)
    assert ctx.attempt == 1
    
    # Сохраняем с увеличенным attempt
    await save_retry_context(
        state=state,
        callback_data=ctx.callback_data,
        user_id=ctx.user_id,
        chat_id=ctx.chat_id,
        message_id=ctx.message_id,
        attempt=ctx.attempt + 1,
    )
    
    # Проверяем
    ctx = await load_retry_context(state)
    assert ctx.attempt == 2
    assert ctx.can_retry() is True
    
    # Ещё раз
    await save_retry_context(
        state=state,
        callback_data=ctx.callback_data,
        user_id=ctx.user_id,
        chat_id=ctx.chat_id,
        message_id=ctx.message_id,
        attempt=ctx.attempt + 1,
    )
    
    ctx = await load_retry_context(state)
    assert ctx.attempt == 3
    assert ctx.can_retry() is False  # Достигнут лимит
