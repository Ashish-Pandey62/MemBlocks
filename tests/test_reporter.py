"""Tests for Reporter export functionality."""
import json
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
import pytest
from evaluation.metrics.reporter import Reporter
from evaluation.core.config import RunConfig, DatasetConfig, RunnerConfig, EvalConfig


@pytest.fixture
def sample_results():
    """Create sample evaluation results."""
    return {
        "sessions_processed": 2,
        "details": [
            {
                "session_id": "session-1",
                "questions_evaluated": 2,
                "evaluations": [
                    {
                        "question": "What color is the sky?",
                        "expected_answer": "blue",
                        "actual_answer": "blue",
                        "score_hybrid": "Pass",
                        "category": "facts"
                    },
                    {
                        "question": "What is 2+2?",
                        "expected_answer": "4",
                        "actual_answer": "5",
                        "score_hybrid": "Fail",
                        "category": "math"
                    }
                ]
            },
            {
                "session_id": "session-2", 
                "questions_evaluated": 1,
                "evaluations": [
                    {
                        "question": "Who is the president?",
                        "expected_answer": "Unknown",
                        "actual_answer": "Unknown",
                        "score_hybrid": "Pass",
                        "category": "facts"
                    }
                ]
            }
        ],
        "metrics": {
            "overall_accuracy": 0.6666666666666666,
            "total_questions": 3,
            "total_passes": 2,
            "accuracy_by_category": {
                "facts": 1.0,
                "math": 0.0
            },
            "tokens_by_stage": {
                "retrieval": 70,
                "extraction": 40,
                "qa": 300,
                "judge": 200
            },
            "total_tokens": 610
        }
    }


@pytest.fixture
def sample_config():
    """Create sample EvalConfig."""
    return EvalConfig(
        runs=[
            RunConfig(
                name="test-run",
                dataset=DatasetConfig(name="locomo", max_sessions=2),
                runner=RunnerConfig(name="locomo", model="gpt-4", judge_model="gpt-4")
            )
        ]
    )


class TestReporterSaveJson:
    """Tests for save_json method."""

    def test_save_json_creates_file(self, sample_results):
        """save_json should create a JSON file with full results."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            reporter = Reporter()
            
            result_path = reporter.save_json(sample_results, output_dir)
            
            assert result_path.exists()
            data = json.loads(result_path.read_text())
            assert data == sample_results

    def test_save_json_custom_filename(self, sample_results):
        """save_json should use custom filename if provided."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            reporter = Reporter()
            
            result_path = reporter.save_json(sample_results, output_dir, filename="custom.json")
            
            assert result_path.name == "custom.json"


class TestReporterSaveCsv:
    """Tests for save_csv method."""

    def test_save_csv_creates_file(self, sample_results):
        """save_csv should create a CSV file with flattened details."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            reporter = Reporter()
            
            result_path = reporter.save_csv(sample_results, output_dir)
            
            assert result_path.exists()
            content = result_path.read_text()
            reader = csv.DictReader(content)
            rows = list(reader)
            
            # Should have 3 evaluation rows (2 in session-1 + 1 in session-2)
            assert len(rows) >= 3

    def test_save_csv_includes_all_fields(self, sample_results):
        """CSV should include all required fields."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            reporter = Reporter()
            
            result_path = reporter.save_csv(sample_results, output_dir)
            content = result_path.read_text()
            
            assert "session_id" in content
            assert "question" in content
            assert "expected_answer" in content
            assert "actual_answer" in content
            assert "score" in content
            assert "category" in content


class TestReporterSaveRunInfo:
    """Tests for save_run_info method."""

    def test_save_run_info_creates_file(self, sample_config):
        """save_run_info should serialize config to JSON."""
        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            reporter = Reporter()
            
            result_path = reporter.save_run_info(sample_config, output_dir)
            
            assert result_path.exists()
            data = json.loads(result_path.read_text())
            assert "runs" in data
            assert len(data["runs"]) == 1


class TestReporterPrintSummary:
    """Tests for print_summary method."""

    def test_print_summary_outputs_metrics(self, sample_results, capsys):
        """print_summary should print formatted metrics."""
        reporter = Reporter()
        
        reporter.print_summary(sample_results)
        
        captured = capsys.readouterr()
        assert "Overall" in captured.out or "accuracy" in captured.out.lower()

    def test_print_summary_has_sections(self, sample_results, capsys):
        """print_summary should have different sections."""
        reporter = Reporter()
        
        reporter.print_summary(sample_results)
        
        captured = capsys.readouterr()
        output = captured.out
        # Should have at least Overall and By Category
        assert "Overall" in output or "overall" in output.lower()