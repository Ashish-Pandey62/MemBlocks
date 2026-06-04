"""Tests for Pydantic models — no live infrastructure required."""

import pytest
from datetime import datetime, timezone

from memblocks.models import (
    SemanticMemoryUnit,
    CoreMemoryUnit,
    ResourceMemoryUnit,
    MemoryBlock,
    MemoryBlockMetaData,
    RetrievalResult,
    MemoryOperation,
)
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings


# ---------------------------------------------------------------------------
# SemanticMemoryUnit
# ---------------------------------------------------------------------------

def test_semantic_memory_unit_instantiation():
    unit = SemanticMemoryUnit(
        content="User lives in Kathmandu",
        type="fact",
        confidence=0.9,
        memory_time=None,
        updated_at="2026-01-01T00:00:00",
    )
    assert unit.content == "User lives in Kathmandu"
    assert unit.type == "fact"
    assert unit.confidence == 0.9


def test_semantic_memory_unit_confidence_lower_bound():
    with pytest.raises(Exception):
        SemanticMemoryUnit(
            content="x", type="fact", confidence=-0.1,
            memory_time=None, updated_at="2026-01-01T00:00:00",
        )


def test_semantic_memory_unit_confidence_upper_bound():
    with pytest.raises(Exception):
        SemanticMemoryUnit(
            content="x", type="fact", confidence=1.1,
            memory_time=None, updated_at="2026-01-01T00:00:00",
        )


def test_semantic_memory_unit_optional_fields_default():
    unit = SemanticMemoryUnit(
        content="x", type="event", confidence=0.5,
        memory_time="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
    )
    assert unit.keywords == []
    assert unit.entities == []
    assert unit.memory_id is None


# ---------------------------------------------------------------------------
# CoreMemoryUnit
# ---------------------------------------------------------------------------

def test_core_memory_unit_instantiation():
    unit = CoreMemoryUnit(
        persona_content="You are a helpful assistant.",
        human_content="User is a software engineer.",
    )
    assert unit.persona_content == "You are a helpful assistant."
    assert unit.human_content == "User is a software engineer."


def test_core_memory_unit_empty_strings_allowed():
    unit = CoreMemoryUnit(persona_content="", human_content="")
    assert unit.persona_content == ""


# ---------------------------------------------------------------------------
# ResourceMemoryUnit
# ---------------------------------------------------------------------------

def test_resource_memory_unit_instantiation():
    unit = ResourceMemoryUnit(content="API docs", resource_type="document")
    assert unit.resource_type == "document"
    assert unit.resource_link is None


def test_resource_memory_unit_with_link():
    unit = ResourceMemoryUnit(
        content="Homepage",
        resource_type="link",
        resource_link="https://example.com",
    )
    assert unit.resource_link == "https://example.com"


# ---------------------------------------------------------------------------
# MemoryBlock
# ---------------------------------------------------------------------------

def _make_block(**kwargs) -> MemoryBlock:
    defaults = dict(
        meta_data=MemoryBlockMetaData(
            id="block_1",
            created_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            user_id="user_1",
        ),
        name="Work Memory",
        description="Work-related memories",
        semantic_collection="block_1_semantic",
        core_memory_block_id="block_1",
    )
    defaults.update(kwargs)
    return MemoryBlock(**defaults)


def test_memory_block_to_dict_from_dict_roundtrip():
    block = _make_block()
    d = block.to_dict()
    restored = MemoryBlock.from_dict(d)
    assert restored.name == block.name
    assert restored.description == block.description
    assert restored.semantic_collection == block.semantic_collection
    assert restored.core_memory_block_id == block.core_memory_block_id
    assert restored.meta_data.id == block.meta_data.id


def test_memory_block_touch_updates_timestamp():
    block = _make_block()
    original = block.meta_data.updated_at
    block.touch()
    assert block.meta_data.updated_at != original


def test_memory_block_optional_collections_none_by_default():
    block = _make_block(semantic_collection=None, core_memory_block_id=None)
    d = block.to_dict()
    assert d["semantic_collection"] is None
    assert d["core_memory_block_id"] is None


# ---------------------------------------------------------------------------
# RetrievalResult
# ---------------------------------------------------------------------------

def test_retrieval_result_empty_by_default():
    result = RetrievalResult()
    assert result.is_empty() is True
    assert result.to_prompt_string() == ""


def test_retrieval_result_with_core_memory_not_empty():
    result = RetrievalResult(
        core=CoreMemoryUnit(
            persona_content="You are helpful.",
            human_content="User is an engineer.",
        )
    )
    assert result.is_empty() is False


def test_retrieval_result_to_prompt_string_contains_core_content():
    result = RetrievalResult(
        core=CoreMemoryUnit(
            persona_content="You are helpful.",
            human_content="User is an engineer.",
        )
    )
    prompt = result.to_prompt_string()
    assert "You are helpful." in prompt
    assert "User is an engineer." in prompt
    assert "<Core Memory>" in prompt


def test_retrieval_result_to_prompt_string_contains_semantic_content():
    unit = SemanticMemoryUnit(
        content="User visited Nepal",
        type="event",
        confidence=0.9,
        memory_time="2026-01-01T00:00:00",
        updated_at="2026-01-01T00:00:00",
    )
    result = RetrievalResult(semantic=[unit])
    prompt = result.to_prompt_string()
    assert "User visited Nepal" in prompt
    assert "<Semantic Memories>" in prompt


def test_retrieval_result_empty_core_still_empty():
    result = RetrievalResult(
        core=CoreMemoryUnit(persona_content="", human_content="")
    )
    assert result.is_empty() is True


# ---------------------------------------------------------------------------
# MemoryOperation
# ---------------------------------------------------------------------------

def test_memory_operation_add():
    op = MemoryOperation(operation="ADD", content="new fact")
    assert op.operation == "ADD"
    assert op.memory_id is None


def test_memory_operation_update_has_old_content():
    op = MemoryOperation(
        operation="UPDATE",
        content="updated fact",
        old_content="old fact",
        memory_id="abc",
    )
    assert op.old_content == "old fact"
    assert op.memory_id == "abc"


def test_memory_operation_invalid_type():
    with pytest.raises(Exception):
        MemoryOperation(operation="REPLACE", content="x")


# ---------------------------------------------------------------------------
# LLMTaskSettings / LLMSettings
# ---------------------------------------------------------------------------

def test_llm_task_settings_instantiation():
    s = LLMTaskSettings(provider="groq", model="llama3-8b", temperature=0.3)
    assert s.provider == "groq"
    assert s.temperature == 0.3
    assert s.fallback_models == []
    assert s.enable_thinking is False


def test_llm_settings_for_task_falls_back_to_default():
    default = LLMTaskSettings(provider="ollama", model="llama3", temperature=0.0)
    settings = LLMSettings(default=default)
    assert settings.for_task("conversation") is default
    assert settings.for_task("ps1_semantic_extraction") is default
    assert settings.for_task("nonexistent_task") is default


def test_llm_settings_for_task_uses_override():
    default = LLMTaskSettings(provider="ollama", model="llama3", temperature=0.0)
    override = LLMTaskSettings(provider="groq", model="llama3-8b", temperature=0.4)
    settings = LLMSettings(default=default, retrieval=override)
    assert settings.for_task("retrieval") is override
    assert settings.for_task("conversation") is default
