"""Main evaluation entrypoint script."""

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path so we can import evaluation modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from evaluation.core.config import load_config

# ── Logging setup ─────────────────────────────────────────────────────────────
# Two log files written to evaluation/logs/<timestamp>/:
#   eval.log      — eval harness + runner pipeline steps (INFO+)
#   memblocks.log — memblocks library internals including every LLM call (DEBUG)
# Terminal shows eval harness INFO and memblocks DEBUG side-by-side.

LOG_ROOT = Path("evaluation/logs")


class _FlushingFileHandler(logging.FileHandler):
    """FileHandler that flushes after every record so logs are live-tailable."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


_SESSION_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
_LOG_DIR: Path | None = None  # set by _setup_logging()


def _setup_logging() -> Path:
    """Configure root + memblocks loggers and return the session log directory."""
    global _LOG_DIR
    log_dir = LOG_ROOT / _SESSION_TS
    log_dir.mkdir(parents=True, exist_ok=True)
    _LOG_DIR = log_dir

    SHORT_FMT = "%(asctime)s [%(levelname)s] %(message)s"
    LONG_FMT = "%(asctime)s [%(name)s] %(levelname)s %(message)s"

    # ── Root / eval logger ────────────────────────────────────────────────────
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()

    # Console: show eval + runner messages at INFO; suppress noisy third-parties
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(SHORT_FMT))
    console.addFilter(lambda r: not r.name.startswith("memblocks"))
    root.addHandler(console)

    # eval.log: everything from the eval harness (not memblocks internals)
    eval_file = _FlushingFileHandler(log_dir / "eval.log")
    eval_file.setLevel(logging.DEBUG)
    eval_file.setFormatter(logging.Formatter(LONG_FMT))
    eval_file.addFilter(lambda r: not r.name.startswith("memblocks"))
    root.addHandler(eval_file)

    # ── memblocks library logger ──────────────────────────────────────────────
    mb_logger = logging.getLogger("memblocks")
    mb_logger.setLevel(logging.DEBUG)
    mb_logger.propagate = False  # don't double-log to root handlers

    # Console: show memblocks DEBUG so LLM calls appear live in the terminal
    mb_console = logging.StreamHandler(sys.stderr)
    mb_console.setLevel(logging.DEBUG)
    mb_console.setFormatter(logging.Formatter(SHORT_FMT))
    mb_logger.addHandler(mb_console)

    # memblocks.log: full DEBUG dump for post-mortem inspection
    mb_file = _FlushingFileHandler(log_dir / "memblocks.log")
    mb_file.setLevel(logging.DEBUG)
    mb_file.setFormatter(logging.Formatter(LONG_FMT))
    mb_logger.addHandler(mb_file)

    # Suppress noisy third-party libraries
    for name in ("httpx", "httpcore", "groq", "pymongo", "urllib3", "openinference"):
        logging.getLogger(name).setLevel(logging.WARNING)

    return log_dir


_log_dir = _setup_logging()
logger = logging.getLogger(__name__)
logger.info("Eval session log directory: %s", _log_dir.absolute())


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