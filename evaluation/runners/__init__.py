"""Evaluation runners module."""

from evaluation.runners.base import BaseRunner
from evaluation.runners.locomo import LocomoRunner

__all__ = ["BaseRunner", "LocomoRunner"]