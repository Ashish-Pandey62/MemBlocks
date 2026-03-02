import asyncio
import os
import sys

os.environ["PYTHONIOENCODING"] = "utf-8"

from datetime import datetime
from memblocks.client import MemBlocksClient
from memblocks.config import MemBlocksConfig
from memblocks.models.units import SemanticMemoryUnit, MemoryUnitMetaData


async def run_test():
    print("Initializing Config and Client...")
    config = MemBlocksConfig()

    client = MemBlocksClient(config)

    def log_retrieval(payload):
        print(
            f"\n[Transparency Event Bus] Retrieved {payload['num_results']} memories via {payload['source']}"
        )

    client.subscribe("on_memory_retrieved", log_retrieval)

    try:
        user = await client.get_or_create_user("test_hybrid_user")

        blocks = await client.get_user_blocks("test_hybrid_user")
        block = next((b for b in blocks if b.name == "BM25 Hybrid Test Block"), None)

        if not block:
            block = await client.create_block(
                user_id="test_hybrid_user", name="BM25 Hybrid Test Block"
            )
            print(f"Created new block: {block.id}")

            print("Storing test memories...")
            memories = [
                SemanticMemoryUnit(
                    content="The user has a meeting in San Francisco regarding the new app delivery.",
                    type="event",
                    source="conversation",
                    confidence=1.0,
                    memory_time=datetime.utcnow().isoformat(),
                    updated_at=datetime.utcnow().isoformat(),
                    keywords=["san", "francisco", "app", "delivery"],
                    entities=["san francisco", "app", "delivery"],
                    embedding_text="The user has a meeting in San Francisco regarding the new app delivery. Keywords: san, francisco, app, delivery. Entities: san francisco, app, delivery",
                    meta_data=MemoryUnitMetaData(
                        usage=[], status="active", Parent_Memory_ids=[], message_ids=[]
                    ),
                ),
                SemanticMemoryUnit(
                    content="San Francisco is a city in California.",
                    type="fact",
                    source="conversation",
                    confidence=1.0,
                    memory_time=None,
                    updated_at=datetime.utcnow().isoformat(),
                    keywords=["san", "francisco", "city", "california"],
                    entities=["san francisco", "california"],
                    embedding_text="San Francisco is a city in California. Keywords: san, francisco, city, california. Entities: san francisco, california",
                    meta_data=MemoryUnitMetaData(
                        usage=[], status="active", Parent_Memory_ids=[], message_ids=[]
                    ),
                ),
                SemanticMemoryUnit(
                    content="User deployed the application to production yesterday.",
                    type="event",
                    source="conversation",
                    confidence=1.0,
                    memory_time=datetime.utcnow().isoformat(),
                    updated_at=datetime.utcnow().isoformat(),
                    keywords=["deployed", "application", "production", "yesterday"],
                    entities=["application", "production"],
                    embedding_text="User deployed the application to production yesterday. Keywords: deployed, application, production, yesterday. Entities: application, production",
                    meta_data=MemoryUnitMetaData(
                        usage=[], status="active", Parent_Memory_ids=[], message_ids=[]
                    ),
                ),
            ]

            for mem in memories:
                await block._semantic.store(mem)
        else:
            print(f"Using existing block: {block.id}")
            await client.delete_block(block.id, "test_hybrid_user")
            block = await client.create_block(
                user_id="test_hybrid_user", name="BM25 Hybrid Test Block"
            )
            print(f"Recreated block: {block.id}")
            print("Storing test memories...")
            memories = [
                SemanticMemoryUnit(
                    content="The user has a meeting in San Francisco regarding the new app delivery.",
                    type="event",
                    source="conversation",
                    confidence=1.0,
                    memory_time=datetime.utcnow().isoformat(),
                    updated_at=datetime.utcnow().isoformat(),
                    keywords=["san", "francisco", "app", "delivery"],
                    entities=["san francisco", "app", "delivery"],
                    embedding_text="The user has a meeting in San Francisco regarding the new app delivery. Keywords: san, francisco, app, delivery. Entities: san francisco, app, delivery",
                    meta_data=MemoryUnitMetaData(
                        usage=[], status="active", Parent_Memory_ids=[], message_ids=[]
                    ),
                ),
                SemanticMemoryUnit(
                    content="San Francisco is a city in California.",
                    type="fact",
                    source="conversation",
                    confidence=1.0,
                    memory_time=None,
                    updated_at=datetime.utcnow().isoformat(),
                    keywords=["san", "francisco", "city", "california"],
                    entities=["san francisco", "california"],
                    embedding_text="San Francisco is a city in California. Keywords: san, francisco, city, california. Entities: san francisco, california",
                    meta_data=MemoryUnitMetaData(
                        usage=[], status="active", Parent_Memory_ids=[], message_ids=[]
                    ),
                ),
                SemanticMemoryUnit(
                    content="User deployed the application to production yesterday.",
                    type="event",
                    source="conversation",
                    confidence=1.0,
                    memory_time=datetime.utcnow().isoformat(),
                    updated_at=datetime.utcnow().isoformat(),
                    keywords=["deployed", "application", "production", "yesterday"],
                    entities=["application", "production"],
                    embedding_text="User deployed the application to production yesterday. Keywords: deployed, application, production, yesterday. Entities: application, production",
                    meta_data=MemoryUnitMetaData(
                        usage=[], status="active", Parent_Memory_ids=[], message_ids=[]
                    ),
                ),
            ]
            for mem in memories:
                await block._semantic.store(mem)

        print("\n--- Running Hybrid Search Test ---")
        context = await block.retrieve("Tell me about the app in San Francisco?")

        print("\n--- Retrieved Results ---")
        for mem in context.semantic:
            print(f"- {mem.content}")

        print("\n--- Checking Transparency Logs explicitly ---")
        retrieval_log = client.get_retrieval_log().get_last_retrieval()
        print(
            "Last Retrieval Log Source:",
            retrieval_log.source if retrieval_log else "None",
        )
        print("Time:", retrieval_log.timestamp if retrieval_log else "None")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(run_test())
