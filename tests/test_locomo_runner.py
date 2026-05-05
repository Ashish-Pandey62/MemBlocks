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


# --- Plan-required test_retrieval() function ---
def test_retrieval(mock_memblocks, sample_session, mock_dataset):
    """Plan-specified test_retrieval() function for Task 2 verification."""
    # Mock retrieve method to return dummy context
    mock_memblocks["client_instance"].retrieve = MagicMock(
        side_effect=lambda text, strategy, top_k: f"context-{strategy}"
    )
    
    # Create runner with proper config
    config = RunnerConfig(name="locomo-test-runner")
    runner = LocomoRunner(config=config, dataset=mock_dataset)
    
    # Run the pipeline
    result = runner.run(output_dir=Path("/tmp/test-output"))
    
    # Check that retrieval was attempted (ingestion succeeds)
    detail = result["details"][0]
    assert detail["ingestion_status"] == "success"
    
    # Check that all 3 strategies were called for each question
    question = sample_session.questions[0]
    expected_retrieve_calls = [
        call(question.question, strategy="semantic", top_k=5),
        call(question.question, strategy="core", top_k=5),
        call(question.question, strategy="hybrid", top_k=5)
    ]
    mock_memblocks["client_instance"].retrieve.assert_has_calls(expected_retrieve_calls, any_order=True)
    
    # Check that retrieved context is stored in eval_result
    eval_result = detail["evaluations"][0]
    assert eval_result["retrieved_context_semantic"] == "context-semantic"
    assert eval_result["retrieved_context_core"] == "context-core"
    assert eval_result["retrieved_context_hybrid"] == "context-hybrid"
    assert eval_result["status"] == "retrieval_success"


# --- Task 2: Retrieval Tests ---
class TestRetrieval:
    """Tests for multi-strategy context retrieval logic (PIPE-02)."""
    
    def test_three_strategies_called_per_question(self, runner, mock_memblocks, sample_session):
        """Verify all 3 retrieval strategies are called for each question."""
        # Mock retrieve method
        mock_memblocks["client_instance"].retrieve = MagicMock(
            side_effect=lambda text, strategy, top_k: f"context-{strategy}"
        )
        
        # Run pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check 3 calls per question (one per strategy)
        question_count = len(sample_session.questions)
        assert mock_memblocks["client_instance"].retrieve.call_count == question_count * 3
    
    def test_retrieved_context_stored_in_eval_result(self, runner, mock_memblocks, sample_session):
        """Verify retrieved context is stored in eval_result per strategy."""
        # Mock retrieve method
        mock_memblocks["client_instance"].retrieve = MagicMock(
            side_effect=lambda text, strategy, top_k: f"ctx-{strategy}"
        )
        
        # Run pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check eval_result fields
        eval_result = result["details"][0]["evaluations"][0]
        assert eval_result["retrieved_context_semantic"] == "ctx-semantic"
        assert eval_result["retrieved_context_core"] == "ctx-core"
        assert eval_result["retrieved_context_hybrid"] == "ctx-hybrid"
    
    def test_retrieval_skipped_if_no_block_client(self, mock_memblocks, sample_session, mock_dataset):
        """Verify retrieval is skipped if ingestion failed (no block client)."""
        # Make MemBlocksClient raise error during ingestion
        mock_memblocks["client"].side_effect = Exception("Ingestion failed")
        
        # Create runner
        config = RunnerConfig(name="locomo-test-runner")
        runner = LocomoRunner(config=config, dataset=mock_dataset)
        
        # Run pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check retrieval was skipped
        eval_result = result["details"][0]["evaluations"][0]
        assert eval_result["status"] == "skipped_no_block_client"
        # Ensure retrieve was not called
        mock_memblocks["client_instance"].retrieve.assert_not_called()
    
    def test_retrieval_error_handling(self, runner, mock_memblocks, sample_session):
        """Verify retrieval errors are caught and logged."""
        # Make retrieve raise an exception
        mock_memblocks["client_instance"].retrieve.side_effect = Exception("Retrieval failed")
        
        # Run pipeline
        result = runner.run(output_dir=Path("/tmp/test-output"))
        
        # Check error is recorded
        eval_result = result["details"][0]["evaluations"][0]
        assert "retrieval_failed" in eval_result["status"]
