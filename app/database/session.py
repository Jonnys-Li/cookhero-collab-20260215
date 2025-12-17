# app/database/session.py
"""
Async database session management for CookHero.
Provides session factory and dependency injection for FastAPI.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.database.models import Base

logger = logging.getLogger(__name__)

# Create async engine
_engine = create_async_engine(
    settings.database.postgres.async_url,
    pool_size=settings.database.postgres.pool_size,
    max_overflow=settings.database.postgres.max_overflow,
    pool_timeout=settings.database.postgres.pool_timeout,
    pool_recycle=settings.database.postgres.pool_recycle,
    echo=settings.database.postgres.echo,
)

# Create session factory
async_session_factory = async_sessionmaker(
    bind=_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Initialize database schema (create tables if not exist)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables initialized.")


async def close_db() -> None:
    """Close database connections."""
    await _engine.dispose()
    logger.info("Database connections closed.")


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency injection for async database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for manual session handling."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
