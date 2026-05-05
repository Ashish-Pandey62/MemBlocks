"""Dataset module for evaluation framework."""

from evaluation.datasets.base import BaseDataset
from evaluation.datasets.locomo import LocomoDataset

__all__ = ["BaseDataset", "LocomoDataset"]