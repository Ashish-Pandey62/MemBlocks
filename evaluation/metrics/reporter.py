"""Reporter module for exporting evaluation results."""
import csv
import json
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List

from evaluation.core.config import EvalConfig


class Reporter:
    """Exports evaluation results to various formats."""

    def save_json(
        self,
        results: Dict[str, Any],
        output_dir: Path,
        filename: str = "report.json"
    ) -> Path:
        """Save full results dictionary to JSON file.
        
        Args:
            results: The evaluation results dictionary.
            output_dir: Directory to save to.
            filename: Output filename (default: report.json).
            
        Returns:
            Path to the saved file.
        """
        output_path = output_dir / filename
        output_dir.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        
        return output_path

    def save_csv(
        self,
        results: Dict[str, Any],
        output_dir: Path,
        filename: str = "report.csv"
    ) -> Path:
        """Save flattened evaluation details to CSV file.
        
        Creates one row per question across all sessions.
        
        Args:
            results: The evaluation results dictionary.
            output_dir: Directory to save to.
            filename: Output filename (default: report.csv).
            
        Returns:
            Path to the saved file.
        """
        output_path = output_dir / filename
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Flatten details into rows
        rows: List[Dict[str, str]] = []
        
        for session in results.get("details", []):
            session_id = session.get("session_id", "")
            
            for eval_entry in session.get("evaluations", []):
                row = {
                    "session_id": session_id,
                    "question": eval_entry.get("question", ""),
                    "expected_answer": eval_entry.get("expected_answer", ""),
                    "actual_answer": eval_entry.get("actual_answer", ""),
                    "score": eval_entry.get("score_hybrid", ""),
                    "category": eval_entry.get("category", ""),
                }
                rows.append(row)
        
        # Write CSV using StringIO for cross-platform compatibility
        fieldnames = ["session_id", "question", "expected_answer", "actual_answer", "score", "category"]
        
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        
        # Write to file (use text mode on Windows)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(output.getvalue())
        
        return output_path

    def save_run_info(
        self,
        config: EvalConfig,
        output_dir: Path,
        filename: str = "run_info.json"
    ) -> Path:
        """Save evaluation config to JSON file.
        
        Args:
            config: The EvalConfig model to serialize.
            output_dir: Directory to save to.
            filename: Output filename (default: run_info.json).
            
        Returns:
            Path to the saved file.
        """
        output_path = output_dir / filename
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Serialize Pydantic model to JSON
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, indent=2, default=str)
        
        return output_path

    def print_summary(self, results: Dict[str, Any]) -> None:
        """Print formatted summary of metrics to console.
        
        Args:
            results: The evaluation results dictionary containing metrics.
        """
        metrics = results.get("metrics", {})
        
        # Header
        print("\n" + "=" * 60)
        print("EVALUATION SUMMARY")
        print("=" * 60)
        
        # Overall Stats
        overall_accuracy = metrics.get("overall_accuracy", 0.0)
        total_questions = metrics.get("total_questions", 0)
        total_passes = metrics.get("total_passes", 0)
        
        print("\n📊 Overall Statistics:")
        print(f"  Questions Evaluated: {total_questions}")
        print(f"  Passes: {total_passes}")
        print(f"  Fails: {total_questions - total_passes}")
        print(f"  Accuracy: {overall_accuracy * 100:.1f}%")
        
        # By Reasoning Type (Category)
        accuracy_by_category = metrics.get("accuracy_by_category", {})
        if accuracy_by_category:
            print("\n📈 By Reasoning Type:")
            print("-" * 40)
            for category, accuracy in sorted(accuracy_by_category.items()):
                pct = accuracy * 100
                bar_len = int(pct / 5)  # 20 chars = 100%
                bar = "█" * bar_len + "░" * (20 - bar_len)
                print(f"  {category:15s} [{bar}] {pct:5.1f}%")
        
        # Token Summary
        tokens_by_stage = metrics.get("tokens_by_stage", {})
        total_tokens = metrics.get("total_tokens", 0)
        if tokens_by_stage:
            print("\n💰 Token Usage by Stage:")
            print("-" * 40)
            for stage, tokens in sorted(tokens_by_stage.items()):
                pct = (tokens / total_tokens * 100) if total_tokens > 0 else 0
                print(f"  {stage:15s}: {tokens:6,d} ({pct:5.1f}%)")
            print(f"  {'-' * 15}--------")
            print(f"  {'TOTAL':15s}: {total_tokens:6,d}")
        
        print("\n" + "=" * 60 + "\n")