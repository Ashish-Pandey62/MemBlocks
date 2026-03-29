"""Re-run only the full_history_baseline for an existing evaluation run."""

import asyncio
import sys
from pathlib import Path

# Add parent to path to import evaluation script
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.run_memblocks_evaluation import (
    build_method_config,
    evaluate_full_history_baseline,
    load_messages,
    MethodSpec,
    parse_args,
    write_json,
    build_comparison_rows,
    add_full_history_deltas,
    write_comparison_csv,
    write_comparison_markdown,
)
from memblocks import MemBlocksConfig


async def main():
    # Parse args to reuse existing configuration
    args = parse_args()

    # Load existing run directory
    run_dir = Path(args.out_dir) / "run_20260329_020528"
    if not run_dir.exists():
        print(f"Error: Run directory not found: {run_dir}")
        return

    print(f"Re-running baseline for: {run_dir}")

    # Load messages
    dataset_path = Path(args.dataset)
    messages = load_messages(dataset_path, enforce_30=args.enforce_30)
    print(f"Loaded {len(messages)} messages from {dataset_path}")

    # Build base config
    base_config = MemBlocksConfig(
        memory_window_limit=args.memory_window_limit,
        keep_last_n=args.keep_last_n,
    )

    # Build baseline config
    baseline_config = build_method_config(
        base_config=base_config,
        method=MethodSpec(name="full_history_baseline"),
        use_reference_task_models=args.use_reference_task_models,
    )

    # Run baseline evaluation
    print("\n[RUN] full_history_baseline")
    baseline_dir = run_dir / "full_history_baseline"
    baseline_report = await evaluate_full_history_baseline(
        config=baseline_config,
        messages=messages,
        baseline_system_prompt=args.baseline_system_prompt,
        method_output_dir=baseline_dir,
        continue_on_error=args.continue_on_error,
        turn_delay_seconds=args.turn_delay_seconds,
        user_prefix=args.user_prefix,
    )

    baseline_tokens = baseline_report["token_usage"]["total_tokens"]
    baseline_turn_avg = baseline_report["timing_ms"]["turn_total"].get("avg")
    baseline_turn_avg_str = (
        f"{baseline_turn_avg:.2f}"
        if isinstance(baseline_turn_avg, (int, float))
        else "n/a"
    )
    print(
        f"[DONE] full_history_baseline "
        f"| total_tokens={baseline_tokens} "
        f"| turn_avg_ms={baseline_turn_avg_str}"
    )

    # Load existing memblocks method reports
    comparison_summary_path = run_dir / "comparison_summary.json"
    if comparison_summary_path.exists():
        import json

        with open(comparison_summary_path) as f:
            existing_reports = json.load(f)

        # Filter out old baseline and add new one
        method_reports = [
            r
            for r in existing_reports
            if r.get("method", {}).get("name") != "full_history_baseline"
        ]
        method_reports.append(baseline_report)

        # Regenerate comparison files
        comparison_rows = build_comparison_rows(method_reports)
        add_full_history_deltas(comparison_rows)

        write_json(run_dir / "comparison_summary.json", method_reports)
        write_json(run_dir / "comparison_rows.json", comparison_rows)
        write_comparison_csv(run_dir / "comparison.csv", comparison_rows)
        write_comparison_markdown(run_dir / "comparison.md", comparison_rows)

        print(f"\n[SUCCESS] Updated comparison files in {run_dir}")
    else:
        print(
            f"\n[WARNING] No existing comparison_summary.json found, only baseline report written"
        )


if __name__ == "__main__":
    asyncio.run(main())
