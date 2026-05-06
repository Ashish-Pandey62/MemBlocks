# Testing Patterns

**Analysis Date:** 2026-05-04

## Test Framework

**Runner:**
- `pytest` version 9.0.2
- `pytest-asyncio` version 0.25.2 (for async test support)
- Configured in `mcp_server/pyproject.toml` dependency group

**Assertion Library:**
- Standard pytest assertions
- `pytest.raises()` for exception testing

**Run Commands:**
```bash
pytest                          # Run all tests
pytest mcp_server/tests/        # Run MCP server tests
pytest tests/                   # Run integration tests
pytest -v                       # Verbose output
pytest --asyncio-mode=auto     # Auto-detect async tests
```

## Test File Organization

**Location:**
- Tests co-located with source in `mcp_server/tests/` directory
- Additional integration tests in root `tests/` directory

**Naming:**
- `test_*.py` - Test files with `test_` prefix
- Example: `test_store_background_tools.py`, `test_cli_resources.py`

**Structure:**
```
mcp_server/
├── server.py           # Source
├── cli.py              # Source
├── state.py            # Source
└── tests/
    ├── __init__.py
    ├── test_store_background_tools.py    # 316 lines
    └── test_cli_resources.py             # 348 lines

tests/
├── test_store_tools.py    # 58 lines (placeholder stubs)
└── test_hybrid.py         # 161 lines (manual test script)
```

## Test Structure

**Suite Organization:**
- Test classes grouped by feature/command
- Example classes:
  - `TestStateLayer` - Tests for `state.py` functions
  - `TestCLISetBlock` - CLI set-block command tests
  - `TestCLIHelp` - CLI help output tests
  - `TestStateMcpLock` - MCP lock state tests
  - `TestServerLockGuard` - Server lock guard tests

**Patterns:**
```python
class TestStateLayer:
    """Test the state.py functions."""

    def test_set_and_get_block_id(self, tmp_path):
        """Test: set_active_block_id writes state, get_active_block_id returns it."""
        from mcp_server import state

        # Monkeypatch STATE_FILE to tmp location
        original_state_file = state.STATE_FILE
        state.STATE_FILE = tmp_path / "active_block.json"

        try:
            state.set_active_block_id("abc123")
            result = state.get_active_block_id()
            assert result == "abc123"
        finally:
            state.STATE_FILE = original_state_file
```

**Setup Pattern:**
- Use pytest fixtures for test setup
- Use `monkeypatch` fixture for patching
- Use `tmp_path` fixture for temporary files
- Restore original state in finally blocks

**Teardown Pattern:**
- Always restore patched state in finally blocks
- Example:
```python
finally:
    state.STATE_FILE = original_state_file
```

## Mocking

**Framework:**
- `unittest.mock` - Standard library mocking
- `unittest.mock.AsyncMock` - For async methods
- `unittest.mock.MagicMock` - For general mocking

**Patterns:**
```python
class MockBlock:
    """Mock block for testing background dispatch."""

    def __init__(self, block_id: str = "test-block-id"):
        self.id = block_id
        self.core_memory_block_id = block_id
        self._semantic = MockSemantic()
        self._core = MockCore()


class MockSemantic:
    """Mock semantic memory section."""

    async def extract_and_store(self, messages, ps1_prompt=None, min_confidence=0.0):
        """Simulates slow extraction + storage - should NOT be awaited directly."""
        await asyncio.sleep(10)  # Simulate slow LLM operation
        return [MagicMock()]


class FakeContext:
    """Fake FastMCP context for testing."""

    def __init__(self, client, user_id="test-user"):
        self.request_context = MagicMock()
        self.request_context.lifespan_context = {
            "client": client,
            "user_id": user_id,
        }
```

**Async Mocking:**
```python
mock_client = MagicMock()
mock_client.get_block = AsyncMock(return_value=mock_block)
```

**Tracking Method Calls:**
```python
call_tracker = {"called": False, "messages": None}

async def tracking_extract_and_store(self, messages, ps1_prompt=None, min_confidence=0.0):
    call_tracker["called"] = True
    call_tracker["messages"] = messages
    return await original_extract_and_store(self, messages, ps1_prompt, min_confidence)
```

