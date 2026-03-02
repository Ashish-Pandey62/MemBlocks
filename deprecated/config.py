"""Application configuration using pydantic BaseSettings.

This centralizes environment configuration so modules import `settings` instead
of calling `os.getenv` or `load_dotenv` directly.
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

# Always resolve .env relative to this file's directory (project root),
# regardless of the current working directory at runtime.
_ENV_FILE = Path(__file__).resolve().parent / ".env"


class Settings(BaseSettings):
    """All application environment/settings live here.

    Fields map to environment variables. Use `Field(..., env=...)` to make the
    mapping explicit and robust across platforms.
    """

    groq_api_key: Optional[str] = Field(None, env="GROQ_API_KEY")
    gemini_api_key: Optional[str] = Field(None, env="GEMINI_API_KEY")
    mongodb_connection_string: Optional[str] = Field(
        None, env="MONGODB_CONNECTION_STRING"
    )
    ollama_base_url: Optional[str] = Field(
        "http://localhost:11434", env="OLLAMA_BASE_URL"
    )
    embeddings_model: Optional[str] = Field("nomic-embed-text", env="EMBEDDINGS_MODEL")
    # Qdrant defaults (used by demonstration scripts). These can be overridden
    # via env variables QDRANT_HOST, QDRANT_PORT, QDRANT_PREFER_GRPC.
    qdrant_host: str = Field("localhost", env="QDRANT_HOST")
    qdrant_port: int = Field(6333, env="QDRANT_PORT")
    qdrant_prefer_grpc: bool = Field(True, env="QDRANT_PREFER_GRPC")

    # LLM defaults
    llm_provider: str = Field(
        "groq",  # Options: "groq" or "gemini"
        env="LLM_PROVIDER",
    )
    llm_model: str = Field(
        "meta-llama/llama-4-maverick-17b-128e-instruct", # or "gemini-3-flash-preview"
        env="LLM_MODEL",
    )
    llm_convo_temperature: float = Field(0.7, env="LLM_CONVO_TEMPERATURE")
    llm_semantic_extraction_temperature: float = Field(
        0.0, env="LLM_SEMANTIC_EXTRACTION_TEMPERATURE"
    )
    llm_core_extraction_temperature: float = Field(
        0.0, env="LLM_CORE_EXTRACTION_TEMPERATURE"
    )
    llm_recursive_summary_gen_temperature: float = Field(
        0.3, env="LLM_RECURSIVE_SUMMARY_GEN_TEMPERATURE"
    )
    llm_memory_update_temperature: float = Field(
        default=0.0,  # Very low for deterministic conflict resolution
        env="LLM_MEMORY_UPDATE_TEMPERATURE",
    )

    # Arize (for monitoring) - optional, monitoring is skipped if not set
    arize_space_id: Optional[str] = Field(None, env="ARIZE_SPACE_ID")
    arize_api_key: Optional[str] = Field(None, env="ARIZE_API_KEY")
    arize_project_name: Optional[str] = Field("memBlocks", env="ARIZE_PROJECT_NAME")

    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8")


# Single configured settings instance to import from other modules
settings = Settings()


__all__ = ["settings", "Settings"]
