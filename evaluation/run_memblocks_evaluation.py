"""Run MemBlocks transparency-driven evaluation over a fixed message set.

This script runs one or more MemBlocks method variants against a dataset
(default: 30 messages), then writes comparison-ready artifacts:

- per-turn latency and token deltas
- process-level token/timing breakdowns (PS1, PS2, retrieval, core, summary, conversation)
- retrieval/pipeline transparency logs
- aggregated high/low/avg/p95 timings
- cross-method comparison CSV/Markdown
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import statistics
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from memblocks import MemBlocksClient, MemBlocksConfig
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings


VALID_TASK_NAMES = {
    "default",
    "conversation",
    "ps1_semantic_extraction",
    "ps2_conflict_resolution",
    "retrieval",
    "core_memory_extraction",
    "recursive_summary",
}

EVENT_NAMES = [
    "on_memory_extracted",
    "on_conflict_resolved",
    "on_memory_stored",
    "on_core_memory_updated",
    "on_summary_generated",
    "on_pipeline_started",
    "on_pipeline_completed",
    "on_pipeline_failed",
    "on_memory_retrieved",
    "on_db_write",
    "on_message_processed",
]

PROCESS_ORDER = [
    "ps1_extraction",
    "ps2_conflict",
    "retrieval",
    "core_memory",
    "summary",
    "conversation",
]

USER_PATH_CALL_TYPES = {"retrieval", "conversation"}
BACKGROUND_CALL_TYPES = {"ps1_extraction", "ps2_conflict", "core_memory", "summary"}


@dataclass
class MethodSpec:
    """Single evaluation method variant loaded from a JSON file."""

    name: str
    description: str = ""
    config_overrides: Dict[str, Any] = field(default_factory=dict)
    llm_task_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)


class EventCollector:
    """Collect published transparency events in-memory for later analysis."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []
        self.counts: Dict[str, int] = defaultdict(int)

    def make_callback(self, event_name: str):
        def _callback(payload: Any) -> None:
            self.events.append(
                {
                    "timestamp": utc_now_iso(),
                    "event_name": event_name,
                    "payload": payload,
                }
            )
            self.counts[event_name] += 1

        return _callback


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def to_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable primitives."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_serializable(v) for v in obj]
    if isinstance(obj, tuple):
        return [to_serializable(v) for v in obj]
    return obj


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(to_serializable(payload), f, indent=2, default=str)


def percentile(sorted_values: List[float], q: float) -> Optional[float]:
    """Calculate percentile using linear interpolation (matches numpy method)."""
    if not sorted_values:
        return None
    if q <= 0:
        return sorted_values[0]
    if q >= 1:
        return sorted_values[-1]

    # Linear interpolation between two nearest values
    pos = (len(sorted_values) - 1) * q
    idx_low = int(pos)
    idx_high = min(idx_low + 1, len(sorted_values) - 1)

    if idx_low == idx_high:
        return sorted_values[idx_low]

    # Interpolate between the two values
    weight = pos - idx_low
    return sorted_values[idx_low] * (1 - weight) + sorted_values[idx_high] * weight


def numeric_stats(values: Iterable[Optional[float]]) -> Dict[str, Optional[float]]:
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "avg": None,
            "p50": None,
            "p95": None,
            "stdev": None,
        }

    sorted_values = sorted(clean)
    avg = statistics.fmean(clean)
    stdev = statistics.pstdev(clean) if len(clean) > 1 else 0.0
    return {
        "count": len(clean),
        "min": min(clean),
        "max": max(clean),
        "avg": avg,
        "p50": percentile(sorted_values, 0.50),
        "p95": percentile(sorted_values, 0.95),
        "stdev": stdev,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MemBlocks evaluation with transparency metrics."
    )
    parser.add_argument(
        "--dataset",
        default="evaluation/datasets/default_30_messages.json",
        help="Path to JSON array of user messages.",
    )
    parser.add_argument(
        "--methods",
        default="evaluation/methods/default_methods.json",
        help="Path to JSON array of method specs.",
    )
    parser.add_argument(
        "--out-dir",
        default="evaluation/runs",
        help="Base output directory for run artifacts.",
    )
    parser.add_argument(
        "--user-prefix",
        default="evaluation_user",
        help="Prefix for generated evaluation user IDs.",
    )
    parser.add_argument(
        "--enforce-30",
        action="store_true",
        help="Fail if dataset does not contain exactly 30 messages.",
    )
    parser.add_argument(
        "--flush-at-end",
        action="store_true",
        default=True,
        help="Flush session at end to process residual messages.",
    )
    parser.add_argument(
        "--no-flush-at-end",
        action="store_false",
        dest="flush_at_end",
        help="Do not flush session at the end.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue evaluation even if a turn fails.",
    )
    parser.add_argument(
        "--use-reference-task-models",
        action="store_true",
        help=(
            "Use backend/src/cli/main.py-style per-task models as the base "
            "LLM settings before applying method overrides."
        ),
    )
    parser.add_argument(
        "--full-history-baseline",
        action="store_true",
        default=True,
        help=(
            "Also run a baseline that sends full chat history to the main "
            "conversation LLM at every turn."
        ),
    )
    parser.add_argument(
        "--no-full-history-baseline",
        action="store_false",
        dest="full_history_baseline",
        help="Disable full-history baseline calls.",
    )
    parser.add_argument(
        "--baseline-system-prompt",
        default="You are a helpful assistant with memory of past conversations.",
        help="System prompt used for the full-history baseline run.",
    )
    parser.add_argument(
        "--turn-delay-seconds",
        type=float,
        default=3.25,
        help=(
            "Delay after each turn to reduce rate-limit risk. "
            "Default 3.25s keeps per-turn model calls below ~20/min."
        ),
    )
    parser.add_argument(
        "--method-delay-seconds",
        type=float,
        default=8.0,
        help="Delay between method variants.",
    )
    parser.add_argument(
        "--memory-window-limit",
        type=int,
        default=20,
        help="Session memory window limit before pipeline flush triggers.",
    )
    parser.add_argument(
        "--keep-last-n",
        type=int,
        default=10,
        help="Messages kept in session after a pipeline flush.",
    )
    parser.add_argument(
        "--session-add-background",
        action="store_true",
        default=True,
        help="Queue session.add in background (matches production async pattern).",
    )
    parser.add_argument(
        "--no-session-add-background",
        action="store_false",
        dest="session_add_background",
        help="Await session.add inline instead of background queuing.",
    )
    return parser.parse_args()


def load_messages(path: Path, enforce_30: bool) -> List[str]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list) or any(not isinstance(x, str) for x in payload):
        raise ValueError("Dataset must be a JSON array of strings.")

    messages = [x.strip() for x in payload if x.strip()]
    if enforce_30 and len(messages) != 30:
        raise ValueError(f"--enforce-30 set but dataset has {len(messages)} messages.")
    return messages


