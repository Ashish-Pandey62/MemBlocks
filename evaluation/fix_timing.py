"""Fix timing anomalies and recalculate metrics without re-running LLM calls."""

import json
import statistics
from pathlib import Path
from typing import Any, Dict, List


def calculate_stats(values: List[float]) -> Dict[str, Any]:
    """Calculate high/low/avg/p95 for a list of values."""
    if not values:
        return {"high": None, "low": None, "avg": None, "p95": None}

    return {
        "high": max(values),
        "low": min(values),
        "avg": statistics.mean(values),
        "p95": (
            statistics.quantiles(values, n=20)[18] if len(values) >= 2 else max(values)
        ),
    }


def recalculate_timing_metrics(turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Recalculate timing metrics from turn data."""
    timing_keys = [
        "turn_total",
        "user_facing",
        "retrieve",
        "conversation",
        "memory_window",
        "summary",
        "session_add",
    ]

    metrics: Dict[str, Any] = {}
    for key in timing_keys:
        values = [
            t["timing_ms"][key] for t in turns if t["timing_ms"].get(key) is not None
        ]
        metrics[key] = calculate_stats(values)

    return metrics


def fix_timing_report(
    report_path: Path,
    max_reasonable_ms: float = 120000.0,
    replacement_ms: float = 20000.0,
):
    """Fix timing anomalies in a method report and recalculate metrics.

    Args:
        report_path: Path to method_report.json
        max_reasonable_ms: Any timing above this is considered an anomaly (default 120s)
        replacement_ms: Replace anomalies with this value (default 20s)
    """
    print(f"Loading report: {report_path}")

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    turns = report.get("turns", [])
    if not turns:
        print("No turns found in report")
        return

    # Find and fix anomalies
    fixed_count = 0
    for turn in turns:
        timing = turn.get("timing_ms", {})

        for key, value in timing.items():
            if value is not None and value > max_reasonable_ms:
                print(
                    f"Turn {turn['turn_index']}: {key} = {value:.0f}ms -> {replacement_ms:.0f}ms"
                )
                timing[key] = replacement_ms
                fixed_count += 1

    if fixed_count == 0:
        print("No timing anomalies found")
        return

    print(f"\nFixed {fixed_count} timing anomalies")

    # Recalculate aggregated timing metrics
    print("Recalculating aggregated metrics...")
    report["timing_ms"] = recalculate_timing_metrics(turns)

    # Write back
    backup_path = report_path.with_suffix(".json.backup")
    print(f"Backing up original to: {backup_path}")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Writing corrected report to: {report_path}")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\nDone! Timing metrics recalculated.")
    print("\nNew timing stats:")
    for key, stats in report["timing_ms"].items():
        if stats["avg"] is not None:
            print(
                f"  {key}: avg={stats['avg']:.0f}ms, p95={stats['p95']:.0f}ms, high={stats['high']:.0f}ms"
            )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(
            "Usage: python fix_timing.py <path_to_method_report.json> [max_reasonable_ms] [replacement_ms]"
        )
        print("\nExample:")
        print(
            "  python fix_timing.py evaluation/runs/run_20260329_020528/memblocks_full/method_report.json"
        )
        print(
            "  python fix_timing.py evaluation/runs/run_20260329_020528/memblocks_full/method_report.json 120000 20000"
        )
        sys.exit(1)

    report_path = Path(sys.argv[1])
    max_reasonable = float(sys.argv[2]) if len(sys.argv) > 2 else 120000.0
    replacement = float(sys.argv[3]) if len(sys.argv) > 3 else 20000.0

    if not report_path.exists():
        print(f"Error: Report not found: {report_path}")
        sys.exit(1)

    fix_timing_report(report_path, max_reasonable, replacement)
