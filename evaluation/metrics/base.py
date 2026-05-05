"""Base classes for evaluation metrics."""

from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseMetric(ABC):
    """Abstract base class for all metrics.

    Subclass this to implement a specific metric calculation.
    """

    @abstractmethod
    def compute(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Compute the metric from evaluation results.

        Args:
            results: Dictionary containing evaluation results.

        Returns:
            Dictionary containing the computed metric values.

        Raises:
            NotImplementedError: This method must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement the compute() method")