"""
AI-Driven SRS Generator — FastAPI application entry point.

Start the server:
    python -m app.main

Or with uvicorn directly:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Prerequisites:
    1. Copy .env.example to .env and fill in your values.
    2. docker compose up -d  (starts PostgreSQL)
    3. pip install -r requirements.txt
    4. (Optional) npm install -g @mermaid-js/mermaid-cli  (for strict Mermaid validation)
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager

# psycopg3 (and other async DB drivers) are incompatible with Windows'
# default ProactorEventLoop. Switch to SelectorEventLoop before any
# event-loop-dependent code is imported.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.db.checkpointer import managed_checkpointer
from app.graph.graph import build_graph
from app.rag.vectorstore import init_vectorstore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan handler.

    Startup:
        1. Initialise ChromaDB and seed regulatory documents.
        2. Open PostgreSQL connection pool and prepare LangGraph checkpointer.
        3. Compile the LangGraph workflow with the persistent checkpointer.

    Shutdown:
        4. Close the PostgreSQL connection pool gracefully.
    """
    logger.info("=== SRS Generator startup ===")

    # 1. Vector store — synchronous, fast
    logger.info("Initialising ChromaDB vector store …")
    init_vectorstore()

    # 2 & 3. Postgres checkpointer + graph compilation
    async with managed_checkpointer() as checkpointer:
        logger.info("Compiling LangGraph workflow …")
        app.state.graph = build_graph(checkpointer=checkpointer)
        logger.info("=== Server ready ===")
        yield

    # After yield — checkpointer pool is closed by managed_checkpointer
    logger.info("=== SRS Generator shutdown complete ===")


def create_app() -> FastAPI:
    settings = get_settings()
    cors_origins = settings.cors_origin_list
    allow_credentials = settings.cors_allow_credentials and "*" not in cors_origins

    application = FastAPI(
        title="AI-Driven SRS Generator",
        description=(
            "Automated Software Requirements Specification generator powered by "
            "LangGraph, FastAPI, and OpenRouter. Converts vague stakeholder ideas "
            "into IEEE 830-compliant SRS documents via recursive multi-agent elicitation."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — permissive by default for local dev; tighten for production
    application.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(router)

    @application.get("/health", tags=["meta"])
    async def health_check() -> dict:
        return {
            "status": "ok",
            "model": settings.model_name,
            "graph_ready": hasattr(application.state, "graph")
            and application.state.graph is not None,
        }

    return application


app = create_app()


if __name__ == "__main__":
    # Re-apply selector policy here too so it's active before any uvicorn
    # internals run (matters on Windows when started via `python -m app.main`).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_reload,
        reload_dirs=["app"],   # watch only backend source; ignore frontend build output
        log_level="info",
    )
