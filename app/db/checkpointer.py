"""
PostgreSQL-backed LangGraph checkpointer using psycopg3's async connection pool.

Install prerequisite:
    pip install langgraph-checkpoint-postgres psycopg[binary,pool]

Usage (see app/main.py lifespan):
    async with managed_checkpointer(settings.db_uri) as checkpointer:
        graph = compile_graph(checkpointer)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def managed_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    """
    Async context manager that opens a psycopg3 connection pool, wires it to
    AsyncPostgresSaver, runs first-time schema setup, and tears down on exit.

    Yields:
        AsyncPostgresSaver: A ready-to-use LangGraph checkpointer.
    """
    settings = get_settings()

    # Convert SQLAlchemy-style URI to plain libpq URI expected by psycopg3.
    # e.g. "postgresql+psycopg://..." → "postgresql://..."
    db_uri = settings.db_uri.replace("postgresql+psycopg://", "postgresql://")

    logger.info("Opening async Postgres connection pool …")
    pool = AsyncConnectionPool(
        conninfo=db_uri,
        min_size=2,
        max_size=10,
        kwargs={"autocommit": True},  # Required: CREATE INDEX CONCURRENTLY cannot run in a transaction
        open=False,  # We open manually below so errors surface cleanly
    )
    await pool.open()

    try:
        checkpointer = AsyncPostgresSaver(pool)
        # Create LangGraph's internal checkpoint tables on first run.
        # This is idempotent — safe to call multiple times.
        await checkpointer.setup()
        logger.info("AsyncPostgresSaver ready.")
        yield checkpointer
    finally:
        logger.info("Closing Postgres connection pool …")
        await pool.close()
