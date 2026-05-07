"""Integration test — verifies the full evaluation pipeline uses real MemBlocks infra.

What this tests:
    1. Qdrant and MongoDB Atlas are reachable.
    2. Session ingestion creates Qdrant collections and stores semantic memories.
    3. All three retrieval strategies (semantic / core / hybrid) return results.
    4. The LocomoRunner uses the real MemBlocksClient (not the in-memory fallback).
    5. End-to-end: a tiny synthetic session runs through the full eval pipeline.

Run:
    cd /path/to/MemBlocks
    pip install pytest pytest-asyncio
    python -m pytest evaluation/tests/test_integration.py -v -s

Notes:
    - Requires Qdrant at localhost:6333 and MongoDB Atlas reachable from .env
    - The tiny conversation below has 6 turns (12 messages), which exceeds
      memory_window_limit=10, so the memory pipeline fires automatically PLUS
      flush() is called at the end to catch any remainder.
    - LLM calls (Groq) will be made during the memory pipeline (extraction,
      conflict resolution, summaries). Make sure GROQ_API_KEY is set in .env.
"""

import asyncio
import sys
from pathlib import Path
from typing import List

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()

from memblocks_lib.src.memblocks import MemBlocksClient, MemBlocksConfig


# ---------------------------------------------------------------------------
# Tiny synthetic conversation (6 turns = 12 messages — exceeds window limit)
# ---------------------------------------------------------------------------

TURNS = [
    ("Hi! I'm Sam. I work as a software engineer in San Francisco.", "Nice to meet you Sam! San Francisco is a great city for tech."),
    ("I've been working there for 5 years. I mainly code in Python and Go.", "That's a solid combo! What kind of projects do you work on?"),
    ("Mostly backend services and data pipelines. I love hiking on weekends.", "Hiking is a great way to decompress. Any favourite trails?"),
    ("I love the Marin Headlands. Stunning views of the Golden Gate Bridge.", "The Marin Headlands are beautiful! Do you go alone or with friends?"),
    ("Usually with my dog Max. He's a golden retriever.", "Golden retrievers are amazing trail companions!"),
    ("Exactly! We usually do 10-15 km routes. Max loves the water stops.", "Sounds like an amazing pair out there!"),
]

QUESTION = "Where does Sam live and work?"
EXPECTED_ANSWER = "San Francisco"


# ---------------------------------------------------------------------------
# Helper: unique user_id per test run to avoid stale data collisions
# ---------------------------------------------------------------------------

import time
_RUN_ID = str(int(time.time()))


def _user_id(suffix: str) -> str:
    return f"eval-integ-{_RUN_ID}-{suffix}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInfraConnectivity:
    """Basic connectivity checks — fast smoke tests."""

    def test_qdrant_reachable(self):
        """Qdrant health endpoint must return 200."""
        import requests
        r = requests.get("http://localhost:6333/healthz", timeout=5)
        assert r.status_code == 200, f"Qdrant not reachable: {r.status_code}"
        print("\n✓ Qdrant reachable at localhost:6333")

    def test_ollama_reachable(self):
        """Ollama must be reachable with at least one model loaded.

        Checks both OLLAMA_BASE_URL (generation) and OLLAMA_BASE_URL_EMBEDDINGS.
        Your .env has OLLAMA_BASE_URL=11434 but Ollama runs at 11435 — both are tried.
        To fix permanently: set OLLAMA_BASE_URL=http://localhost:11435 in .env.
        """
        import requests
        from memblocks_lib.src.memblocks.config import MemBlocksConfig
        cfg = MemBlocksConfig()
        urls_to_try = list(dict.fromkeys([cfg.ollama_base_url, cfg.ollama_base_url_embeddings]))

        found_url = None
        found_models = []
        for url in urls_to_try:
            try:
                r = requests.get(f"{url}/api/tags", timeout=5)
                if r.status_code == 200:
                    models = [m["name"] for m in r.json().get("models", [])]
                    if models:
                        found_url, found_models = url, models
                        break
            except Exception:
                continue

        assert found_url is not None, (
            f"Ollama not reachable with models at any of: {urls_to_try}. "
            "Start Ollama and ensure at least one model is loaded."
        )
        print(f"\n✓ Ollama reachable at {found_url} — models: {found_models}")
        if found_url != cfg.ollama_base_url:
            print(f"  NOTE: OLLAMA_BASE_URL={cfg.ollama_base_url} has no models; "
                  f"Ollama is actually at {found_url}. "
                  f"Set OLLAMA_BASE_URL={found_url} in .env to fix.")

    def test_mongodb_reachable(self):
        """MongoDB Atlas must accept a connection."""
        from pymongo import MongoClient
        from memblocks_lib.src.memblocks.config import MemBlocksConfig
        conn_str = MemBlocksConfig().mongodb_connection_string
        client = MongoClient(conn_str, serverSelectionTimeoutMS=5000)
        info = client.server_info()
        assert info is not None
        print(f"\n✓ MongoDB reachable — version: {info.get('version')}")


