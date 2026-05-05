"""FastAPI dependency injection — provides a shared MemBlocksClient instance."""

from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from memblocks import MemBlocksClient, MemBlocksConfig
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings


@lru_cache(maxsize=1)
def get_config() -> MemBlocksConfig:
    """Return (and cache) the MemBlocksConfig instance read from .env."""
    return MemBlocksConfig(llm_settings=LLMSettings(
                default=LLMTaskSettings(
                    provider="groq",
                    model="moonshotai/kimi-k2-instruct-0905"
                ),
                retrieval=LLMTaskSettings(
                    provider="groq",
                    model="openai/gpt-oss-20b"
                ),
                ps1_semantic_extraction=LLMTaskSettings(
                    provider="groq",
                    model="openai/gpt-oss-120b"
                ),
                ps2_conflict_resolution=LLMTaskSettings(
                    provider="groq",
                    model="moonshotai/kimi-k2-instruct-0905"
                ),
                core_memory_extraction=LLMTaskSettings(
                    provider="groq",
                    model="openai/gpt-oss-120b"
                ),
                recursive_summary=LLMTaskSettings(
                    provider="groq",
                    model="openai/gpt-oss-120b"
                ),
            )
    )


@lru_cache(maxsize=1)
def get_client() -> MemBlocksClient:
    """Return (and cache) the shared MemBlocksClient instance."""
    config = get_config()
    return MemBlocksClient(config)


__all__ = [
    "get_config",
    "get_client",
    "get_backend_config",
    "BackendConfig",
    "LLMConfig",
]
