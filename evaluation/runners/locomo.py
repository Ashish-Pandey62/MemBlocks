"""LoCoMo specific evaluation runner."""

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from evaluation.core.config import RunConfig, RunnerConfig
from evaluation.datasets.locomo import LocomoDataset, LocomoMessage
from evaluation.metrics.locomo import LocomoEvaluator, PipelineStage, StageTokenUsage
from evaluation.metrics.reporter import Reporter
from evaluation.runners.base import BaseRunner

try:
    from memblocks import MemBlocksClient, MemBlocksConfig
except ImportError:
    MemBlocksClient = None
    MemBlocksConfig = None

# Path to QA prompt template (relative to project root)
QA_TEMPLATE_PATH = Path(__file__).parent.parent.parent / ".planning" / "phases" / "08-evaluation-pipeline" / "templates" / "qa_prompt.txt"


# ---------------------------------------------------------------------------
# In-memory fallback classes (mirror the real SDK's async interface)
# ---------------------------------------------------------------------------

class _InMemoryRetrievalResult:
    """Minimal stand-in for memblocks.models.retrieval.RetrievalResult."""

    def __init__(self, context: str) -> None:
        self._context = context

    def to_prompt_string(self) -> str:
        return self._context

    def __str__(self) -> str:
        return self._context


class _InMemoryBlock:
    """Async stand-in for memblocks.services.block.Block."""

    def __init__(self) -> None:
        self.id: str = ""
        self._session: Optional["_InMemorySession"] = None

    def _all_texts(self) -> List[str]:
        if not self._session:
            return []
        return [t for pair in self._session._turns for t in pair if t]

    def _keyword_search(self, query: str, top_k: int = 5) -> str:
        terms = set(query.lower().split())
        scored = sorted(
            ((sum(1 for t in terms if t in txt.lower()), txt) for txt in self._all_texts()),
            reverse=True,
        )
        return "\n".join(txt for _, txt in scored[:top_k])

    async def retrieve(self, query: str) -> _InMemoryRetrievalResult:
        return _InMemoryRetrievalResult(self._keyword_search(query))

    async def semantic_retrieve(self, query: str) -> _InMemoryRetrievalResult:
        return _InMemoryRetrievalResult(self._keyword_search(query))

    async def core_retrieve(self) -> _InMemoryRetrievalResult:
        texts = self._all_texts()[-10:]
        return _InMemoryRetrievalResult("\n".join(texts))


class _InMemorySession:
    """Async stand-in for memblocks.services.session.Session."""

    def __init__(self) -> None:
        self._turns: List[tuple] = []
        self._user_id: str = ""

    async def add(self, user_msg: str, ai_response: str) -> None:
        self._turns.append((user_msg, ai_response))

    async def flush(self) -> str:
        return ""

    async def get_memory_window(self) -> List[Dict[str, str]]:
        msgs: List[Dict[str, str]] = []
        for u, a in self._turns[-5:]:
            msgs.append({"role": "user", "content": u})
            if a:
                msgs.append({"role": "assistant", "content": a})
        return msgs

    async def get_recursive_summary(self) -> str:
        return ""


class _InMemoryClient:
    """Async stand-in for MemBlocksClient when real SDK unavailable."""

    def __init__(self) -> None:
        self._blocks: Dict[str, _InMemoryBlock] = {}

    async def get_or_create_user(self, user_id: str) -> Dict[str, Any]:
        return {"user_id": user_id}

    async def create_block(self, user_id: str, name: str) -> _InMemoryBlock:
        block = _InMemoryBlock()
        block.id = f"block_{user_id}_{name}"
        self._blocks[block.id] = block
        return block

    async def create_session(self, user_id: str, block_id: str) -> _InMemorySession:
        session = _InMemorySession()
        session._user_id = user_id
        block = self._blocks.get(block_id)
        if block:
            block._session = session
        return session

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