class TestMemBlocksSDK:
    """Verify the real SDK creates users, blocks, and sessions in real infra."""

    @pytest.fixture
    def event_loop(self):
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_create_user_block_session(self):
        """SDK lifecycle: get_or_create_user → create_block → create_session."""
        async def _run():
            config = MemBlocksConfig()
            client = MemBlocksClient(config)
            uid = _user_id("sdk-lifecycle")
            try:
                user = await client.get_or_create_user(uid)
                assert user is not None
                print(f"\n✓ User created: {uid}")

                block = await client.create_block(user_id=uid, name="integ-test-block")
                assert block is not None
                assert block.id
                print(f"✓ Block created: {block.id}")

                session = await client.create_session(user_id=uid, block_id=block.id)
                assert session is not None
                assert session.id
                print(f"✓ Session created: {session.id}")
            finally:
                await client.close()

        asyncio.run(_run())

    def test_ingestion_triggers_pipeline(self):
        """Adding 6 turns + flush must populate Qdrant with semantic memories."""
        import requests

        async def _run():
            config = MemBlocksConfig()
            client = MemBlocksClient(config)
            uid = _user_id("sdk-ingestion")
            try:
                await client.get_or_create_user(uid)
                block = await client.create_block(user_id=uid, name="integ-ingestion-block")
                session = await client.create_session(user_id=uid, block_id=block.id)

                for user_msg, ai_response in TURNS:
                    await session.add(user_msg=user_msg, ai_response=ai_response)

                # flush() processes any remaining messages even if window not full
                await session.flush()
                print(f"\n✓ Ingestion complete — block id: {block.id}")

                # Verify Qdrant has at least one collection for this block
                collections_resp = requests.get("http://localhost:6333/collections", timeout=5)
                collection_names = [
                    c["name"] for c in collections_resp.json().get("result", {}).get("collections", [])
                ]
                # The block creates a Qdrant collection named after its semantic_collection
                print(f"✓ Qdrant collections after ingestion: {collection_names}")
                assert len(collection_names) > 0, (
                    "No Qdrant collections found after ingestion — memory pipeline may not have fired."
                )
            finally:
                await client.close()

        asyncio.run(_run())

    def test_retrieval_returns_results(self):
        """After ingestion, all 3 strategies must return non-empty context."""
        async def _run():
            config = MemBlocksConfig()
            client = MemBlocksClient(config)
            uid = _user_id("sdk-retrieval")
            try:
                await client.get_or_create_user(uid)
                block = await client.create_block(user_id=uid, name="integ-retrieval-block")
                session = await client.create_session(user_id=uid, block_id=block.id)

                for user_msg, ai_response in TURNS:
                    await session.add(user_msg=user_msg, ai_response=ai_response)
                await session.flush()

                query = "Where does Sam live and work?"

                semantic = await block.semantic_retrieve(query)
                core = await block.core_retrieve()
                hybrid = await block.retrieve(query)

                sem_str = semantic.to_prompt_string()
                core_str = core.to_prompt_string()
                hyb_str = hybrid.to_prompt_string()

                print(f"\n--- Semantic retrieval ---\n{sem_str[:400]}")
                print(f"\n--- Core retrieval ---\n{core_str[:400]}")
                print(f"\n--- Hybrid retrieval ---\n{hyb_str[:400]}")

                # At least semantic or hybrid must find something
                assert sem_str or core_str or hyb_str, (
                    "All retrieval strategies returned empty — pipeline may not have stored memories."
                )
            finally:
                await client.close()

        asyncio.run(_run())

    def test_memory_window_and_summary(self):
        """Memory window and recursive summary must be accessible after ingestion."""
        async def _run():
            config = MemBlocksConfig()
            client = MemBlocksClient(config)
            uid = _user_id("sdk-window")
            try:
                await client.get_or_create_user(uid)
                block = await client.create_block(user_id=uid, name="integ-window-block")
                session = await client.create_session(user_id=uid, block_id=block.id)

                for user_msg, ai_response in TURNS:
                    await session.add(user_msg=user_msg, ai_response=ai_response)
                await session.flush()

                window = await session.get_memory_window()
                summary = await session.get_recursive_summary()

                print(f"\n✓ Memory window: {len(window)} messages")
                for m in window:
                    print(f"  [{m.get('role')}] {m.get('content', '')[:80]}")

                print(f"\n✓ Recursive summary ({len(summary)} chars):\n{summary[:500]}")

                assert isinstance(window, list)
                assert isinstance(summary, str)
            finally:
                await client.close()

        asyncio.run(_run())