def load_methods(path: Path) -> List[MethodSpec]:
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, list):
        raise ValueError("Methods file must be a JSON array.")

    methods: List[MethodSpec] = []
    seen_names: set[str] = set()
    for raw in payload:
        if not isinstance(raw, dict):
            raise ValueError("Each method entry must be a JSON object.")
        name = str(raw.get("name", "")).strip()
        if not name:
            raise ValueError("Each method must have a non-empty 'name'.")
        if name in seen_names:
            raise ValueError(f"Duplicate method name: {name}")
        seen_names.add(name)

        llm_task_overrides = raw.get("llm_task_overrides", {}) or {}
        if not isinstance(llm_task_overrides, dict):
            raise ValueError(f"llm_task_overrides for '{name}' must be an object.")

        for task_name, override in llm_task_overrides.items():
            if task_name not in VALID_TASK_NAMES:
                raise ValueError(
                    f"Unknown llm task '{task_name}' for '{name}'. "
                    f"Valid tasks: {sorted(VALID_TASK_NAMES)}"
                )
            if not isinstance(override, dict):
                raise ValueError(
                    f"llm_task_overrides[{task_name}] for '{name}' must be an object."
                )

        methods.append(
            MethodSpec(
                name=name,
                description=str(raw.get("description", "")).strip(),
                config_overrides=raw.get("config_overrides", {}) or {},
                llm_task_overrides=llm_task_overrides,
            )
        )

    if not methods:
        raise ValueError("No methods found.")
    return methods


def build_reference_llm_settings() -> LLMSettings:
    """Match the reference style used in backend/src/cli/main.py."""
    return LLMSettings(
        default=LLMTaskSettings(
            provider="ollama",
            model="hf.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M",
            temperature=0.0,
        ),
        conversation=LLMTaskSettings(
            provider="ollama",
            model="hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M",
            temperature=0.7,
        ),
        retrieval=LLMTaskSettings(
            provider="ollama",
            model="hf.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M",
            temperature=0.4,
        ),
        ps1_semantic_extraction=LLMTaskSettings(
            provider="groq", model="openai/gpt-oss-120b", temperature=0.0
        ),
        ps2_conflict_resolution=LLMTaskSettings(
            provider="ollama",
            model="hf.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M",
            temperature=0.0,
        ),
        core_memory_extraction=LLMTaskSettings(
            provider="groq", model="openai/gpt-oss-120b", temperature=0.0
        ),
        recursive_summary=LLMTaskSettings(
            provider="groq", model="openai/gpt-oss-120b", temperature=0.3
        ),
    )


def apply_llm_task_overrides(
    base_settings: LLMSettings,
    task_overrides: Dict[str, Dict[str, Any]],
) -> LLMSettings:
    """Return LLMSettings with task-level overrides merged in."""
    merged = base_settings.model_copy(deep=True)

    for task_name, override in task_overrides.items():
        if task_name == "default":
            base_task = merged.default
            payload = base_task.model_dump()
            payload.update(override)
            merged.default = LLMTaskSettings(**payload)
            continue

        existing = getattr(merged, task_name)
        if existing is None:
            existing = merged.default

        payload = existing.model_dump()
        payload.update(override)
        setattr(merged, task_name, LLMTaskSettings(**payload))

    return merged


def build_method_config(
    base_config: MemBlocksConfig,
    method: MethodSpec,
    use_reference_task_models: bool,
) -> MemBlocksConfig:
    """Construct method config by merging base config + method overrides."""
    config_data = base_config.model_dump()

    base_llm_settings = (
        build_reference_llm_settings()
        if use_reference_task_models
        else base_config.resolved_llm_settings
    )
    effective_llm_settings = apply_llm_task_overrides(
        base_llm_settings,
        method.llm_task_overrides,
    )

    config_data["llm_settings"] = effective_llm_settings.model_dump()
    config_data.update(method.config_overrides)
    return MemBlocksConfig(**config_data)


def build_system_prompt(summary: str, memory_prompt: str) -> str:
    parts = ["You are a helpful assistant with memory of past conversations."]
    if summary:
        parts.append(f"<Conversation Summary>\n{summary}\n</Conversation Summary>")
    if memory_prompt:
        parts.append(memory_prompt)
    return "\n\n".join(parts)


def messages_char_len(messages: List[Dict[str, str]]) -> int:
    return sum(len(m.get("content", "")) for m in messages)


async def maybe_sleep(seconds: float) -> None:
    if seconds > 0:
        await asyncio.sleep(seconds)


def summarize_llm_records(records: List[Any]) -> Dict[str, Any]:
    """Aggregate LLM usage records by process and by process+model."""
    by_call_type: Dict[str, Dict[str, Any]] = {}
    by_process_model: Dict[str, Dict[str, Any]] = {}

    for ct in PROCESS_ORDER:
        ct_records = [r for r in records if r.call_type.value == ct]
        latencies = [float(r.latency_ms) for r in ct_records]
        by_call_type[ct] = {
            "request_count": len(ct_records),
            "total_input_tokens": sum(int(r.input_tokens) for r in ct_records),
            "total_output_tokens": sum(int(r.output_tokens) for r in ct_records),
            "total_tokens": sum(int(r.total_tokens) for r in ct_records),
            "latency_ms": numeric_stats(latencies),
            "providers": sorted({r.provider for r in ct_records}),
            "models": sorted({r.model for r in ct_records}),
        }

    grouped: Dict[tuple[str, str, str], List[Any]] = defaultdict(list)
    for r in records:
        grouped[(r.call_type.value, r.provider, r.model)].append(r)

    for (call_type, provider, model), group in grouped.items():
        key = f"{call_type}|{provider}|{model}"
        by_process_model[key] = {
            "call_type": call_type,
            "provider": provider,
            "model": model,
            "request_count": len(group),
            "total_input_tokens": sum(int(r.input_tokens) for r in group),
            "total_output_tokens": sum(int(r.output_tokens) for r in group),
            "total_tokens": sum(int(r.total_tokens) for r in group),
            "latency_ms": numeric_stats(float(r.latency_ms) for r in group),
        }

    total_latencies = [float(r.latency_ms) for r in records]
    return {
        "request_count": len(records),
        "total_input_tokens": sum(int(r.input_tokens) for r in records),
        "total_output_tokens": sum(int(r.output_tokens) for r in records),
        "total_tokens": sum(int(r.total_tokens) for r in records),
        "latency_ms": numeric_stats(total_latencies),
        "by_call_type": by_call_type,
        "by_process_model": by_process_model,
    }


def summarize_llm_records_by_allowed_call_types(
    records: List[Any],
    allowed_call_types: set[str],
) -> Dict[str, Any]:
    filtered = [
        r for r in records if getattr(r.call_type, "value", "") in allowed_call_types
    ]
    return summarize_llm_records(filtered)


