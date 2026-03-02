"""MemBlocksConfig — library-level configuration.

A non-singleton Pydantic BaseSettings model. Users instantiate it directly:

    config = MemBlocksConfig()                 # reads from .env in cwd
    config = MemBlocksConfig(groq_api_key="…") # explicit values

Unlike the old root config.py (which used a hardcoded _ENV_FILE path and a
module-level singleton), this class:
- defaults env_file to ".env" (cwd-relative, works in any project)
- adds new fields required by the library (database_name, memory_window, etc.)
- is instantiated by the caller, never at import time
"""

from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MemBlocksConfig(BaseSettings):
    """All configuration for the memBlocks library.

    Values are read from environment variables or a .env file.
    Every field has a sensible default so the library works out-of-the-box
    against a local Docker Compose stack.
    """

    # -------------------------------------------------------------------------
    # LLM (Groq)
    # -------------------------------------------------------------------------
    llm_provider_name: str = Field(
        "groq", validation_alias="LLM_PROVIDER_NAME", description="LLM provider to use (e.g. 'groq')"
    ) #TODO: support multiple providers in the future, not just Groq — this field is a starting point for that.
    
    groq_api_key: Optional[str] = Field(None, validation_alias="GROQ_API_KEY")
    llm_model: str = Field(
        "meta-llama/llama-4-maverick-17b-128e-instruct",
        validation_alias="LLM_MODEL",
    )
    llm_convo_temperature: float = Field(0.7, validation_alias="LLM_CONVO_TEMPERATURE")
    llm_semantic_extraction_temperature: float = Field(
        0.0, validation_alias="LLM_SEMANTIC_EXTRACTION_TEMPERATURE"
    )
    llm_core_extraction_temperature: float = Field(
        0.0, validation_alias="LLM_CORE_EXTRACTION_TEMPERATURE"
    )
    llm_recursive_summary_gen_temperature: float = Field(
        0.3, validation_alias="LLM_RECURSIVE_SUMMARY_GEN_TEMPERATURE"
    )
    llm_memory_update_temperature: float = Field(
        0.0, validation_alias="LLM_MEMORY_UPDATE_TEMPERATURE"
    )

    # -------------------------------------------------------------------------
    # MongoDB
    # -------------------------------------------------------------------------
    mongodb_connection_string: Optional[str] = Field(
        None, validation_alias="MONGODB_CONNECTION_STRING"
    )
    mongodb_database_name: str = Field(
        "memblocks_v2", validation_alias="MONGODB_DATABASE_NAME"
    )
    # MongoDB collection names
    mongo_collection_users: str = Field(
        "users", validation_alias="MONGO_COLLECTION_USERS"
    )
    mongo_collection_blocks: str = Field(
        "memory_blocks", validation_alias="MONGO_COLLECTION_BLOCKS"
    )
    mongo_collection_core_memories: str = Field(
        "core_memories", validation_alias="MONGO_COLLECTION_CORE_MEMORIES"
    )

    # -------------------------------------------------------------------------
    # Qdrant
    # -------------------------------------------------------------------------
    qdrant_host: str = Field("localhost", validation_alias="QDRANT_HOST")
    qdrant_port: int = Field(6333, validation_alias="QDRANT_PORT")
    qdrant_prefer_grpc: bool = Field(True, validation_alias="QDRANT_PREFER_GRPC")

    # Qdrant collection name templates (formatted with block_id at runtime)
    semantic_collection_template: str = Field(
        "{block_id}_semantic", validation_alias="SEMANTIC_COLLECTION_TEMPLATE"
    )
    resource_collection_template: str = Field(
        "{block_id}_resource", validation_alias="RESOURCE_COLLECTION_TEMPLATE"
    )

    # -------------------------------------------------------------------------
    # Ollama / Embeddings
    # -------------------------------------------------------------------------
    ollama_base_url: str = Field(
        "http://localhost:11434", validation_alias="OLLAMA_BASE_URL"
    )
    embeddings_model: str = Field(
        "nomic-embed-text", validation_alias="EMBEDDINGS_MODEL"
    )
    sparse_embeddings_model: str = Field(
        "prithivida/Splade_PP_en_v1", validation_alias="SPARSE_EMBEDDINGS_MODEL"
    )

    # -------------------------------------------------------------------------
    # Memory pipeline behaviour
    # -------------------------------------------------------------------------
    memory_window: int = Field(
        10,
        validation_alias="MEMORY_WINDOW",
        description="Number of messages to accumulate before triggering memory processing.",
    )
    keep_last_n: int = Field(
        5,
        validation_alias="KEEP_LAST_N",
        description="Messages kept in active context after the window is processed.",
    )
    max_concurrent_processing: int = Field(
        3,
        validation_alias="MAX_CONCURRENT_PROCESSING",
        description="Maximum number of concurrent background memory processing tasks.",
    )

    # -------------------------------------------------------------------------
    # Arize (optional monitoring)
    # -------------------------------------------------------------------------
    arize_space_id: Optional[str] = Field(None, validation_alias="ARIZE_SPACE_ID")
    arize_api_key: Optional[str] = Field(None, validation_alias="ARIZE_API_KEY")
    arize_project_name: str = Field("memBlocks", validation_alias="ARIZE_PROJECT_NAME")

    # -------------------------------------------------------------------------
    # Pydantic settings config
    # -------------------------------------------------------------------------
    model_config = SettingsConfigDict(
        env_file=".env",  # cwd-relative; works from any project root
        env_file_encoding="utf-8",
        populate_by_name=True,  # allow field name as well as alias
        extra="ignore",  # silently ignore unknown env vars
    )

    def semantic_collection(self, block_id: str) -> str:
        """Return the Qdrant collection name for a block's semantic memories."""
        return self.semantic_collection_template.format(block_id=block_id)

    def resource_collection(self, block_id: str) -> str:
        """Return the Qdrant collection name for a block's resource memories."""
        return self.resource_collection_template.format(block_id=block_id)


__all__ = ["MemBlocksConfig"]
