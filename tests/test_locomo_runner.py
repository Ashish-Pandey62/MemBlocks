"""Tests for LocomoRunner ingestion and retrieval logic."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch, call
from pathlib import Path
from evaluation.runners.locomo import LocomoRunner
from evaluation.core.config import RunnerConfig
from evaluation.datasets.locomo import LocomoDataset, LocomoSession, LocomoMessage, LocomoQuestion

# --- Test Fixtures ---
@pytest.fixture
def mock_memblocks():
    """Mock MemBlocksClient and MemBlocksConfig with proper async support."""
    with patch("evaluation.runners.locomo.MemBlocksClient") as mock_client, \
         patch("evaluation.runners.locomo.MemBlocksConfig") as mock_config:
        # Retrieval result with to_prompt_string support
        def _make_retrieve_result(label):
            r = MagicMock()
            r.to_prompt_string.return_value = f"context-{label}"
            return r

        # Block with async retrieval methods
        mock_block = MagicMock()
        mock_block.id = "locomo-session-test-session-1"
        mock_block.semantic_retrieve = AsyncMock(return_value=_make_retrieve_result("semantic"))
        mock_block.core_retrieve = AsyncMock(return_value=_make_retrieve_result("core"))
        mock_block.retrieve = AsyncMock(return_value=_make_retrieve_result("hybrid"))

        # Session with async add/flush/memory methods
        mock_session = MagicMock()
        mock_session.add = AsyncMock()
        mock_session.flush = AsyncMock()
        mock_session.get_memory_window = AsyncMock(return_value=[])
        mock_session.get_recursive_summary = AsyncMock(return_value="")

        # Client with async lifecycle methods
        mock_client_instance = MagicMock()
        mock_client_instance.get_or_create_user = AsyncMock()
        mock_client_instance.create_block = AsyncMock(return_value=mock_block)
        mock_client_instance.create_session = AsyncMock(return_value=mock_session)
        mock_client_instance.close = AsyncMock()
        mock_client.return_value = mock_client_instance

        # Config (sync)
        mock_config_instance = MagicMock()
        mock_config.return_value = mock_config_instance

        yield {
            "client": mock_client,
            "client_instance": mock_client_instance,
            "session": mock_session,
            "block": mock_block,
            "config": mock_config,
            "config_instance": mock_config_instance,
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
        # Check create_block was called with the correct block name
        mock_memblocks["client_instance"].create_block.assert_called_once_with(
            user_id=f"eval-locomo-{sample_session.session_id}",
            name=f"locomo-session-{sample_session.session_id}",
        )
    
    def test_session_add_called_for_each_turn(self, runner, mock_memblocks, sample_session):
        """Verify session.add() is called once per paired (user, assistant) turn."""
        result = runner.run(output_dir=Path("/tmp/test-output"))

        # 3 messages → 2 turns: (Hello!, Hi there!) and (How are you?, "")
        assert mock_memblocks["session"].add.call_count == 2
        # Each call uses user_msg / ai_response kwargs
        calls = mock_memblocks["session"].add.call_args_list
        assert calls[0] == call(user_msg="Hello!", ai_response="Hi there!")
        assert calls[1] == call(user_msg="How are you?", ai_response="")

    def test_session_flush_called_once_after_ingestion(self, runner, mock_memblocks, sample_session):
        """Verify session.flush() is called once after all turns are ingested."""
        result = runner.run(output_dir=Path("/tmp/test-output"))

        assert mock_memblocks["session"].flush.call_count == 1

    def test_ingestion_status_recorded(self, runner, mock_memblocks, sample_session):
        """Verify ingestion status is recorded in results."""
        result = runner.run(output_dir=Path("/tmp/test-output"))

        detail = result["details"][0]
        assert detail["ingestion_status"] == "success"
        assert detail["block_id"] == mock_memblocks["block"].id
    
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


# --- Retrieval function test ---
def test_retrieval(mock_memblocks, sample_session, mock_dataset):
    """Verify all 3 retrieval strategies are invoked and context is stored."""
    config = RunnerConfig(name="locomo-test-runner")
    runner = LocomoRunner(config=config, dataset=mock_dataset)

    result = runner.run(output_dir=Path("/tmp/test-output"))

    detail = result["details"][0]
    assert detail["ingestion_status"] == "success"

    # All 3 block-level retrieval methods called once per question
    mock_memblocks["block"].semantic_retrieve.assert_called_once()
    mock_memblocks["block"].core_retrieve.assert_called_once()
    mock_memblocks["block"].retrieve.assert_called_once()

    # Context strings come from the fixture's to_prompt_string() return values
    eval_result = detail["evaluations"][0]
    assert eval_result["retrieved_context_semantic"] == "context-semantic"
    assert eval_result["retrieved_context_core"] == "context-core"
    assert eval_result["retrieved_context_hybrid"] == "context-hybrid"


# --- Task 2: Retrieval Tests ---
class TestRetrieval:
    """Tests for multi-strategy context retrieval logic (PIPE-02)."""

    def test_three_strategies_called_per_question(self, runner, mock_memblocks, sample_session):
        """Verify all 3 retrieval strategies are called for each question."""
        result = runner.run(output_dir=Path("/tmp/test-output"))

        question_count = len(sample_session.questions)
        assert mock_memblocks["block"].semantic_retrieve.call_count == question_count
        assert mock_memblocks["block"].core_retrieve.call_count == question_count
        assert mock_memblocks["block"].retrieve.call_count == question_count

    def test_retrieved_context_stored_in_eval_result(self, runner, mock_memblocks, sample_session):
        """Verify retrieved context is stored in eval_result per strategy."""
        result = runner.run(output_dir=Path("/tmp/test-output"))

        eval_result = result["details"][0]["evaluations"][0]
        assert eval_result["retrieved_context_semantic"] == "context-semantic"
        assert eval_result["retrieved_context_core"] == "context-core"
        assert eval_result["retrieved_context_hybrid"] == "context-hybrid"

    def test_retrieval_skipped_if_ingestion_failed(self, mock_memblocks, sample_session, mock_dataset):
        """Verify retrieval is skipped if ingestion failed."""
        mock_memblocks["client"].side_effect = Exception("Ingestion failed")

        config = RunnerConfig(name="locomo-test-runner")
        runner = LocomoRunner(config=config, dataset=mock_dataset)

        result = runner.run(output_dir=Path("/tmp/test-output"))

        detail = result["details"][0]
        assert "memblocks_error" in detail["ingestion_status"]
        # No evaluations run when ingestion fails
        assert len(detail["evaluations"]) == 0
        mock_memblocks["block"].semantic_retrieve.assert_not_called()

    def test_retrieval_error_handling(self, runner, mock_memblocks, sample_session):
        """Verify retrieval errors are caught and logged."""
        mock_memblocks["block"].semantic_retrieve.side_effect = Exception("Retrieval failed")

        result = runner.run(output_dir=Path("/tmp/test-output"))

        eval_result = result["details"][0]["evaluations"][0]
        assert "retrieval_failed" in eval_result["status"]


# --- Task 1 (Plan 08-02): LLM QA with CoT Tests (PIPE-03) ---
def test_qa(mock_memblocks, sample_session, mock_dataset):
    """Test LLM QA with CoT prompt and answer storage per strategy."""
    sample_template = (
        "Answer the user's question using the provided context.\n\n"
        "Think step by step before providing your final answer.\n\n"
        "<context>{retrieved_context}</context>\n\n"
        "Question: {question_text}\n\n"
        "Provide your final answer in 1-2 sentences."
    )

    config = RunnerConfig(name="locomo-test-runner")
    runner = LocomoRunner(config=config, dataset=mock_dataset)

    runner._load_qa_template = MagicMock(return_value=sample_template)
    runner._call_llm = MagicMock(side_effect=lambda prompt: f"Answer: {prompt[:30]}...")

    result = runner.run(output_dir=Path("/tmp/test-output"))

    runner._load_qa_template.assert_called_once()
    assert runner._call_llm.call_count == 3  # once per strategy

    eval_result = result["details"][0]["evaluations"][0]
    assert eval_result.get("answer_semantic") is not None
    assert eval_result.get("answer_core") is not None
    assert eval_result.get("answer_hybrid") is not None

    for c in runner._call_llm.call_args_list:
        prompt = c[0][0]
        assert "<context>" in prompt
        assert "</context>" in prompt
        assert "Think step by step" in prompt
        assert "Question:" in prompt


# --- Task 2 (Plan 08-02): Baseline Deferral Tests (PIPE-04) ---
def test_baseline_deferred(mock_memblocks, sample_session, mock_dataset):
    """Test baseline comparison is properly deferred per user decision."""
    config = RunnerConfig(name="locomo-test-runner")
    runner = LocomoRunner(config=config, dataset=mock_dataset)

    runner._load_qa_template = MagicMock(return_value=None)

    result = runner.run(output_dir=Path("/tmp/test-output"))

    eval_result = result["details"][0]["evaluations"][0]
    assert eval_result.get("baseline_status") == "deferred_per_user_decision"
    assert "baseline_context" not in eval_result
    assert "baseline_answer" not in eval_result
