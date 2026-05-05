"""Tests for LocomoRunner ingestion and retrieval logic."""
import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
from evaluation.runners.locomo import LocomoRunner
from evaluation.core.config import RunnerConfig
from evaluation.datasets.locomo import LocomoDataset, LocomoSession, LocomoMessage, LocomoQuestion

# --- Test Fixtures ---
@pytest.fixture
def mock_memblocks():
    """Mock MemBlocksClient and MemBlocksConfig."""
    with patch("evaluation.runners.locomo.MemBlocksClient") as mock_client, \
         patch("evaluation.runners.locomo.MemBlocksConfig") as mock_config:
        # Configure mock client
        mock_session = MagicMock()
        mock_client_instance = MagicMock()
        mock_client_instance.session = mock_session
        mock_client.return_value = mock_client_instance
        
        # Configure mock config
        mock_config_instance = MagicMock()
        mock_config.return_value = mock_config_instance
        
        yield {
            "client": mock_client,
            "client_instance": mock_client_instance,
            "session": mock_session,
            "config": mock_config,
            "config_instance": mock_config_instance
        }

@pytest.fixture
def sample_session():
    """Create a sample LocomoSession for testing."""
    messages = [
        LocomoMessage(role="user", content="Hello!"),
        LocomoMessage(role="assistant", content="Hi there!"),
        LocomoMessage(role="user", content="How are you?")
    ]
    questions = [
        LocomoQuestion(
            question="How did the conversation start?",
            answer="The user said Hello!",
            category="facts"
        )
    ]
    return LocomoSession(
        session_id="test-session-1",
        messages=messages,
        questions=questions
    )

@pytest.fixture
def mock_dataset(sample_session):
    """Mock LocomoDataset that returns sample sessions."""
    dataset = MagicMock(spec=LocomoDataset)
    dataset.load.return_value = [sample_session]
    return dataset

@pytest.fixture
def runner(mock_dataset):
    """Create LocomoRunner with mock dataset."""
    config = RunnerConfig(name="locomo-test-runner")
    return LocomoRunner(config=config, dataset=mock_dataset)

# --- Task 1: Ingestion Tests ---
class TestIngestion:
    """Tests for MemBlocks session ingestion logic (PIPE-01)."""
    
    def test_one_block_created_per_session(self, runner, mock_memblocks, sample_session):
        """Verify one MemBlocks block is created per session."""
        # Run the pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check that MemBlocksClient was initialized once (for one session)
        assert mock_memblocks["client"].call_count == 1
        # Check block_id format
        block_id_call = mock_memblocks["config"].call_args[1].get("block_id")
        assert block_id_call == f"locomo-session-{sample_session.session_id}"
    
    def test_session_add_called_for_each_message(self, runner, mock_memblocks, sample_session):
        """Verify session.add() is called for each message in the session."""
        # Run the pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check that add() was called once per message
        assert mock_memblocks["session"].add.call_count == len(sample_session.messages)
        # Verify each message was added
        expected_calls = [call(msg) for msg in sample_session.messages]
        mock_memblocks["session"].add.assert_has_calls(expected_calls, any_order=False)
    
    def test_session_flush_called_after_each_message(self, runner, mock_memblocks, sample_session):
        """Verify session.flush() is called after each message."""
        # Run the pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check that flush() was called once per message (after each add)
        assert mock_memblocks["session"].flush.call_count == len(sample_session.messages)
    
    def test_ingestion_status_recorded(self, runner, mock_memblocks, sample_session):
        """Verify ingestion status is recorded in results."""
        # Run the pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check result details
        detail = result["details"][0]
        assert detail["ingestion_status"] == "success"
        assert detail["block_id"] == f"locomo-session-{sample_session.session_id}"
    
    def test_ingestion_error_handling(self, runner, mock_memblocks, sample_session):
        """Verify errors during ingestion are caught and logged."""
        # Make MemBlocksClient raise an exception
        mock_memblocks["client"].side_effect = Exception("Connection failed")
        
        # Run the pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check error is recorded
        detail = result["details"][0]
        assert "failed" in detail["ingestion_status"]
        assert detail["block_id"] is None


# --- Plan-required test_ingestion() function ---
def test_ingestion(mock_memblocks, sample_session, mock_dataset):
    """Plan-specified test_ingestion() function for Task 1 verification."""
    # Create runner with proper config
    config = RunnerConfig(name="locomo-test-runner")
    runner = LocomoRunner(config=config, dataset=mock_dataset)
    
    # Run the pipeline
    result = runner.run(output_dir=Path("/tmp/test-output"))
    
    # Verify one block created per session
    assert mock_memblocks["client"].call_count == 1
    block_id_call = mock_memblocks["config"].call_args[1].get("block_id")
    assert block_id_call == f"locomo-session-{sample_session.session_id}"
    
    # Verify session.add() called for each message
    assert mock_memblocks["session"].add.call_count == len(sample_session.messages)
    expected_calls = [call(msg) for msg in sample_session.messages]
    mock_memblocks["session"].add.assert_has_calls(expected_calls, any_order=False)
    
    # Verify session.flush() called after each message
    assert mock_memblocks["session"].flush.call_count == len(sample_session.messages)
    
    # Verify ingestion status recorded
    detail = result["details"][0]
    assert detail["ingestion_status"] == "success"
    assert detail["block_id"] == f"locomo-session-{sample_session.session_id}"
