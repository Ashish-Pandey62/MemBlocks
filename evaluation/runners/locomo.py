"""LoCoMo specific evaluation runner.

All data flows go through the real MemBlocks SDK (Qdrant + MongoDB).
There are no in-memory fallbacks — if infrastructure is unavailable the
session is marked as failed and its questions are skipped.
"""

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Union

from evaluation.core.config import RunConfig, RunnerConfig
from evaluation.datasets.locomo import LocomoDataset, LocomoMessage
from evaluation.metrics.locomo import LocomoEvaluator, PipelineStage, StageTokenUsage
from evaluation.metrics.reporter import Reporter
from evaluation.runners.base import BaseRunner

try:
    from memblocks import MemBlocksClient, MemBlocksConfig
except ImportError as _e:
    raise ImportError(
        "The 'memblocks' package is required to run evaluation. "
        "Install it with:  pip install -e memblocks_lib"
    ) from _e

# Path to QA prompt template (relative to project root)
QA_TEMPLATE_PATH = (
    Path(__file__).parent.parent.parent
    / ".planning"
    / "phases"
    / "08-evaluation-pipeline"
    / "templates"
    / "qa_prompt.txt"
)

QA_TEMPLATE = """
Based on the above context, write an answer in the form of a short phrase for the following question. Answer with exact words from the context whenever possible.

<context>{retrieved_context}</context>

Question: {question_text}

"""

