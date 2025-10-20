"""Enhanced logging for Field Service project.

This module provides comprehensive logging across all layers:
- Request/Response tracking
- Database query logging
- Service call tracing
- Error context capture
"""
from __future__ import annotations

import functools
import logging
import time
import traceback
from typing import Any, Callable, TypeVar
from datetime import datetime

T = TypeVar('T')

# Create module logger
logger = logging.getLogger(__name__)


def log_function_call(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to log function entry, exit, duration and errors."""
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        func_name = f"{func.__module__}.{func.__qualname__}"
        start_time = time.time()
        
        # Log entry
        logger.info(f"[ENTER] {func_name}")
        logger.debug(f"[ARGS] {func_name} args={args}, kwargs={kwargs}")
        
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log success exit
            logger.info(f"[EXIT] {func_name} duration={duration:.3f}s")
            logger.debug(f"[RESULT] {func_name} result={result}")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Log error with full context
            logger.error(
                f"[ERROR] {func_name} failed after {duration:.3f}s",
                exc_info=True,
                extra={
                    "function": func_name,
                    "args": str(args),
                    "kwargs": str(kwargs),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc()
                }
            )
            raise
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        func_name = f"{func.__module__}.{func.__qualname__}"
        start_time = time.time()
        
        # Log entry
        logger.info(f"[ENTER] {func_name}")
        logger.debug(f"[ARGS] {func_name} args={args}, kwargs={kwargs}")
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            # Log success exit
            logger.info(f"[EXIT] {func_name} duration={duration:.3f}s")
            logger.debug(f"[RESULT] {func_name} result={result}")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            
            # Log error with full context
            logger.error(
                f"[ERROR] {func_name} failed after {duration:.3f}s",
                exc_info=True,
                extra={
                    "function": func_name,
                    "args": str(args),
                    "kwargs": str(kwargs),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "traceback": traceback.format_exc()
                }
            )
            raise
    
    # Return appropriate wrapper based on whether function is async
    import inspect
    if inspect.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper


def log_db_query(query: str, params: dict | None = None) -> None:
    """Log database query execution."""
    logger.debug(f"[DB_QUERY] {query}")
    if params:
        logger.debug(f"[DB_PARAMS] {params}")


def log_service_call(service: str, method: str, **context: Any) -> None:
    """Log service method call."""
    logger.info(f"[SERVICE] {service}.{method}")
    if context:
        logger.debug(f"[SERVICE_CONTEXT] {service}.{method} context={context}")


def log_callback_received(data: str, user_id: int) -> None:
    """Log callback query received."""
    logger.info(f"[CALLBACK] data={data} user_id={user_id}")


def log_message_received(text: str, user_id: int, chat_id: int) -> None:
    """Log message received."""
    logger.info(f"[MESSAGE] user={user_id} chat={chat_id} text={text[:100]}")


def log_state_transition(user_id: int, from_state: str | None, to_state: str | None) -> None:
    """Log FSM state transition."""
    logger.info(f"[FSM_STATE] user={user_id} from={from_state} to={to_state}")


def log_bot_action(action: str, **details: Any) -> None:
    """Log bot action (send message, edit message, etc)."""
    logger.info(f"[BOT_ACTION] {action}")
    if details:
        logger.debug(f"[BOT_DETAILS] {action} details={details}")


class LoggingContext:
    """Context manager for logging operations."""
    
    def __init__(self, operation: str, **context: Any):
        self.operation = operation
        self.context = context
        self.start_time: float | None = None
        
    async def __aenter__(self):
        self.start_time = time.time()
        logger.info(f"[START] {self.operation}")
        if self.context:
            logger.debug(f"[CONTEXT] {self.operation} context={self.context}")
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - (self.start_time or time.time())
        
        if exc_type is None:
            logger.info(f"[COMPLETE] {self.operation} duration={duration:.3f}s")
        else:
            logger.error(
                f"[FAILED] {self.operation} after {duration:.3f}s",
                exc_info=(exc_type, exc_val, exc_tb),
                extra={
                    "operation": self.operation,
                    "context": self.context,
                    "error_type": exc_type.__name__ if exc_type else None,
                    "error_message": str(exc_val) if exc_val else None,
                }
            )
        return False  # Don't suppress exceptions
    
    def __enter__(self):
        self.start_time = time.time()
        logger.info(f"[START] {self.operation}")
        if self.context:
            logger.debug(f"[CONTEXT] {self.operation} context={self.context}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - (self.start_time or time.time())
        
        if exc_type is None:
            logger.info(f"[COMPLETE] {self.operation} duration={duration:.3f}s")
        else:
            logger.error(
                f"[FAILED] {self.operation} after {duration:.3f}s",
                exc_info=(exc_type, exc_val, exc_tb),
                extra={
                    "operation": self.operation,
                    "context": self.context,
                    "error_type": exc_type.__name__ if exc_type else None,
                    "error_message": str(exc_val) if exc_val else None,
                }
            )
        return False  # Don't suppress exceptions


def setup_enhanced_logging(level: str = "INFO"):
    """Setup enhanced logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format='%(asctime)s %(levelname)-8s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Set specific loggers
    logging.getLogger("field_service").setLevel(logging.DEBUG)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