def summarize_retrieval_entries(entries: List[Any]) -> Dict[str, Any]:
    if not entries:
        return {
            "count": 0,
            "num_results": numeric_stats([]),
            "expanded_queries_generated": numeric_stats([]),
            "hypothetical_paragraphs_generated": numeric_stats([]),
            "reranked_ratio": 0.0,
            "retrieval_method_counts": {},
            "source_counts": {},
        }

    num_results = [int(e.num_results) for e in entries]
    expanded = [max(0, len(getattr(e, "expanded_queries", [])) - 1) for e in entries]
    hypothetical = [len(getattr(e, "hypothetical_paragraphs", [])) for e in entries]
    reranked_count = sum(1 for e in entries if bool(getattr(e, "reranked", False)))

    method_counts: Dict[str, int] = defaultdict(int)
    source_counts: Dict[str, int] = defaultdict(int)
    for e in entries:
        method_counts[str(getattr(e, "retrieval_method", "unknown"))] += 1
        source_counts[str(getattr(e, "source", "unknown"))] += 1

    return {
        "count": len(entries),
        "num_results": numeric_stats(num_results),
        "expanded_queries_generated": numeric_stats(expanded),
        "hypothetical_paragraphs_generated": numeric_stats(hypothetical),
        "reranked_ratio": reranked_count / len(entries),
        "retrieval_method_counts": dict(method_counts),
        "source_counts": dict(source_counts),
    }


def summarize_processing_runs(runs: List[Any]) -> Dict[str, Any]:
    if not runs:
        return {
            "count": 0,
            "status_counts": {},
            "duration_ms": numeric_stats([]),
            "trigger_counts": {},
            "llm_usage_snapshot_aggregate": {},
        }

    status_counts: Dict[str, int] = defaultdict(int)
    trigger_counts: Dict[str, int] = defaultdict(int)
    durations: List[float] = []

    llm_usage_aggregate: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "request_count": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "total_latency_ms": 0.0,
        }
    )

    for run in runs:
        status = str(getattr(run, "status", "unknown"))
        trigger = str(getattr(run, "trigger_event", "unknown"))
        status_counts[status] += 1
        trigger_counts[trigger] += 1

        started = getattr(run, "timestamp_started", None)
        completed = getattr(run, "timestamp_completed", None)
        if started and completed:
            durations.append((completed - started).total_seconds() * 1000.0)

        usage_snapshot = getattr(run, "llm_usage", {}) or {}
        if isinstance(usage_snapshot, dict):
            for call_type, stats in usage_snapshot.items():
                if not isinstance(stats, dict):
                    continue
                bucket = llm_usage_aggregate[call_type]
                bucket["request_count"] += int(stats.get("request_count", 0))
                bucket["total_input_tokens"] += int(stats.get("total_input_tokens", 0))
                bucket["total_output_tokens"] += int(
                    stats.get("total_output_tokens", 0)
                )
                bucket["total_tokens"] += int(stats.get("total_tokens", 0))
                bucket["total_latency_ms"] += float(stats.get("total_latency_ms", 0.0))

    for call_type, bucket in llm_usage_aggregate.items():
        count = bucket["request_count"]
        bucket["avg_latency_ms"] = (
            bucket["total_latency_ms"] / count if count > 0 else None
        )

    return {
        "count": len(runs),
        "status_counts": dict(status_counts),
        "duration_ms": numeric_stats(durations),
        "trigger_counts": dict(trigger_counts),
        "llm_usage_snapshot_aggregate": dict(llm_usage_aggregate),
    }


def summarize_operation_entries(entries: List[Any]) -> Dict[str, Any]:
    by_db: Dict[str, int] = defaultdict(int)
    by_operation: Dict[str, int] = defaultdict(int)
    success_count = 0
    failure_count = 0
    for e in entries:
        by_db[str(e.db_type.value if hasattr(e.db_type, "value") else e.db_type)] += 1
        by_operation[
            str(
                e.operation_type.value
                if hasattr(e.operation_type, "value")
                else e.operation_type
            )
        ] += 1
        if bool(getattr(e, "success", False)):
            success_count += 1
        else:
            failure_count += 1

    return {
        "count": len(entries),
        "success_count": success_count,
        "failure_count": failure_count,
        "by_db": dict(by_db),
        "by_operation": dict(by_operation),
    }


def effective_task_map(config: MemBlocksConfig) -> Dict[str, Dict[str, Any]]:
    settings = config.resolved_llm_settings
    task_names = [
        "default",
        "conversation",
        "ps1_semantic_extraction",
        "ps2_conflict_resolution",
        "retrieval",
        "core_memory_extraction",
        "recursive_summary",
    ]
    output: Dict[str, Dict[str, Any]] = {}
    for task in task_names:
        resolved = settings.for_task(task)
        output[task] = resolved.model_dump()
    return output


def retrieval_config_map(config: MemBlocksConfig) -> Dict[str, Any]:
    keys = [
        "retrieval_enable_sparse",
        "retrieval_enable_query_expansion",
        "retrieval_enable_hypothetical_paragraphs",
        "retrieval_enable_reranking",
        "retrieval_top_k_per_query",
        "retrieval_final_top_k",
        "retrieval_num_query_expansions",
        "retrieval_num_hypothetical_paragraphs",
    ]
    return {k: getattr(config, k) for k in keys}


