"""SemanticMemoryService — extracted from models/sections.py SemanticMemorySection."""

import json
import re
import string
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from memblocks.models.llm_outputs import (
    SemanticMemoriesOutput,
    PS2MemoryUpdateOutput,
    ExistingSemanticMemoryUnitForPS2,
    QueryExpansionOutput,
    HypotheticalParagraphsOutput,
    QueryEnhancementOutput,
)
from memblocks.services.reranker import CohereReranker
from memblocks.models.units import (
    MemoryOperation,
    MemoryUnitMetaData,
    SemanticMemoryUnit,
)
from memblocks.prompts import (
    PS1_SEMANTIC_PROMPT,
    PS2_MEMORY_UPDATE_PROMPT,
    QUERY_ENHANCEMENT_PROMPT,
)
from memblocks.logger import get_logger

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig
    from memblocks.llm.base import LLMProvider
    from memblocks.storage.embeddings import EmbeddingProvider
    from memblocks.storage.qdrant import QdrantAdapter
    from memblocks.services.transparency import OperationLog, RetrievalLog

logger = get_logger(__name__)


class SemanticMemoryService:
    """
    Handles all semantic memory operations:
    - PS1 extraction from conversation
    - PS2 conflict resolution
    - Vector storage via QdrantAdapter (with SPLADE sparse vectors when enabled)
    - Enhanced vector retrieval with SPLADE hybrid search, query expansion,
      hypothetical paragraphs, and Cohere-based re-ranking

    Replaces:
    - SemanticMemorySection.extract_semantic_memories() (sections.py:53-125)
    - SemanticMemorySection.extract_and_store_memories() (sections.py:127-160)
    - SemanticMemorySection.store_memory() (sections.py:166-338)
    - SemanticMemorySection.retrieve_memories() (sections.py:344-378)

    Bug Fix 3: store() return type is now correctly List[MemoryOperation]
    (old store_memory() was annotated -> bool but returned List[MemoryOperation]).

    Enhancement: retrieve() now supports query expansion, hypothetical paragraph generation,
    and Cohere-based re-ranking for improved semantic retrieval coverage and relevance
    with reduced latency compared to LLM-based re-ranking.

    Per-task LLM providers:
    - ps1_llm:       Used for PS1 semantic memory extraction.
    - ps2_llm:       Used for PS2 conflict resolution (ADD/UPDATE/DELETE).
    - retrieval_llm: Used for query enhancement (HyDE + expansion).
    Each can be a different model/provider, configured via ``LLMSettings`` in
    ``MemBlocksConfig``.
    
    Re-ranking: Uses Cohere's dedicated re-rank API (rerank-english-v3.0) instead of
    LLM-based re-ranking for faster, more accurate relevance scoring.
    """

    def __init__(
        self,
        ps1_llm: "LLMProvider",
        embedding_provider: "EmbeddingProvider",
        qdrant_adapter: "QdrantAdapter",
        collection_name: str,
        config: "MemBlocksConfig",
        ps2_llm: Optional["LLMProvider"] = None,
        retrieval_llm: Optional["LLMProvider"] = None,
        operation_log: Optional["OperationLog"] = None,
        retrieval_log: Optional["RetrievalLog"] = None,
        event_bus: Optional[Any] = None
    ) -> None:
        """
        Args:
            ps1_llm: LLM provider for PS1 semantic memory extraction.
            embedding_provider: Embeddings for vector operations.
            qdrant_adapter: Vector DB adapter.
            collection_name: Qdrant collection to operate on.
            config: Library configuration (temperatures etc.).
            ps2_llm: LLM provider for PS2 conflict resolution. Defaults to
                ``ps1_llm`` when not provided.
            retrieval_llm: LLM provider for query enhancement (HyDE + expansion).
                Defaults to ``ps1_llm`` when not provided.
            operation_log: Phase-9 transparency placeholder.
            retrieval_log: Records every retrieval for observability.
            event_bus: Phase-9 event publishing placeholder
        """
        self._ps1_llm = ps1_llm
        self._ps2_llm = ps2_llm if ps2_llm is not None else ps1_llm
        self._retrieval_llm = retrieval_llm if retrieval_llm is not None else ps1_llm
        # Backward-compat alias — internal methods may still use self._llm
        self._llm = ps1_llm
        self._embeddings = embedding_provider
        self._qdrant = qdrant_adapter
        self._collection = collection_name
        self._config = config
        self._log = operation_log
        self._retrieval_log = retrieval_log
        self._bus = event_bus
        
        # Initialize Cohere re-ranker (lazy initialization on first use)
        self._reranker: Optional[CohereReranker] = None

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
        current_time = datetime.now(timezone.utc).isoformat()
        user_input = (
            f"Current time (ISO 8601): {current_time}\n\n"
            f"Conversation to analyze:\n\n{conversation_text}\n\n"
            f"Extract structured semantic memories. Analyze each significant piece of information."
        )

        try:
            chain = self._ps1_llm.create_structured_chain(
                system_prompt=ps1_prompt,
                pydantic_model=SemanticMemoriesOutput,
                temperature=self._config.llm_semantic_extraction_temperature,
            )
            result = await chain.ainvoke({"input": user_input})

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
                    memory_time=(item.memory_time if item.type == "event" else None),
                    entities=item.entities,
                    updated_at=current_time,
                    meta_data=MemoryUnitMetaData(usage=[current_time]),
                    keywords=item.keywords,
                    embedding_text=embedding_text,
                )
                extracted.append(unit)

            return extracted

        except Exception as e:
            logger.warning("Failed to extract semantic memories: %s", e)
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

        current_time = datetime.now(timezone.utc).isoformat()
        operations: List[MemoryOperation] = []

        text_to_embed = memory_unit.embedding_text or memory_unit.content
        new_vector = self._embeddings.embed_text(text_to_embed)
        new_sparse_vector = (
            self._embeddings.embed_sparse_text(text_to_embed)
            if self._config.retrieval_enable_sparse
            else None
        )

        similar_results = self._qdrant.retrieve_from_vector(
            self._collection, new_vector, top_k=5
        )

        new_memory_dict = memory_unit.model_dump()
        new_memory_dict["updated_at"] = current_time

        # Build mapping: simple_index → real Qdrant UUID and original ScoredPoint
        existing_memories_list: List[Dict[str, Any]] = []
        id_mapping: Dict[str, str] = {}
        point_mapping: Dict[
            str, Any
        ] = {}  # simple_id → ScoredPoint (for reconstruction)
        existing_contents: Dict[str, str] = {}

        for idx, point in enumerate(similar_results):
            if isinstance(point, ScoredPoint):
                simple_id = str(idx)
                id_mapping[simple_id] = point.id
                point_mapping[simple_id] = point
                existing_mem = ExistingSemanticMemoryUnitForPS2(
                    id=simple_id,
                    memory_time=point.payload.get("memory_time"),
                    updated_at=point.payload.get("updated_at"),
                    content=point.payload.get("content", ""),
                    type=point.payload.get("type", ""),
                    entities=point.payload.get("entities", []),
                    keywords=point.payload.get("keywords", []),
                    confidence=point.payload.get("confidence", 0.0),
                ).model_dump()
                existing_memories_list.append(existing_mem)
                existing_contents[simple_id] = point.payload.get("content", "")

        # ---- No similar memories → just ADD ----
        if not existing_memories_list:
            payload = memory_unit.model_dump(exclude={"memory_id"})
            success = self._qdrant.store_vector(
                self._collection, new_vector, payload, sparse_vector=new_sparse_vector
            )
            if success:
                logger.debug(
                    "Added new memory (no similar): %s...", memory_unit.content[:60]
                )
                operations.append(
                    MemoryOperation(operation="ADD", content=memory_unit.content)
                )
            return operations

        # ---- PS2 conflict resolution ----
        try:
            chain = self._ps2_llm.create_structured_chain(
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
            logger.warning("PS2 conflict resolution failed: %s", e)
            logger.debug("Fallback: Adding memory without conflict check")
            payload = memory_unit.model_dump(exclude={"memory_id"})
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
            payload = memory_unit.model_dump(exclude={"memory_id"})
            success = self._qdrant.store_vector(
                self._collection, new_vector, payload, sparse_vector=new_sparse_vector
            )
            if success:
                operations_performed.append("ADD new memory")
                logger.debug("Added new memory: %s...", memory_unit.content[:60])
                operations.append(
                    MemoryOperation(operation="ADD", content=memory_unit.content)
                )
        else:
            operations_performed.append(
                f"NONE (new): {result.new_memory_operation.reason or 'Redundant'}"
            )
            logger.debug("Skipped new memory (redundant)")
            operations.append(
                MemoryOperation(operation="NONE", content=memory_unit.content)
            )

        # Handle existing memory decisions
        for op in result.existing_memory_operations:
            real_id = id_mapping.get(op.id)
            if not real_id:
                logger.warning("Could not map ID %s to real Qdrant ID, skipping", op.id)
                continue

            if op.operation == "UPDATE":
                if op.updated_memory is None:
                    logger.warning(
                        "UPDATE operation for ID %s has no updated_memory, skipping",
                        op.id,
                    )
                    continue

                updated_mem = op.updated_memory  # ExistingSemanticMemoryUnitForPS2
                original_point = point_mapping[op.id]

                # Reconstruct embedding_text from the updated content/keywords/entities
                new_embedding_text = (
                    f"{updated_mem.content}\n"
                    f"Keywords: {', '.join(updated_mem.keywords)}\n"
                    f"Entities: {', '.join(updated_mem.entities)}"
                ).strip()

                # Preserve meta_data from original, append current_time to usage list
                original_meta = original_point.payload.get("meta_data") or {}
                existing_usage: List[str] = original_meta.get("usage", [])
                updated_usage = existing_usage + [current_time]
                updated_meta = MemoryUnitMetaData(
                    usage=updated_usage,
                    status=original_meta.get("status", "active"),
                    message_ids=original_meta.get("message_ids", []),
                )

                # Reconstruct the full SemanticMemoryUnit
                old_content = existing_contents.get(op.id, "")
                updated_unit = SemanticMemoryUnit(
                    content=updated_mem.content,
                    type=updated_mem.type,
                    keywords=updated_mem.keywords,
                    entities=updated_mem.entities,
                    confidence=updated_mem.confidence,
                    memory_time=updated_mem.memory_time,
                    updated_at=current_time,
                    embedding_text=new_embedding_text,
                    source=original_point.payload.get("source"),
                    meta_data=updated_meta,
                    memory_id=real_id,
                )

                updated_text = updated_unit.embedding_text or updated_unit.content
                updated_vector = self._embeddings.embed_text(updated_text)
                updated_sparse_vector = (
                    self._embeddings.embed_sparse_text(updated_text)
                    if self._config.retrieval_enable_sparse
                    else None
                )

                # Payload excludes memory_id (stored as the Qdrant point ID, not in payload)
                payload = updated_unit.model_dump(exclude={"memory_id"})

                success = self._qdrant.store_vector(
                    self._collection,
                    updated_vector,
                    payload,
                    point_id=real_id,
                    sparse_vector=updated_sparse_vector,
                )
                if success:
                    operations_performed.append(f"UPDATE {real_id[:8]}...")
                    logger.debug(
                        "Updated memory %s...: %s...",
                        real_id[:8],
                        updated_unit.content[:60],
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
                    logger.debug("Deleted memory %s...", real_id[:8])
                    operations.append(
                        MemoryOperation(
                            operation="DELETE",
                            memory_id=real_id,
                            content=old_content,
                        )
                    )
            else:
                operations_performed.append(f"NONE {real_id[:8]}...")

        logger.debug("Operations: %s", ", ".join(operations_performed))
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
    # Enhanced Retrieval with Query Expansion, Hypothetical Paragraphs, and Re-ranking
    # ------------------------------------------------------------------ #

    async def _enhance_query(self, query: str) -> Tuple[List[str], List[str]]:
        """
        Generate both expanded queries and hypothetical paragraphs in a SINGLE API call.

        This combines query expansion and hypothetical paragraph generation to reduce latency
        by halving the number of LLM API calls during retrieval.

        Args:
            query: Original query text.

        Returns:
            Tuple of (expanded_queries, hypothetical_paragraphs).
            expanded_queries includes the original query.
        """
        # Check if both features are disabled
        expansion_enabled = self._config.retrieval_enable_query_expansion
        hypothetical_enabled = self._config.retrieval_enable_hypothetical_paragraphs

        if not expansion_enabled and not hypothetical_enabled:
            logger.debug("Query enhancement disabled, returning original query only")
            return [query], []

        try:
            num_expansions = self._config.retrieval_num_query_expansions
            num_paragraphs = self._config.retrieval_num_hypothetical_paragraphs

            # Use combined prompt for both operations
            prompt = QUERY_ENHANCEMENT_PROMPT.format(
                num_expansions=num_expansions, num_paragraphs=num_paragraphs
            )

            chain = self._retrieval_llm.create_structured_chain(
                system_prompt=prompt,
                pydantic_model=QueryEnhancementOutput,
                temperature=0.4,  # Balanced temperature for both tasks
            )

            user_input = (
                f"Original Query: {query}\n\n"
                f"Generate {num_expansions} expanded queries AND "
                f"{num_paragraphs} hypothetical answer paragraphs."
            )
            result = await chain.ainvoke({"input": user_input})

            # Include original query + expanded queries
            expanded_queries = (
                [query] + result.expanded_queries if expansion_enabled else [query]
            )
            hypothetical_paragraphs = (
                result.hypothetical_paragraphs if hypothetical_enabled else []
            )

            logger.debug(
                "Query enhancement: %d expanded queries + %d hypothetical paragraphs from: %s",
                len(expanded_queries),
                len(hypothetical_paragraphs),
                query[:50],
            )
            return expanded_queries, hypothetical_paragraphs

        except Exception as e:
            logger.warning(
                "Query enhancement failed: %s. Using original query only.", e
            )
            return [query], []

    async def _expand_query(self, query: str) -> List[str]:
        """
        [DEPRECATED] Use _enhance_query() instead for better performance.

        Generate expanded queries with additional related terms for better retrieval coverage.
        This method is kept for backward compatibility but calls the optimized _enhance_query().

        Args:
            query: Original query text.

        Returns:
            List of expanded queries including the original.
        """
        expanded_queries, _ = await self._enhance_query(query)
        return expanded_queries

    async def _generate_hypothetical_paragraphs(self, query: str) -> List[str]:
        """
        [DEPRECATED] Use _enhance_query() instead for better performance.

        Generate hypothetical answer paragraphs for the query (HyDE technique).
        This method is kept for backward compatibility but calls the optimized _enhance_query().

        Args:
            query: Original query text.

        Returns:
            List of hypothetical answer paragraphs.
        """
        _, hypothetical_paragraphs = await self._enhance_query(query)
        return hypothetical_paragraphs

    def _retrieve_with_hybrid(
        self,
        query_texts: List[str],
        top_k: int,
    ) -> Tuple[List[SemanticMemoryUnit], Set[str]]:
        """
        Retrieve memories for multiple query texts using hybrid (dense + SPLADE)
        or pure-dense search depending on config.retrieval_enable_sparse.

        Runs all queries in parallel via ThreadPoolExecutor, then deduplicates
        results by memory_id across all query groups.

        Args:
            query_texts: List of query strings (original + expanded + hypothetical).
            top_k: Number of results to retrieve per query.

        Returns:
            Tuple of (deduplicated_memories, set_of_seen_memory_ids).
        """
        logger.debug(
            "Retrieving with %d query variations, top_k=%d, sparse=%s",
            len(query_texts),
            top_k,
            self._config.retrieval_enable_sparse,
        )

        query_vectors = self._embeddings.embed_documents(query_texts)
        logger.debug("Generated dense vectors for all query variations")
        if self._config.retrieval_enable_sparse:
            query_sparse_vectors = self._embeddings.embed_sparse_documents(query_texts)
            logger.debug("Generated sparse vectors for all query variations")
            def _hybrid_search(
                args: Tuple[List[float], Dict[str, Any]],
            ) -> List[SemanticMemoryUnit]:
                dense_vec, sparse_vec = args
                results = self._qdrant.retrieve_hybrid(
                    self._collection, dense_vec, sparse_vec, top_k
                )
                memories = []
                for hit in results:
                    try:
                        memories.append(
                            SemanticMemoryUnit(**hit.payload, memory_id=str(hit.id))
                        )
                    except Exception:
                        pass
                return memories

            with ThreadPoolExecutor(
                max_workers=min(10, len(query_vectors))
            ) as executor:
                grouped_results = list(
                    executor.map(
                        _hybrid_search, zip(query_vectors, query_sparse_vectors)
                    )
                )
        else:

            def _dense_search(dense_vec: List[float]) -> List[SemanticMemoryUnit]:
                results = self._qdrant.retrieve_from_vector(
                    self._collection, dense_vec, top_k
                )
                memories = []
                for hit in results:
                    try:
                        memories.append(
                            SemanticMemoryUnit(**hit.payload, memory_id=str(hit.id))
                        )
                    except Exception:
                        pass
                return memories

            with ThreadPoolExecutor(
                max_workers=min(10, len(query_vectors))
            ) as executor:
                grouped_results = list(executor.map(_dense_search, query_vectors))

        # De-duplicate by memory_id across all query groups
        seen_ids: Set[str] = set()
        deduplicated: List[SemanticMemoryUnit] = []
        for group in grouped_results:
            for memory in group:
                if memory.memory_id and memory.memory_id not in seen_ids:
                    seen_ids.add(memory.memory_id)
                    deduplicated.append(memory)

        logger.debug(
            "Hybrid retrieval: %d unique memories from %d query vectors",
            len(deduplicated),
            len(query_vectors),
        )
        return deduplicated, seen_ids

    def _get_reranker(self) -> CohereReranker:
        """Lazy initialization of Cohere re-ranker.

        The reranker is created with ``config`` object so that the re-ranker itself can resolve the key
        """
        if self._reranker is None:
            self._reranker = CohereReranker(
                config=self._config
            )
        return self._reranker

    async def _rerank_memories(
        self, query: str, memories: List[SemanticMemoryUnit]
    ) -> List[SemanticMemoryUnit]:
        """
        Re-rank retrieved memories using Cohere's re-rank API.

        This replaces the previous LLM-based re-ranking with Cohere's dedicated
        re-ranking model, which is significantly faster and more accurate.

        Args:
            query: Original query text.
            memories: List of memories to re-rank.

        Returns:
            Re-ranked list of memories, ordered by relevance.
        """
        if not self._config.retrieval_enable_reranking or not memories:
            logger.debug("Re-ranking disabled or no memories to rank")
            return memories

        try:
            reranker = self._get_reranker()
            
            # Use Cohere's re-ranking (no top_n limit here, we apply final_top_k later)
            reranked = await reranker.rerank(
                query=query,
                memories=memories,
                top_n=None,  # Get all ranked results
            )
            
            logger.debug(
                "Re-ranked %d memories for query: %s",
                len(reranked),
                query[:50],
            )
            
            return reranked

        except Exception as e:
            logger.warning("Re-ranking failed: %s. Returning original order.", e)
            return memories

    async def retrieve(
        self,
        query_texts: List[str],
        top_k: int = 5,
    ) -> List[List[SemanticMemoryUnit]]:
        """
        Retrieve top-k semantically similar memories for each query text with enhanced retrieval.

        Enhanced Pipeline (Optimized with single LLM call for steps 1-2):
        1. Query Enhancement: Generate alternative query formulations AND hypothetical paragraphs (single API call)
        2. Vector Search: Retrieve using all query variations
        3. Re-ranking: Use LLM to re-rank results by relevance
        4. Deduplication: Remove duplicates and return final results

        Mirrors SemanticMemorySection.retrieve_memories() (sections.py:344-378) but with
        significant enhancements for better retrieval coverage and relevance.

        Args:
            query_texts: List of query strings.
            top_k: Number of results per query (before re-ranking and final selection).

        Returns:
            List of lists — one list of SemanticMemoryUnit per original query,
            enhanced and de-duplicated.
        """
        # Process each query independently
        all_results: List[List[SemanticMemoryUnit]] = []

        for query in query_texts:
            logger.info("Processing retrieval for query: %s", query[:60])

            # Track metadata for transparency logging
            expanded_queries: List[str] = []
            hypothetical_paragraphs: List[str] = []

            try:
                # Step 1: Query Enhancement (Combined query expansion + hypothetical paragraphs in single API call)
                expanded_queries, hypothetical_paragraphs = await self._enhance_query(
                    query
                )

                # Step 2: Combine all query variations for retrieval
                all_query_texts = expanded_queries + hypothetical_paragraphs

                # Step 3: Vector Search
                top_k_per_query = self._config.retrieval_top_k_per_query
                retrieved_memories, seen_ids = self._retrieve_with_hybrid(
                    all_query_texts, top_k_per_query
                )

                # Step 4: Re-ranking
                reranked_memories = await self._rerank_memories(
                    query, retrieved_memories
                )

                # Step 5: Apply final top-k limit
                final_top_k = self._config.retrieval_final_top_k
                final_memories = reranked_memories[:final_top_k]

                all_results.append(final_memories)

                # Step 6: Transparency logging
                if self._retrieval_log is not None:
                    from memblocks.models.transparency import RetrievalEntry

                    self._retrieval_log.record(
                        RetrievalEntry(
                            query_text=query,
                            source="semantic",
                            num_results=len(final_memories),
                            memory_ids=[
                                m.memory_id for m in final_memories if m.memory_id
                            ],
                            memory_summaries=[m.content[:80] for m in final_memories],
                            expanded_queries=expanded_queries,
                            hypothetical_paragraphs=hypothetical_paragraphs,
                            reranked=self._config.retrieval_enable_reranking,
                            retrieval_method=(
                                "hybrid_enhanced"
                                if self._config.retrieval_enable_sparse
                                else "vector_enhanced"
                            ),
                        )
                    )

                # Step 7: Event bus notification
                if self._bus is not None:
                    self._bus.publish(
                        "on_memory_retrieved",
                        {
                            "source": "semantic",
                            "collection": self._collection,
                            "query": query,
                            "num_results": len(final_memories),
                            "num_expanded_queries": len(expanded_queries),
                            "num_hypothetical_paragraphs": len(hypothetical_paragraphs),
                            "reranked": self._config.retrieval_enable_reranking,
                        },
                    )

                logger.info(
                    "Retrieved %d memories for query (expanded: %d, hypothetical: %d, reranked: %s)",
                    len(final_memories),
                    len(expanded_queries),
                    len(hypothetical_paragraphs),
                    self._config.retrieval_enable_reranking,
                )

            except Exception as e:
                logger.error("Retrieval failed for query '%s': %s", query[:50], e)
                all_results.append([])  # Return empty list for failed query

        return all_results
