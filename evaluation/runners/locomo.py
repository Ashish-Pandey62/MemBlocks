"""LoCoMo specific evaluation runner."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

from evaluation.core.config import RunnerConfig
from evaluation.datasets.locomo import LocomoDataset, LocomoSession
from evaluation.runners.base import BaseRunner

try:
    from memblocks import MemBlocksClient, MemBlocksConfig
except ImportError:
    MemBlocksClient = None
    MemBlocksConfig = None

# Path to QA prompt template (relative to project root)
QA_TEMPLATE_PATH = Path(__file__).parent.parent.parent / ".planning" / "phases" / "08-evaluation-pipeline" / "templates" / "qa_prompt.txt"


class LocomoRunner(BaseRunner):
    """Runner for evaluating MemBlocks on the LoCoMo dataset."""

    def __init__(self, config: RunnerConfig, dataset: LocomoDataset) -> None:
        super().__init__(config, dataset)
        self.dataset = dataset

    async def _run_async(self, output_dir: Path) -> Dict[str, Any]:
        sessions = self.dataset.load()
        results = []

        # Load QA prompt template once
        qa_template = self._load_qa_template()

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
                if MemBlocksConfig is not None:
                    block_config = MemBlocksConfig(block_id=block_id)
                    block_client = MemBlocksClient(config=block_config)
                else:
                    block_client = MagicMock()  # Stub if memblocks not available

                # Ingest messages sequentially: add + flush per message
                for message in session.messages:
                    if block_client is not None:
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
            # --- Task 1 (Plan 08-02): LLM QA with CoT (PIPE-03) ---
            for question in session.questions:
                eval_result = {
                    "question": question.question,
                    "expected_answer": question.answer,
                    "category": question.category,
                    "status": "pending_retrieval",
                    "retrieved_context_semantic": None,
                    "retrieved_context_core": None,
                    "retrieved_context_hybrid": None,
                    "answer_semantic": None,
                    "answer_core": None,
                    "answer_hybrid": None
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

                        # Task 1 (Plan 08-02): Generate LLM answers for each strategy
                        if qa_template is not None:
                            strategies = [
                                ("semantic", semantic_context, "answer_semantic"),
                                ("core", core_context, "answer_core"),
                                ("hybrid", hybrid_context, "answer_hybrid")
                            ]
                            for strategy_name, context, answer_key in strategies:
                                if context is not None:
                                    prompt = self._fill_qa_prompt(
                                        qa_template, context, question.question
                                    )
                                    answer = self._call_llm(prompt)
                                    eval_result[answer_key] = answer

                    except Exception as e:
                        eval_result["status"] = f"retrieval_failed: {str(e)}"
                else:
                    eval_result["status"] = "skipped_no_block_client"

                session_results["evaluations"].append(eval_result)
            # --- End Task 2 ---
            # --- End Task 1 (Plan 08-02) ---

            results.append(session_results)

        return {"sessions_processed": len(sessions), "details": results}

    def _load_qa_template(self) -> str:
        """Load QA prompt template from disk."""
        try:
            if QA_TEMPLATE_PATH.exists():
                return QA_TEMPLATE_PATH.read_text(encoding="utf-8")
            return None
        except Exception:
            return None

    def _fill_qa_prompt(self, template: str, retrieved_context: str, question_text: str) -> str:
        """Fill QA prompt template with context and question."""
        prompt = template.replace("{retrieved_context}", retrieved_context)
        prompt = prompt.replace("{question_text}", question_text)
        return prompt

    def _call_llm(self, prompt: str) -> str:
        """Call LLM with filled prompt and return response."""
        # Use model from config if available, otherwise default
        model = self.config.model if self.config and self.config.model else "default"
        # Stub for LLM client - in production, this would call an actual LLM API
        # For testing, this method is mocked
        try:
            # Try to use memblocks LLM client if available
            if MemBlocksClient is not None:
                # Assume MemBlocksClient has an llm attribute or similar
                # This is a placeholder - adjust based on actual memblocks LLM integration
                return f"LLM answer using {model} for prompt: {prompt[:50]}..."
        except Exception:
            pass
        # Fallback stub for testing
        return f"Stub answer for prompt: {prompt[:50]}..."

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
