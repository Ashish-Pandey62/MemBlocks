"""Integration test for hybrid (dense + sparse) semantic search.

Requires live MongoDB and Qdrant. Run with:
    uv run --package memblocks pytest -m integration -v

Or run directly as a script:
    uv run --package memblocks python tests/test_hybrid.py
"""

import asyncio
import os
import pytest
from datetime import datetime

os.environ["PYTHONIOENCODING"] = "utf-8"

from memblocks.client import MemBlocksClient
from memblocks.config import MemBlocksConfig
from memblocks.models.units import SemanticMemoryUnit, MemoryUnitMetaData


def _make_memories() -> list[SemanticMemoryUnit]:
    now = datetime.utcnow().isoformat()
    return [
        SemanticMemoryUnit(
            content="The user has a meeting in San Francisco regarding the new app delivery.",
            type="event",
            source="conversation",
            confidence=1.0,
            memory_time=now,
            updated_at=now,
            keywords=["san", "francisco", "app", "delivery"],
            entities=["san francisco", "app", "delivery"],
            embedding_text="The user has a meeting in San Francisco regarding the new app delivery. Keywords: san, francisco, app, delivery. Entities: san francisco, app, delivery",
            meta_data=MemoryUnitMetaData(usage=[], status="active", message_ids=[]),
        ),
        SemanticMemoryUnit(
            content="San Francisco is a city in California.",
            type="fact",
            source="conversation",
            confidence=1.0,
            memory_time=None,
            updated_at=now,
            keywords=["san", "francisco", "city", "california"],
            entities=["san francisco", "california"],
            embedding_text="San Francisco is a city in California. Keywords: san, francisco, city, california. Entities: san francisco, california",
            meta_data=MemoryUnitMetaData(usage=[], status="active", message_ids=[]),
        ),
        SemanticMemoryUnit(
            content="User deployed the application to production yesterday.",
            type="event",
            source="conversation",
            confidence=1.0,
            memory_time=now,
            updated_at=now,
            keywords=["deployed", "application", "production", "yesterday"],
            entities=["application", "production"],
            embedding_text="User deployed the application to production yesterday. Keywords: deployed, application, production, yesterday. Entities: application, production",
            meta_data=MemoryUnitMetaData(usage=[], status="active", message_ids=[]),
        ),
    ]


@pytest.mark.integration
async def test_hybrid_search_retrieves_relevant_memories():
    """Full pipeline: store memories, run hybrid search, verify relevant results returned."""
    config = MemBlocksConfig()
    client = MemBlocksClient(config)

    retrieval_events = []
    client.subscribe("on_memory_retrieved", lambda p: retrieval_events.append(p))

    try:
        await client.get_or_create_user("test_hybrid_user")

        # Always start fresh — delete existing block if present
        blocks = await client.get_user_blocks("test_hybrid_user")
        existing = next((b for b in blocks if b.name == "BM25 Hybrid Test Block"), None)
        if existing:
            await client.delete_block(existing.id, "test_hybrid_user")

        block = await client.create_block(
            user_id="test_hybrid_user", name="BM25 Hybrid Test Block"
        )
        assert block is not None
        assert block.id is not None

        for mem in _make_memories():
            await block._semantic.store(mem)

        # Run hybrid search
        context = await block.retrieve("Tell me about the app in San Francisco?")

        # Core assertions
        assert context is not None
        assert len(context.semantic) > 0, "Expected at least one semantic result"

        contents = [m.content for m in context.semantic]
        assert any("San Francisco" in c for c in contents), (
            "Expected San Francisco memory in results"
        )

        # Transparency assertions
        retrieval_log = client.get_retrieval_log().get_last_retrieval()
        assert retrieval_log is not None, "Expected retrieval log entry"
        assert retrieval_log.source is not None

        assert len(retrieval_events) > 0, "Expected on_memory_retrieved event to fire"

    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Standalone script entry point
# ---------------------------------------------------------------------------

async def _run():
    config = MemBlocksConfig()
    client = MemBlocksClient(config)

    client.subscribe(
        "on_memory_retrieved",
        lambda p: print(f"\n[Event Bus] Retrieved {p['num_results']} memories via {p['source']}"),
    )

    try:
        await client.get_or_create_user("test_hybrid_user")

        blocks = await client.get_user_blocks("test_hybrid_user")
        existing = next((b for b in blocks if b.name == "BM25 Hybrid Test Block"), None)
        if existing:
            await client.delete_block(existing.id, "test_hybrid_user")

        block = await client.create_block(
            user_id="test_hybrid_user", name="BM25 Hybrid Test Block"
        )
        print(f"Created block: {block.id}")

        for mem in _make_memories():
            await block._semantic.store(mem)

        print("\n--- Running Hybrid Search ---")
        context = await block.retrieve("Tell me about the app in San Francisco?")

        print("\n--- Retrieved Results ---")
        for mem in context.semantic:
            print(f"- {mem.content}")

        retrieval_log = client.get_retrieval_log().get_last_retrieval()
        print("\nLast Retrieval Source:", retrieval_log.source if retrieval_log else "None")
        print("Timestamp:", retrieval_log.timestamp if retrieval_log else "None")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(_run())
