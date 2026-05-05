"""Interactive CLI for memBlocks with Enhanced Retrieval Visibility."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from memblocks import MemBlocksClient, MemBlocksConfig
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings

LOG_DIR = Path("memblocks_cli_output")
LOG_DIR.mkdir(exist_ok=True)


class FlushingFileHandler(logging.FileHandler):
    """FileHandler that flushes to disk after every emitted record."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def setup_logging() -> None:
    """Configure logging for the CLI and memblocks library."""
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            FlushingFileHandler(LOG_DIR / "cli.log"),
        ],
    )
    logging.getLogger("memblocks").setLevel(logging.DEBUG)
    logging.getLogger("memblocks").addHandler(
        FlushingFileHandler(LOG_DIR / "memblocks.log")
    )
    # Suppress noisy third-party loggers from the CLI
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("groq").setLevel(logging.WARNING)
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("openinference").setLevel(logging.WARNING)


async def save_transparency_data(client: MemBlocksClient) -> None:
    """Save transparency data to JSON files."""
    logger = logging.getLogger(__name__)

    retrieval_log = client.get_retrieval_log()
    if retrieval_log:
        retrievals = retrieval_log.get_entries(limit=1000)
        retrieval_data = [r.model_dump(mode="json") for r in retrievals]
        retrieval_file = LOG_DIR / "retrieval_log.json"
        with open(retrieval_file, "w") as f:
            json.dump(retrieval_data, f, indent=2, default=str)

    processing_history = client.get_processing_history()
    if processing_history:
        runs = processing_history.get_runs(limit=100)
        runs_data = [run.model_dump(mode="json") for run in runs]
        history_file = LOG_DIR / "processing_history.json"
        with open(history_file, "w") as f:
            json.dump(runs_data, f, indent=2, default=str)

    usage_tracker = client.get_llm_usage()
    summary = usage_tracker.get_summary()
    totals = usage_tracker.get_totals()
    if totals.request_count > 0:
        usage_data = {
            "summary": {k: v.model_dump(mode="json") for k, v in summary.items()},
            "totals": totals.model_dump(mode="json"),
        }
        usage_file = LOG_DIR / "llm_usage.json"
        with open(usage_file, "w") as f:
            json.dump(usage_data, f, indent=2, default=str)


