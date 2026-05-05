"""Base runner interface for evaluation pipelines."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from evaluation.core.config import RunnerConfig
from evaluation.datasets.base import BaseDataset


class BaseRunner(ABC):
    """Abstract base class for all evaluation runners.

    Subclass this to implement a specific evaluation pipeline.
    """

    def __init__(self, config: RunnerConfig, dataset: BaseDataset) -> None:
        """Initialize the runner with configuration and dataset.

        Args:
            config: Configuration for the runner.
            dataset: The dataset to evaluate against.
        """
        self.config = config
        self.dataset = dataset

    @abstractmethod
    def run(self, output_dir: Path) -> Any:
        """Execute the evaluation pipeline.

        Args:
            output_dir: Directory where output files should be written.

        Returns:
            Any results from the evaluation run.

        Raises:
            NotImplementedError: This method must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement the run() method")