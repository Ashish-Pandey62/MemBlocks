"""LoCoMo specific evaluation runner.

All data flows go through the real MemBlocks SDK (Qdrant + MongoDB).
There are no in-memory fallbacks — if infrastructure is unavailable the
session is marked as failed and its questions are skipped.
"""

import asyncio
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Generator, List, Literal, Optional, Union
from unittest.mock import patch

logger = logging.getLogger(__name__)

from memblocks.llm.task_settings import LLMTaskSettings

from evaluation.core.config import RunConfig, RunnerConfig
from evaluation.datasets.locomo import LocomoDataset, LocomoMessage
from evaluation.metrics.locomo import PipelineStage, StageTokenUsage
from evaluation.metrics.reporter import Reporter
from evaluation.runners.base import BaseRunner

try:
    from memblocks import MemBlocksClient, MemBlocksConfig, LLMSettings
except ImportError as _e:
    raise ImportError(
        "The 'memblocks' package is required to run evaluation. "
        "Install it with:  pip install -e memblocks_lib"
    ) from _e


_DATETIME_PATCH_TARGETS = [
    "memblocks.services.session.datetime",
    "memblocks.services.memory_pipeline.datetime",
    "memblocks.services.semantic_memory.datetime",
]


@contextmanager
def _freeze_datetime(dt: datetime) -> Generator[None, None, None]:
    """Patch datetime in memblocks service modules so they report dt as the current time.

    session.py and memory_pipeline.py call datetime.utcnow(); semantic_memory.py calls
    datetime.now(timezone.utc). Both are redirected to dt for accurate dataset timestamps.
    """
    dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
    dt_aware = dt.replace(tzinfo=timezone.utc) if not dt.tzinfo else dt
    patches = [patch(t) for t in _DATETIME_PATCH_TARGETS]
    mocks = [p.start() for p in patches]
    for m in mocks:
        m.utcnow.return_value = dt_naive
        m.now.return_value = dt_aware
    try:
        yield
    finally:
        for p in patches:
            p.stop()


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
        client = MemBlocksClient(
            MemBlocksConfig(
                    memory_window_limit=30, keep_last_n = 6,
                    llm_settings=LLMSettings(
                    default=LLMTaskSettings(
                        provider="groq",
                        model="openai/gpt-oss-120b"
                    ),
                    ps1_semantic_extraction=LLMTaskSettings(
                        provider="openrouter",
                        model="nvidia/nemotron-3-super-120b-a12b:free"
                    ),
                    ps2_conflict_resolution=LLMTaskSettings(
                        provider="ollama",
                        model="llama-3.1-8b-ctx20000:latest"
                    ),
                    retrieval=LLMTaskSettings(
                        provider="groq",
                        model="openai/gpt-oss-20b"
                    ),
                )
            )
        )
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
                date_time = messages[i].date_time  # capture before i is incremented
                if i + 1 < len(messages) and messages[i + 1].role == "assistant":
                    ai_content = messages[i + 1].content
                    i += 2
                else:
                    ai_content = ""
                    i += 1
                turns.append((user_content, ai_content, date_time))
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

    # def _ollama_base_url(self) -> str:
    #     """Return the Ollama generation base URL from MemBlocksConfig (.env OLLAMA_BASE_URL)."""
    #     try:
    #         return MemBlocksConfig().ollama_base_url
    #     except Exception:
    #         return "http://localhost:11434"

    # def _call_llm(self, prompt: str) -> str:
    #     """POST prompt to the configured Ollama model and return its response text."""
    #     # Keeping this for backward compatibility - new code uses conversation_llm
    #     import requests

    #     model = self.config.model if self.config and self.config.model else None
    #     if not model:
    #         raise ValueError("LLM model not specified in configuration")

    #     try:
    #         response = requests.post(
    #             f"{self._ollama_base_url()}/api/generate",
    #             json={
    #                 "model": model,
    #                 "prompt": prompt,
    #                 "stream": False,
    #                 "options": {"temperature": 0},
    #             },
    #             timeout=180,
    #         )
    #         return response.json().get("response", "").strip()
    #     except Exception as e:
    #         return f"LLM call failed: {e}"

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

    async def _run_async(self, output_dir: str) -> Dict[str, Any]:
        sessions = self.dataset.load()
        results: List[Dict[str, Any]] = []
        qa_template = self._load_qa_template()

        user_id = f"eval-locomo-{str(output_dir).replace('/', '-')}"

        total_sessions = len(sessions)
        logger.info("=" * 70)
        logger.info("EVAL START — %d session(s) to process", total_sessions)
        logger.info("  model=%s  judge=%s", self.config.model, self.config.judge_model)
        logger.info("=" * 70)

        for session_idx, session in enumerate(sessions, 1):
            sid = session.session_id
            n_msgs = len(session.messages)
            n_qs = len(session.questions)
            logger.info("")
            logger.info("─" * 70)
            logger.info(
                "[SESSION %d/%d] id=%s  messages=%d  questions=%d",
                session_idx, total_sessions, sid, n_msgs, n_qs,
            )
            logger.info("─" * 70)

            session_results: Dict[str, Any] = {
                "session_id": sid,
                "questions_evaluated": n_qs,
                "messages_processed": n_msgs,
                "evaluations": [],
            }

            client = None
            block = None
            mb_session = None
            qa_client = None
            judge_client = None

            try:

                block_name = f"locomo-session-{sid}"

                logger.info("[SETUP] Creating MemBlocks session — user=%s block=%s", user_id, block_name)
                client, block, mb_session = await self._create_session(user_id, block_name)
                logger.info("[SETUP] Session ready — block_id=%s", block.id)

                # Ingest conversation as paired (user_msg, ai_response) turns
                turns = self._pair_messages(session.messages)
                logger.info("[INGEST] Pairing %d messages → %d turn(s)", n_msgs, len(turns))
                for turn_idx, (user_msg, ai_response, date_time_cur) in enumerate(turns, 1):
                    logger.debug(
                        "[INGEST] Turn %d/%d  USER=%.80r  AI=%.80r",
                        turn_idx, len(turns),
                        user_msg, ai_response,
                    )
                    if date_time_cur is not None:
                        with _freeze_datetime(date_time_cur):
                            await mb_session.add(user_msg=user_msg, ai_response=ai_response)
                    else:
                        await mb_session.add(user_msg=user_msg, ai_response=ai_response)
                logger.info("[INGEST] All %d turn(s) added — flushing memory pipeline", len(turns))

                # Flush at end of ingestion to run the memory pipeline on remaining turns
                if turns:
                    await mb_session.flush()
                    logger.info("[FLUSH] Memory pipeline flush complete for block %s", block.id)

                session_results["ingestion_status"] = "success"
                session_results["block_id"] = block.id

                # Create separate clients for QA and judging
                qa_client = self._create_qa_client()
                judge_client = self._create_judge_client()
                logger.info(
                    "[SETUP] QA client model=%s  Judge client model=%s",
                    self.config.model, self.config.judge_model,
                )

                # ----------------------------------------------------------
                # Retrieval + QA — only runs when ingestion succeeded
                # ----------------------------------------------------------
                session_passes = 0
                for q_idx, question in enumerate(session.questions, 1):
                    logger.info("")
                    logger.info(
                        "  [Q %d/%d] category=%-20s  q=%.80s",
                        q_idx, n_qs, question.category, question.question,
                    )
                    logger.debug("  [Q %d/%d] expected_answer=%r", q_idx, n_qs, question.answer)

                    eval_result: Dict[str, Any] = {
                        "question": question.question,
                        "expected_answer": question.answer,
                        "category": question.category,
                        "status": "pending",
                        "baseline_status": "deferred_per_user_decision",
                    }

                    try:
                        # Retrieve via hybrid strategy (semantic + core combined)
                        logger.debug("  [RETRIEVE] query=%.80r", question.question)
                        retrieved_ctx = await self._retrieve_context(question.question, block)
                        ctx_len = len(retrieved_ctx) if retrieved_ctx else 0
                        logger.info("  [RETRIEVE] done — context_chars=%d", ctx_len)
                        logger.debug("  [RETRIEVE] context_preview=%.200r", retrieved_ctx)

                        # Pull recursive summary from MemBlocks
                        summary = await mb_session.get_recursive_summary()
                        has_summary = bool(summary)
                        logger.debug(
                            "  [SUMMARY] has_summary=%s  summary_chars=%d",
                            has_summary, len(summary) if summary else 0,
                        )

                        eval_result["retrieved_context"] = retrieved_ctx
                        eval_result["memory_window_size"] = 0
                        eval_result["has_summary"] = has_summary

                        if qa_template is None:
                            logger.warning("  [QA] Skipping — no QA template found at %s", QA_TEMPLATE_PATH)
                            eval_result["status"] = "skipped_no_qa_template"
                        else:
                            full_ctx = self._build_full_context(retrieved_ctx, summary, memory_window=None)
                            prompt = self._fill_qa_prompt(qa_template, full_ctx, question.question)
                            logger.debug("  [QA] prompt_chars=%d  model=%s", len(prompt), self.config.model)

                            answer = await qa_client.conversation_llm.chat(
                                [{"role": "user", "content": prompt}]
                            )
                            logger.info("  [QA] answer=%.120r", answer)
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
                            logger.debug("  [JUDGE] model=%s  input_chars=%d", self.config.judge_model, len(judge_input))
                            judge_output = await judge_chain.ainvoke({"input": judge_input})

                            decision = judge_output.decision.lower()
                            reasoning = judge_output.reasoning
                            eval_result["score"] = decision
                            eval_result["actual_answer"] = answer
                            eval_result["status"] = "evaluated"
                            if decision == "pass":
                                session_passes += 1

                            logger.info(
                                "  [JUDGE] %s | reasoning=%.100s",
                                decision.upper(), reasoning,
                            )

                            # Extract real token usage from clients
                            token_usage = {
                                "retrieval": self._extract_token_usage(client, PipelineStage.RETRIEVAL),
                                "extraction": self._extract_token_usage(client, PipelineStage.EXTRACTION),
                                "qa": self._extract_token_usage(qa_client, PipelineStage.QA),
                                "conflict_management": self._extract_token_usage(client, PipelineStage.CONFLICT_MANAGEMENT),
                                "summary_generation": self._extract_token_usage(client, PipelineStage.SUMMARY_GENERATION),
                                "core_memory_generation": self._extract_token_usage(client, PipelineStage.CORE_MEMORY_GENERATION),
                                "judge": self._extract_token_usage(judge_client, PipelineStage.JUDGE),
                            }
                            eval_result["tokens"] = token_usage

                            token_summary = "  ".join(
                                f"{k}={v.total_tokens}"
                                for k, v in token_usage.items()
                                if isinstance(v, StageTokenUsage) and v.total_tokens
                            )
                            logger.debug("  [TOKENS] %s", token_summary or "no usage data")

                    except Exception as e:
                        logger.error("  [Q %d/%d] FAILED: %s", q_idx, n_qs, e, exc_info=True)
                        eval_result["status"] = f"retrieval_failed: {e}"

                    session_results["evaluations"].append(eval_result)

                # Session summary
                evaluated = [e for e in session_results["evaluations"] if e.get("status") == "evaluated"]
                pct = (session_passes / len(evaluated) * 100) if evaluated else 0.0
                logger.info("")
                logger.info(
                    "[SESSION RESULT] id=%s  %d/%d Pass  accuracy=%.1f%%",
                    sid, session_passes, len(evaluated), pct,
                )

            except Exception as e:
                logger.error(
                    "[SESSION %d/%d] MemBlocks infrastructure error for session %s: %s",
                    session_idx, total_sessions, sid, e, exc_info=True,
                )
                session_results["ingestion_status"] = f"memblocks_error: {e}"
                session_results["block_id"] = None

            finally:
                for label, c in [("main", client), ("qa", qa_client), ("judge", judge_client)]:
                    if c is not None:
                        await c.close()
                        logger.debug("[TEARDOWN] Closed %s client", label)

            results.append(session_results)

        # Final aggregate log
        metrics = self._aggregate_metrics(results)
        logger.info("")
        logger.info("=" * 70)
        logger.info(
            "EVAL COMPLETE — sessions=%d  questions=%d  passes=%d  accuracy=%.1f%%",
            len(sessions),
            metrics["total_questions"],
            metrics["total_passes"],
            metrics["overall_accuracy"] * 100,
        )
        if metrics.get("accuracy_by_category"):
            for cat, acc in metrics["accuracy_by_category"].items():
                logger.info("  category=%-25s  accuracy=%.1f%%", cat, acc * 100)
        logger.info("=" * 70)

        return {
            "sessions_processed": len(sessions),
            "details": results,
            "metrics": metrics,
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
        results = asyncio.run(self._run_async(output_dir))

        reporter = Reporter()
        reporter.save_json(results, output_dir)
        reporter.save_csv(results, output_dir)
        reporter.save_run_info(self.run_config, output_dir)
        reporter.print_summary(results)

        return results
    

    