"""Tests for LoCoMo dataset parsing."""

import pytest
from evaluation.core.config import DatasetConfig
from evaluation.datasets import LocomoDataset
from evaluation.datasets.locomo import LocomoMessage, LocomoQuestion, LocomoSession


def test_locomo_imports():
    """Test that LocomoDataset can be imported."""
    from evaluation.datasets import LocomoDataset
    assert LocomoDataset is not None


def test_locomo_dataset_instantiation():
    """Test that LocomoDataset can be instantiated."""
    config = DatasetConfig(name="locomo")
    dataset = LocomoDataset(config)
    assert dataset is not None
    assert dataset.config.name == "locomo"


def test_locomo_dataclasses():
    """Test that the dataclasses can be imported."""
    from evaluation.datasets.locomo import (
        LocomoMessage,
        LocomoQuestion,
        LocomoSession,
        LocomoDataset,
    )
    assert LocomoMessage is not None
    assert LocomoQuestion is not None
    assert LocomoSession is not None
    assert LocomoDataset is not None


def test_basic_instantiation_with_config():
    """Test basic instantiation with various config options."""
    # Test with max_sessions
    config = DatasetConfig(name="locomo", max_sessions=5)
    dataset = LocomoDataset(config)
    assert dataset.config.max_sessions == 5

    # Test with max_questions_per_session
    config = DatasetConfig(name="locomo", max_questions_per_session=10)
    dataset = LocomoDataset(config)
    assert dataset.config.max_questions_per_session == 10