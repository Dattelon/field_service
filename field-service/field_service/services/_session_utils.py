"""
Session management utilities for services.

This module provides a context manager that allows services to work
with both test-provided sessions (already in transaction) and production
sessions (need their own transaction).
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from field_service.db.session import SessionLocal


@asynccontextmanager
async def maybe_managed_session(
    session: Optional[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager that either uses provided session or creates a new one.

    If session is provided (typically from test fixtures), yields it as-is
    without starting a new transaction - the caller manages transactions.

    If session is None (production case), creates new session with automatic
    transaction management (commit on success, rollback on error).

    Args:
        session: Optional session from caller (typically test fixture)

    Yields:
        AsyncSession: Either the provided session or a new managed session

    Example:
        >>> async def my_service(session: Optional[AsyncSession] = None):
        ...     async with maybe_managed_session(session) as s:
        ...         # Work with s - no explicit commit/rollback needed
        ...         result = await s.execute(...)
        ...         return result.scalar_one()
    """
    if session is not None:
        # Test/external code manages transaction
        yield session
    else:
        # Production: create session with automatic transaction
        async with SessionLocal() as s:
            async with s.begin():
                yield s