class LocomoRunner(BaseRunner):
    """Runner for evaluating MemBlocks on the LoCoMo dataset."""

    def __init__(self, config: Union[RunnerConfig, RunConfig], dataset: LocomoDataset) -> None:
        runner_config = config.runner if isinstance(config, RunConfig) else config
        super().__init__(runner_config, dataset)
        self.dataset = dataset
        self.config = runner_config
        self.run_config = config

    # ------------------------------------------------------------------
    # Session setup helpers
    # ------------------------------------------------------------------

    async def _setup_session(self, user_id: str, block_name: str):
        """Try real SDK first; fall back to in-memory client."""
        if MemBlocksClient is not None and MemBlocksConfig is not None:
            try:
                client = MemBlocksClient(MemBlocksConfig())
                await client.get_or_create_user(user_id)
                block = await client.create_block(user_id=user_id, name=block_name)
                session = await client.create_session(user_id=user_id, block_id=block.id)
                return client, block, session, "real"
            except Exception:
                pass
        client = _InMemoryClient()
        await client.get_or_create_user(user_id)
        block = await client.create_block(user_id=user_id, name=block_name)
        session = await client.create_session(user_id=user_id, block_id=block.id)
        return client, block, session, "in-memory"

    # ------------------------------------------------------------------
    # Message pairing
    # ------------------------------------------------------------------

    def _pair_messages(self, messages: List[LocomoMessage]) -> List[tuple]:
        """Pair consecutive user/assistant messages into (user_msg, ai_response) turns."""
        turns = []
        i = 0
        while i < len(messages):
            if messages[i].role == "user":
                user_content = messages[i].content
                if i + 1 < len(messages) and messages[i + 1].role == "assistant":
                    ai_content = messages[i + 1].content
                    i += 2
                else:
                    ai_content = ""
                    i += 1
                turns.append((user_content, ai_content))
            else:
                # skip leading/extra assistant messages
                i += 1
        return turns

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------

    async def _retrieve_context(self, question_text: str, block, strategy: str) -> str:
        """Retrieve context from the block using the specified strategy."""
        if strategy == "semantic":
            result = await block.semantic_retrieve(question_text)
        elif strategy == "core":
            result = await block.core_retrieve()
        else:
            result = await block.retrieve(question_text)
        return result.to_prompt_string()

    def _build_full_context(
        self,
        retrieved_ctx: str,
        memory_window: List[Dict[str, str]],
        summary: str,
    ) -> str:
        """Augment retrieved context with memory window and summary."""
        parts = []
        if summary:
            parts.append(f"[Conversation Summary]\n{summary}")
        if memory_window:
            window_text = "\n".join(
                f"{m.get('role', '').upper()}: {m.get('content', '')}" for m in memory_window
            )
            parts.append(f"[Recent Messages]\n{window_text}")
        if retrieved_ctx:
            parts.append(retrieved_ctx)
        return "\n\n".join(parts) if parts else "[No context available]"

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    def _load_qa_template(self) -> Optional[str]:
        """Load QA prompt template from disk."""
        try:
            if QA_TEMPLATE_PATH.exists():
                return QA_TEMPLATE_PATH.read_text(encoding="utf-8")
            return None
        except Exception:
            return None

    def _fill_qa_prompt(self, template: str, retrieved_context: Any, question_text: str) -> str:
        """Fill QA prompt template with context and question."""
        prompt = template.replace("{retrieved_context}", str(retrieved_context))
        prompt = prompt.replace("{question_text}", str(question_text))
        return prompt

    def _ollama_base_url(self) -> str:
        """Return the Ollama generation base URL from MemBlocksConfig if available."""
        if MemBlocksConfig is not None:
            try:
                return MemBlocksConfig().ollama_base_url
            except Exception:
                pass
        return "http://localhost:11434"

    def _call_llm(self, prompt: str) -> str:
        """Call the configured Ollama model and return its response."""
        import requests

        model = self.config.model if self.config and self.config.model else None
        stub_names = {None, "stub-model", "default", ""}
        if model in stub_names:
            return f"Stub answer for prompt: {prompt[:50]}..."

        try:
            response = requests.post(
                f"{self._ollama_base_url()}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=180,
            )
            return response.json().get("response", "").strip()
        except Exception as e:
            return f"LLM call failed: {e}"

    # ------------------------------------------------------------------
    # Metrics aggregation
    # ------------------------------------------------------------------

    def _aggregate_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate metrics from evaluation results across all 3 strategies."""
        total_questions = 0
        strategy_passes: Dict[str, int] = {"semantic": 0, "core": 0, "hybrid": 0}
        category_stats: Dict[str, Dict[str, int]] = {}
        aggregate_tokens: Dict[str, int] = {
            "retrieval": 0,
            "extraction": 0,
            "conflict_management": 0,
            "summary_generation": 0,
            "core_memory_generation": 0,
            "qa": 0,
            "judge": 0,
        }

        for session in results:
            for ev in session.get("evaluations", []):
                total_questions += 1

                for strategy in ("semantic", "core", "hybrid"):
                    if ev.get(f"score_{strategy}") == "Pass":
                        strategy_passes[strategy] += 1

                category = ev.get("category", "unknown")
                if category not in category_stats:
                    category_stats[category] = {"total": 0, "passes": 0}
                category_stats[category]["total"] += 1
                if ev.get("score_hybrid") == "Pass":
                    category_stats[category]["passes"] += 1

                for stage_name, stage_usage in ev.get("tokens", {}).items():
                    if isinstance(stage_usage, StageTokenUsage):
                        aggregate_tokens[stage_name] += stage_usage.total_tokens

        total_passes = strategy_passes["hybrid"]
        overall_accuracy = total_passes / total_questions if total_questions else 0.0

        accuracy_by_category = {
            cat: stats["passes"] / stats["total"] if stats["total"] else 0.0
            for cat, stats in category_stats.items()
        }

        accuracy_by_strategy = {
            s: strategy_passes[s] / total_questions if total_questions else 0.0
            for s in ("semantic", "core", "hybrid")
        }

        return {
            "overall_accuracy": overall_accuracy,
            "total_questions": total_questions,
            "total_passes": total_passes,
            "accuracy_by_category": accuracy_by_category,
            "accuracy_by_strategy": accuracy_by_strategy,
            "tokens_by_stage": aggregate_tokens,
            "total_tokens": sum(aggregate_tokens.values()),
        }

    # ------------------------------------------------------------------
    # Main async pipeline
    # ------------------------------------------------------------------

    async def _run_async(self) -> Dict[str, Any]:
        sessions = self.dataset.load()
        results: List[Dict[str, Any]] = []

        # Load QA prompt template once
        qa_template = self._load_qa_template()

        for session in sessions:
            session_results: Dict[str, Any] = {
                "session_id": session.session_id,
                "questions_evaluated": len(session.questions),
                "messages_processed": len(session.messages),
                "evaluations": [],
            }

            client = None
            block = None
            mb_session = None
            client_type = "none"

            try:
                user_id = f"eval-locomo-{session.session_id}"
                block_name = f"locomo-session-{session.session_id}"
                client, block, mb_session, client_type = await self._setup_session(
                    user_id, block_name
                )

                # Ingest conversation as paired (user_msg, ai_response) turns
                turns = self._pair_messages(session.messages)
                for user_msg, ai_response in turns:
                    await mb_session.add(user_msg=user_msg, ai_response=ai_response)

                # Single flush after all turns to process remaining messages
                if turns:
                    await mb_session.flush()

                session_results["ingestion_status"] = "success"
                session_results["block_id"] = block.id
                session_results["client_type"] = client_type

                # ----------------------------------------------------------
                # Retrieval + QA
                # ----------------------------------------------------------
                for question in session.questions:
                    eval_result: Dict[str, Any] = {
                        "question": question.question,
                        "expected_answer": question.answer,
                        "category": question.category,
                        "status": "pending",
                        "baseline_status": "deferred_per_user_decision",
                    }

                    try:
                        # Retrieve context using all 3 strategies
                        semantic_ctx = await self._retrieve_context(
                            question.question, block, "semantic"
                        )
                        core_ctx = await self._retrieve_context(
                            question.question, block, "core"
                        )
                        hybrid_ctx = await self._retrieve_context(
                            question.question, block, "hybrid"
                        )

                        # Fetch memory window and summary for context augmentation
                        memory_window = await mb_session.get_memory_window()
                        summary = await mb_session.get_recursive_summary()

                        eval_result["retrieved_context_semantic"] = semantic_ctx
                        eval_result["retrieved_context_core"] = core_ctx
                        eval_result["retrieved_context_hybrid"] = hybrid_ctx
                        eval_result["memory_window_size"] = len(memory_window)
                        eval_result["has_summary"] = bool(summary)

                        if qa_template is None:
                            # Explicitly flag that QA was skipped due to missing template
                            eval_result["status"] = "skipped_no_qa_template"
                        else:
                            evaluator = LocomoEvaluator(self.config)

                            for strategy_name, ctx in [
                                ("semantic", semantic_ctx),
                                ("core", core_ctx),
                                ("hybrid", hybrid_ctx),
                            ]:
                                full_ctx = self._build_full_context(ctx, memory_window, summary)
                                prompt = self._fill_qa_prompt(
                                    qa_template, full_ctx, question.question
                                )
                                answer = self._call_llm(prompt)
                                eval_result[f"answer_{strategy_name}"] = answer
                                eval_result[f"score_{strategy_name}"] = (
                                    evaluator.evaluate_with_judge(
                                        question.question, question.answer, answer
                                    )
                                )

                            # Convenience alias: primary answer is from hybrid strategy
                            eval_result["actual_answer"] = eval_result.get("answer_hybrid", "")
                            eval_result["status"] = "evaluated"

                            # Capture prompt/response trace for the hybrid strategy
                            hybrid_prompt = self._fill_qa_prompt(
                                qa_template,
                                self._build_full_context(hybrid_ctx, memory_window, summary),
                                question.question,
                            )
                            eval_result["prompt_trace"] = hybrid_prompt
                            eval_result["response_trace"] = eval_result.get("answer_hybrid", "")

                            # Stub token metrics (kept until real LLM usage tracking is wired)
                            eval_result["tokens"] = {
                                "retrieval": StageTokenUsage(
                                    stage=PipelineStage.RETRIEVAL,
                                    prompt_tokens=50,
                                    completion_tokens=20,
                                    total_tokens=70,
                                ),
                                "extraction": StageTokenUsage(
                                    stage=PipelineStage.EXTRACTION,
                                    prompt_tokens=30,
                                    completion_tokens=10,
                                    total_tokens=40,
                                ),
                                "qa": StageTokenUsage(
                                    stage=PipelineStage.QA,
                                    prompt_tokens=200,
                                    completion_tokens=100,
                                    total_tokens=300,
                                ),
                                "conflict_management": StageTokenUsage(
                                    stage=PipelineStage.CONFLICT_MANAGEMENT,
                                    prompt_tokens=0,
                                    completion_tokens=0,
                                    total_tokens=0,
                                ),
                                "summary_generation": StageTokenUsage(
                                    stage=PipelineStage.SUMMARY_GENERATION,
                                    prompt_tokens=0,
                                    completion_tokens=0,
                                    total_tokens=0,
                                ),
                                "core_memory_generation": StageTokenUsage(
                                    stage=PipelineStage.CORE_MEMORY_GENERATION,
                                    prompt_tokens=0,
                                    completion_tokens=0,
                                    total_tokens=0,
                                ),
                                "judge": StageTokenUsage(
                                    stage=PipelineStage.JUDGE,
                                    prompt_tokens=150,
                                    completion_tokens=50,
                                    total_tokens=200,
                                ),
                            }

                    except Exception as e:
                        eval_result["status"] = f"failed: {e}"

                    session_results["evaluations"].append(eval_result)

            except Exception as e:
                session_results["ingestion_status"] = f"failed: {e}"
                session_results["block_id"] = None
                session_results["client_type"] = "none"

            finally:
                if client is not None:
                    await client.close()

            results.append(session_results)

        metrics = self._aggregate_metrics(results)

        return {
            "sessions_processed": len(sessions),
            "details": results,
            "metrics": metrics,
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, output_dir: Path) -> Dict[str, Any]:
        """Execute the LoCoMo evaluation pipeline.

        Generates JSON, CSV, run_info.json reports and prints console summary.

        Args:
            output_dir: Directory to save evaluation outputs.

        Returns:
            Dictionary containing evaluation results.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        results = asyncio.run(self._run_async())

        reporter = Reporter()
        reporter.save_json(results, output_dir)
        reporter.save_csv(results, output_dir)
        reporter.save_run_info(self.run_config, output_dir)
        reporter.print_summary(results)

        return results
