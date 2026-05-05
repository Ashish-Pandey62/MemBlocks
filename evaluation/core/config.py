"""Configuration models for the evaluation framework."""

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, Field


class DatasetConfig(BaseModel):
    """Configuration for a dataset."""
    name: str = Field(..., description="Name of the dataset")
    path: Optional[str] = Field(None, description="Path to the dataset files")
    max_sessions: Optional[int] = Field(None, description="Maximum number of sessions to load")
    max_questions_per_session: Optional[int] = Field(None, description="Maximum questions per session")


class RunnerConfig(BaseModel):
    """Configuration for a runner."""
    name: str = Field(..., description="Name of the runner")
    model: Optional[str] = Field(None, description="Model to use")


class RunConfig(BaseModel):
    """Configuration for a single evaluation run."""
    name: str = Field(..., description="Name of this run")
    dataset: str = Field(..., description="Name of the dataset to use")
    runner: str = Field(..., description="Name of the runner to use")
    metrics: List[str] = Field(default_factory=list, description="List of metric names to compute")


class EvalConfig(BaseModel):
    """Top-level configuration for an evaluation."""
    runs: List[RunConfig] = Field(default_factory=list, description="List of run configurations")


def load_config(path: Path) -> EvalConfig:
    """Load and parse a YAML configuration file into an EvalConfig.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Parsed EvalConfig instance.
    """
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return EvalConfig(**data)