async def evaluate_method(
    method: MethodSpec,
    config: MemBlocksConfig,
    messages: List[str],
    user_prefix: str,
    method_output_dir: Path,
    continue_on_error: bool,
    flush_at_end: bool,
    turn_delay_seconds: float,
    memory_window_limit: int,
    keep_last_n: int,
    session_add_background: bool,
) -> Dict[str, Any]:
    """Run a single method and return full report payload."""
    client = MemBlocksClient(config)
    collector = EventCollector()
    for event_name in EVENT_NAMES:
        client.subscribe(event_name, collector.make_callback(event_name))

    run_token = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    user_id = f"{user_prefix}_{method.name}_{run_token}"

    operation_log = client.get_operation_log()
    retrieval_log = client.get_retrieval_log()
    processing_history = client.get_processing_history()
    usage_tracker = client.get_llm_usage()

    turns: List[Dict[str, Any]] = []
    flush_report: Optional[Dict[str, Any]] = None
    background_add_tasks: List[asyncio.Task[Any]] = []

    try:
        await client.get_or_create_user(user_id)
        block = await client.create_block(
            user_id=user_id,
            name=f"Evaluation {method.name}",
            description=f"Auto-created evaluation block for {method.name}",
        )
        session = await client.create_session(user_id=user_id, block_id=block.id)
        session._memory_window_limit = memory_window_limit
        session._keep_last_n = keep_last_n

        for idx, user_message in enumerate(messages, start=1):
            print(
                f"[PROGRESS] Turn {idx}/{len(messages)} - {method.name}",
                end="\r",
                flush=True,
            )

            turn_started_at = utc_now()
            turn_t0 = time.perf_counter()

            usage_before = usage_tracker.get_records(limit=100000)
            retrieval_before = retrieval_log.get_entries(limit=100000)
            runs_before = processing_history.get_runs(limit=100000)
            operations_before = operation_log.get_entries(limit=100000)

            turn_error: Optional[str] = None
            ai_response = ""
            retrieval_ms: Optional[float] = None
            conversation_ms: Optional[float] = None
            memory_window_ms: Optional[float] = None
            summary_ms: Optional[float] = None
            session_add_ms: Optional[float] = None
            prompt_char_len: Optional[int] = None
            memory_window_len: Optional[int] = None

            try:
                t0_retrieve = time.perf_counter()
                context = await block.retrieve(user_message)
                retrieval_ms = (time.perf_counter() - t0_retrieve) * 1000.0

                t0_memory_window = time.perf_counter()
                memory_window = await session.get_memory_window()
                memory_window_len = len(memory_window)
                memory_window_ms = (time.perf_counter() - t0_memory_window) * 1000.0

                t0_summary = time.perf_counter()
                summary = await session.get_recursive_summary()
                summary_ms = (time.perf_counter() - t0_summary) * 1000.0

                system_prompt = build_system_prompt(summary, context.to_prompt_string())
                prompt_char_len = len(system_prompt)

                llm_messages = [
                    {"role": "system", "content": system_prompt},
                    *memory_window,
                    {"role": "user", "content": user_message},
                ]

                t0_conversation = time.perf_counter()
                conversation_llm: Any = client.conversation_llm
                ai_response = await conversation_llm.chat(
                    messages=llm_messages,
                    block_id=block.id,
                )
                conversation_ms = (time.perf_counter() - t0_conversation) * 1000.0

                if session_add_background:
                    task = asyncio.create_task(
                        session.add(user_msg=user_message, ai_response=ai_response)
                    )
                    background_add_tasks.append(task)
                else:
                    t0_session_add = time.perf_counter()
                    await session.add(user_msg=user_message, ai_response=ai_response)
                    session_add_ms = (time.perf_counter() - t0_session_add) * 1000.0

            except Exception as exc:
                turn_error = str(exc)
                if not continue_on_error:
                    raise

            turn_total_ms = (time.perf_counter() - turn_t0) * 1000.0

            # Calculate user-facing latency (only operations that block the user)
            user_facing_ms = (
                (retrieval_ms or 0)
                + (conversation_ms or 0)
                + (memory_window_ms or 0)
                + (summary_ms or 0)
            )

            usage_after = usage_tracker.get_records(limit=100000)
            retrieval_after = retrieval_log.get_entries(limit=100000)
            runs_after = processing_history.get_runs(limit=100000)
            operations_after = operation_log.get_entries(limit=100000)

            new_usage = usage_after[len(usage_before) :]
            new_retrieval = retrieval_after[len(retrieval_before) :]
            new_runs = runs_after[len(runs_before) :]
            new_operations = operations_after[len(operations_before) :]

            turn_usage_summary = summarize_llm_records(new_usage)
            turn_user_path_usage_summary = summarize_llm_records_by_allowed_call_types(
                new_usage,
                USER_PATH_CALL_TYPES,
            )
            turn_background_usage_summary = summarize_llm_records_by_allowed_call_types(
                new_usage,
                BACKGROUND_CALL_TYPES,
            )
            turn_retrieval_summary = summarize_retrieval_entries(new_retrieval)
            turn_pipeline_summary = summarize_processing_runs(new_runs)
            turn_operation_summary = summarize_operation_entries(new_operations)

            turns.append(
                {
                    "turn_index": idx,
                    "user_message": user_message,
                    "assistant_response": ai_response,
                    "assistant_response_char_len": len(ai_response),
                    "timing_ms": {
                        "turn_total": turn_total_ms,
                        "user_facing": user_facing_ms,  # NEW: Only user-blocking operations
                        "retrieve": retrieval_ms,
                        "conversation": conversation_ms,
                        "memory_window": memory_window_ms,  # NEW
                        "summary": summary_ms,  # NEW
                        "session_add": session_add_ms,  # NEW: Only set if sync mode
                    },
                    "prompt_char_len": prompt_char_len,
                    "memory_window_len": memory_window_len,
                    "status": "error" if turn_error else "success",
                    "error": turn_error,
                    "token_usage": turn_usage_summary,
                    "token_usage_user_path": turn_user_path_usage_summary,
                    "token_usage_background": turn_background_usage_summary,
                    "retrieval": turn_retrieval_summary,
                    "pipeline": turn_pipeline_summary,
                    "operations": turn_operation_summary,
                    "started_at": turn_started_at.isoformat(),
                    "completed_at": utc_now_iso(),
                }
            )

            await maybe_sleep(turn_delay_seconds)

        # Wait for all background tasks and capture errors
        background_errors: List[Dict[str, Any]] = []
        if background_add_tasks:
            print(
                f"\n[BACKGROUND] Waiting for {len(background_add_tasks)} background tasks..."
            )
            background_results = await asyncio.gather(
                *background_add_tasks, return_exceptions=True
            )
            for idx, result in enumerate(background_results):
                if isinstance(result, Exception):
                    error_info = {
                        "turn_index": idx + 1,
                        "error": str(result),
                        "error_type": type(result).__name__,
                    }
                    background_errors.append(error_info)
                    print(
                        f"[WARNING] Background task for turn {idx + 1} failed: {result}"
                    )

            if background_errors:
                print(
                    f"[WARNING] {len(background_errors)} background tasks failed out of {len(background_add_tasks)}"
                )
            else:
                print(
                    f"[SUCCESS] All {len(background_add_tasks)} background tasks completed successfully"
                )

        if flush_at_end:
            flush_started = utc_now()
            flush_t0 = time.perf_counter()

            usage_before = usage_tracker.get_records(limit=100000)
            retrieval_before = retrieval_log.get_entries(limit=100000)
            runs_before = processing_history.get_runs(limit=100000)
            operations_before = operation_log.get_entries(limit=100000)

            flush_error: Optional[str] = None
            flush_summary_text = ""
            try:
                flush_summary_text = await session.flush()
            except Exception as exc:
                flush_error = str(exc)

            flush_total_ms = (time.perf_counter() - flush_t0) * 1000.0

            usage_after = usage_tracker.get_records(limit=100000)
            retrieval_after = retrieval_log.get_entries(limit=100000)
            runs_after = processing_history.get_runs(limit=100000)
            operations_after = operation_log.get_entries(limit=100000)

            new_usage = usage_after[len(usage_before) :]
            new_retrieval = retrieval_after[len(retrieval_before) :]
            new_runs = runs_after[len(runs_before) :]
            new_operations = operations_after[len(operations_before) :]

            flush_report = {
                "status": "error" if flush_error else "success",
                "error": flush_error,
                "summary_char_len": len(flush_summary_text),
                "timing_ms": flush_total_ms,
                "token_usage": summarize_llm_records(new_usage),
                "retrieval": summarize_retrieval_entries(new_retrieval),
                "pipeline": summarize_processing_runs(new_runs),
                "operations": summarize_operation_entries(new_operations),
                "started_at": flush_started.isoformat(),
                "completed_at": utc_now_iso(),
            }

        llm_records = usage_tracker.get_records(limit=100000)
        retrieval_entries = retrieval_log.get_entries(limit=100000)
        processing_runs = processing_history.get_runs(limit=100000)
        operation_entries = operation_log.get_entries(limit=100000)

        # Validate turn count
        if len(turns) != len(messages):
            error_msg = f"Expected {len(messages)} turns but got {len(turns)}"
            print(f"\n[ERROR] {error_msg}")

        turn_total_latencies = [
            t["timing_ms"]["turn_total"] for t in turns if t["timing_ms"]["turn_total"]
        ]
        turn_user_facing_latencies = [
            t["timing_ms"]["user_facing"]
            for t in turns
            if t["timing_ms"].get("user_facing") is not None
        ]
        turn_retrieve_latencies = [
            t["timing_ms"]["retrieve"]
            for t in turns
            if t["timing_ms"]["retrieve"] is not None
        ]
        turn_conversation_latencies = [
            t["timing_ms"]["conversation"]
            for t in turns
            if t["timing_ms"]["conversation"] is not None
        ]

        llm_summary = summarize_llm_records(llm_records)
        llm_user_path_summary = summarize_llm_records_by_allowed_call_types(
            llm_records,
            USER_PATH_CALL_TYPES,
        )
        llm_background_summary = summarize_llm_records_by_allowed_call_types(
            llm_records,
            BACKGROUND_CALL_TYPES,
        )
        retrieval_summary = summarize_retrieval_entries(retrieval_entries)
        pipeline_summary = summarize_processing_runs(processing_runs)
        operation_summary = summarize_operation_entries(operation_entries)

        successful_turns = sum(1 for t in turns if t["status"] == "success")
        failed_turns = len(turns) - successful_turns

        method_report = {
            "method": {
                "name": method.name,
                "description": method.description,
                "config_overrides": method.config_overrides,
                "llm_task_overrides": method.llm_task_overrides,
                "effective_retrieval_config": retrieval_config_map(config),
                "effective_llm_tasks": effective_task_map(config),
            },
            "run_context": {
                "started_at": turns[0]["started_at"] if turns else utc_now_iso(),
                "completed_at": utc_now_iso(),
                "user_id": user_id,
                "block_id": block.id,
                "session_id": session.id,
            },
            "dataset": {
                "message_count": len(messages),
            },
            "totals": {
                "turn_count": len(turns),
                "successful_turns": successful_turns,
                "failed_turns": failed_turns,
                "failure_rate": (failed_turns / len(turns)) if turns else 0.0,
            },
            "timing_ms": {
                "turn_total": numeric_stats(turn_total_latencies),
                "user_facing": numeric_stats(turn_user_facing_latencies),  # NEW
                "retrieve": numeric_stats(turn_retrieve_latencies),
                "conversation": numeric_stats(turn_conversation_latencies),
                "pipeline_run_duration": pipeline_summary["duration_ms"],
            },
            "background_task_errors": background_errors,  # NEW
            "token_usage": llm_summary,
            "token_usage_user_path": llm_user_path_summary,
            "token_usage_background": llm_background_summary,
            "token_usage_split": split_user_vs_background_llm(llm_summary),
            "retrieval": retrieval_summary,
            "pipeline": pipeline_summary,
            "operations": operation_summary,
            "events": {
                "counts": dict(collector.counts),
                "total_events": len(collector.events),
            },
            "flush": flush_report,
            "turns": turns,
        }

        method_output_dir.mkdir(parents=True, exist_ok=True)
        write_json(method_output_dir / "method_report.json", method_report)
        write_json(method_output_dir / "turns.json", turns)
        write_json(method_output_dir / "events.json", collector.events)
        write_turns_csv(method_output_dir / "turns.csv", turns)
        write_call_type_csv(
            method_output_dir / "llm_call_type_summary.csv", llm_summary
        )
        write_json(
            method_output_dir / "llm_records.json",
            [r.model_dump(mode="json") for r in llm_records],
        )
        write_json(
            method_output_dir / "retrieval_log.json",
            [r.model_dump(mode="json") for r in retrieval_entries],
        )
        write_json(
            method_output_dir / "processing_history.json",
            [r.model_dump(mode="json") for r in processing_runs],
        )
        write_json(
            method_output_dir / "operation_log.json",
            [r.model_dump(mode="json") for r in operation_entries],
        )

        return method_report

    finally:
        await client.close()


