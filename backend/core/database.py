import logging
from typing import AsyncGenerator, Optional
from urllib.parse import urlparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    pass


# Lazy engine — created on first use, never at import time.
_engine = None
_sessionmaker: Optional[async_sessionmaker] = None


def _build_engine():
    """Build the async engine, handling Supabase pooler usernames with dots."""
    raw_url = settings.database_url
    if not raw_url:
        raise RuntimeError("DATABASE_URL is not set")

    parsed = urlparse(raw_url)
    username = parsed.username or "postgres"
    password = parsed.password or ""
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    database = parsed.path.lstrip("/") or "postgres"

    # Build SQLAlchemy URL with explicit user/password to avoid dot-parsing issues.
    # asyncpg connect_args override whatever SQLAlchemy parses from the URL.
    sa_url = f"postgresql+asyncpg://x:x@{host}:{port}/{database}"

    logger.info("Creating database engine for: %s:%s/%s (user=%s)", host, port, database, username)

    return create_async_engine(
        sa_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        echo=settings.debug,
        connect_args={
            "user": username,
            "password": password,
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        },
    )


def get_engine():
    global _engine
    if _engine is None:
        _engine = _build_engine()
    return _engine


def get_sessionmaker() -> async_sessionmaker:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _sessionmaker


# Backwards-compatible alias used across the codebase
class _LazySessionLocal:
    """Proxy so `AsyncSessionLocal()` works without eager engine creation."""
    def __call__(self):
        return get_sessionmaker()()


AsyncSessionLocal = _LazySessionLocal()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency — yields a DB session per request."""
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def ping_db() -> bool:
    """Health check — returns True if DB is reachable. Never raises."""
    try:
        session = get_sessionmaker()()
        try:
            await session.execute(text("SELECT 1"))
        finally:
            await session.close()
        return True
    except Exception as exc:
        logger.warning("DB ping failed: %s", exc)
        return False