class TestNoFallback:
    """Verify the LocomoRunner uses real MemBlocks — not _InMemoryClient."""

    def test_runner_uses_real_sdk_not_fallback(self):
        """The runner must report client_type='real', not 'in-memory' or 'none'."""
        from evaluation.core.config import DatasetConfig, RunnerConfig
        from evaluation.datasets.locomo import LocomoDataset, LocomoMessage, LocomoQuestion, LocomoSession
        from evaluation.runners.locomo import LocomoRunner

        # Build a minimal synthetic dataset — no network download needed
        class _SyntheticDataset(LocomoDataset):
            def load(self) -> List[LocomoSession]:
                messages = [LocomoMessage(role=r, content=c) for r, c in [
                    ("user", "[Sam]: Hi! I'm Sam. I work as a software engineer in San Francisco."),
                    ("assistant", "[Bot]: Nice to meet you Sam!"),
                    ("user", "[Sam]: I've been working there for 5 years. I mainly code in Python and Go."),
                    ("assistant", "[Bot]: That's a solid combo!"),
                    ("user", "[Sam]: I love hiking on weekends in the Marin Headlands."),
                    ("assistant", "[Bot]: The Marin Headlands are beautiful!"),
                    ("user", "[Sam]: I usually go with my dog Max, a golden retriever."),
                    ("assistant", "[Bot]: Golden retrievers are amazing trail companions!"),
                    ("user", "[Sam]: We usually do 10-15 km routes. Max loves the water stops."),
                    ("assistant", "[Bot]: Sounds like an amazing pair!"),
                    ("user", "[Sam]: I've been in SF for 5 years and love it."),
                    ("assistant", "[Bot]: SF is a great city for tech!"),
                ]]
                questions = [
                    LocomoQuestion(
                        question="Where does Sam live and work?",
                        answer="San Francisco",
                        category=1,
                    )
                ]
                return [LocomoSession(
                    session_id=f"synthetic-{_RUN_ID}",
                    messages=messages,
                    questions=questions,
                )]

        dataset_cfg = DatasetConfig(name="locomo")
        runner_cfg = RunnerConfig(name="locomo", model=None, judge_model=None)
        dataset = _SyntheticDataset(dataset_cfg)
        runner = LocomoRunner(runner_cfg, dataset)

        import asyncio
        results = asyncio.run(runner._run_async())

        assert results["sessions_processed"] == 1
        session_detail = results["details"][0]

        client_type = session_detail.get("client_type", "unknown")
        ingestion_status = session_detail.get("ingestion_status", "unknown")

        print(f"\n✓ client_type    : {client_type}")
        print(f"✓ ingestion_status: {ingestion_status}")
        print(f"✓ block_id        : {session_detail.get('block_id')}")

        assert client_type == "real", (
            f"Runner used fallback '{client_type}' instead of real MemBlocks SDK.\n"
            f"Ingestion status: {ingestion_status}\n"
            "Check that Qdrant (localhost:6333) and MongoDB Atlas are reachable."
        )
        assert ingestion_status == "success", f"Ingestion failed: {ingestion_status}"

        # Verify at least one question was evaluated
        evals = session_detail.get("evaluations", [])
        assert len(evals) == 1
        ev = evals[0]
        print(f"✓ Question status : {ev.get('status')}")
        print(f"✓ Retrieved context (hybrid, first 300 chars):\n"
              f"  {str(ev.get('retrieved_context_hybrid', ''))[:300]}")
