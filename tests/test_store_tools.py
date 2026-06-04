"""Tests for MemBlocksClient provider validation and construction.

These tests verify that the client correctly validates LLM provider
configuration and raises clear errors before any network call is made.
All tests use mocks — no live MongoDB, Qdrant, or LLM required.
"""

import pytest
from unittest.mock import MagicMock

from memblocks import MemBlocksConfig
from memblocks.client import _build_provider
from memblocks.llm.task_settings import LLMTaskSettings


# ---------------------------------------------------------------------------
# _build_provider — error path validation
# ---------------------------------------------------------------------------

def _task(provider: str, model: str = "test-model") -> LLMTaskSettings:
    return LLMTaskSettings(provider=provider, model=model, temperature=0.0)


def test_build_provider_raises_for_unknown_provider():
    config = MemBlocksConfig()
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        _build_provider(_task("unknown_provider"), config)


def test_build_provider_raises_for_groq_without_api_key():
    config = MemBlocksConfig().model_copy(update={"groq_api_key": None})
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        _build_provider(_task("groq"), config)


def test_build_provider_raises_for_gemini_without_api_key():
    config = MemBlocksConfig()
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        _build_provider(_task("gemini"), config)


def test_build_provider_raises_for_openrouter_without_api_key():
    config = MemBlocksConfig().model_copy(update={"openrouter_api_key": None})
    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        _build_provider(_task("openrouter"), config)


# ---------------------------------------------------------------------------
# MemBlocksClient — construction with mocked infrastructure
# ---------------------------------------------------------------------------

def _make_mock_adapters():
    return MagicMock(), MagicMock(), MagicMock()


def test_client_constructs_with_ollama_and_mocked_adapters():
    """Client should construct without errors when using Ollama (no API key needed)."""
    from memblocks import MemBlocksClient

    config = MemBlocksConfig(LLM_PROVIDER_NAME="ollama", LLM_MODEL="llama3")
    mongo, embeddings, qdrant = _make_mock_adapters()

    client = MemBlocksClient(
        config,
        mongo_adapter=mongo,
        embedding_provider=embeddings,
        qdrant_adapter=qdrant,
    )
    assert client is not None
    assert client.config is config


def test_client_exposes_transparency_objects():
    from memblocks import MemBlocksClient
    from memblocks.services.transparency import (
        EventBus, OperationLog, RetrievalLog, ProcessingHistory, LLMUsageTracker,
    )

    config = MemBlocksConfig(LLM_PROVIDER_NAME="ollama", LLM_MODEL="llama3")
    mongo, embeddings, qdrant = _make_mock_adapters()
    client = MemBlocksClient(
        config, mongo_adapter=mongo, embedding_provider=embeddings, qdrant_adapter=qdrant
    )

    assert isinstance(client.event_bus, EventBus)
    assert isinstance(client.operation_log, OperationLog)
    assert isinstance(client.retrieval_log, RetrievalLog)
    assert isinstance(client.processing_history, ProcessingHistory)
    assert isinstance(client.llm_usage, LLMUsageTracker)


def test_client_subscribe_and_unsubscribe():
    from memblocks import MemBlocksClient

    config = MemBlocksConfig(LLM_PROVIDER_NAME="ollama", LLM_MODEL="llama3")
    mongo, embeddings, qdrant = _make_mock_adapters()
    client = MemBlocksClient(
        config, mongo_adapter=mongo, embedding_provider=embeddings, qdrant_adapter=qdrant
    )

    received = []
    callback = lambda data: received.append(data)

    client.subscribe("on_memory_stored", callback)
    client.event_bus.publish("on_memory_stored", {"test": True})
    assert received == [{"test": True}]

    client.unsubscribe("on_memory_stored", callback)
    client.event_bus.publish("on_memory_stored", {"test": False})
    assert len(received) == 1  # no new event after unsubscribe


def test_client_llm_alias_matches_conversation_llm():
    from memblocks import MemBlocksClient

    config = MemBlocksConfig(LLM_PROVIDER_NAME="ollama", LLM_MODEL="llama3")
    mongo, embeddings, qdrant = _make_mock_adapters()
    client = MemBlocksClient(
        config, mongo_adapter=mongo, embedding_provider=embeddings, qdrant_adapter=qdrant
    )

    assert client.llm is client.conversation_llm
