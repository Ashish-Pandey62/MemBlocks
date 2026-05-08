"""MemBlocksConfig — library-level configuration.

A non-singleton Pydantic BaseSettings model. Users instantiate it directly:

    config = MemBlocksConfig()                 # reads from .env in cwd
    config = MemBlocksConfig(groq_api_key="…") # explicit values

Unlike the old root config.py (which used a hardcoded _ENV_FILE path and a
module-level singleton), this class:
- defaults env_file to ".env" (cwd-relative, works in any project)
- adds new fields required by the library (database_name, memory_window, etc.)
- is instantiated by the caller, never at import time

Per-task LLM configuration:
    Pass an ``LLMSettings`` instance to ``llm_settings`` to assign a different
    provider, model, and temperature to each task (PS1 extraction, PS2 conflict
    resolution, retrieval, core memory, summary, conversation).  When
    ``llm_settings`` is ``None`` the client auto-constructs it from the flat
    legacy fields below so existing code continues to work unchanged.

    from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings

    config = MemBlocksConfig(
        openrouter_api_key="...",
        llm_settings=LLMSettings(
            default=LLMTaskSettings(provider="openrouter",
                                    model="meta-llama/llama-4-maverick-17b-128e-instruct",
                                    temperature=0.0),
            retrieval=LLMTaskSettings(provider="groq",
                                      model="llama-3.1-8b-instant",
                                      temperature=0.4),
        ),
    )
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings


class MemBlocksConfig(BaseSettings):
    """All configuration for the memBlocks library.

    Values are read from environment variables or a .env file.
    Every field has a sensible default so the library works out-of-the-box
    against a local Docker Compose stack.
    """

    # -------------------------------------------------------------------------
    # LLM Configuration
    # -------------------------------------------------------------------------
    llm_provider_name: str = Field(
        "ollama",
        validation_alias="LLM_PROVIDER_NAME",
        description="LLM provider to use (e.g. 'groq', 'gemini')",
    )

    # Groq API
    groq_api_key: Optional[str] = Field(None, validation_alias="GROQ_API_KEY")

    # Google Gemini API
    gemini_api_key: Optional[str] = Field(None, validation_alias="GEMINI_API_KEY")

    # OpenRouter API
    openrouter_api_key: Optional[str] = Field(
        None, validation_alias="OPENROUTER_API_KEY"
    )

    # Cohere re-ranker API
    cohere_api_key: Optional[str] = Field(
        None,
        validation_alias="COHERE_API_KEY",
        description="API key for the Cohere re-ranker service.",
    )
    openrouter_fallback_models: Optional[str] = Field(
        None,
        validation_alias="OPENROUTER_FALLBACK_MODELS",
        description=(
            "Comma-separated fallback model IDs tried in order if the primary model fails. "
            "Example: anthropic/claude-3.5-sonnet,gryphe/mythomax-l2-13b"
        ),
    )
    openrouter_enable_thinking: bool = Field(
        False,
        validation_alias="OPENROUTER_ENABLE_THINKING",
        description="Enable extended thinking/reasoning for supported OpenRouter models.",
    )

    @property
    def openrouter_fallback_models_list(self) -> List[str]:
        """Parse the comma-separated fallback models string into a list."""
        if not self.openrouter_fallback_models:
            return []
        return [
            m.strip() for m in self.openrouter_fallback_models.split(",") if m.strip()
        ]

    llm_model: str = Field(
        "hf.co/unsloth/gemma-3n-E4B-it-GGUF:Q4_K_M",
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
    # Per-task LLM Settings (optional — overrides the flat fields above)
    # -------------------------------------------------------------------------
    llm_settings: Optional[LLMSettings] = Field(
        None,
        description=(
            "Per-task LLM configuration. When set, each task can use a "
            "different provider, model, and temperature. When None, the "
            "client auto-constructs LLMSettings from the flat fields above "
            "(llm_provider_name, llm_model, llm_*_temperature) so existing "
            "code continues to work unchanged."
        ),
    )

    @property
    def resolved_llm_settings(self) -> LLMSettings:
        """Return the effective ``LLMSettings``, constructing from flat fields if needed.

        When ``llm_settings`` is explicitly provided it is returned as-is.
        Otherwise a single ``LLMTaskSettings`` is built from the flat legacy
        fields and used as the ``default`` for all tasks, with per-task
        temperature overrides applied individually.

        This property is the single place ``MemBlocksClient`` reads from —
        services never touch the flat temperature fields directly.
        """
        if self.llm_settings is not None:
            return self.llm_settings

        # Build per-task settings from flat legacy fields
        def _make(temperature: float) -> LLMTaskSettings:
            return LLMTaskSettings(
                provider=self.llm_provider_name,
                model=self.llm_model,
                temperature=temperature,
                fallback_models=self.openrouter_fallback_models_list,
                enable_thinking=self.openrouter_enable_thinking,
            )

        return LLMSettings(
            default=_make(self.llm_convo_temperature),
            conversation=_make(self.llm_convo_temperature),
            ps1_semantic_extraction=_make(self.llm_semantic_extraction_temperature),
            ps2_conflict_resolution=_make(self.llm_memory_update_temperature),
            retrieval=_make(0.4),  # hardcoded default for query enhancement
            core_memory_extraction=_make(self.llm_core_extraction_temperature),
            recursive_summary=_make(self.llm_recursive_summary_gen_temperature),
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
    ollama_base_url_embeddings: str = Field(
        "http://localhost:11435", validation_alias="OLLAMA_BASE_URL_EMBEDDINGS"
    )
    ollama_keep_alive: str = Field(
        "10m",
        validation_alias="OLLAMA_KEEP_ALIVE",
        description=(
            "How long to keep Ollama models loaded in memory after last request. "
            "Duration string: '10s', '5m', '1h', or '-1' for unlimited."
        ),
    )
    embeddings_model: str = Field(
        "nomic-embed-text", validation_alias="EMBEDDINGS_MODEL"
    )
    sparse_embeddings_model: str = Field(
        "prithivida/Splade_PP_en_v1",
        validation_alias="SPARSE_EMBEDDINGS_MODEL",
        description="SPLADE model used by fastembed for sparse vector generation.",
    )

    # -------------------------------------------------------------------------
    # Memory pipeline behaviour
    # -------------------------------------------------------------------------
    memory_window_limit: int = Field(
        10,
        validation_alias="MEMORY_WINDOW",
        description="Number of messages to accumulate before triggering memory processing.",
    )
    keep_last_n: int = Field(
        4,
        validation_alias="KEEP_LAST_N",
        description="Messages kept in active context after the window is processed.",
    )

    # -------------------------------------------------------------------------
    # Retrieval Configuration
    # -------------------------------------------------------------------------
    retrieval_num_query_expansions: int = Field(
        3,
        validation_alias="RETRIEVAL_NUM_QUERY_EXPANSIONS",
        description="Number of expanded queries to generate for each original query.",
    )
    retrieval_num_hypothetical_paragraphs: int = Field(
        2,
        validation_alias="RETRIEVAL_NUM_HYPOTHETICAL_PARAGRAPHS",
        description="Number of hypothetical answer paragraphs to generate for each query.",
    )
    retrieval_top_k_per_query: int = Field(
        5,
        validation_alias="RETRIEVAL_TOP_K_PER_QUERY",
        description="Number of top results to retrieve per expanded query.",
    )
    retrieval_final_top_k: int = Field(
        10,
        validation_alias="RETRIEVAL_FINAL_TOP_K",
        description="Final number of results to return after re-ranking.",
    )
    retrieval_enable_query_expansion: bool = Field(
        True,
        validation_alias="RETRIEVAL_ENABLE_QUERY_EXPANSION",
        description="Enable query expansion with related terms.",
    )
    retrieval_enable_hypothetical_paragraphs: bool = Field(
        False,
        validation_alias="RETRIEVAL_ENABLE_HYPOTHETICAL_PARAGRAPHS",
        description="Enable hypothetical paragraph generation for retrieval.",
    )
    retrieval_enable_reranking: bool = Field(
        True,
        validation_alias="RETRIEVAL_ENABLE_RERANKING",
        description="Enable LLM-based re-ranking of retrieved results.",
    )
    retrieval_enable_sparse: bool = Field(
        True,
        validation_alias="RETRIEVAL_ENABLE_SPARSE",
        description=(
            "Enable SPLADE sparse vector hybrid search (dense + sparse via Qdrant RRF). "
            "When False, falls back to pure dense vector search."
        ),
    )

    # -------------------------------------------------------------------------
    # Arize (optional monitoring)
    # -------------------------------------------------------------------------
    arize_space_id: Optional[str] = Field(None, validation_alias="ARIZE_SPACE_ID")
    arize_api_key: Optional[str] = Field(None, validation_alias="ARIZE_API_KEY")
    arize_project_name: str = Field("memBlocks", validation_alias="ARIZE_PROJECT_NAME")

    # -------------------------------------------------------------------------
    # Clerk Authentication
    # -------------------------------------------------------------------------
    clerk_publishable_key: Optional[str] = Field(
        None, validation_alias="CLERK_PUBLISHABLE_KEY"
    )
    clerk_secret_key: Optional[str] = Field(None, validation_alias="CLERK_SECRET_KEY")

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
