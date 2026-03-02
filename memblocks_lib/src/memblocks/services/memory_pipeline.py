"""MemoryPipeline — memory processing pipeline called explicitly by Session.add()."""

from datetime import datetime
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from memblocks.models.llm_outputs import SummaryOutput
from memblocks.models.units import MemoryOperation, ProcessingEvent, SemanticMemoryUnit
from memblocks.prompts import SUMMARY_SYSTEM_PROMPT

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig
    from memblocks.llm.base import LLMProvider
    from memblocks.services.core_memory import CoreMemoryService
    from memblocks.services.semantic_memory import SemanticMemoryService
    from memblocks.services.transparency import OperationLog, ProcessingHistory


class MemoryPipeline:
    """
    Orchestrates the full memory processing pipeline.

    Called explicitly via ``await pipeline.run(...)`` from ``Session.add()``.
    The caller decides whether to await inline or schedule as a background task
    via ``asyncio.create_task(session.add(...))``.

    Pipeline steps:
    1. Semantic memory extraction (PS1) + conflict resolution (PS2) + storage.
    2. Core memory update.
    3. Recursive summary generation.

    Post-run state management (session messages + summary) is handled by the
    caller (Session.add()) after this coroutine returns, so this class has no
    knowledge of session IDs or MongoDB session documents.
    """

    def __init__(
        self,
        semantic_memory_service: "SemanticMemoryService",
        core_memory_service: "CoreMemoryService",
        llm_provider: "LLMProvider",
        config: "MemBlocksConfig",
        processing_history: Optional["ProcessingHistory"] = None,
        operation_log: Optional["OperationLog"] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """
        Args:
            semantic_memory_service: Handles semantic extraction/storage.
            core_memory_service: Handles core memory updates.
            llm_provider: LLM for summary generation.
            config: Library configuration (temperatures etc.).
            processing_history: Transparency — records pipeline runs.
            operation_log: Transparency — records DB writes.
            event_bus: Transparency — publishes pipeline events.
        """
        self._semantic = semantic_memory_service
        self._core = core_memory_service
        self._llm = llm_provider
        self._config = config
        self._history = processing_history
        self._log = operation_log
        self._bus = event_bus

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def run(
        self,
        user_id: str,
        block_id: str,
        messages: List[Dict[str, str]],
        current_summary: str = "",
    ) -> str:
        """
        Execute the full pipeline and return the new recursive summary.

        This is a plain coroutine — the caller (Session.add) decides whether
        to await it directly or wrap it in asyncio.create_task().

        Steps:
        1. Semantic extraction (PS1) + conflict resolution (PS2) + storage.
        2. Core memory update.
        3. Recursive summary generation.

        Args:
            user_id: Owner user ID (used for transparency logging).
            block_id: Active memory block ID.
            messages: Snapshot of the message window to process.
            current_summary: Current recursive summary (empty string if none).

        Returns:
            New recursive summary string.
        """
        run_id = f"pipeline_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"

        if self._history:
            self._history.record_start(
                task_id=run_id,
                trigger_event="message_window_full",
                message_count=len(messages),
            )
        if self._bus:
            self._bus.publish(
                "on_pipeline_started",
                {"run_id": run_id, "message_count": len(messages)},
            )

        print(f"\n[RUN] MEMORY PIPELINE START ({run_id})")
        print(f"   Processing {len(messages)} messages for block {block_id}...")

        all_operations: List[MemoryOperation] = []

        try:
            # ---- STEP 1: Semantic Memory ----
            print("   -- STEP 1: Semantic Extraction...")
            semantic_memories = await self._semantic.extract(messages)
            print(f"   [OK] Extracted {len(semantic_memories)} semantic memories")

            for mem in semantic_memories:
                ops = await self._semantic.store(mem)
                all_operations.extend(ops)
            print(
                f"   [OK] Stored semantic memories ({len(all_operations)} operations)"
            )

            # ---- STEP 2: Core Memory ----
            print("   -- STEP 2: Core Memory Update...")
            await self._core.update(block_id=block_id, messages=messages)
            print("   [OK] Core memory updated")

            # ---- STEP 3: Recursive Summary ----
            print("   -- STEP 3: Recursive Summary Generation...")
            new_summary = await self._generate_summary(messages, current_summary)
            print("   [OK] Summary generated")

            # Transparency
            ProcessingEvent(
                messages_processed=len(messages),
                operations=all_operations,
            )
            if self._history:
                self._history.record_complete(
                    run_id,
                    {
                        "summary_generated": bool(new_summary),
                        "core_memory_updated": True,
                        "semantic_ops": len(all_operations),
                    },
                )
            if self._bus:
                self._bus.publish("on_pipeline_completed", {"run_id": run_id})

            print(f"[OK] MEMORY PIPELINE COMPLETE ({run_id})")
            return new_summary

        except Exception as exc:
            if self._history:
                self._history.record_failure(run_id, str(exc))
            if self._bus:
                self._bus.publish(
                    "on_pipeline_failed",
                    {"run_id": run_id, "error": str(exc)},
                )
            print(f"[ERR] Memory pipeline failed ({run_id}): {exc}")
            raise

    # ------------------------------------------------------------------ #
    # Summary generation
    # ------------------------------------------------------------------ #

    async def _generate_summary(
        self,
        messages: List[Dict[str, str]],
        previous_summary: str,
    ) -> str:
        """
        Generate a recursive summary that incorporates the current message window.

        Args:
            messages: Message window being processed.
            previous_summary: Existing recursive summary (empty string if none).

        Returns:
            Updated summary string. Falls back to previous_summary on error.
        """
        conversation_text = "\n".join(
            [f"{msg['role'].upper()}: {msg['content']}\n" for msg in messages]
        )

        user_input = (
            f"Previous Summary:\n"
            f"{previous_summary if previous_summary else 'None'}\n\n"
            f"Recent Conversation:\n{conversation_text}\n\n"
            f"Generate an updated recursive summary that incorporates the new conversation."
        )

        try:
            chain = self._llm.create_structured_chain(
                system_prompt=SUMMARY_SYSTEM_PROMPT,
                pydantic_model=SummaryOutput,
                temperature=self._config.llm_recursive_summary_gen_temperature,
            )
            result = await chain.ainvoke({"input": user_input})
            return result.summary

        except Exception as e:
            print(f"[WARN] Failed to generate summary: {e}")
            return previous_summary
