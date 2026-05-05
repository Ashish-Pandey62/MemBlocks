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
        block_clients = {}  # Cache block clients per session

        for session in sessions:
            session_results = {
                "session_id": session.session_id,
                "questions_evaluated": len(session.questions),
                "messages_processed": len(session.messages),
                "evaluations": []
            }

            # --- Task 1: Session Ingestion (PIPE-01) ---
            try:
                # Create isolated MemBlocks block per session
                block_id = f"locomo-session-{session.session_id}"
                # Initialize MemBlocksClient with default config for this block
                block_config = MemBlocksConfig(block_id=block_id)
                block_client = MemBlocksClient(config=block_config)
                block_clients[session.session_id] = block_client

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

            for question in session.questions:
                # Stub out open-ended generation evaluation for now
                eval_result = {
                    "question": question.question,
                    "expected_answer": question.answer,
                    "category": question.category,
                    "status": "pending_implementation",
                    "retrieved_context_semantic": None,
                    "retrieved_context_core": None,
                    "retrieved_context_hybrid": None
                }
                session_results["evaluations"].append(eval_result)
            
            results.append(session_results)

        return {"sessions_processed": len(sessions), "details": results}

    def run(self, output_dir: Path) -> Dict[str, Any]:
        """Execute the LoCoMo evaluation pipeline."""
        return asyncio.run(self._run_async(output_dir))