async def evaluate_full_history_baseline(
    config: MemBlocksConfig,
    messages: List[str],
    baseline_system_prompt: str,
    method_output_dir: Path,
    continue_on_error: bool,
    turn_delay_seconds: float,
    user_prefix: str,  # NEW: Need user_prefix for block creation
) -> Dict[str, Any]:
    """Run baseline using only full chat history for the conversation LLM.

    This baseline does not call MemBlocks retrieval/session pipeline. It simulates
    the common approach: always pass entire prior chat messages to the main LLM.
    """
    client = MemBlocksClient(config)
    history: List[Dict[str, str]] = []
    turns: List[Dict[str, Any]] = []

    usage_tracker = client.get_llm_usage()

    # Create a baseline block for consistency with MemBlocks evaluation
    run_token = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    user_id = f"{user_prefix}_baseline_{run_token}"
    baseline_block_id: Optional[str] = None

    try:
        await client.get_or_create_user(user_id)
        baseline_block = await client.create_block(
            user_id=user_id,
            name="Evaluation Baseline",
            description="Full history baseline block",
        )
        baseline_block_id = baseline_block.id

        for idx, user_message in enumerate(messages, start=1):
            print(
                f"[PROGRESS] Turn {idx}/{len(messages)} - full_history_baseline",
                end="\r",
                flush=True,
            )

            turn_started_at = utc_now()
            turn_t0 = time.perf_counter()

            usage_before = usage_tracker.get_records(limit=100000)

            error_msg: Optional[str] = None
            ai_response = ""
            conversation_ms: Optional[float] = None

            llm_messages = [
                {"role": "system", "content": baseline_system_prompt},
                *history,
                {"role": "user", "content": user_message},
            ]

            try:
                t0 = time.perf_counter()
                conversation_llm: Any = client.conversation_llm
                ai_response = await conversation_llm.chat(
                    messages=llm_messages,
                    block_id=baseline_block_id,  # FIXED: Now consistent with MemBlocks
                )
                conversation_ms = (time.perf_counter() - t0) * 1000.0

                history.append({"role": "user", "content": user_message})
                history.append({"role": "assistant", "content": ai_response})
            except Exception as exc:
                error_msg = str(exc)
                if not continue_on_error:
                    raise

            turn_total_ms = (time.perf_counter() - turn_t0) * 1000.0

            usage_after = usage_tracker.get_records(limit=100000)
            new_usage = usage_after[len(usage_before) :]
            turn_usage_summary = summarize_llm_records(new_usage)

            turns.append(
                {
                    "turn_index": idx,
                    "user_message": user_message,
                    "assistant_response": ai_response,
                    "assistant_response_char_len": len(ai_response),
                    "status": "error" if error_msg else "success",
                    "error": error_msg,
                    "timing_ms": {
                        "turn_total": turn_total_ms,
                        "conversation": conversation_ms,
                    },
                    "full_history_message_count": len(llm_messages),
                    "full_history_char_len": messages_char_len(llm_messages),
                    "token_usage": turn_usage_summary,
                    "token_usage_user_path": turn_usage_summary,
                    "token_usage_background": summarize_llm_records([]),
                    "started_at": turn_started_at.isoformat(),
                    "completed_at": utc_now_iso(),
                }
            )

            await maybe_sleep(turn_delay_seconds)

        # Validate turn count
        if len(turns) != len(messages):
            error_msg = f"Expected {len(messages)} turns but got {len(turns)}"
            print(f"\n[ERROR] Baseline {error_msg}")

        llm_records = usage_tracker.get_records(limit=100000)
        llm_summary = summarize_llm_records(llm_records)

        turn_total_latencies = [
            t["timing_ms"].get("turn_total")
            for t in turns
            if t["timing_ms"].get("turn_total") is not None
        ]
        turn_conversation_latencies = [
            t["timing_ms"].get("conversation")
            for t in turns
            if t["timing_ms"].get("conversation") is not None
        ]

        successful_turns = sum(1 for t in turns if t["status"] == "success")
        failed_turns = len(turns) - successful_turns

        baseline_report = {
            "method": {
                "name": "full_history_baseline",
                "description": (
                    "Baseline: pass entire chat history to main conversation LLM "
                    "for each turn, without MemBlocks retrieval/pipeline context."
                ),
                "baseline_system_prompt": baseline_system_prompt,
            },
            "run_context": {
                "started_at": turns[0]["started_at"] if turns else utc_now_iso(),
                "completed_at": utc_now_iso(),
            },
            "dataset": {
                "message_count": len(messages),
            },
            "totals": {
                "turn_count": len(turns),
                "successful_turns": successful_turns,
                "failed_turns": failed_turns,
                "failure_rate": (failed_turns / len(turns)) if turns else 0.0,
            },
            "timing_ms": {
                "turn_total": numeric_stats(turn_total_latencies),
                "retrieve": numeric_stats([]),
                "conversation": numeric_stats(turn_conversation_latencies),
                "pipeline_run_duration": numeric_stats([]),
            },
            "token_usage": llm_summary,
            "token_usage_user_path": llm_summary,
            "token_usage_background": summarize_llm_records([]),
            "token_usage_split": {
                "user_path": {
                    "request_count": llm_summary.get("request_count", 0),
                    "total_input_tokens": llm_summary.get("total_input_tokens", 0),
                    "total_output_tokens": llm_summary.get("total_output_tokens", 0),
                    "total_tokens": llm_summary.get("total_tokens", 0),
                    "avg_tokens_per_request": (
                        llm_summary.get("total_tokens", 0)
                        / llm_summary.get("request_count", 1)
                        if llm_summary.get("request_count", 0) > 0
                        else None
                    ),
                },
                "background_pipeline": {
                    "request_count": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tokens": 0,
                    "avg_tokens_per_request": None,
                },
            },
            "retrieval": {
                "count": 0,
                "num_results": numeric_stats([]),
                "expanded_queries_generated": numeric_stats([]),
                "hypothetical_paragraphs_generated": numeric_stats([]),
                "reranked_ratio": 0.0,
                "retrieval_method_counts": {},
                "source_counts": {},
            },
            "pipeline": {
                "count": 0,
                "status_counts": {},
                "duration_ms": numeric_stats([]),
                "trigger_counts": {},
                "llm_usage_snapshot_aggregate": {},
            },
            "operations": {
                "count": 0,
                "success_count": 0,
                "failure_count": 0,
                "by_db": {},
                "by_operation": {},
            },
            "events": {
                "counts": {},
                "total_events": 0,
            },
            "flush": None,
            "turns": turns,
        }

        method_output_dir.mkdir(parents=True, exist_ok=True)
        write_json(method_output_dir / "method_report.json", baseline_report)
        write_json(method_output_dir / "turns.json", turns)
        write_turns_csv(method_output_dir / "turns.csv", turns)
        write_call_type_csv(
            method_output_dir / "llm_call_type_summary.csv", llm_summary
        )
        write_json(
            method_output_dir / "llm_records.json",
            [r.model_dump(mode="json") for r in llm_records],
        )

        return baseline_report

    finally:
        await client.close()


