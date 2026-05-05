"""Tests for LoCoMo dataset parsing."""

import pytest
from evaluation.core.config import DatasetConfig
from evaluation.datasets import LocomoDataset


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