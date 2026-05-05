"""Base classes for dataset loading."""

from abc import ABC, abstractmethod
from typing import Any

from evaluation.core.config import DatasetConfig


class BaseDataset(ABC):
    """Abstract base class for all datasets.

    Subclass this to implement a specific data loading mechanism.
    """

    def __init__(self, config: DatasetConfig) -> None:
        """Initialize the dataset with configuration.

        Args:
            config: Configuration for the dataset.
        """
        self.config = config

    @abstractmethod
    def load(self) -> Any:
        """Load and return the dataset.

        Returns:
            The loaded dataset in whatever format is appropriate.

        Raises:
            NotImplementedError: This method must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement the load() method")