class LocomoRunner(BaseRunner):
    """Runner for evaluating MemBlocks on the LoCoMo dataset.

    Uses the real MemBlocks SDK for all data operations.
    If MemBlocks infrastructure (Qdrant / MongoDB) is unavailable for a
    session, that session is recorded as failed and its questions are skipped.
    No in-memory substitution is ever performed.
    """

    def __init__(self, config: Union[RunnerConfig, RunConfig], dataset: LocomoDataset) -> None:
        runner_config = config.runner if isinstance(config, RunConfig) else config
        super().__init__(runner_config, dataset)
        self.dataset = dataset
        self.config = runner_config
        self.run_config = config

    # ------------------------------------------------------------------
    # MemBlocks session lifecycle
    # ------------------------------------------------------------------

    async def _create_session(self, user_id: str, block_name: str):
        """Create a MemBlocks client, block, and session against real infrastructure.

        Raises:
            Any exception from MemBlocksClient (MongoDB / Qdrant connectivity).
        """
        client = MemBlocksClient(MemBlocksConfig(memory_window_limit=10000))
        await client.get_or_create_user(user_id)
        block = await client.create_block(user_id=user_id, name=block_name)
        session = await client.create_session(user_id=user_id, block_id=block.id)
        return client, block, session

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
                i += 1  # skip leading/extra assistant messages
        return turns

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------

    async def _retrieve_context(self, question_text: str, block) -> str:
        """Retrieve context from the MemBlocks block using hybrid strategy (semantic + core)."""
        result = await block.retrieve(question_text)
        return result.to_prompt_string()

    def _build_full_context(
        self,
        retrieved_ctx: str,
        summary: str,
        memory_window: List[Dict[str, str]] = None,
    ) -> str:
        """Combine retrieved memories, memory window, and summary into one context string."""
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
    # LLM helpers (QA + judge via Ollama)
    # ------------------------------------------------------------------

    def _load_qa_template(self) -> Optional[str]:
        """Load QA prompt template from disk."""
        try:
            if QA_TEMPLATE_PATH.exists():
                return QA_TEMPLATE_PATH.read_text(encoding="utf-8")
            else:
                return QA_TEMPLATE  # fallback to hardcoded template if file is missing
        except Exception:
            return None

    def _create_qa_client(self) -> "MemBlocksClient":
        """Create a MemBlocksClient configured for QA generation using Ollama."""
        config = MemBlocksConfig(
            llm_provider_name="ollama",
            llm_model=self.config.model,
            llm_convo_temperature=0.0,
        )
        return MemBlocksClient(config)

    def _create_judge_client(self) -> "MemBlocksClient":
        """Create a MemBlocksClient configured for judging using Ollama."""
        config = MemBlocksConfig(
            llm_provider_name="ollama",
            llm_model=self.config.judge_model,
            llm_convo_temperature=0.0,
        )
        return MemBlocksClient(config)

    def _fill_qa_prompt(self, template: str, retrieved_context: Any, question_text: str) -> str:
        """Fill QA prompt template with context and question."""
        prompt = template.replace("{retrieved_context}", str(retrieved_context))
        prompt = prompt.replace("{question_text}", str(question_text))
        return prompt

    def _ollama_base_url(self) -> str:
        """Return the Ollama generation base URL from MemBlocksConfig (.env OLLAMA_BASE_URL)."""
        try:
            return MemBlocksConfig().ollama_base_url
        except Exception:
            return "http://localhost:11434"

    def _call_llm(self, prompt: str) -> str:
        """POST prompt to the configured Ollama model and return its response text."""
        # Keeping this for backward compatibility - new code uses conversation_llm
        import requests

        model = self.config.model if self.config and self.config.model else None
        if not model:
            raise ValueError("LLM model not specified in configuration")

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

    def _extract_token_usage(
        self,
        client: "MemBlocksClient",
        stage: PipelineStage,
    ) -> StageTokenUsage:
        """Extract token usage from client.llm_usage for a specific stage."""
        try:
            from memblocks.models.transparency import LLMCallType
            
            call_type_map = {
                PipelineStage.QA: LLMCallType.CONVERSATION,
                PipelineStage.JUDGE: LLMCallType.CONVERSATION,
                PipelineStage.RETRIEVAL: LLMCallType.RETRIEVAL,
                PipelineStage.EXTRACTION: LLMCallType.PS1_EXTRACTION,
                PipelineStage.CONFLICT_MANAGEMENT: LLMCallType.PS2_CONFLICT,
                PipelineStage.CORE_MEMORY_GENERATION: LLMCallType.CORE_MEMORY,
                PipelineStage.SUMMARY_GENERATION: LLMCallType.SUMMARY,
            }
            
            llm_call_type = call_type_map.get(stage, LLMCallType.CONVERSATION)
            records = client.llm_usage.get_records(call_type=llm_call_type, limit=10)
            
            if records:
                latest = records[-1]
                return StageTokenUsage(
                    stage=stage,
                    prompt_tokens=latest.input_tokens,
                    completion_tokens=latest.output_tokens,
                    total_tokens=latest.total_tokens,
                )
        except Exception:
            pass
        
        return StageTokenUsage(stage=stage, prompt_tokens=0, completion_tokens=0, total_tokens=0)

    # ------------------------------------------------------------------
    # Metrics aggregation
    # ------------------------------------------------------------------

    def _aggregate_metrics(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate pass/fail metrics across all sessions."""
        total_questions = 0
        total_passes = 0
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

                if ev.get("score") == "Pass":
                    total_passes += 1

                category = ev.get("category", "unknown")
                if category not in category_stats:
                    category_stats[category] = {"total": 0, "passes": 0}
                category_stats[category]["total"] += 1
                if ev.get("score") == "Pass":
                    category_stats[category]["passes"] += 1

                for stage_name, stage_usage in ev.get("tokens", {}).items():
                    if isinstance(stage_usage, StageTokenUsage):
                        aggregate_tokens[stage_name] += stage_usage.total_tokens

        overall_accuracy = total_passes / total_questions if total_questions else 0.0

        return {
            "overall_accuracy": overall_accuracy,
            "total_questions": total_questions,
            "total_passes": total_passes,
            "accuracy_by_category": {
                cat: stats["passes"] / stats["total"] if stats["total"] else 0.0
                for cat, stats in category_stats.items()
            },
            "tokens_by_stage": aggregate_tokens,
            "total_tokens": sum(aggregate_tokens.values()),
        }

    # ------------------------------------------------------------------
    # Main async pipeline
    # ------------------------------------------------------------------

    async def _run_async(self) -> Dict[str, Any]:
        sessions = self.dataset.load()
        results: List[Dict[str, Any]] = []
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
            qa_client = None
            judge_client = None

            try:
                user_id = f"eval-locomo-{session.session_id}"
                block_name = f"locomo-session-{session.session_id}"

                client, block, mb_session = await self._create_session(user_id, block_name)

                # Ingest conversation as paired (user_msg, ai_response) turns
                turns = self._pair_messages(session.messages)
                for user_msg, ai_response in turns:
                    await mb_session.add(user_msg=user_msg, ai_response=ai_response)

                # Flush at end of ingestion to run the memory pipeline on remaining turns
                if turns:
                    await mb_session.flush()

                session_results["ingestion_status"] = "success"
                session_results["block_id"] = block.id

                # Create separate clients for QA and judging
                qa_client = self._create_qa_client()
                judge_client = self._create_judge_client()

                # ----------------------------------------------------------
                # Retrieval + QA — only runs when ingestion succeeded
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
                        # Retrieve via hybrid strategy (semantic + core combined)
                        retrieved_ctx = await self._retrieve_context(
                            question.question, block
                        )

                        # Pull memory window + recursive summary from MemBlocks
                        # memory_window = await mb_session.get_memory_window()
                        summary = await mb_session.get_recursive_summary()

                        eval_result["retrieved_context"] = retrieved_ctx
                        eval_result["memory_window_size"] = 0#len(memory_window)
                        eval_result["has_summary"] = bool(summary)

                        if qa_template is None:
                            eval_result["status"] = "skipped_no_qa_template"
                        else:
                            evaluator = LocomoEvaluator(
                                self.config,
                                qa_provider=qa_client.conversation_llm,
                                judge_provider=judge_client.conversation_llm,
                            )

                            full_ctx = self._build_full_context(retrieved_ctx, summary, memory_window=None)
                            prompt = self._fill_qa_prompt(
                                qa_template, full_ctx, question.question
                            )
                            answer = await qa_client.conversation_llm.chat(
                                [{"role": "user", "content": prompt}]
                            )
                            eval_result["answer"] = answer
                            
                            # Use structured output for judge
                            from pydantic import BaseModel
                            
                            class JudgeOutput(BaseModel):
                                decision: Literal["Pass", "Fail"]
                                reasoning: str
                            
                            judge_chain = judge_client.conversation_llm.create_structured_chain(
                                system_prompt=(
                                    "You are a strict evaluator. Respond with a JSON object containing "
                                    "'decision' (either 'Pass' or 'Fail') and 'reasoning' (brief explanation). "
                                    "Respond Pass ONLY if the actual answer contains the key facts from the expected answer. "
                                    "Respond Fail if the actual answer says 'I cannot answer', 'I don't know', "
                                    "refuses to answer, gives wrong facts, or omits the key information."
                                ),
                                pydantic_model=JudgeOutput,
                                temperature=0.0,
                            )
                            judge_input = (
                                f"Question: {question.question}\n"
                                f"Expected Answer: {question.answer}\n"
                                f"Actual Answer: {answer}"
                            )
                            judge_output = await judge_chain.ainvoke({"input": judge_input})
                            eval_result["score"] = judge_output.decision

                            eval_result["actual_answer"] = answer
                            eval_result["status"] = "evaluated"

                            # Extract real token usage from clients
                            eval_result["tokens"] = {
                                "retrieval": self._extract_token_usage(
                                    client, PipelineStage.RETRIEVAL
                                ),
                                "extraction": self._extract_token_usage(
                                    client, PipelineStage.EXTRACTION
                                ),
                                "qa": self._extract_token_usage(
                                    qa_client, PipelineStage.QA
                                ),
                                "conflict_management": self._extract_token_usage(
                                    client, PipelineStage.CONFLICT_MANAGEMENT
                                ),
                                "summary_generation": self._extract_token_usage(
                                    client, PipelineStage.SUMMARY_GENERATION
                                ),
                                "core_memory_generation": self._extract_token_usage(
                                    client, PipelineStage.CORE_MEMORY_GENERATION
                                ),
                                "judge": self._extract_token_usage(
                                    judge_client, PipelineStage.JUDGE
                                ),
                            }

                    except Exception as e:
                        eval_result["status"] = f"retrieval_failed: {e}"

                    session_results["evaluations"].append(eval_result)

            except Exception as e:
                # MemBlocks infrastructure error — record and skip QA for this session.
                # No in-memory substitution: the session result reflects the real failure.
                session_results["ingestion_status"] = f"memblocks_error: {e}"
                session_results["block_id"] = None

            finally:
                if client is not None:
                    await client.close()
                if qa_client is not None:
                    await qa_client.close()
                if judge_client is not None:
                    await judge_client.close()

            results.append(session_results)

        return {
            "sessions_processed": len(sessions),
            "details": results,
            "metrics": self._aggregate_metrics(results),
        }

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self, output_dir: Path) -> Dict[str, Any]:
        """Execute the LoCoMo evaluation pipeline and write reports.

        Args:
            output_dir: Directory to save report.json / report.csv / run_info.json.

        Returns:
            Evaluation results dictionary.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        results = asyncio.run(self._run_async())

        reporter = Reporter()
        reporter.save_json(results, output_dir)
        reporter.save_csv(results, output_dir)
        reporter.save_run_info(self.run_config, output_dir)
        reporter.print_summary(results)

        return results
    

    