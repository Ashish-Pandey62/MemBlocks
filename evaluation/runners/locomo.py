"""LoCoMo specific evaluation runner."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List

from evaluation.core.config import RunnerConfig
from evaluation.datasets.locomo import LocomoDataset, LocomoSession
from evaluation.runners.base import BaseRunner

try:
    from memblocks import MemBlocksClient, MemBlocksConfig
except ImportError:
    pass # Stub if not running inside MemBlocks environment


class LocomoRunner(BaseRunner):
    """Runner for evaluating MemBlocks on the LoCoMo dataset."""

    def __init__(self, config: RunnerConfig, dataset: LocomoDataset) -> None:
        super().__init__(config, dataset)
        self.dataset = dataset

    async def _run_async(self, output_dir: Path) -> Dict[str, Any]:
        sessions = self.dataset.load()
        results = []

        for session in sessions:
            session_results = {
                "session_id": session.session_id,
                "questions_evaluated": len(session.questions),
                "messages_processed": len(session.messages),
                "evaluations": []
            }

            # --- Task 1: Session Ingestion (PIPE-01) ---
            block_client = None
            try:
                # Create isolated MemBlocks block per session
                block_id = f"locomo-session-{session.session_id}"
                # Initialize MemBlocksClient with default config for this block
                block_config = MemBlocksConfig(block_id=block_id)
                block_client = MemBlocksClient(config=block_config)

                # Ingest messages sequentially: add + flush per message
                for message in session.messages:
                    block_client.session.add(message)
                    block_client.session.flush()

                session_results["ingestion_status"] = "success"
                session_results["block_id"] = block_id

            except Exception as e:
                # Handle MemBlocks connection/issues gracefully
                session_results["ingestion_status"] = f"failed: {str(e)}"
                session_results["block_id"] = None
            # --- End Task 1 ---

            # --- Task 2: Multi-Strategy Context Retrieval (PIPE-02) ---
            for question in session.questions:
                eval_result = {
                    "question": question.question,
                    "expected_answer": question.answer,
                    "category": question.category,
                    "status": "pending_implementation",
                    "retrieved_context_semantic": None,
                    "retrieved_context_core": None,
                    "retrieved_context_hybrid": None
                }

                # Only attempt retrieval if ingestion succeeded and we have a block client
                if block_client is not None:
                    try:
                        # Retrieve context using all 3 strategies with top_k=5
                        semantic_context = self._retrieve_context(
                            question.question, block_client, strategy="semantic"
                        )
                        core_context = self._retrieve_context(
                            question.question, block_client, strategy="core"
                        )
                        hybrid_context = self._retrieve_context(
                            question.question, block_client, strategy="hybrid"
                        )

                        eval_result["retrieved_context_semantic"] = semantic_context
                        eval_result["retrieved_context_core"] = core_context
                        eval_result["retrieved_context_hybrid"] = hybrid_context
                        eval_result["status"] = "retrieval_success"
                    except Exception as e:
                        eval_result["status"] = f"retrieval_failed: {str(e)}"
                else:
                    eval_result["status"] = "skipped_no_block_client"

                session_results["evaluations"].append(eval_result)
            # --- End Task 2 ---

            results.append(session_results)

        return {"sessions_processed": len(sessions), "details": results}

    def _retrieve_context(self, question_text: str, block_client: "MemBlocksClient", strategy: str) -> Any:
        """Retrieve context from MemBlocks using specified strategy.
        
        Args:
            question_text: The question to retrieve context for
            block_client: MemBlocksClient for the session's block
            strategy: Retrieval strategy ("semantic", "core", "hybrid")
            
        Returns:
            Retrieved context from MemBlocks
        """
        return block_client.retrieve(question_text, strategy=strategy, top_k=5)

    def run(self, output_dir: Path) -> Dict[str, Any]:
        """Execute the LoCoMo evaluation pipeline."""
        return asyncio.run(self._run_async(output_dir))