def build_comparison_rows(method_reports: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for report in method_reports:
        token_usage = report["token_usage"]
        by_call_type = token_usage.get("by_call_type", {})

        row = {
            "method": report["method"]["name"],
            "turns": report["totals"]["turn_count"],
            "failed_turns": report["totals"]["failed_turns"],
            "turn_avg_ms": report["timing_ms"]["turn_total"].get("avg"),
            "turn_p95_ms": report["timing_ms"]["turn_total"].get("p95"),
            "user_facing_avg_ms": report["timing_ms"]
            .get("user_facing", {})
            .get("avg"),  # NEW
            "user_facing_p95_ms": report["timing_ms"]
            .get("user_facing", {})
            .get("p95"),  # NEW
            "retrieval_avg_ms": report["timing_ms"]["retrieve"].get("avg"),
            "conversation_avg_ms": report["timing_ms"]["conversation"].get("avg"),
            "pipeline_avg_ms": report["timing_ms"]["pipeline_run_duration"].get("avg"),
            "llm_requests": token_usage.get("request_count", 0),
            "total_input_tokens": token_usage.get("total_input_tokens", 0),
            "total_output_tokens": token_usage.get("total_output_tokens", 0),
            "total_tokens": token_usage.get("total_tokens", 0),
            "user_path_tokens": report.get("token_usage_user_path", {}).get(
                "total_tokens", 0
            ),
            "background_tokens": report.get("token_usage_background", {}).get(
                "total_tokens", 0
            ),
            "user_path_requests": report.get("token_usage_user_path", {}).get(
                "request_count", 0
            ),
            "background_requests": report.get("token_usage_background", {}).get(
                "request_count", 0
            ),
            "tokens_per_turn": (
                token_usage.get("total_tokens", 0) / report["totals"]["turn_count"]
                if report["totals"]["turn_count"]
                else None
            ),
            "user_path_tokens_per_turn": (
                report.get("token_usage_user_path", {}).get("total_tokens", 0)
                / report["totals"]["turn_count"]
                if report["totals"]["turn_count"]
                else None
            ),
            "background_tokens_per_turn": (
                report.get("token_usage_background", {}).get("total_tokens", 0)
                / report["totals"]["turn_count"]
                if report["totals"]["turn_count"]
                else None
            ),
            "retrieval_entries": report["retrieval"]["count"],
            "retrieval_avg_results": report["retrieval"]["num_results"].get("avg"),
            "pipeline_runs": report["pipeline"]["count"],
            "full_history_baseline": report["method"]["name"]
            == "full_history_baseline",
        }

        for process in PROCESS_ORDER:
            process_metrics = by_call_type.get(process, {})
            row[f"{process}_requests"] = process_metrics.get("request_count", 0)
            row[f"{process}_input_tokens"] = process_metrics.get(
                "total_input_tokens", 0
            )
            row[f"{process}_output_tokens"] = process_metrics.get(
                "total_output_tokens", 0
            )
            row[f"{process}_tokens"] = process_metrics.get("total_tokens", 0)
            row[f"{process}_avg_latency_ms"] = (
                process_metrics.get("latency_ms", {}).get("avg")
                if process_metrics
                else None
            )

        rows.append(row)

    return rows


def add_full_history_deltas(rows: List[Dict[str, Any]]) -> None:
    """Calculate deltas vs baseline. Positive delta means MORE tokens (investment), negative means LESS (savings)."""
    baseline = next(
        (row for row in rows if row.get("method") == "full_history_baseline"), None
    )
    if not baseline:
        return

    baseline_total = baseline.get("total_tokens") or 0
    baseline_user_path_total = baseline.get("user_path_tokens") or 0
    baseline_conversation = baseline.get("conversation_tokens") or 0

    for row in rows:
        total = row.get("total_tokens") or 0
        user_path_total = row.get("user_path_tokens") or 0
        conv = row.get("conversation_tokens") or 0

        # Total token comparison
        row["vs_full_history_total_token_delta"] = total - baseline_total
        row["vs_full_history_total_token_delta_pct"] = (
            ((total - baseline_total) / baseline_total) * 100.0
            if baseline_total > 0
            else None
        )

        # Conversation token comparison
        row["vs_full_history_conversation_token_delta"] = conv - baseline_conversation
        row["vs_full_history_conversation_token_delta_pct"] = (
            ((conv - baseline_conversation) / baseline_conversation) * 100.0
            if baseline_conversation > 0
            else None
        )

        # User path token comparison
        row["vs_full_history_user_path_token_delta"] = (
            user_path_total - baseline_user_path_total
        )
        row["vs_full_history_user_path_token_delta_pct"] = (
            ((user_path_total - baseline_user_path_total) / baseline_user_path_total)
            * 100.0
            if baseline_user_path_total > 0
            else None
        )


def write_comparison_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_comparison_markdown(path: Path, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        path.write_text("# Comparison\n\nNo rows.\n", encoding="utf-8")
        return

    columns = [
        "method",
        "turn_avg_ms",
        "turn_p95_ms",
        "user_facing_avg_ms",  # NEW
        "user_facing_p95_ms",  # NEW
        "total_tokens",
        "tokens_per_turn",
        "user_path_tokens",
        "user_path_tokens_per_turn",
        "background_tokens",
        "background_tokens_per_turn",
        "vs_full_history_total_token_delta",
        "vs_full_history_total_token_delta_pct",  # RENAMED from savings_pct
        "vs_full_history_user_path_token_delta",
        "vs_full_history_user_path_token_delta_pct",  # RENAMED from savings_pct
        "llm_requests",
        "retrieval_avg_results",
        "pipeline_runs",
        "ps1_extraction_tokens",
        "ps2_conflict_tokens",
        "retrieval_tokens",
        "core_memory_tokens",
        "summary_tokens",
        "conversation_tokens",
    ]

    def _fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)

    lines = ["# Method Comparison", ""]
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")
    for row in rows:
        lines.append("| " + " | ".join(_fmt(row.get(c, "")) for c in columns) + " |")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_turns_csv(path: Path, turns: List[Dict[str, Any]]) -> None:
    if not turns:
        return

    rows: List[Dict[str, Any]] = []
    for turn in turns:
        row: Dict[str, Any] = {
            "turn_index": turn.get("turn_index"),
            "status": turn.get("status"),
            "timing_turn_total_ms": turn.get("timing_ms", {}).get("turn_total"),
            "timing_retrieve_ms": turn.get("timing_ms", {}).get("retrieve"),
            "timing_conversation_ms": turn.get("timing_ms", {}).get("conversation"),
            "prompt_char_len": turn.get("prompt_char_len"),
            "memory_window_len": turn.get("memory_window_len"),
            "assistant_response_char_len": turn.get("assistant_response_char_len"),
            "total_tokens": turn.get("token_usage", {}).get("total_tokens"),
            "user_path_tokens": turn.get("token_usage_user_path", {}).get(
                "total_tokens"
            ),
            "background_tokens": turn.get("token_usage_background", {}).get(
                "total_tokens"
            ),
            "total_input_tokens": turn.get("token_usage", {}).get("total_input_tokens"),
            "total_output_tokens": turn.get("token_usage", {}).get(
                "total_output_tokens"
            ),
            "llm_requests": turn.get("token_usage", {}).get("request_count"),
            "user_path_requests": turn.get("token_usage_user_path", {}).get(
                "request_count"
            ),
            "background_requests": turn.get("token_usage_background", {}).get(
                "request_count"
            ),
            "pipeline_runs": turn.get("pipeline", {}).get("count"),
            "retrieval_entries": turn.get("retrieval", {}).get("count"),
            "error": turn.get("error"),
        }

        by_call_type = turn.get("token_usage", {}).get("by_call_type", {})
        for process in PROCESS_ORDER:
            process_metrics = by_call_type.get(process, {})
            row[f"{process}_requests"] = process_metrics.get("request_count", 0)
            row[f"{process}_tokens"] = process_metrics.get("total_tokens", 0)
            row[f"{process}_avg_latency_ms"] = (
                process_metrics.get("latency_ms", {}).get("avg")
                if process_metrics
                else None
            )

        rows.append(row)

    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_call_type_csv(path: Path, llm_summary: Dict[str, Any]) -> None:
    by_call_type = llm_summary.get("by_call_type", {})
    if not by_call_type:
        return

    rows: List[Dict[str, Any]] = []
    for process in PROCESS_ORDER:
        metrics = by_call_type.get(process, {})
        lat = metrics.get("latency_ms", {})
        rows.append(
            {
                "call_type": process,
                "request_count": metrics.get("request_count", 0),
                "total_input_tokens": metrics.get("total_input_tokens", 0),
                "total_output_tokens": metrics.get("total_output_tokens", 0),
                "total_tokens": metrics.get("total_tokens", 0),
                "latency_min_ms": lat.get("min"),
                "latency_max_ms": lat.get("max"),
                "latency_avg_ms": lat.get("avg"),
                "latency_p95_ms": lat.get("p95"),
                "providers": ",".join(metrics.get("providers", [])),
                "models": ",".join(metrics.get("models", [])),
            }
        )

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def split_user_vs_background_llm(usage_summary: Dict[str, Any]) -> Dict[str, Any]:
    by_call_type = usage_summary.get("by_call_type", {})

    def _accumulate(call_types: set[str]) -> Dict[str, Any]:
        selected = [by_call_type.get(ct, {}) for ct in call_types]
        req = sum(int(s.get("request_count", 0)) for s in selected)
        in_tok = sum(int(s.get("total_input_tokens", 0)) for s in selected)
        out_tok = sum(int(s.get("total_output_tokens", 0)) for s in selected)
        total_tok = sum(int(s.get("total_tokens", 0)) for s in selected)
        return {
            "request_count": req,
            "total_input_tokens": in_tok,
            "total_output_tokens": out_tok,
            "total_tokens": total_tok,
            "avg_tokens_per_request": (total_tok / req) if req > 0 else None,
        }

    return {
        "user_path": _accumulate(USER_PATH_CALL_TYPES),
        "background_pipeline": _accumulate(BACKGROUND_CALL_TYPES),
    }


async def run() -> None:
    args = parse_args()

    dataset_path = Path(args.dataset)
    methods_path = Path(args.methods)
    out_base = Path(args.out_dir)

    messages = load_messages(dataset_path, enforce_30=args.enforce_30)
    methods = load_methods(methods_path)

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = out_base / f"run_{run_stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    base_config = MemBlocksConfig.model_validate({})

    print("=" * 80)
    print("MemBlocks Evaluation")
    print("=" * 80)
    print(f"Dataset: {dataset_path} ({len(messages)} messages)")
    print(f"Methods: {methods_path} ({len(methods)} variants)")
    print(f"Output:  {run_dir}")
    print(
        f"Full-history baseline: {'enabled' if args.full_history_baseline else 'disabled'}"
    )
    print(f"Turn delay (sec): {args.turn_delay_seconds}")
    print(f"Method delay (sec): {args.method_delay_seconds}")
    print(f"Memory window limit: {args.memory_window_limit}")
    print(f"Keep last N: {args.keep_last_n}")
    print(f"Session.add background: {args.session_add_background}")
    print("=" * 80)

    run_started_at = utc_now_iso()

    write_json(
        run_dir / "run_metadata.json",
        {
            "started_at": run_started_at,
            "dataset": str(dataset_path),
            "methods": str(methods_path),
            "message_count": len(messages),
            "flush_at_end": args.flush_at_end,
            "continue_on_error": args.continue_on_error,
            "use_reference_task_models": args.use_reference_task_models,
            "full_history_baseline": args.full_history_baseline,
            "baseline_system_prompt": args.baseline_system_prompt,
            "turn_delay_seconds": args.turn_delay_seconds,
            "method_delay_seconds": args.method_delay_seconds,
            "memory_window_limit": args.memory_window_limit,
            "keep_last_n": args.keep_last_n,
            "session_add_background": args.session_add_background,  # ADDED
        },
    )
    write_json(run_dir / "messages.json", messages)
    write_json(
        run_dir / "methods.json",
        [
            {
                "name": m.name,
                "description": m.description,
                "config_overrides": m.config_overrides,
                "llm_task_overrides": m.llm_task_overrides,
            }
            for m in methods
        ],
    )

    method_reports: List[Dict[str, Any]] = []

    for method in methods:
        print(f"\n[RUN] {method.name}")
        method_dir = run_dir / method.name
        method_config = build_method_config(
            base_config=base_config,
            method=method,
            use_reference_task_models=args.use_reference_task_models,
        )

        report = await evaluate_method(
            method=method,
            config=method_config,
            messages=messages,
            user_prefix=args.user_prefix,
            method_output_dir=method_dir,
            continue_on_error=args.continue_on_error,
            flush_at_end=args.flush_at_end,
            turn_delay_seconds=args.turn_delay_seconds,
            memory_window_limit=args.memory_window_limit,
            keep_last_n=args.keep_last_n,
            session_add_background=args.session_add_background,
        )
        method_reports.append(report)

        tokens = report["token_usage"]["total_tokens"]
        turn_avg = report["timing_ms"]["turn_total"].get("avg")
        turn_avg_str = (
            f"{turn_avg:.2f}" if isinstance(turn_avg, (int, float)) else "n/a"
        )
        print(
            f"[DONE] {method.name} | total_tokens={tokens} | turn_avg_ms={turn_avg_str}"
        )
        await maybe_sleep(args.method_delay_seconds)

    if args.full_history_baseline:
        print("\n[RUN] full_history_baseline")
        baseline_config = build_method_config(
            base_config=base_config,
            method=MethodSpec(name="full_history_baseline"),
            use_reference_task_models=args.use_reference_task_models,
        )
        baseline_dir = run_dir / "full_history_baseline"
        baseline_report = await evaluate_full_history_baseline(
            config=baseline_config,
            messages=messages,
            baseline_system_prompt=args.baseline_system_prompt,
            method_output_dir=baseline_dir,
            continue_on_error=args.continue_on_error,
            turn_delay_seconds=args.turn_delay_seconds,
            user_prefix=args.user_prefix,  # ADDED
        )
        method_reports.append(baseline_report)

        baseline_tokens = baseline_report["token_usage"]["total_tokens"]
        baseline_turn_avg = baseline_report["timing_ms"]["turn_total"].get("avg")
        baseline_turn_avg_str = (
            f"{baseline_turn_avg:.2f}"
            if isinstance(baseline_turn_avg, (int, float))
            else "n/a"
        )
        print(
            "[DONE] full_history_baseline "
            f"| total_tokens={baseline_tokens} "
            f"| turn_avg_ms={baseline_turn_avg_str}"
        )
        await maybe_sleep(args.method_delay_seconds)

    comparison_rows = build_comparison_rows(method_reports)
    add_full_history_deltas(comparison_rows)

    write_json(run_dir / "comparison_summary.json", method_reports)
    write_json(run_dir / "comparison_rows.json", comparison_rows)
    write_comparison_csv(run_dir / "comparison.csv", comparison_rows)
    write_comparison_markdown(run_dir / "comparison.md", comparison_rows)

    write_json(
        run_dir / "run_metadata.json",
        {
            "started_at": run_started_at,
            "completed_at": utc_now_iso(),
            "dataset": str(dataset_path),
            "methods": str(methods_path),
            "message_count": len(messages),
            "flush_at_end": args.flush_at_end,
            "continue_on_error": args.continue_on_error,
            "use_reference_task_models": args.use_reference_task_models,
            "full_history_baseline": args.full_history_baseline,
            "baseline_system_prompt": args.baseline_system_prompt,
            "turn_delay_seconds": args.turn_delay_seconds,
            "method_delay_seconds": args.method_delay_seconds,
            "memory_window_limit": args.memory_window_limit,
            "keep_last_n": args.keep_last_n,
            "session_add_background": args.session_add_background,  # ADDED
            "method_count": len(methods),
            "evaluated_variant_count": len(method_reports),
        },
    )

    print("\n" + "=" * 80)
    print("Evaluation Complete")
    print("=" * 80)
    print(f"Artifacts written to: {run_dir}")
    print(f"- {run_dir / 'comparison.csv'}")
    print(f"- {run_dir / 'comparison.md'}")
    print(f"- {run_dir / 'comparison_summary.json'}")
    print("=" * 80)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
