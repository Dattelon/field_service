from __future__ import annotations

import os
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine


# Ensure project root on sys.path and load .env
BASE_DIR = Path(__file__).resolve().parents[1]  # .../field-service
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:
    # dotenv is optional; ignore if unavailable
    pass

# Alembic Config object
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve DATABASE_URL from env, alembic.ini, or sane default
DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or config.get_main_option("sqlalchemy.url")
    or "postgresql+asyncpg://fs_user:fs_password@127.0.0.1:5439/field_service"
)

# Import metadata (models import ensures all tables are registered)
from field_service.db.base import metadata  # noqa: E402
from field_service.db import models  # noqa: F401,E402  (import for side effects)

target_metadata = metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        version_table="alembic_version",
        version_table_schema=None,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' async mode."""
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
        future=True,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
        version_table="alembic_version",
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
