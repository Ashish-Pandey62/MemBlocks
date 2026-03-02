"""CoreMemoryService — extracted from models/sections.py CoreMemorySection."""

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from memblocks.models.llm_outputs import CoreMemoryOutput
from memblocks.models.units import CoreMemoryUnit
from memblocks.prompts import CORE_MEMORY_PROMPT

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig
    from memblocks.llm.base import LLMProvider
    from memblocks.storage.mongo import MongoDBAdapter
    from memblocks.services.transparency import OperationLog


class CoreMemoryService:
    """
    Handles all core memory operations:
    - LLM-based extraction from conversation history
    - Persistence in MongoDB (always retrieved in full, no vector search)
    - Retrieval for context assembly

    Replaces:
    - CoreMemorySection.create_new_core_memory() (sections.py:425-485)
    - CoreMemorySection.store_memory() (sections.py:487-507)
    - CoreMemorySection.get_memories() (sections.py:509-529)
    """

    def __init__(
        self,
        llm_provider: "LLMProvider",
        mongo_adapter: "MongoDBAdapter",
        config: "MemBlocksConfig",
        operation_log: Optional["OperationLog"] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """
        Args:
            llm_provider: LLM abstraction for core memory extraction chain.
            mongo_adapter: MongoDB adapter for persistence.
            config: Library configuration (temperatures etc.).
            operation_log: Phase-9 transparency placeholder.
            event_bus: Phase-9 event publishing placeholder.
        """
        self._llm = llm_provider
        self._mongo = mongo_adapter
        self._config = config
        self._log = operation_log
        self._bus = event_bus

    # ------------------------------------------------------------------ #
    # Extraction
    # ------------------------------------------------------------------ #

    async def extract(
        self,
        messages: List[Dict[str, str]],
        old_core_memory: Optional[CoreMemoryUnit] = None,
        core_creation_prompt: str = CORE_MEMORY_PROMPT,
    ) -> CoreMemoryUnit:
        """
        Create an updated CoreMemoryUnit from conversation messages and previous state.

        Uses LLM to generate replacement persona and human paragraphs.

        Mirrors CoreMemorySection.create_new_core_memory() (sections.py:425-485).

        Args:
            messages: Recent conversation messages.
            old_core_memory: Previous core memory (None if first extraction).
            core_creation_prompt: System prompt for core memory extraction.

        Returns:
            New CoreMemoryUnit with updated persona and human content.
        """
        conversation_text = "\n".join(
            [f"{msg['role'].upper()}: {msg['content']}\n" for msg in messages]
        )

        old_persona = old_core_memory.persona_content if old_core_memory else ""
        old_human = old_core_memory.human_content if old_core_memory else ""

        user_input = (
            f"Current Core Memory:\n"
            f"PERSONA: {old_persona}\n"
            f"HUMAN: {old_human}\n\n"
            f"Recent Conversation:\n{conversation_text}\n\n"
            f"Generate updated core memory paragraphs that incorporate new stable facts."
        )

        try:
            chain = self._llm.create_structured_chain(
                system_prompt=core_creation_prompt,
                pydantic_model=CoreMemoryOutput,
                temperature=self._config.llm_core_extraction_temperature,
            )
            result = await chain.ainvoke({"input": user_input})

            return CoreMemoryUnit(
                persona_content=result.persona_content,
                human_content=result.human_content,
            )

        except Exception as e:
            print(f"[WARN] Failed to extract core memory: {e}")
            # Return old core memory or empty if extraction fails
            if old_core_memory:
                return old_core_memory
            return CoreMemoryUnit(persona_content="", human_content="")

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    async def save(self, block_id: str, memory_unit: CoreMemoryUnit) -> bool:
        """
        Store CoreMemoryUnit in MongoDB, replacing the previous version.

        Mirrors CoreMemorySection.store_memory() (sections.py:487-507).

        Args:
            block_id: The memory block ID (used as the document key).
            memory_unit: The core memory unit to store.

        Returns:
            True if storage was successful.
        """
        try:
            await self._mongo.save_core_memory(
                block_id=block_id,
                persona_content=memory_unit.persona_content,
                human_content=memory_unit.human_content,
            )
            return True
        except Exception as e:
            print(f"[WARN] Failed to store core memory: {e}")
            return False

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #

    async def get(self, block_id: str) -> Optional[CoreMemoryUnit]:
        """
        Retrieve core memory for a block from MongoDB.

        Core memories are always retrieved in full (no vector search needed).

        Mirrors CoreMemorySection.get_memories() (sections.py:509-529).

        Args:
            block_id: The memory block ID.

        Returns:
            CoreMemoryUnit or None if not found.
        """
        try:
            doc = await self._mongo.get_core_memory(block_id)
            if doc:
                return CoreMemoryUnit(
                    persona_content=doc.get("persona_content", ""),
                    human_content=doc.get("human_content", ""),
                )
            return None
        except Exception as e:
            print(f"[WARN] Failed to retrieve core memory: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Convenience: extract + save in one call
    # ------------------------------------------------------------------ #

    async def update(
        self,
        block_id: str,
        messages: List[Dict[str, str]],
        core_creation_prompt: str = CORE_MEMORY_PROMPT,
    ) -> CoreMemoryUnit:
        """
        Extract and immediately persist updated core memory.

        Args:
            block_id: The memory block ID.
            messages: Recent conversation messages.
            core_creation_prompt: System prompt for core memory extraction.

        Returns:
            The newly extracted and saved CoreMemoryUnit.
        """
        old_core = await self.get(block_id)
        new_core = await self.extract(messages, old_core, core_creation_prompt)
        await self.save(block_id, new_core)
        return new_core
