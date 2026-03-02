"""
Transparency & observability layer — full implementation (Phase 9).

Four components:
- OperationLog       — thread-safe log of every database write
- RetrievalLog       — thread-safe log of every memory retrieval
- ProcessingHistory  — thread-safe log of every pipeline run
- EventBus           — synchronous publish/subscribe for pipeline events

All four are always-on (no opt-in flag). The overhead is negligible for
in-memory append-only lists bounded by a configurable max_entries cap.
"""

import threading
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from memblocks.models.transparency import (
    DBType,
    OperationEntry,
    OperationType,
    PipelineRunEntry,
    RetrievalEntry,
)


# --------------------------------------------------------------------------- #
# OperationLog
# --------------------------------------------------------------------------- #


class OperationLog:
    """Thread-safe log of all database write operations.

    Replaces scattered ``print()`` statements in storage adapters
    (e.g., ``"✓ Added new memory"`` at sections.py:218,
    ``"✓ Deleted vector"`` at vector_db_manager.py:164).
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: List[OperationEntry] = []
        self._max = max_entries
        self._lock = threading.Lock()

    def record(self, entry: OperationEntry) -> None:
        """Append an operation entry, evicting the oldest if at capacity."""
        with self._lock:
            if len(self._entries) >= self._max:
                self._entries.pop(0)
            self._entries.append(entry)

    def get_entries(
        self,
        limit: int = 100,
        db_type: Optional[DBType] = None,
    ) -> List[OperationEntry]:
        """Return the most recent *limit* entries, optionally filtered by DB type."""
        with self._lock:
            entries = list(self._entries)
        if db_type is not None:
            entries = [e for e in entries if e.db_type == db_type]
        return entries[-limit:]

    def get_entries_since(self, since: datetime) -> List[OperationEntry]:
        """Return all entries recorded at or after *since*."""
        with self._lock:
            return [e for e in self._entries if e.timestamp >= since]

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._entries.clear()

    def summary(self) -> Dict[str, int]:
        """Return per-operation-type counts, e.g. ``{'insert': 5, 'update': 3}``."""
        with self._lock:
            counts: Dict[str, int] = defaultdict(int)
            for e in self._entries:
                counts[e.operation_type.value] += 1
        return dict(counts)


# --------------------------------------------------------------------------- #
# RetrievalLog
# --------------------------------------------------------------------------- #


class RetrievalLog:
    """Thread-safe log of all memory retrieval events."""

    def __init__(self, max_entries: int = 1000) -> None:
        self._entries: List[RetrievalEntry] = []
        self._max = max_entries
        self._lock = threading.Lock()

    def record(self, entry: RetrievalEntry) -> None:
        """Append a retrieval entry, evicting the oldest if at capacity."""
        with self._lock:
            if len(self._entries) >= self._max:
                self._entries.pop(0)
            self._entries.append(entry)

    def get_entries(
        self,
        limit: int = 100,
        source: Optional[str] = None,
    ) -> List[RetrievalEntry]:
        """Return the most recent *limit* entries, optionally filtered by source."""
        with self._lock:
            entries = list(self._entries)
        if source is not None:
            entries = [e for e in entries if e.source == source]
        return entries[-limit:]

    def get_last_retrieval(self) -> Optional[RetrievalEntry]:
        """Return the most recent retrieval entry, or None if log is empty."""
        with self._lock:
            return self._entries[-1] if self._entries else None

    def clear(self) -> None:
        """Remove all entries."""
        with self._lock:
            self._entries.clear()


# --------------------------------------------------------------------------- #
# ProcessingHistory
# --------------------------------------------------------------------------- #


class ProcessingHistory:
    """Thread-safe log of all memory pipeline processing runs.

    Replaces ``ProcessingHistoryTracker`` (chat_service.py:123-143) —
    same concept but tracks the full pipeline lifecycle including per-step
    timing, extraction counts, and errors.
    """

    def __init__(self, max_entries: int = 500) -> None:
        self._runs: Dict[str, PipelineRunEntry] = {}
        self._order: List[str] = []  # insertion order for slicing
        self._max = max_entries
        self._lock = threading.Lock()

    def record_start(
        self,
        task_id: str,
        trigger_event: str,
        message_count: int,
    ) -> PipelineRunEntry:
        """
        Record that a pipeline run has started.

        Args:
            task_id: Unique task identifier from MemoryPipeline.trigger().
            trigger_event: Human-readable reason, e.g. "message_window_full".
            message_count: Number of messages being processed.

        Returns:
            The newly created PipelineRunEntry.
        """
        entry = PipelineRunEntry(
            task_id=task_id,
            trigger_event=trigger_event,
            input_message_count=message_count,
            status="running",
        )
        with self._lock:
            if len(self._order) >= self._max:
                oldest = self._order.pop(0)
                self._runs.pop(oldest, None)
            self._runs[task_id] = entry
            self._order.append(task_id)
        return entry

    def record_complete(
        self,
        task_id: str,
        result: Dict[str, Any],
    ) -> PipelineRunEntry:
        """
        Update an existing run entry as completed.

        Args:
            task_id: Identifier matching a prior record_start() call.
            result: Dict with optional keys:
                - extracted_semantic_count (int)
                - conflicts_resolved_count (int)
                - core_memory_updated (bool)
                - summary_generated (bool)

        Returns:
            The updated PipelineRunEntry.
        """
        with self._lock:
            entry = self._runs.get(task_id)
        if entry is None:
            return PipelineRunEntry(task_id=task_id, status="unknown")
        entry.status = "success"
        entry.timestamp_completed = datetime.utcnow()
        entry.extracted_semantic_count = result.get("extracted_semantic_count", 0)
        entry.conflicts_resolved_count = result.get("conflicts_resolved_count", 0)
        entry.core_memory_updated = result.get("core_memory_updated", False)
        entry.summary_generated = result.get("summary_generated", False)
        return entry

    def record_failure(self, task_id: str, error: str) -> PipelineRunEntry:
        """
        Update an existing run entry as failed.

        Args:
            task_id: Identifier matching a prior record_start() call.
            error: Error description string.

        Returns:
            The updated PipelineRunEntry.
        """
        with self._lock:
            entry = self._runs.get(task_id)
        if entry is None:
            return PipelineRunEntry(task_id=task_id, status="unknown")
        entry.status = "failure"
        entry.timestamp_completed = datetime.utcnow()
        entry.error_details = error
        return entry

    def get_runs(
        self,
        limit: int = 50,
        status: Optional[str] = None,
    ) -> List[PipelineRunEntry]:
        """Return the most recent *limit* runs, optionally filtered by status."""
        with self._lock:
            runs = [self._runs[tid] for tid in self._order if tid in self._runs]
        if status is not None:
            runs = [r for r in runs if r.status == status]
        return runs[-limit:]

    def get_run(self, task_id: str) -> Optional[PipelineRunEntry]:
        """Return the run entry for *task_id*, or None."""
        with self._lock:
            return self._runs.get(task_id)

    def get_last_run(self) -> Optional[PipelineRunEntry]:
        """Return the most recently started run, or None."""
        with self._lock:
            if not self._order:
                return None
            return self._runs.get(self._order[-1])

    def clear(self) -> None:
        """Remove all run records."""
        with self._lock:
            self._runs.clear()
            self._order.clear()


# --------------------------------------------------------------------------- #
# EventBus
# --------------------------------------------------------------------------- #


class EventBus:
    """Simple synchronous publish/subscribe event bus.

    Allows external code to react to internal library events in real-time
    without coupling to the services directly.

    Example usage::

        def my_handler(payload):
            print("Memory stored:", payload)

        client.event_bus.subscribe("on_memory_stored", my_handler)
        # … chat interactions happen …
        client.event_bus.unsubscribe("on_memory_stored", my_handler)
    """

    VALID_EVENTS = [
        "on_memory_extracted",  # After PS1 semantic extraction
        "on_conflict_resolved",  # After PS2 conflict resolution
        "on_memory_stored",  # After memories written to Qdrant
        "on_core_memory_updated",  # After core memory updated in Mongo
        "on_summary_generated",  # After conversation summary created
        "on_pipeline_started",  # When memory pipeline begins
        "on_pipeline_completed",  # When memory pipeline finishes successfully
        "on_pipeline_failed",  # When memory pipeline errors
        "on_memory_retrieved",  # When memories are retrieved for context
        "on_db_write",  # On any database write operation
        "on_message_processed",  # After a chat message is fully processed
    ]

    def __init__(self) -> None:
        # event_name → list of callbacks
        self._subscribers: Dict[str, List[Callable[[Any], None]]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, event_name: str, callback: Callable[[Any], None]) -> None:
        """
        Register *callback* to be called when *event_name* is published.

        Args:
            event_name: One of the VALID_EVENTS strings.
            callback: A callable accepting a single payload argument.

        Raises:
            ValueError: If *event_name* is not in VALID_EVENTS.
        """
        if event_name not in self.VALID_EVENTS:
            raise ValueError(
                f"Unknown event '{event_name}'. Valid events: {self.VALID_EVENTS}"
            )
        with self._lock:
            if callback not in self._subscribers[event_name]:
                self._subscribers[event_name].append(callback)

    def unsubscribe(self, event_name: str, callback: Callable[[Any], None]) -> None:
        """
        Remove *callback* from *event_name* subscriptions. Silent no-op if not found.

        Args:
            event_name: Event name to unsubscribe from.
            callback: The same callable passed to subscribe().
        """
        with self._lock:
            subscribers = self._subscribers.get(event_name, [])
            if callback in subscribers:
                subscribers.remove(callback)

    def publish(self, event_name: str, payload: Any) -> None:
        """
        Call all callbacks subscribed to *event_name* with *payload*.

        Exceptions raised by individual callbacks are caught and printed
        so that a bad callback cannot crash the pipeline.

        Args:
            event_name: Event to publish.
            payload: Arbitrary data passed to each callback.
        """
        with self._lock:
            callbacks = list(self._subscribers.get(event_name, []))
        for cb in callbacks:
            try:
                cb(payload)
            except Exception as exc:
                print(f"[WARN] EventBus callback error for '{event_name}': {exc}")


__all__ = [
    "OperationLog",
    "RetrievalLog",
    "ProcessingHistory",
    "EventBus",
]