def display_token_usage(client: MemBlocksClient, since: Optional[datetime] = None) -> None:
    """Log a summary of token usage and optional recent individual records to a file."""
    usage_tracker = client.get_llm_usage()
    log_file = LOG_DIR / "token_usage.log"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write("\n" + "=" * 70 + "\n")
        f.write(f"ENTRY AT {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
        f.write("=" * 70 + "\n")

        # 1. Individual recent records if requested
        if since:
            recent_records = usage_tracker.get_records(limit=20)
            recent_records = [r for r in recent_records if r.timestamp >= since]

            if recent_records:
                f.write("\n🚀 RECENT LLM CALLS\n")
                f.write("─" * 70 + "\n")
                f.write(f"{'Time':<8} | {'Type':<15} | {'Model':<20} | {'Tokens':>6} | {'Lat':>6}\n")
                f.write("-" * 70 + "\n")
                for r in recent_records:
                    time_str = r.timestamp.strftime("%H:%M:%S")
                    call_type_str = r.call_type.value if hasattr(r.call_type, "value") else str(r.call_type)
                    f.write(f"{time_str:<8} | {call_type_str:<15} | {r.model[:20]:<20} | {r.total_tokens:>6} | {r.latency_ms:>5.0f}ms\n")
                f.write("─" * 70 + "\n")

        # 2. Cumulative summary
        summary = usage_tracker.get_summary()
        totals = usage_tracker.get_totals()

        if summary or totals.request_count > 0:
            f.write("\n💰 CUMULATIVE LLM USAGE\n")
            f.write("─" * 70 + "\n")
            f.write(
                f"{'Call Type':<20} | {'Reqs':>4} | {'In':>8} | {'Out':>8} | {'Total':>8} | {'Avg Lat':>8}\n"
            )
            f.write("-" * 70 + "\n")

            for call_type, stats in summary.items():
                f.write(
                    f"{call_type:<20} | {stats.request_count:>4} | "
                    f"{stats.total_input_tokens:>8} | {stats.total_output_tokens:>8} | "
                    f"{stats.total_tokens:>8} | {stats.avg_latency_ms:>7.0f}ms\n"
                )

            f.write("-" * 70 + "\n")
            f.write(
                f"{'GRAND TOTAL':<20} | {totals.request_count:>4} | "
                f"{totals.total_input_tokens:>8} | {totals.total_output_tokens:>8} | "
                f"{totals.total_tokens:>8} | {totals.avg_latency_ms:>7.0f}ms\n"
            )
            f.write("─" * 70 + "\n")
        
        f.write("\n")

    # Brief hint in terminal
    print(f"📊 Token usage logged to: {log_file.name}")


def display_retrieval_summary(client: MemBlocksClient) -> None:
    """Display a summary of the last retrieval with enhanced info."""
    retrieval_log = client.get_retrieval_log()
    if not retrieval_log:
        return

    last = retrieval_log.get_last_retrieval()
    if not last:
        return

    print("\n" + "─" * 70)
    print("🔍 RETRIEVAL SUMMARY")
    print("─" * 70)

    # Query expansion
    expanded = getattr(last, "expanded_queries", [])
    if expanded:
        print(f"\n📢 Query Expansion ({len(expanded)} queries):")
        for i, q in enumerate(expanded[:4], 1):  # Show first 4
            print(f"  {i}. {q[:80]}{'...' if len(q) > 80 else ''}")

    # Hypothetical paragraphs
    hypo = getattr(last, "hypothetical_paragraphs", [])
    if hypo:
        print(f"\n💭 Hypothetical Paragraphs ({len(hypo)} generated):")
        for i, p in enumerate(hypo[:2], 1):  # Show first 2
            print(f"  {i}. {p[:100]}{'...' if len(p) > 100 else ''}")

    # Results
    num_results = getattr(last, "num_results", 0)
    reranked = getattr(last, "reranked", False)
    method = getattr(last, "retrieval_method", "N/A")

    print(f"\n📊 Results: {num_results} memories")
    print(f"♻️  Re-ranked: {' Yes' if reranked else ' No'}")
    print(f"🎯 Method: {method}")

    # Show a few memories
    summaries = getattr(last, "memory_summaries", [])
    if summaries:
        print(f"\n🧠 Top Memories Retrieved:")
        for i, summary in enumerate(summaries[:3], 1):
            print(f"  {i}. {summary[:90]}{'...' if len(summary) > 90 else ''}")

    print("─" * 70)
    print(f"💾 Full logs saved to: {LOG_DIR}/retrieval_log.json")
    print("─" * 70 + "\n")


async def ainput(prompt: str = "") -> str:
    """Non-blocking input using asyncio.to_thread (requires Python 3.9+)."""
    return await asyncio.to_thread(input, prompt)


async def _run_cli() -> None:
    """Main async CLI loop."""
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting memBlocks CLI with Enhanced Retrieval")

    # Load config - try current dir first, then parent
    try:
        config = MemBlocksConfig(llm_settings=LLMSettings(
                default=LLMTaskSettings(
                    provider="groq",
                    model="moonshotai/kimi-k2-instruct-0905"
                ),
                retrieval=LLMTaskSettings(
                    provider="groq",
                    model="openai/gpt-oss-20b"
                ),
                ps1_semantic_extraction=LLMTaskSettings(
                    provider="groq",
                    model="openai/gpt-oss-120b"
                ),
                ps2_conflict_resolution=LLMTaskSettings(
                    provider="groq",
                    model="moonshotai/kimi-k2-instruct-0905"
                ),
                core_memory_extraction=LLMTaskSettings(
                    provider="groq",
                    model="openai/gpt-oss-120b"
                ),
                recursive_summary=LLMTaskSettings(
                    provider="groq",
                    model="openai/gpt-oss-120b"
                ),
            )
                                 
        )
    except Exception as e:
        print(f"Error loading config: {e}")
        print("\n Make sure your .env file is in the project root")
        print("   Or run from the project root directory")
        return

    # Display retrieval configuration
    print("\n" + "=" * 70)
    print("  memBlocks CLI - Enhanced Semantic Retrieval")
    print("=" * 70)
    print("\n🔧 Retrieval Configuration:")
    print(
        f"  Query Expansion: {' Enabled' if config.retrieval_enable_query_expansion else ' Disabled'}"
    )
    print(f"     - Expansions per query: {config.retrieval_num_query_expansions}")
    print(
        f"  Hypothetical Paragraphs: {' Enabled' if config.retrieval_enable_hypothetical_paragraphs else ' Disabled'}"
    )
    print(
        f"     - Paragraphs per query: {config.retrieval_num_hypothetical_paragraphs}"
    )
    print(
        f"   Re-ranking: {' Enabled' if config.retrieval_enable_reranking else ' Disabled'}"
    )
    print(f"  Final top-k: {config.retrieval_final_top_k}")
    print("=" * 70)

    client = MemBlocksClient(config)

    # Track if we've already displayed the retrieval summary for this query
    _last_retrieval_timestamp = None

    def on_event(event_name: str, payload: dict) -> None:
        nonlocal _last_retrieval_timestamp
        logger.info(f"Event: {event_name} - {json.dumps(payload, default=str)}")
        # Save and display retrieval info
        if event_name == "on_memory_retrieved":
            asyncio.create_task(save_transparency_data(client))
            # Display summary only once per retrieval by checking timestamp
            retrieval_log = client.get_retrieval_log()
            if retrieval_log:
                last = retrieval_log.get_last_retrieval()
                if (
                    last
                    and getattr(last, "timestamp", None) != _last_retrieval_timestamp
                ):
                    _last_retrieval_timestamp = getattr(last, "timestamp", None)
                    # Display immediately since save is async
                    display_retrieval_summary(client)

        if event_name == "on_pipeline_completed":
            asyncio.create_task(save_transparency_data(client))
            print("\n Memory pipeline completed.")
            
            # Show tokens for this specific run
            history = client.get_processing_history()
            last_run = history.get_last_run()
            pipe_since = last_run.timestamp_started if last_run else None
            display_token_usage(client, since=pipe_since)

    events = [
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
    for event in events:
        client.subscribe(event, lambda p, e=event: on_event(e, p))

    # ---- user setup ----
    user_id = (
        await ainput("\nEnter user ID (or press Enter for 'default_user'): ")
    ).strip()
    if not user_id:
        user_id = "default_user"

    user = await client.get_or_create_user(user_id)
    print(f" User: {user.get('user_id')}")

    # ---- block selection ----
    blocks = await client.get_user_blocks(user_id)

    block = None
    if blocks:
        print(f"\n📦 Found {len(blocks)} existing block(s):")
        for i, b in enumerate(blocks, 1):
            print(f"  {i}. {b.name} ({b.id})")

        choice = (
            await ainput("\nSelect block number, or press Enter to create new: ")
        ).strip()
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(blocks):
                block = blocks[idx]

    if not block:
        name = (
            await ainput("New block name (Enter for 'My Memory'): ")
        ).strip() or "My Memory"
        desc = (await ainput("Block description (Enter to skip): ")).strip()
        print("Creating block...")
        block = await client.create_block(user_id=user_id, name=name, description=desc)

    print(f"\n Using block: {block.name} ({block.id})")

    # ---- session setup ----
    session = await client.create_session(user_id=user_id, block_id=block.id)
    print(f" Session: {session.id}")

    # ---- chat loop ----
    async def _persist_turn(session, user_msg, ai_response) -> None:
        try:
            await session.add(user_msg=user_msg, ai_response=ai_response)
        except Exception as e:
            print(f"⚠️  Warning: failed to persist turn: {e}")

    print("\n" + "=" * 70)
    print(" Chat with your assistant")
    print("   Type 'quit' to exit")
    print("   Type 'logs' to view latest retrieval details")
    print("   Type 'tokens' to view cumulative LLM usage")
    print("=" * 70 + "\n")

    try:
        while True:
            try:
                user_input = (await ainput("You: ")).strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break

            # Special command to show retrieval logs
            if user_input.lower() == "logs":
                display_retrieval_summary(client)
                display_token_usage(client)
                continue

            if user_input.lower() == "tokens":
                display_token_usage(client)
                continue

            try:
                print(" Retrieving memories...")
                start_time = asyncio.get_event_loop().time()
                interaction_dt = datetime.utcnow()

                # Retrieve memory context
                context = await block.retrieve(user_input)
                memory_window = await session.get_memory_window()
                summary = await session.get_recursive_summary()

                # Build system prompt
                system_parts = [
                    "You are a helpful assistant with memory of past conversations."
                ]
                if summary:
                    system_parts.append(
                        f"<Conversation Summary>\n{summary}\n</Conversation Summary>"
                    )
                memory_str = context.to_prompt_string()
                if memory_str:
                    system_parts.append(memory_str)
                system_prompt = "\n\n".join(system_parts)

                # Call LLM
                messages_for_llm = (
                    [{"role": "system", "content": system_prompt}]
                    + memory_window
                    + [{"role": "user", "content": user_input}]
                )
                ai_response = await client.conversation_llm.chat(
                    messages=messages_for_llm
                )
                end_time = asyncio.get_event_loop().time()
                logger.info(f"LLM response time: {end_time - start_time:.2f} seconds")

                print(f"\n Assistant: {ai_response}\n")

                # Show tokens for this interaction
                display_token_usage(client, since=interaction_dt)

                # Persist turn in background
                asyncio.create_task(_persist_turn(session, user_input, ai_response))

            except Exception as e:
                print(f" Error: {e}\n")
                logger.exception("Chat loop error")

    except KeyboardInterrupt:
        pass

    finally:
        print("\n Flushing final transparency data...")
        await save_transparency_data(client)
        display_token_usage(client)
        print("🔌 Closing connections...")
        await client.close()
        print("\n Goodbye!\n")
        print(f" View detailed logs at: {LOG_DIR.absolute()}")
        print(f"   - retrieval_log.json - All retrieval details")
        print(f"   - memblocks.log - Debug logs")
        print(f"\n Run 'python verify_retrieval.py' to analyze retrievals\n")


def main() -> None:
    """Entry point for the `memblocks` CLI command."""
    asyncio.run(_run_cli())


if __name__ == "__main__":
    main()
