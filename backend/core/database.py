"""
backend/core/database.py
────────────────────────
Async SQLAlchemy engine, session factory, declarative base, and
LangGraph PostgresSaver checkpointer setup.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, MappedColumn
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool

from backend.core.config import settings

logger = logging.getLogger(__name__)

# ── Engine ─────────────────────────────────────────────────────────────────────

def _build_engine(pool_class=None) -> AsyncEngine:
    """Create the async SQLAlchemy engine with connection pooling."""
    kwargs: dict = {
        "echo": settings.DEBUG,
        "echo_pool": settings.DEBUG,
        "pool_pre_ping": True,
    }

    if pool_class is NullPool:
        # Used for Alembic migrations which need a fresh connection each time
        kwargs["poolclass"] = NullPool
    else:
        kwargs.update(
            {
                "pool_size": settings.DATABASE_POOL_SIZE,
                "max_overflow": settings.DATABASE_MAX_OVERFLOW,
                "pool_timeout": settings.DATABASE_POOL_TIMEOUT,
                "pool_recycle": settings.DATABASE_POOL_RECYCLE,
            }
        )

    engine = create_async_engine(settings.async_database_url, **kwargs)
    return engine


# Application-wide engine (pooled)
engine: AsyncEngine = _build_engine()

# Session factory — yields AsyncSession objects
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


# ── Declarative Base ───────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    """Project-wide declarative base.

    All ORM models inherit from this class.  The ``__tablename__`` is derived
    automatically from the class name (snake_case), but each model may
    override it.
    """

    pass


# ── Dependency ────────────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session per request.

    Usage::

        @router.get("/items")
        async def list_items(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Context-manager helper ────────────────────────────────────────────────────

@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for use outside of FastAPI request scope.

    Usage::

        async with get_db_context() as db:
            result = await db.execute(...)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Database lifecycle ────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create all tables defined in the ORM models.

    In production you should use Alembic migrations instead. This function
    is useful for tests and initial development setup.
    """
    # Import all models so their metadata is registered before create_all
    import backend.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified.")


async def drop_db() -> None:
    """Drop ALL tables – **destructive**, only use in tests."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("All database tables dropped.")


async def check_db_connection() -> bool:
    """Return True if the database is reachable."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("Database connection check failed: %s", exc)
        return False


async def close_db() -> None:
    """Dispose the engine connection pool on shutdown."""
    await engine.dispose()
    logger.info("Database engine disposed.")


# ── LangGraph PostgresSaver ────────────────────────────────────────────────────

class LangGraphCheckpointer:
    """Wrapper around LangGraph's PostgresSaver for async checkpoint storage.

    LangGraph uses checkpoints to persist agent state between steps, enabling
    pause-and-resume workflows (e.g., human-in-the-loop approval gates).
    """

    _instance: "LangGraphCheckpointer | None" = None
    _saver = None  # langgraph_checkpoint_postgres.PostgresSaver or compatible

    def __init__(self) -> None:
        self._saver = None

    @classmethod
    async def get_instance(cls) -> "LangGraphCheckpointer":
        if cls._instance is None:
            cls._instance = cls()
            await cls._instance._initialize()
        return cls._instance

    async def _initialize(self) -> None:
        """Set up the PostgresSaver against our database."""
        try:
            # langgraph-checkpoint-postgres uses psycopg (sync) under the hood.
            # We build a sync DSN for it while keeping our own async engine.
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            import psycopg

            conn_str = settings.sync_database_url.replace(
                "postgresql://", "postgres://"
            )
            conn = await psycopg.AsyncConnection.connect(conn_str, autocommit=True)
            self._saver = AsyncPostgresSaver(conn)
            await self._saver.setup()
            logger.info("LangGraph AsyncPostgresSaver initialised.")
        except ImportError:
            logger.warning(
                "langgraph-checkpoint-postgres not installed; "
                "falling back to MemorySaver for checkpointing."
            )
            from langgraph.checkpoint.memory import MemorySaver
            self._saver = MemorySaver()
        except Exception as exc:
            logger.error("LangGraph checkpointer init failed: %s", exc)
            from langgraph.checkpoint.memory import MemorySaver
            self._saver = MemorySaver()

    @property
    def saver(self):
        """Return the underlying saver object (pass directly to StateGraph)."""
        return self._saver


async def get_checkpointer():
    """FastAPI dependency / helper that returns the LangGraph checkpointer."""
    cp = await LangGraphCheckpointer.get_instance()
    return cp.saver
