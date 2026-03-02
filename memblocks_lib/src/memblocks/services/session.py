"""Session — stateful object returned from client.create_session() / client.get_session().

Users interact with the conversation window through this object:

    messages = await session.get_memory_window()
    summary  = await session.get_recursive_summary()

    # After the user runs their own LLM:
    await session.add(user_msg="...", ai_response="...")
    # or in the background:
    asyncio.create_task(session.add(user_msg="...", ai_response="..."))
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from memblocks.services.memory_pipeline import MemoryPipeline
    from memblocks.storage.mongo import MongoDBAdapter


class Session:
    """
    Stateful handle to a conversation session.

    Returned by:
        client.create_session(user_id, block_id)
        client.get_session(session_id)

    Manages the message window and rolling recursive summary.  The user calls
    ``session.add(user_msg, ai_response)`` after their own LLM returns, which
    persists the turn and triggers the memory pipeline when the window is full.

    Attributes:
        id:         Session ID (e.g. "session_a1b2c3d4").
        user_id:    Owner user ID.
        block_id:   Associated memory block ID.
        created_at: ISO 8601 creation timestamp.
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        block_id: str,
        mongo: "MongoDBAdapter",
        pipeline: "MemoryPipeline",
        memory_window: int = 10,
        keep_last_n: int = 5,
        created_at: Optional[str] = None,
    ) -> None:
        self.id = session_id
        self.user_id = user_id
        self.block_id = block_id
        self.created_at = created_at or datetime.utcnow().isoformat()

        self._mongo = mongo
        self._pipeline = pipeline
        self._memory_window = memory_window
        self._keep_last_n = keep_last_n

    # ------------------------------------------------------------------ #
    # Memory window
    # ------------------------------------------------------------------ #

    async def get_memory_window(self) -> List[Dict[str, Any]]:
        """
        Return the current message window from MongoDB.

        After a pipeline flush, the window is trimmed to the last
        ``keep_last_n`` messages.  Each message is a dict with at minimum:
            {"role": "user" | "assistant", "content": "..."}

        Returns:
            List of message dicts in chronological order.
        """
        return await self._mongo.get_session_messages(
            self.id, limit=self._memory_window
        )

    # ------------------------------------------------------------------ #
    # Recursive summary
    # ------------------------------------------------------------------ #

    async def get_recursive_summary(self) -> str:
        """
        Return the persisted rolling recursive summary for this session.

        The summary is updated after every memory pipeline run and stored
        in MongoDB so it survives process restarts.

        Returns:
            Summary string, or empty string if no pipeline run has occurred yet.
        """
        return await self._mongo.get_session_summary(self.id)

    # ------------------------------------------------------------------ #
    # Add turn
    # ------------------------------------------------------------------ #

    async def add(self, user_msg: str, ai_response: str) -> None:
        """
        Persist a conversation turn and trigger memory management if needed.

        Steps:
        1. Append user message to MongoDB session.
        2. Append assistant message to MongoDB session.
        3. Count total messages.
        4. If count >= memory_window:
           a. Snapshot current messages.
           b. Fetch current recursive summary.
           c. Run the memory pipeline (semantic + core + summary).
           d. Persist new summary to session document in MongoDB.
           e. Trim session messages in MongoDB to last keep_last_n.

        The user decides whether to await this coroutine directly or schedule
        it as a background task via asyncio.create_task(session.add(...)).

        Args:
            user_msg:    The user's message text.
            ai_response: The assistant's response text.

        Raises:
            Any exception raised by the memory pipeline propagates to the caller.
        """
        now = datetime.utcnow().isoformat()

        await self._mongo.add_message_to_session(
            self.id,
            {"role": "user", "content": user_msg, "timestamp": now},
        )
        await self._mongo.add_message_to_session(
            self.id,
            {"role": "assistant", "content": ai_response, "timestamp": now},
        )

        msg_count = await self._mongo.get_session_message_count(self.id)

        if msg_count >= self._memory_window:
            # Snapshot the full window for the pipeline
            messages = await self._mongo.get_session_messages(self.id, limit=msg_count)
            current_summary = await self._mongo.get_session_summary(self.id)

            new_summary = await self._pipeline.run(
                user_id=self.user_id,
                block_id=self.block_id,
                messages=messages,
                current_summary=current_summary,
            )

            # Persist updated summary and trim messages
            await self._mongo.set_session_summary(self.id, new_summary)
            await self._mongo.trim_session_messages(self.id, self._keep_last_n)
            print(
                f"   [OK] Session {self.id}: flushed ({msg_count} -> {self._keep_last_n} messages)"
            )

    # ------------------------------------------------------------------ #
    # Repr
    # ------------------------------------------------------------------ #

    def __repr__(self) -> str:
        return (
            f"Session(id={self.id!r}, user_id={self.user_id!r}, "
            f"block_id={self.block_id!r})"
        )
