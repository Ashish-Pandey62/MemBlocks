"""Tests for MemBlocksConfig — no live infrastructure required."""

import pytest
from memblocks import MemBlocksConfig
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings


def test_default_instantiation():
    config = MemBlocksConfig()
    assert config is not None


def test_custom_field_values_are_preserved():
    config = MemBlocksConfig(
        MONGODB_DATABASE_NAME="my_db",
        QDRANT_HOST="qdrant.internal",
        QDRANT_PORT=6334,
        MEMORY_WINDOW=20,
    )
    assert config.mongodb_database_name == "my_db"
    assert config.qdrant_host == "qdrant.internal"
    assert config.qdrant_port == 6334
    assert config.memory_window_limit == 20


def test_semantic_collection_formats_block_id():
    config = MemBlocksConfig()
    result = config.semantic_collection("block_abc123")
    assert result == "block_abc123_semantic"


def test_resource_collection_formats_block_id():
    config = MemBlocksConfig()
    result = config.resource_collection("block_abc123")
    assert result == "block_abc123_resource"


def test_custom_collection_template():
    config = MemBlocksConfig(SEMANTIC_COLLECTION_TEMPLATE="sem_{block_id}_v2")
    assert config.semantic_collection("x") == "sem_x_v2"


def test_memory_window_defaults_are_positive():
    config = MemBlocksConfig()
    assert config.memory_window_limit > 0
    assert config.keep_last_n > 0
    assert config.keep_last_n < config.memory_window_limit


def test_retrieval_defaults():
    config = MemBlocksConfig()
    assert config.retrieval_final_top_k > 0
    assert config.retrieval_top_k_per_query > 0
    assert config.retrieval_enable_query_expansion is True
    assert config.retrieval_enable_sparse is True


def test_resolved_llm_settings_builds_from_flat_fields():
    config = MemBlocksConfig(LLM_PROVIDER_NAME="ollama", LLM_MODEL="llama3")
    settings = config.resolved_llm_settings
    assert isinstance(settings, LLMSettings)
    assert settings.default.provider == "ollama"
    assert settings.default.model == "llama3"


def test_resolved_llm_settings_returns_explicit_when_set():
    explicit = LLMSettings(
        default=LLMTaskSettings(provider="ollama", model="llama3", temperature=0.1)
    )
    config = MemBlocksConfig(llm_settings=explicit)
    assert config.resolved_llm_settings is explicit


def test_resolved_llm_settings_per_task_temperatures():
    config = MemBlocksConfig(
        LLM_PROVIDER_NAME="ollama",
        LLM_SEMANTIC_EXTRACTION_TEMPERATURE=0.0,
        LLM_CONVO_TEMPERATURE=0.8,
    )
    settings = config.resolved_llm_settings
    assert settings.for_task("conversation").temperature == 0.8
    assert settings.for_task("ps1_semantic_extraction").temperature == 0.0


def test_openrouter_fallback_models_list_parsing():
    config = MemBlocksConfig(
        OPENROUTER_FALLBACK_MODELS="model-a,model-b, model-c"
    )
    models = config.openrouter_fallback_models_list
    assert models == ["model-a", "model-b", "model-c"]


def test_openrouter_fallback_models_list_empty_when_not_set():
    config = MemBlocksConfig()
    assert config.openrouter_fallback_models_list == []
