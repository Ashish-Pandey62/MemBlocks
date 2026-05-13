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

        # For this skeleton, we're just going to log what would be evaluated
        # This will be replaced with actual model calls later.
        for session in sessions:
            session_results = {
                "session_id": session.session_id,
                "questions_evaluated": len(session.questions),
                "messages_processed": len(session.messages),
                "evaluations": []
            }

            for question in session.questions:
                # Stub out open-ended generation evaluation
                eval_result = {
                    "question": question.question,
                    "expected_answer": question.answer,
                    "category": question.category,
                    "status": "pending_implementation"
                }
                session_results["evaluations"].append(eval_result)
            
            results.append(session_results)

        return {"sessions_processed": len(sessions), "details": results}

    def run(self, output_dir: Path) -> Dict[str, Any]:
        """Execute the LoCoMo evaluation pipeline."""
        return asyncio.run(self._run_async(output_dir))
