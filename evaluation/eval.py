"""Main evaluation entrypoint script."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path so we can import evaluation modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.core.config import load_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_output_dir(run_name: str) -> Path:
    """Create a timestamped output directory for a run.

    Args:
        run_name: Name of the run.

    Returns:
        Path to the created output directory.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_name = f"{timestamp}_{run_name}"
    output_dir = Path("evaluation/runs") / dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def run_evaluation(config_path: Path) -> None:
    """Run evaluation based on configuration file.

    Args:
        config_path: Path to the YAML configuration file.
    """
    logger.info(f"Loading configuration from: {config_path}")
    config = load_config(config_path)

    if not config.runs:
        logger.warning("No runs defined in configuration")
        return

    logger.info(f"Found {len(config.runs)} run(s) to execute")

    for run in config.runs:
        logger.info(f"Starting run: {run.name}")
        output_dir = create_output_dir(run.name)
        logger.info(f"Output directory: {output_dir}")

        try:
            # Get the dataset config
            dataset_name = run.dataset.name
            
            # Instantiate dataset and runner
            if dataset_name == "locomo":
                from evaluation.datasets.locomo import LocomoDataset
                from evaluation.runners.locomo import LocomoRunner
                
                dataset = LocomoDataset(run.dataset)
                runner = LocomoRunner(run, dataset)
            else:
                logger.warning(f"Unknown dataset: {dataset_name}")
                continue

            results = runner.run(output_dir)
            logger.info(f"Run '{run.name}' completed with {results.get('sessions_processed', 0)} sessions")
        except Exception as e:
            logger.error(f"Error executing run '{run.name}': {e}")
            # Continue to next run - do not halt the entire suite
            logger.info(f"Proceeding to next run...")

    logger.info("All runs completed")


def main() -> int:
    """Main entry point for the evaluation script."""
    parser = argparse.ArgumentParser(
        description="Run evaluation pipelines using YAML configuration."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to the YAML configuration file",
    )

    args = parser.parse_args()

    if not args.config.exists():
        logger.error(f"Configuration file not found: {args.config}")
        return 1

    try:
        run_evaluation(args.config)
        return 0
    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())