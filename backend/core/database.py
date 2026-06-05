import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backend.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _normalize_url(url: str) -> str:
    """Force asyncpg driver and handle Supabase pooler usernames with dots."""
    from urllib.parse import urlparse, urlunparse, quote

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    parsed = urlparse(url)

    # Supabase pooler uses 'postgres.projectref' as username —
    # the dot can confuse some drivers, so we URL-encode the username.
    if parsed.username and "." in parsed.username:
        encoded_user = quote(parsed.username, safe="")
        # Rebuild netloc with encoded username
        if parsed.password:
            netloc = f"{encoded_user}:{parsed.password}@{parsed.hostname}"
        else:
            netloc = f"{encoded_user}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        url = urlunparse(parsed._replace(netloc=netloc))

    # Force asyncpg driver
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    return url


class Base(DeclarativeBase):
    pass


# Lazy engine — created on first use, never at import time.
# This prevents the app from crashing on startup if DATABASE_URL is
# missing or malformed (healthcheck still passes, app stays up).
_engine = None
_sessionmaker: Optional[async_sessionmaker] = None


def get_engine():
    global _engine
    url = _normalize_url(settings.database_url)
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    if _engine is None:
        logger.info("Creating database engine for: %s", url.split("@")[-1] if "@" in url else "unknown")
        _engine = create_async_engine(
            url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            echo=settings.debug,
            # pgbouncer (Supabase pooler, port 6543) does NOT support
            # prepared statements — disable asyncpg's statement cache.
            connect_args={
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            },
        )
        logger.info("Database engine created")
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
