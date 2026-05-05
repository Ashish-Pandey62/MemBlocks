"""Component registry for dynamic component loading."""

from typing import Any, Dict, Type


class Registry:
    """A simple registry for registering and retrieving components.

    Supports three component types: datasets, runners, and metrics.
    Components can be registered by name and retrieved later for use.
    """

    def __init__(self) -> None:
        self._datasets: Dict[str, Type] = {}
        self._runners: Dict[str, Type] = {}
        self._metrics: Dict[str, Type] = {}

    def register_dataset(self, name: str, cls: Type) -> None:
        """Register a dataset class.

        Args:
            name: Name to register the dataset under.
            cls: Dataset class to register.
        """
        self._datasets[name] = cls

    def register_runner(self, name: str, cls: Type) -> None:
        """Register a runner class.

        Args:
            name: Name to register the runner under.
            cls: Runner class to register.
        """
        self._runners[name] = cls

    def register_metric(self, name: str, cls: Type) -> None:
        """Register a metric class.

        Args:
            name: Name to register the metric under.
            cls: Metric class to register.
        """
        self._metrics[name] = cls

    def get_dataset(self, name: str) -> Type:
        """Retrieve a dataset class by name.

        Args:
            name: Name of the dataset to retrieve.

        Returns:
            The registered dataset class.

        Raises:
            KeyError: If the dataset is not registered.
        """
        if name not in self._datasets:
            raise KeyError(f"Dataset '{name}' not found. Available: {list(self._datasets.keys())}")
        return self._datasets[name]

    def get_runner(self, name: str) -> Type:
        """Retrieve a runner class by name.

        Args:
            name: Name of the runner to retrieve.

        Returns:
            The registered runner class.

        Raises:
            KeyError: If the runner is not registered.
        """
        if name not in self._runners:
            raise KeyError(f"Runner '{name}' not found. Available: {list(self._runners.keys())}")
        return self._runners[name]

    def get_metric(self, name: str) -> Type:
        """Retrieve a metric class by name.

        Args:
            name: Name of the metric to retrieve.

        Returns:
            The registered metric class.

        Raises:
            KeyError: If the metric is not registered.
        """
        if name not in self._metrics:
            raise KeyError(f"Metric '{name}' not found. Available: {list(self._metrics.keys())}")
        return self._metrics[name]

    def list_datasets(self) -> list[str]:
        """List all registered dataset names."""
        return list(self._datasets.keys())

    def list_runners(self) -> list[str]:
        """List all registered runner names."""
        return list(self._runners.keys())

    def list_metrics(self) -> list[str]:
        """List all registered metric names."""
        return list(self._metrics.keys())


# Global registry instance for convenience
_global_registry = Registry()


def get_registry() -> Registry:
    """Get the global registry instance.

    Returns:
        The global Registry instance.
    """
    return _global_registry