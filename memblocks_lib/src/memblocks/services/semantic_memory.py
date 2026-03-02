"""SemanticMemoryService — extracted from models/sections.py SemanticMemorySection."""

import json
import re
import string
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from memblocks.models.llm_outputs import SemanticMemoriesOutput, PS2MemoryUpdateOutput
from memblocks.models.units import (
    MemoryOperation,
    MemoryUnitMetaData,
    SemanticMemoryUnit,
)
from memblocks.prompts import PS1_SEMANTIC_PROMPT, PS2_MEMORY_UPDATE_PROMPT

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig
    from memblocks.llm.base import LLMProvider
    from memblocks.storage.embeddings import EmbeddingProvider
    from memblocks.storage.qdrant import QdrantAdapter
    from memblocks.services.transparency import OperationLog, RetrievalLog


class SemanticMemoryService:
    """
    Handles all semantic memory operations:
    - PS1 extraction from conversation
    - PS2 conflict resolution
    - Vector storage via QdrantAdapter
    - Vector retrieval

    Replaces:
    - SemanticMemorySection.extract_semantic_memories() (sections.py:53-125)
    - SemanticMemorySection.extract_and_store_memories() (sections.py:127-160)
    - SemanticMemorySection.store_memory() (sections.py:166-338)
    - SemanticMemorySection.retrieve_memories() (sections.py:344-378)

    Bug Fix 3: store() return type is now correctly List[MemoryOperation]
    (old store_memory() was annotated -> bool but returned List[MemoryOperation]).
    """

    def __init__(
        self,
        llm_provider: "LLMProvider",
        embedding_provider: "EmbeddingProvider",
        qdrant_adapter: "QdrantAdapter",
        collection_name: str,
        config: "MemBlocksConfig",
        operation_log: Optional["OperationLog"] = None,
        retrieval_log: Optional["RetrievalLog"] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """
        Args:
            llm_provider: LLM abstraction for PS1/PS2 chains.
            embedding_provider: Embeddings for vector operations.
            qdrant_adapter: Vector DB adapter.
            collection_name: Qdrant collection to operate on.
            config: Library configuration (temperatures etc.).
            operation_log: Phase-9 transparency placeholder.
            retrieval_log: Records every retrieval for observability.
            event_bus: Phase-9 event publishing placeholder.
        """
        self._llm = llm_provider
        self._embeddings = embedding_provider
        self._qdrant = qdrant_adapter
        self._collection = collection_name
        self._config = config
        self._log = operation_log
        self._retrieval_log = retrieval_log
        self._bus = event_bus

    # ------------------------------------------------------------------ #
    # PS1 Extraction
    # ------------------------------------------------------------------ #

    async def extract(
        self,
        messages: List[Dict[str, str]],
        ps1_prompt: str = PS1_SEMANTIC_PROMPT,
    ) -> List[SemanticMemoryUnit]:
        """
        PS1: Extract structured semantic memories from a conversation window.

        Does NOT store them — gives the caller control over filtering before
        calling store().

        Args:
            messages: Conversation messages [{"role": ..., "content": ...}].
            ps1_prompt: Custom PS1 system prompt (default: PS1_SEMANTIC_PROMPT).

        Returns:
            List of extracted SemanticMemoryUnit instances (not yet stored).
        """
        conversation_text = "\n".join(
            [f"{msg['role'].upper()}: {msg['content']}" for msg in messages]
        )
        user_input = (
            f"Conversation to analyze:\n\n{conversation_text}\n\n"
            f"Extract structured semantic memories. Analyze each significant piece of information."
        )

        try:
            chain = self._llm.create_structured_chain(
                system_prompt=ps1_prompt,
                pydantic_model=SemanticMemoriesOutput,
                temperature=self._config.llm_semantic_extraction_temperature,
            )
            result = await chain.ainvoke({"input": user_input})

            current_time = datetime.now().isoformat()
            extracted: List[SemanticMemoryUnit] = []

            for item in result.memories:
                embedding_text = (
                    f"{item.content}\n"
                    f"Keywords: {', '.join(item.keywords)}\n"
                    f"Entities: {', '.join(item.entities)}"
                ).strip()

                unit = SemanticMemoryUnit(
                    content=item.content,
                    type=item.type,
                    source="conversation",
                    confidence=item.confidence,
                    memory_time=(current_time if item.type == "event" else None),
                    entities=item.entities,
                    updated_at=current_time,
                    meta_data=MemoryUnitMetaData(usage=[current_time]),
                    keywords=item.keywords,
                    embedding_text=embedding_text,
                )
                extracted.append(unit)

            return extracted

        except Exception as e:
            print(f"[WARN] Failed to extract semantic memories: {e}")
            return []

    # ------------------------------------------------------------------ #
    # PS2 Storage with conflict resolution
    # ------------------------------------------------------------------ #

    async def store(
        self,
        memory_unit: SemanticMemoryUnit,
    ) -> List[MemoryOperation]:
        """
        Store a memory with PS2 conflict resolution.

        Pipeline:
        1. Embed the new memory.
        2. Retrieve semantically similar existing memories from Qdrant.
        3. Use LLM (PS2) to decide ADD/UPDATE/DELETE for each.
        4. Execute the decided operations atomically.

        Args:
            memory_unit: The new memory to store.

        Returns:
            List of MemoryOperation objects (Bug Fix 3: was annotated -> bool).
        """
        from qdrant_client.models import ScoredPoint  # local import to keep layer clean

        current_time = datetime.now().isoformat()
        operations: List[MemoryOperation] = []

        text_to_embed = memory_unit.embedding_text or memory_unit.content
        new_vector = self._embeddings.embed_text(text_to_embed)
        new_sparse_vector = self._embeddings.embed_sparse_text(text_to_embed)

        similar_results = self._qdrant.retrieve_from_vector(
            self._collection, new_vector, top_k=5
        )

        new_memory_dict = memory_unit.model_dump()
        new_memory_dict["updated_at"] = current_time

        # Build mapping: simple_index -> real Qdrant UUID
        existing_memories_list: List[Dict[str, Any]] = []
        id_mapping: Dict[str, str] = {}
        existing_contents: Dict[str, str] = {}

        for idx, point in enumerate(similar_results):
            if isinstance(point, ScoredPoint):
                simple_id = str(idx)
                id_mapping[simple_id] = point.id
                existing_mem = {**point.payload, "id": simple_id}
                existing_memories_list.append(existing_mem)
                existing_contents[simple_id] = point.payload.get("content", "")

        # ---- No similar memories -> just ADD ----
        if not existing_memories_list:
            payload = memory_unit.model_dump()
            success = self._qdrant.store_vector(
                self._collection, new_vector, payload, sparse_vector=new_sparse_vector
            )
            if success:
                print(
                    f"[OK] Added new memory (no similar): {memory_unit.content[:60]}..."
                )
                operations.append(
                    MemoryOperation(operation="ADD", content=memory_unit.content)
                )
            return operations

        # ---- PS2 conflict resolution ----
        try:
            chain = self._llm.create_structured_chain(
                system_prompt=PS2_MEMORY_UPDATE_PROMPT,
                pydantic_model=PS2MemoryUpdateOutput,
                temperature=self._config.llm_memory_update_temperature,
            )
            user_input = (
                f"\nNEW MEMORY:\n{json.dumps(new_memory_dict, indent=2, default=str)}\n\n"
                f"EXISTING MEMORIES:\n{json.dumps(existing_memories_list, indent=2, default=str)}\n"
            )
            result = await chain.ainvoke({"input": user_input})

        except Exception as e:
            print(f"[WARN] PS2 conflict resolution failed: {e}")
            print("   Fallback: Adding memory without conflict check")
            payload = memory_unit.model_dump()
            success = self._qdrant.store_vector(
                self._collection, new_vector, payload, sparse_vector=new_sparse_vector
            )
            if success:
                operations.append(
                    MemoryOperation(operation="ADD", content=memory_unit.content)
                )
            return operations

        operations_performed: List[str] = []

        # Handle new memory decision
        if result.new_memory_operation.operation == "ADD":
            payload = memory_unit.model_dump()
            success = self._qdrant.store_vector(
                self._collection, new_vector, payload, sparse_vector=new_sparse_vector
            )
            if success:
                operations_performed.append("ADD new memory")
                print(f"[OK] Added new memory: {memory_unit.content[:60]}...")
                operations.append(
                    MemoryOperation(operation="ADD", content=memory_unit.content)
                )
        else:
            operations_performed.append(
                f"NONE (new): {result.new_memory_operation.reason or 'Redundant'}"
            )
            print("  Skipped new memory (redundant)")
            operations.append(
                MemoryOperation(operation="NONE", content=memory_unit.content)
            )

        # Handle existing memory decisions
        for op in result.existing_memory_operations:
            real_id = id_mapping.get(op.id)
            if not real_id:
                print(
                    f"  Warning: Could not map ID {op.id} to real Qdrant ID, skipping"
                )
                continue

            if op.operation == "UPDATE":
                op.updated_memory["id"] = real_id
                updated_unit = SemanticMemoryUnit(**op.updated_memory)
                updated_text = updated_unit.embedding_text or updated_unit.content
                updated_vector = self._embeddings.embed_text(updated_text)
                updated_sparse_vector = self._embeddings.embed_sparse_text(updated_text)

                payload_without_id = {
                    k: v for k, v in op.updated_memory.items() if k != "id"
                }
                old_content = existing_contents.get(op.id, "")

                success = self._qdrant.store_vector(
                    self._collection,
                    updated_vector,
                    payload_without_id,
                    point_id=real_id,
                    sparse_vector=updated_sparse_vector,
                )
                if success:
                    operations_performed.append(f"UPDATE {real_id[:8]}...")
                    print(
                        f"Updated memory {real_id[:8]}...: {updated_unit.content[:60]}..."
                    )
                    operations.append(
                        MemoryOperation(
                            operation="UPDATE",
                            memory_id=real_id,
                            content=updated_unit.content,
                            old_content=old_content,
                        )
                    )

            elif op.operation == "DELETE":
                old_content = existing_contents.get(op.id, "")
                success = self._qdrant.delete_vector(self._collection, real_id)
                if success:
                    operations_performed.append(f"DELETE {real_id[:8]}...")
                    print(f"Deleted memory {real_id[:8]}...")
                    operations.append(
                        MemoryOperation(
                            operation="DELETE",
                            memory_id=real_id,
                            content=old_content,
                        )
                    )
            else:
                operations_performed.append(f"NONE {real_id[:8]}...")

        print(f"   Operations: {', '.join(operations_performed)}")
        return operations

    # ------------------------------------------------------------------ #
    # Convenience: extract + store in one call
    # ------------------------------------------------------------------ #

    async def extract_and_store(
        self,
        messages: List[Dict[str, str]],
        ps1_prompt: str = PS1_SEMANTIC_PROMPT,
        min_confidence: float = 0.0,
    ) -> List[SemanticMemoryUnit]:
        """
        Convenience: extract AND store semantic memories in one call.

        Mirrors SemanticMemorySection.extract_and_store_memories() (sections.py:127-160).

        Args:
            messages: Conversation messages.
            ps1_prompt: Custom PS1 system prompt.
            min_confidence: Only store memories with confidence >= this threshold.

        Returns:
            List of extracted and stored SemanticMemoryUnit instances.
        """
        memories = await self.extract(messages, ps1_prompt)

        if min_confidence > 0.0:
            memories = [m for m in memories if m.confidence >= min_confidence]

        for memory in memories:
            await self.store(memory)

        return memories

    # ------------------------------------------------------------------ #
    # Hybrid Retrieval — vector + keyword/entity + fusion reranking
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_query_terms(query: str) -> Tuple[List[str], List[str]]:
        """
        Lightweight extraction of keywords and entity candidates from a raw
        query string using only Python stdlib (re, string).

        Strategy:
        - ``keywords``: lowercased, punctuation-stripped tokens, stopwords removed.
        - ``entities``:  sequences of consecutive Title-Case words (potential
          named entities: people, places, products etc.).

        No external NLP libraries required.

        Args:
            query: Raw query text from the user.

        Returns:
            (keywords, entities) — both are lists of strings.
        """
        _STOPWORDS = {
            "a",
            "an",
            "and",
            "are",
            "as",
            "at",
            "be",
            "been",
            "but",
            "by",
            "did",
            "do",
            "does",
            "for",
            "from",
            "had",
            "has",
            "have",
            "he",
            "her",
            "him",
            "his",
            "how",
            "i",
            "if",
            "in",
            "is",
            "it",
            "its",
            "just",
            "me",
            "my",
            "no",
            "not",
            "of",
            "on",
            "or",
            "our",
            "she",
            "so",
            "that",
            "the",
            "their",
            "them",
            "then",
            "there",
            "they",
            "this",
            "to",
            "too",
            "up",
            "us",
            "was",
            "we",
            "what",
            "when",
            "where",
            "which",
            "who",
            "will",
            "with",
            "you",
            "your",
        }

        # Strip punctuation and lowercase for keyword extraction
        clean = query.translate(str.maketrans("", "", string.punctuation))
        tokens = clean.lower().split()
        keywords = [t for t in tokens if t and t not in _STOPWORDS and len(t) > 2]

        # Entity candidates: consecutive Title-Case word runs (≥1 word)
        # e.g. "San Francisco" or "OpenAI" — grab individual Title-Case words too
        entity_pattern = re.compile(r"\b[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*\b")
        entities = entity_pattern.findall(query)
        # Lower-case them so they match lowercased payload values
        entities = [e.lower() for e in entities if len(e) > 2]

        return keywords, entities

    def retrieve(
        self,
        query_texts: List[str],
        top_k: int = 5,
    ) -> List[List[SemanticMemoryUnit]]:
        """
        Hybrid retrieval: vector similarity + keyword/entity scroll, fused and
        reranked into a single ordered result list per query.

        Pipeline per query
        ------------------
        1. Extract keywords + entity candidates from the raw query string.
        2. Run in parallel:
           a. Vector similarity search  (cosine distance via Qdrant)
           b. Keyword/entity scroll      (payload MatchAny filter)
        3. Fuse scores:
           - Vector result  -> ``fusion_score = vector_score``
           - Keyword hit    -> ``+0.15`` if already in vector results,
                              ``0.30`` if only from scroll
        4. De-duplicate, sort by ``fusion_score`` desc, return top_k.

        CLI logging is emitted to stdout so the keyword/entity path is
        always visible when running the server or a REPL.

        Args:
            query_texts: List of query strings.
            top_k: Number of results per query.

        Returns:
            List of lists — one list of SemanticMemoryUnit per query.
        """
        import time

        query_vectors = self._embeddings.embed_documents(query_texts)
        query_sparse_vectors = self._embeddings.embed_sparse_documents(query_texts)

        def _hybrid_search(
            args: Tuple[str, List[float], Dict[str, Any]],
        ) -> List[SemanticMemoryUnit]:
            query_text, vector, sparse_vector = args

            # ── Step 1: extract search terms (for manual evaluation only) ─
            keywords, entities = self._extract_query_terms(query_text)

            print("\n[HybridRetrieve]")
            print(f"   Query    : {query_text!r}")
            print(f"   Keywords : {keywords}")
            print(f"   Entities : {entities}")

            # ── Step 2a: Qdrant Native Hybrid Search ──────────────────────
            start_bm25 = time.time()
            vector_points = self._qdrant.retrieve_hybrid(
                self._collection,
                dense_query_vector=vector,
                sparse_query_vector=sparse_vector,
                top_k=top_k * 2,
            )
            bm25_time = time.time() - start_bm25
            print(
                f"   Native Hybrid Search -> {len(vector_points)} result(s) in {bm25_time:.4f}s"
            )

            # ── Step 2b: (Idle) Manual keyword / entity scroll for metrics ──
            start_manual = time.time()
            kw_records = self._qdrant.retrieve_by_keywords_and_entities(
                self._collection,
                keywords=keywords,
                entities=entities,
                top_k=top_k * 2,
            )
            manual_time = time.time() - start_manual
            print(
                f"   Idle Manual Scroll    -> {len(kw_records)} result(s) in {manual_time:.4f}s"
            )

            # ── Step 3: parse candidates ──────────────────────────────────
            candidates: Dict[str, Tuple[SemanticMemoryUnit, float]] = {}

            # --- Qdrant native hybrid results (BM25 + semantic) ---
            for point in vector_points:
                payload = point.payload
                content = payload.get("content", "")
                if not content:
                    continue
                try:
                    unit = SemanticMemoryUnit(**payload)
                except Exception:
                    continue
                score = float(getattr(point, "score", 0.5))
                candidates[content] = (unit, score)

            # --- Manual keyword/entity search (IDLE - for benchmarking only) ---
            # This runs but is NOT combined into results
            # Uncomment below to enable manual scroll in results:
            # for point in kw_records:
            #     payload = point.payload
            #     content = payload.get("content", "")
            #     if not content:
            #         continue
            #     try:
            #         unit = SemanticMemoryUnit(**payload)
            #     except Exception:
            #         continue
            #     bonus_score = 0.1
            #     if content in candidates:
            #         existing_unit, existing_score = candidates[content]
            #         candidates[content] = (existing_unit, existing_score + bonus_score)
            #     else:
            #         candidates[content] = (unit, bonus_score)

            # ── Step 4: sort, return top_k ────────────────────────────────
            ranked = sorted(candidates.values(), key=lambda x: x[1], reverse=True)
            return [unit for unit, _ in ranked[:top_k]]

        # Run hybrid search for each query in parallel
        with ThreadPoolExecutor(max_workers=min(10, len(query_vectors))) as executor:
            grouped_results: List[List[SemanticMemoryUnit]] = list(
                executor.map(
                    _hybrid_search,
                    zip(query_texts, query_vectors, query_sparse_vectors),
                )
            )

        # Global de-duplication across all query groups
        seen_contents: set = set()
        deduplicated: List[List[SemanticMemoryUnit]] = []

        for group in grouped_results:
            unique_group: List[SemanticMemoryUnit] = []
            for memory in group:
                if memory.content not in seen_contents:
                    seen_contents.add(memory.content)
                    unique_group.append(memory)
            deduplicated.append(unique_group)

        # ── Transparency logging ───────────────────────────────────────────
        if self._retrieval_log is not None:
            from memblocks.models.transparency import RetrievalEntry

            flat_memories = [m for group in deduplicated for m in group]
            self._retrieval_log.record(
                RetrievalEntry(
                    query_text=query_texts[0] if query_texts else "",
                    source="semantic_hybrid",
                    num_results=len(flat_memories),
                    memory_summaries=[m.content[:80] for m in flat_memories[:5]],
                )
            )
        if self._bus is not None:
            self._bus.publish(
                "on_memory_retrieved",
                {
                    "source": "semantic_hybrid",
                    "collection": self._collection,
                    "num_results": sum(len(g) for g in deduplicated),
                },
            )

        return deduplicated
