"""BlockManager — creates and loads Block objects wired with retrieval services."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from memblocks.models.block import MemoryBlock, MemoryBlockMetaData
from memblocks.services.block import Block

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig
    from memblocks.services.core_memory import CoreMemoryService
    from memblocks.services.semantic_memory import SemanticMemoryService
    from memblocks.services.transparency import OperationLog
    from memblocks.storage.embeddings import EmbeddingProvider
    from memblocks.storage.mongo import MongoDBAdapter
    from memblocks.storage.qdrant import QdrantAdapter
    from memblocks.llm.base import LLMProvider


class BlockManager:
    """
    Creates, loads, lists, and deletes memory blocks.

    Returns stateful Block objects wired with SemanticMemoryService and
    CoreMemoryService so the caller can immediately call block.retrieve() etc.
    without going back through the client.
    """

    def __init__(
        self,
        mongo_adapter: "MongoDBAdapter",
        qdrant_adapter: "QdrantAdapter",
        embedding_provider: "EmbeddingProvider",
        llm_provider: "LLMProvider",
        core_memory_service: "CoreMemoryService",
        config: "MemBlocksConfig",
        operation_log: Optional["OperationLog"] = None,
        retrieval_top_k: int = 5,
        event_bus: Optional[Any] = None,
        retrieval_log: Optional[Any] = None,
    ) -> None:
        """
        Args:
            mongo_adapter: MongoDB persistence layer.
            qdrant_adapter: Qdrant vector DB layer.
            embedding_provider: Used to create Qdrant collections with correct dim.
            llm_provider: LLM for semantic memory extraction/update.
            core_memory_service: Shared core memory service.
            config: Library config (temperatures, collection templates etc.).
            operation_log: Transparency log.
            retrieval_top_k: Default top-k for vector search.
            event_bus: Transparency event bus.
            retrieval_log: Transparency retrieval log.
        """
        self._mongo = mongo_adapter
        self._qdrant = qdrant_adapter
        self._embeddings = embedding_provider
        self._llm = llm_provider
        self._core = core_memory_service
        self._config = config
        self._log = operation_log
        self._top_k = retrieval_top_k
        self._bus = event_bus
        self._retrieval_log = retrieval_log

    # ------------------------------------------------------------------ #
    # Block lifecycle
    # ------------------------------------------------------------------ #

    async def create_block(
        self,
        user_id: str,
        name: str,
        description: str = "",
        create_semantic: bool = True,
        create_core: bool = True,
        create_resource: bool = False,
    ) -> "Block":
        """
        Create a new memory block with Qdrant collections and MongoDB documents.

        Args:
            user_id: Owner user ID.
            name: Human-readable block name.
            description: Optional description.
            create_semantic: Whether to create a semantic Qdrant collection.
            create_core: Whether to initialise a core memory document in Mongo.
            create_resource: Whether to create a resource Qdrant collection.

        Returns:
            Stateful Block object ready for retrieval.
        """
        block_id = f"block_{uuid.uuid4().hex[:12]}"
        current_time = datetime.utcnow().isoformat()

        semantic_collection: Optional[str] = None
        resource_collection: Optional[str] = None
        core_memory_block_id: Optional[str] = None

        if create_semantic:
            semantic_collection = f"{block_id}_semantic"
            self._qdrant.create_collection(semantic_collection)
            print(f"   [OK] Created semantic collection: {semantic_collection}")

        if create_resource:
            resource_collection = f"{block_id}_resource"
            self._qdrant.create_collection(resource_collection)
            print(f"   [OK] Created resource collection: {resource_collection}")

        if create_core:
            core_memory_block_id = block_id
            await self._mongo.save_core_memory(
                block_id=block_id,
                persona_content="",
                human_content="",
            )
            print(f"   [OK] Created core memory document: {block_id}")

        # Persist block document
        metadata = MemoryBlockMetaData(
            id=block_id,
            created_at=current_time,
            updated_at=current_time,
            usage=[],
            user_id=user_id,
        )
        block_dict = {
            "block_id": block_id,
            "user_id": user_id,
            "name": name,
            "description": description,
            "meta_data": metadata.model_dump(),
            "semantic_collection": semantic_collection,
            "core_memory_block_id": core_memory_block_id,
            "resource_collection": resource_collection,
            "is_active": False,
            "created_at": current_time,
            "updated_at": current_time,
        }
        await self._mongo.create_memory_block(user_id, block_dict)
        await self._mongo.add_block_to_user(user_id, block_id)

        print(f"[OK] Created memory block: {block_id}")
        return self._make_block(
            block_id=block_id,
            name=name,
            description=description,
            user_id=user_id,
            semantic_collection=semantic_collection,
            core_memory_block_id=core_memory_block_id,
            resource_collection=resource_collection,
            created_at=current_time,
            updated_at=current_time,
        )

    async def get_block(self, block_id: str) -> Optional["Block"]:
        """
        Load a memory block from MongoDB and return a stateful Block object.

        Args:
            block_id: Block identifier.

        Returns:
            Block instance or None if not found.
        """
        doc = await self._mongo.get_memory_block(block_id)
        if not doc:
            return None
        return self._doc_to_block(doc)

    async def get_user_blocks(self, user_id: str) -> List["Block"]:
        """
        Return all blocks belonging to a user as stateful Block objects.

        Args:
            user_id: Owner user ID.

        Returns:
            List of Block instances.
        """
        docs = await self._mongo.list_user_blocks(user_id)
        return [self._doc_to_block(doc) for doc in docs]

    async def delete_block(self, block_id: str, user_id: str) -> bool:
        """
        Delete a memory block.

        Args:
            block_id: Block identifier.
            user_id: Owner user ID.

        Returns:
            True if deletion was successful.
        """
        return await self._mongo.delete_memory_block(block_id)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _make_semantic_service(self, collection_name: str) -> "SemanticMemoryService":
        """Construct a SemanticMemoryService scoped to a specific collection."""
        from memblocks.services.semantic_memory import SemanticMemoryService

        return SemanticMemoryService(
            llm_provider=self._llm,
            embedding_provider=self._embeddings,
            qdrant_adapter=self._qdrant,
            collection_name=collection_name,
            config=self._config,
            operation_log=self._log,
            retrieval_log=self._retrieval_log,
            event_bus=self._bus,
        )

    def _make_block(
        self,
        block_id: str,
        name: str,
        description: str,
        user_id: str,
        semantic_collection: Optional[str],
        core_memory_block_id: Optional[str],
        resource_collection: Optional[str],
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ) -> "Block":
        """Build a wired Block object from raw fields."""
        semantic_svc = (
            self._make_semantic_service(semantic_collection)
            if semantic_collection
            else self._make_semantic_service("")
        )
        return Block(
            block_id=block_id,
            name=name,
            description=description,
            user_id=user_id,
            semantic_memory_service=semantic_svc,
            core_memory_service=self._core,
            semantic_collection=semantic_collection,
            core_memory_block_id=core_memory_block_id,
            resource_collection=resource_collection,
            created_at=created_at,
            updated_at=updated_at,
            retrieval_top_k=self._top_k,
        )

    def _doc_to_block(self, doc: Dict[str, Any]) -> "Block":
        """Convert a raw MongoDB document to a stateful Block instance."""
        meta = doc.get("meta_data", {})
        return self._make_block(
            block_id=doc.get("block_id") or meta.get("id", ""),
            name=doc.get("name", ""),
            description=doc.get("description", ""),
            user_id=doc.get("user_id") or meta.get("user_id", ""),
            semantic_collection=doc.get("semantic_collection"),
            core_memory_block_id=doc.get("core_memory_block_id"),
            resource_collection=doc.get("resource_collection"),
            created_at=doc.get("created_at") or meta.get("created_at"),
            updated_at=doc.get("updated_at") or meta.get("updated_at"),
        )
