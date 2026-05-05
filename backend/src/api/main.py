"""FastAPI application factory for the memBlocks backend."""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import APIRouter

from backend.src.api.routers import auth, blocks, chat, memory, transparency, users
from backend.src.api.dependencies import get_client


def setup_logging():
    """Configure logging for memblocks to output to both file and console."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "memblocks.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    memblocks_logger = logging.getLogger("memblocks")
    memblocks_logger.setLevel(logging.DEBUG)
    memblocks_logger.addHandler(file_handler)
    memblocks_logger.addHandler(console_handler)

    logging.getLogger("memblocks.storage").setLevel(logging.DEBUG)
    logging.getLogger("memblocks.services").setLevel(logging.DEBUG)
    logging.getLogger("memblocks.llm").setLevel(logging.DEBUG)

    return memblocks_logger


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan: startup and graceful shutdown."""
    # Eagerly initialise the client so connection errors surface at startup.
    get_client()
    yield
    # Graceful shutdown — close MongoDB connections.
    client = get_client()
    await client.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="memBlocks API",
        description="Intelligent memory management system for LLMs",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_router = APIRouter(prefix="/api")
    api_router.include_router(auth.router)
    api_router.include_router(users.router)
    api_router.include_router(blocks.router)
    api_router.include_router(chat.router)
    api_router.include_router(memory.router)
    api_router.include_router(transparency.router)

    app.include_router(api_router)

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.src.api.main:app", host="0.0.0.0", port=8001, reload=True)