**What to Mock:**
- External services (MemBlocksClient)
- State file access (STATE_FILE)
- Time-consuming operations (LLM calls)
- MCP context objects

**What NOT to Mock:**
- Simple state functions (tested directly)
- Internal logic being tested
- Pydantic models (tested with real data)

## Fixtures and Factories

**Test Data:**
- Inline test data in test functions
- Mock classes defined in test files
- Example:
```python
params = CreateBlockInput(name="test-block")
params = StoreInput(fact="test fact")
```

**Location:**
- Fixtures defined inline in test files
- No separate fixtures file detected
- Example fixture:
```python
@pytest.fixture
def mock_state(monkeypatch, tmp_path):
    """Fixture that patches state to use tmp_path."""
    from mcp_server import state

    original_state_file = state.STATE_FILE
    state.STATE_FILE = tmp_path / "active_block.json"

    # Set a test active block
    state.set_active_block_id("test-block-id")

    yield state

    # Restore
    state.STATE_FILE = original_state_file
```

## Coverage

**Requirements:** None explicitly enforced

**View Coverage:**
```bash
pytest --cov=mcp_server          # With pytest-cov installed
pytest --cov-report=term-missing # Show missing lines
```

## Test Types

**Unit Tests:**
- Test individual functions in `state.py`, `cli.py`
- Test server tool functions with mocked dependencies
- Example: `test_set_and_get_block_id`, `test_get_block_id_returns_none_when_file_missing`

**Integration Tests:**
- Test CLI commands end-to-end with `sys.argv` patching
- Test server tool lock guards
- Example: `test_set_block_writes_state_and_exits_zero`, `test_create_block_blocked_when_locked`

**Async Tests:**
- Test MCP tools that use async/await
- Use `@pytest.mark.asyncio` decorator
- Example:
```python
@pytest.mark.asyncio
async def test_store_returns_immediately(mock_state):
    """memblocks_store should return within 1 second (dispatching both semantic + core)."""
    from mcp_server.server import memblocks_store, StoreInput
    ...
```

**Placeholder Tests:**
- Some test files contain placeholder tests (e.g., `tests/test_store_tools.py`)
- Marked with `pass` - full integration tests require MongoDB and Qdrant

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_store_semantic_returns_immediately(mock_state):
    """Test description."""
    # Setup
    mock_client = MagicMock()
    mock_block = MockBlock()
    mock_client.get_block = AsyncMock(return_value=mock_block)

    ctx = FakeContext(mock_client)

    # Execute with timing
    import time
    start = time.time()
    result = await memblocks_store_semantic(StoreSemanticInput(fact="test fact"), ctx)
    elapsed = time.time() - start

    # Assert
    assert elapsed < 1.0, f"Expected immediate return, took {elapsed:.2f}s"
    data = json.loads(result)
    assert data["status"] == "accepted"
```

**Error Testing:**
```python
@pytest.mark.asyncio
async def test_store_semantic_no_active_block_raises_immediately(monkeypatch, tmp_path):
    """No active block should raise ToolError immediately."""
    from fastmcp.exceptions import ToolError

    with pytest.raises(ToolError) as exc_info:
        await memblocks_store_semantic(StoreSemanticInput(fact="test fact"), ctx)

    assert "No active block" in str(exc_info.value)
```

**CLI Testing:**
```python
def test_set_block_writes_state_and_exits_zero(self, tmp_path, monkeypatch):
    """Test: CLI set-block <block_id> writes state and exits 0."""
    exit_code = None
    monkeypatch.setattr(sys, "argv", ["memblocks", "set-block", "abc123"])

    try:
        cli.main()
    except SystemExit as e:
        exit_code = e.code

    assert exit_code == 0
    assert state.get_active_block_id() == "abc123"
```

**Testing Timeouts:**
```python
import time
start = time.time()
result = await tool_function(...)
elapsed = time.time() - start

assert elapsed < 1.0, f"Expected immediate return, took {elapsed:.2f}s"
```

**Testing Background Tasks:**
```python
# Call tool that dispatches background task
result = await memblocks_store(StoreInput(fact="test fact"), ctx)

# Give the event loop a chance to run the background task
await asyncio.sleep(0.1)

# Verify background work was dispatched
assert call_tracker["called"], "extract_and_store should be called"
```

---

*Testing analysis: 2026-05-04*