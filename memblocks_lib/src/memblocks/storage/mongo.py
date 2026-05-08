"""MongoDBAdapter — non-singleton, config-injected MongoDB layer."""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig
    from memblocks.services.transparency import OperationLog
    from memblocks.models.transparency import DBType, OperationEntry, OperationType


class MongoDBAdapter:
    """
    Async MongoDB adapter for users, blocks, core memories, and sessions.

    Replaces: ``vector_db/mongo_manager.py`` → ``MongoDBManager`` (singleton).
    Also replaces: ``services/background_utils.py`` → ``BackgroundMongoDBManager``
    (that class existed solely because the singleton couldn't be shared across
    event loops).

    Changes from MongoDBManager:
    - No ``__new__`` singleton override.
    - Constructor takes ``MemBlocksConfig`` instead of reading the global
      ``settings`` object (mongo_manager.py:42).
    - Database name comes from ``config.mongodb_database_name`` instead of
      the hardcoded ``self._client.memblocks`` (mongo_manager.py:47).
    - Collection names come from config instead of being hardcoded attribute names
      (mongo_manager.py:50-52).
    - All 10+ async methods preserved with the same signatures.
    - New session-related methods added (needed by SessionManager in Phase 7).
    """

    def __init__(
        self,
        config: "MemBlocksConfig",
        operation_log: Optional["OperationLog"] = None,
    ) -> None:
        """
        Args:
            config: Library configuration. Reads connection string, database
                    name, and collection names from it.
            operation_log: Optional transparency log. When provided, each
                           write operation is recorded before it executes.
                           (Phase 9 will wire this fully — for now it is a
                           placeholder parameter.)
        """
        connection_string = config.mongodb_connection_string
        if not connection_string:
            raise ValueError(
                "MONGODB_CONNECTION_STRING not found in environment variables"
            )

        self._client: AsyncIOMotorClient = AsyncIOMotorClient(connection_string)
        self._db = self._client[config.mongodb_database_name]
        self._log: Optional["OperationLog"] = operation_log

        # Collections — names from config (previously hardcoded in mongo_manager.py:50-52)
        self.users = self._db[config.mongo_collection_users]
        self.blocks = self._db[config.mongo_collection_blocks]
        self.core_memories = self._db[config.mongo_collection_core_memories]

        # New: sessions collection (supports SessionManager in Phase 7)
        self.sessions = self._db["sessions"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _serialize_doc(doc: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Convert ObjectId fields to strings so documents are JSON-serializable.

        Mirrors ``MongoDBManager._serialize_doc()`` (mongo_manager.py:26-38).
        """
        if doc is None:
            return None
        doc = dict(doc)
        if "_id" in doc:
            doc["id"] = str(doc.pop("_id"))
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                doc[key] = str(value)
        return doc

    def _record_op(
        self,
        collection_name: str,
        operation_type: str,
        document_id: Optional[str] = None,
        payload_summary: str = "",
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """Record a write operation in the OperationLog (no-op if log not set)."""
        if self._log is None:
            return
        from memblocks.models.transparency import DBType, OperationEntry, OperationType

        self._log.record(
            OperationEntry(
                db_type=DBType.MONGO,
                collection_name=collection_name,
                operation_type=OperationType(operation_type),
                document_id=document_id,
                payload_summary=payload_summary,
                success=success,
                error=error,
            )
        )

    # ------------------------------------------------------------------
    # USER OPERATIONS
    # Mirrors mongo_manager.py lines 58-115
    # ------------------------------------------------------------------

    async def create_user(
        self,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create a new user.

        Args:
            user_id: Unique user identifier.
            metadata: Optional user metadata dict.

        Returns:
            Created user document with ``id`` field (string).
        """
        user_doc = {
            "user_id": user_id,
            "block_ids": [],
            "created_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }
        result = await self.users.insert_one(user_doc)
        user_doc["id"] = str(result.inserted_id)
        user_doc.pop("_id", None)
        self._record_op(
            "users",
            "insert",
            document_id=user_id,
            payload_summary=f"create user {user_id}",
        )
        return user_doc

    async def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by user_id. Returns None if not found."""
        doc = await self.users.find_one({"user_id": user_id})
        return self._serialize_doc(doc)

    async def add_block_to_user(self, user_id: str, block_id: str) -> bool:
        """
        Add a block ID to the user's ``block_ids`` list (deduplicates via $addToSet).

        Returns:
            True if the document was matched (regardless of whether it was
            actually modified — the block may already have been listed).
        """
        result = await self.users.update_one(
            {"user_id": user_id},
            {"$addToSet": {"block_ids": block_id}},
        )
        self._record_op(
            "users",
            "update",
            document_id=user_id,
            payload_summary=f"add block {block_id} to user",
        )
        return result.modified_count > 0 or result.matched_count > 0

    async def list_users(self) -> List[Dict[str, Any]]:
        """Return all user documents."""
        cursor = self.users.find({})
        docs = await cursor.to_list(length=None)
        return [self._serialize_doc(doc) for doc in docs]

    # ------------------------------------------------------------------
    # BLOCK OPERATIONS
    # Mirrors mongo_manager.py lines 121-186
    # ------------------------------------------------------------------

    async def save_block(self, block_data: Dict[str, Any]) -> str:
        """
        Upsert a memory block document.

        Args:
            block_data: Full block document including ``meta_data.id``.

        Returns:
            Block ID string.
        """
        block_data["meta_data"]["updated_at"] = datetime.utcnow().isoformat()
        block_id: str = block_data["meta_data"]["id"]
        await self.blocks.replace_one(
            {"meta_data.id": block_id},
            block_data,
            upsert=True,
        )
        self._record_op(
            "memory_blocks",
            "upsert",
            document_id=block_id,
            payload_summary=f"save block {block_id}",
        )
        return block_id

    async def create_memory_block(
        self,
        user_id: str,
        block_data: Dict[str, Any],
    ) -> str:
        """
        Insert a new memory block document for a user.

        Args:
            user_id: Owner user ID (stored in block_data but logged here).
            block_data: Full block document including ``block_id`` key.

        Returns:
            Block ID string.
        """
        result = await self.blocks.insert_one(block_data)
        block_id: str = block_data.get("block_id", str(result.inserted_id))
        self._record_op(
            "memory_blocks",
            "insert",
            document_id=block_id,
            payload_summary=f"create block {block_id} for user {user_id}",
        )
        return block_id

    async def get_memory_block(self, block_id: str) -> Optional[Dict[str, Any]]:
        """
        Load a memory block by block_id.

        Args:
            block_id: The block identifier (stored as ``block_id`` field).

        Returns:
            Serialised block document or None.
        """
        doc = await self.blocks.find_one({"block_id": block_id})
        return self._serialize_doc(doc)

    async def delete_memory_block(self, block_id: str) -> bool:
        """
        Delete a memory block document.

        Args:
            block_id: The block identifier.

        Returns:
            True if a document was deleted.
        """
        result = await self.blocks.delete_one({"block_id": block_id})
        if result.deleted_count > 0:
            self._record_op(
                "memory_blocks",
                "delete",
                document_id=block_id,
                payload_summary=f"delete block {block_id}",
            )
        return result.deleted_count > 0

    async def load_block(self, block_id: str) -> Optional[Dict[str, Any]]:
        """Load a block by its meta_data.id. Returns None if not found."""
        doc = await self.blocks.find_one({"meta_data.id": block_id})
        return self._serialize_doc(doc)

    async def list_user_blocks(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Return all blocks belonging to a user.

        Looks up the user document first to get ``block_ids``, then fetches
        all matching blocks in one query.
        """
        user = await self.get_user(user_id)
        if not user or not user.get("block_ids"):
            return []
        cursor = self.blocks.find({"meta_data.id": {"$in": user["block_ids"]}})
        docs = await cursor.to_list(length=None)
        return [self._serialize_doc(doc) for doc in docs]

    async def delete_block(self, block_id: str) -> bool:
        """Delete a block by ID. Returns True if a document was deleted."""
        result = await self.blocks.delete_one({"meta_data.id": block_id})
        return result.deleted_count > 0

    # ------------------------------------------------------------------
    # CORE MEMORY OPERATIONS
    # Mirrors mongo_manager.py lines 192-253
    # ------------------------------------------------------------------

    async def save_core_memory(
        self,
        block_id: str,
        persona_content: str,
        human_content: str,
    ) -> str:
        """
        Upsert core memory for a block.

        Args:
            block_id: The block this core memory belongs to.
            persona_content: Persona paragraph text.
            human_content: Human facts paragraph text.

        Returns:
            MongoDB ObjectId of the core memory document as a string.
        """
        core_memory_doc = {
            "block_id": block_id,
            "persona_content": persona_content,
            "human_content": human_content,
            "updated_at": datetime.utcnow().isoformat(),
        }
        result = await self.core_memories.replace_one(
            {"block_id": block_id},
            core_memory_doc,
            upsert=True,
        )
        if result.upserted_id:
            doc_id = str(result.upserted_id)
            self._record_op(
                "core_memories",
                "insert",
                document_id=block_id,
                payload_summary=f"create core memory for block {block_id}",
            )
            return doc_id
        # Retrieve the existing document id
        doc = await self.core_memories.find_one({"block_id": block_id})
        self._record_op(
            "core_memories",
            "update",
            document_id=block_id,
            payload_summary=f"update core memory for block {block_id}",
        )
        return str(doc["_id"])

    async def get_core_memory(self, block_id: str) -> Optional[Dict[str, Any]]:
        """Return the core memory document for a block, or None if absent."""
        doc = await self.core_memories.find_one({"block_id": block_id})
        return self._serialize_doc(doc)

    async def delete_core_memory(self, block_id: str) -> bool:
        """Delete core memory for a block. Returns True if deleted."""
        result = await self.core_memories.delete_one({"block_id": block_id})
        if result.deleted_count > 0:
            self._record_op(
                "core_memories",
                "delete",
                document_id=block_id,
                payload_summary=f"delete core memory for block {block_id}",
            )
        return result.deleted_count > 0

    # ------------------------------------------------------------------
    # SESSION OPERATIONS
    # New — not in MongoDBManager. Supports SessionManager (Phase 7).
    # ------------------------------------------------------------------

    async def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert a new session document.

        Args:
            session_data: Dict containing at minimum ``session_id``,
                          ``user_id``, and ``created_at``.

        Returns:
            Inserted document with ``id`` field added.
        """
        result = await self.sessions.insert_one(session_data)
        session_data["id"] = str(result.inserted_id)
        session_data.pop("_id", None)
        return session_data

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a session by its session_id. Returns None if not found."""
        doc = await self.sessions.find_one({"session_id": session_id})
        return self._serialize_doc(doc)

    async def update_session(
        self,
        session_id: str,
        update_data: Dict[str, Any],
    ) -> bool:
        """
        Apply a ``$set`` update to a session document.

        Returns:
            True if a document was matched and updated.
        """
        result = await self.sessions.update_one(
            {"session_id": session_id},
            {"$set": update_data},
        )
        return result.matched_count > 0

    async def add_message_to_session(
        self,
        session_id: str,
        message: Dict[str, Any],
    ) -> None:
        """
        Append a message dict to the session's ``messages`` array.

        Args:
            session_id: The session to update.
            message: Dict with at least ``role`` and ``content`` keys.
        """
        await self.sessions.update_one(
            {"session_id": session_id},
            {"$push": {"messages": message}},
        )

    async def get_session_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Return the last ``limit`` messages for a session.

        Args:
            session_id: The session to query.
            limit: Maximum number of messages to return (most recent first).

        Returns:
            List of message dicts in chronological order.
        """
        doc = await self.sessions.find_one({"session_id": session_id})
        if not doc:
            return []
        messages: List[Dict[str, Any]] = doc.get("messages", [])
        # Return the last `limit` messages
        return messages[-limit:] if len(messages) > limit else messages

    async def get_session_message_count(self, session_id: str) -> int:
        """Return the number of messages stored for a session."""
        doc = await self.sessions.find_one(
            {"session_id": session_id},
            {"messages": 1},
        )
        if not doc:
            return 0
        return len(doc.get("messages", []))

    async def clear_session_messages(self, session_id: str) -> None:
        """Clear all messages in a session (called after pipeline flushes a window)."""
        await self.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"messages": []}},
        )

    async def trim_session_messages(self, session_id: str, keep_last_n: int) -> None:
        """
        Trim the session's messages array in MongoDB, keeping only the last
        ``keep_last_n`` messages.

        Called by Session.add() after the memory pipeline completes, so the
        DB stays in sync with what the user sees via get_memory_window().

        Args:
            session_id: The session to trim.
            keep_last_n: Number of most-recent messages to retain.
        """
        doc = await self.sessions.find_one({"session_id": session_id}, {"messages": 1})
        if not doc:
            return
        messages: List[Dict[str, Any]] = doc.get("messages", [])
        if keep_last_n <= 0:
            trimmed = []
        else:
            trimmed = messages[-keep_last_n:] if len(messages) > keep_last_n else messages
        await self.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"messages": trimmed}},
        )

    async def set_session_summary(self, session_id: str, summary: str) -> None:
        """
        Persist the rolling recursive summary for a session.

        Stored as the ``recursive_summary`` field on the session document so
        it survives process restarts.

        Args:
            session_id: The session to update.
            summary: New summary string.
        """
        await self.sessions.update_one(
            {"session_id": session_id},
            {"$set": {"recursive_summary": summary}},
        )

    async def get_session_summary(self, session_id: str) -> str:
        """
        Retrieve the persisted recursive summary for a session.

        Args:
            session_id: The session to query.

        Returns:
            Summary string, or empty string if not yet set.
        """
        doc = await self.sessions.find_one(
            {"session_id": session_id}, {"recursive_summary": 1}
        )
        if not doc:
            return ""
        return doc.get("recursive_summary", "")

    # ------------------------------------------------------------------
    # UTILITY
    # ------------------------------------------------------------------

    async def update_block_llm_usage(
        self, block_id: str, usage_dict: Dict[str, Any]
    ) -> bool:
        """
        Persist cumulative LLM usage statistics into the block document.

        Uses a MongoDB ``$set`` so that repeated calls accumulate the latest
        snapshot without replacing the whole document.

        Args:
            block_id: The block identifier (matched on ``meta_data.id``).
            usage_dict: Serialisable dict produced by
                ``LLMUsageTracker.get_block_summary(block_id)`` — keyed by
                ``LLMCallType`` value strings.

        Returns:
            True if a document was matched (and possibly updated).
        """
        result = await self.blocks.update_one(
            {"meta_data.id": block_id},
            {"$set": {"meta_data.llm_usage": usage_dict}},
        )
        self._record_op(
            "memory_blocks",
            "update",
            document_id=block_id,
            payload_summary=f"update llm_usage for block {block_id}",
        )
        return result.matched_count > 0

    async def close(self) -> None:
        """Close the underlying Motor client connection."""
        if self._client:
            self._client.close()
