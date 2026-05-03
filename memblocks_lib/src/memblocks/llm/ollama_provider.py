"""OllamaLLMProvider — LLMProvider implementation using LangChain + Ollama."""

import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING

from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel

from memblocks.llm.base import LLMProvider
from memblocks.logger import get_logger
from memblocks.models.transparency import LLMCallRecord, LLMCallType

if TYPE_CHECKING:
    from memblocks.config import MemBlocksConfig
    from memblocks.llm.task_settings import LLMTaskSettings
    from memblocks.services.transparency import LLMUsageTracker

logger = get_logger(__name__)


class OllamaLLMProvider(LLMProvider):
    """
    ``LLMProvider`` implementation using ``langchain_ollama.ChatOllama``.

    Connects to a local Ollama server to run open-source models. No API key required.

    Can be instantiated either from a full ``MemBlocksConfig`` (legacy path)
    or from a bare ``LLMTaskSettings`` + ``base_url`` (per-task path used by
    ``MemBlocksClient`` when ``llm_settings`` is configured).
    """

    def __init__(self, config: "MemBlocksConfig") -> None:
        """
        Construct from a full ``MemBlocksConfig``.

        Prefer ``OllamaLLMProvider.from_task_settings()`` when building a
        per-task provider inside ``MemBlocksClient``.

        Args:
            config: Library configuration.  Reads ``ollama_base_url``,
                    ``ollama_keep_alive``, ``llm_model``, ``llm_convo_temperature``,
                    and optional Arize monitoring fields.
        """
        self._base_url: str = config.ollama_base_url
        self._keep_alive: str = config.ollama_keep_alive or "10s"
        self._model: str = config.llm_model
        self._default_temperature: float = config.llm_convo_temperature
        self._usage_tracker: Optional["LLMUsageTracker"] = None
        self._call_type: LLMCallType = LLMCallType.CONVERSATION

        # Arize instrumentation — conditional, inside constructor, not at module level.
        if config.arize_space_id and config.arize_api_key:
            try:
                from openinference.instrumentation.langchain import (
                    LangChainInstrumentor,
                )
                from arize.otel import register
                from opentelemetry import trace

                existing = trace.get_tracer_provider()
                if not hasattr(existing, "_initialized"):
                    tracer_provider = register(
                        space_id=config.arize_space_id,
                        api_key=config.arize_api_key,
                        project_name=config.arize_project_name,
                    )
                    tracer_provider._initialized = True
                    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
            except ImportError:
                logger.warning(
                    "Arize/openinference packages not installed — monitoring disabled."
                )
        else:
            logger.debug(
                "Arize monitoring disabled (ARIZE_SPACE_ID / ARIZE_API_KEY not set)"
            )

    @classmethod
    def from_task_settings(
        cls,
        task_settings: "LLMTaskSettings",
        base_url: str = "http://localhost:11434",
        keep_alive: str = "10s",
        arize_space_id: Optional[str] = None,
        arize_api_key: Optional[str] = None,
        arize_project_name: str = "memBlocks",
        usage_tracker: Optional["LLMUsageTracker"] = None,
        call_type: LLMCallType = LLMCallType.CONVERSATION,
    ) -> "OllamaLLMProvider":
        """Construct a provider directly from ``LLMTaskSettings``.

        This is the preferred path when ``MemBlocksClient`` builds per-task
        providers from ``config.resolved_llm_settings``.

        Args:
            task_settings: Task-specific LLM settings (model, temperature).
                ``fallback_models`` and ``enable_thinking`` are ignored for Ollama.
            base_url: Ollama server base URL (default: http://localhost:11434).
            keep_alive: How long to keep the model loaded after last request
                (default: "10s"). Use duration string like "10s", "5m", "1h", or "-1" for unlimited.
            arize_space_id: Optional Arize monitoring space ID.
            arize_api_key: Optional Arize monitoring API key.
            arize_project_name: Arize project name.
            usage_tracker: Optional tracker to record token usage and latency
                after every LLM call made by this provider instance.
            call_type: The ``LLMCallType`` label recorded with each call.
                Set by ``MemBlocksClient._build_provider()`` based on which
                pipeline task this provider serves.

        Returns:
            Configured ``OllamaLLMProvider`` instance.
        """
        instance = cls.__new__(cls)
        instance._base_url = base_url
        instance._keep_alive = keep_alive
        instance._model = task_settings.model
        instance._default_temperature = task_settings.temperature
        instance._usage_tracker = usage_tracker
        instance._call_type = call_type

        if arize_space_id and arize_api_key:
            try:
                from openinference.instrumentation.langchain import (
                    LangChainInstrumentor,
                )
                from arize.otel import register
                from opentelemetry import trace

                existing = trace.get_tracer_provider()
                if not hasattr(existing, "_initialized"):
                    tracer_provider = register(
                        space_id=arize_space_id,
                        api_key=arize_api_key,
                        project_name=arize_project_name,
                    )
                    tracer_provider._initialized = True
                    LangChainInstrumentor().instrument(tracer_provider=tracer_provider)
            except ImportError:
                logger.warning(
                    "Arize/openinference packages not installed — monitoring disabled."
                )
        else:
            logger.debug(
                "Arize monitoring disabled (ARIZE_SPACE_ID / ARIZE_API_KEY not set)"
            )

        return instance

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_usage(
        self,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        latency_ms: float,
        block_id: Optional[str],
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Push a ``LLMCallRecord`` to the tracker (no-op if not configured)."""
        if self._usage_tracker is None:
            return
        self._usage_tracker.record(
            LLMCallRecord(
                call_type=self._call_type,
                block_id=block_id,
                model=self._model,
                provider="ollama",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                latency_ms=latency_ms,
                success=success,
                error=error,
            )
        )

    # ------------------------------------------------------------------
    # LLMProvider implementation
    # ------------------------------------------------------------------

    def create_structured_chain(
        self,
        system_prompt: str,
        pydantic_model: Type[BaseModel],
        temperature: float = 0.0,
    ) -> Any:
        """
        Create a LangChain structured-output chain using Ollama's JSON mode.

        Token usage and wall-clock latency are captured for every ``ainvoke``
        call via the ``LLMUsageTracker`` supplied at construction time.  The
        chain uses ``include_raw=True`` internally so that ``usage_metadata``
        is accessible; callers still receive the plain parsed Pydantic object.

        Args:
            system_prompt: System-level prompt string.
            pydantic_model: Pydantic v2 model class for output parsing.
            temperature: Sampling temperature.

        Returns:
            An async-callable wrapper that accepts ``{"input": str}`` and
            returns a ``pydantic_model`` instance, recording usage on each call.
        """
        llm = ChatOllama(
            model=self._model,
            temperature=temperature,
            base_url=self._base_url,
            keep_alive=self._keep_alive,
            format="json",
            num_ctx=264000,
            reasoning=False
        )

        # include_raw=True so we can read usage_metadata from the raw AIMessage.
        structured_llm = llm.with_structured_output(
            pydantic_model,
            include_raw=True,
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("user", "{input}"),
            ]
        )

        raw_chain = prompt | structured_llm
        tracker = self._usage_tracker
        call_type = self._call_type
        model = self._model

        class _TrackedChain:
            """Thin async wrapper that times the call and records token usage."""

            async def ainvoke(
                self_inner, inputs: Dict[str, Any], block_id: Optional[str] = None
            ) -> Any:
                t0 = time.monotonic()
                error_msg: Optional[str] = None
                raw_result: Any = None
                try:
                    raw_result = await raw_chain.ainvoke(inputs)
                    return raw_result["parsed"]
                except Exception as exc:
                    error_msg = str(exc)
                    raise
                finally:
                    latency_ms = (time.monotonic() - t0) * 1000
                    in_tok = out_tok = tot_tok = 0
                    if raw_result is not None:
                        raw_msg = raw_result.get("raw")
                        if raw_msg is not None and hasattr(raw_msg, "usage_metadata"):
                            meta = raw_msg.usage_metadata or {}
                            in_tok = meta.get("input_tokens", 0)
                            out_tok = meta.get("output_tokens", 0)
                            tot_tok = meta.get("total_tokens", in_tok + out_tok)
                    if tracker is not None:
                        tracker.record(
                            LLMCallRecord(
                                call_type=call_type,
                                block_id=block_id,
                                model=model,
                                provider="ollama",
                                input_tokens=in_tok,
                                output_tokens=out_tok,
                                total_tokens=tot_tok,
                                latency_ms=latency_ms,
                                success=error_msg is None,
                                error=error_msg,
                            )
                        )

        return _TrackedChain()

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        block_id: Optional[str] = None,
    ) -> str:
        """
        Send a conversation and return the assistant's response text.

        Token usage and latency are captured via the ``LLMUsageTracker``
        supplied at construction time.

        Args:
            messages: Conversation history as ``[{"role": ..., "content": ...}, ...]``.
            temperature: Override temperature.  Defaults to
                         ``config.llm_convo_temperature`` set in ``__init__``.
            block_id: Optional block ID to associate this call with in the
                      usage tracker.

        Returns:
            Assistant response text (``response.content``).
        """
        effective_temp = (
            temperature if temperature is not None else self._default_temperature
        )
        llm = ChatOllama(
            model=self._model,
            temperature=effective_temp,
            base_url=self._base_url,
            keep_alive=self._keep_alive,
            num_ctx=264000,
            reasoning=False,
        )
        t0 = time.monotonic()
        error_msg: Optional[str] = None
        response: Any = None
        try:
            response = await llm.ainvoke(messages)
            return response.content
        except Exception as exc:
            error_msg = str(exc)
            raise
        finally:
            latency_ms = (time.monotonic() - t0) * 1000
            in_tok = out_tok = tot_tok = 0
            if response is not None and hasattr(response, "usage_metadata"):
                meta = response.usage_metadata or {}
                in_tok = meta.get("input_tokens", 0)
                out_tok = meta.get("output_tokens", 0)
                tot_tok = meta.get("total_tokens", in_tok + out_tok)
            self._record_usage(
                input_tokens=in_tok,
                output_tokens=out_tok,
                total_tokens=tot_tok,
                latency_ms=latency_ms,
                block_id=block_id,
                success=error_msg is None,
                error=error_msg,
            )
