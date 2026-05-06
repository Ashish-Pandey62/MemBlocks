# Coding Conventions

**Analysis Date:** 2026-05-04

## Naming Patterns

**Files:**
- `snake_case.py` - All lowercase with underscores
- Example: `server.py`, `state.py`, `cli.py`

**Functions:**
- `snake_case` - Lowercase with underscores
- Example: `get_active_block_id()`, `setup_logging()`, `_dispatch_background_task()`

**Variables:**
- `snake_case` - Lowercase with underscores
- Example: `user_id`, `block_id`, `active_id`, `mcp_lock`

**Classes:**
- `PascalCase` - Capitalized words, no underscores
- Example: `CreateBlockInput`, `SetBlockInput`, `StoreInput`, `FakeContext`, `MockBlock`

**Types/Enums:**
- `PascalCase` - Capitalized words
- Example: `MemBlocksClient`, `LLMSettings`, `LLMTaskSettings`

**Constants:**
- `UPPER_SNAKE_CASE` - All uppercase with underscores
- Example: `STATE_FILE`, `LOG_DIR`

## Code Style

**Formatting:**
- No explicit formatter config detected (no ruff.toml, .prettierrc, etc.)
- Follows standard Python indentation (4 spaces)
- Maximum line length not enforced

**Linting:**
- No explicit linting config detected
- No ruff, pylint, or pyright config files found
- Code follows basic Python conventions

**Import Organization:**
1. Standard library imports (`os`, `sys`, `json`, `asyncio`, `pathlib`)
2. Third-party imports (`fastmcp`, `pydantic`, `starlette`, `uvicorn`)
3. Local application imports (`mcp_server.state`, `mcp_server.server`)
4. Example from `mcp_server/server.py`:
```python
import argparse
import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP, Context
from fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field, ConfigDict
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import uvicorn

from memblocks import MemBlocksClient, MemBlocksConfig
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings
from mcp_server.state import (...)
```

## Type Hints

**Usage:**
- Used extensively throughout codebase
- Return types specified on all functions
- Example: `def get_active_block_id() -> str | None:`
- Union types use Python 3.10+ syntax: `str | None` instead of `Optional[str]`

**Pydantic for Input Validation:**
- Uses Pydantic `BaseModel` for tool input schemas
- Uses `Field` for parameter definitions with description, min_length, max_length
- Uses `model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")` for strict validation
- Example from `mcp_server/server.py`:
```python
class CreateBlockInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(
        ...,
        description="Human-readable name for the new block",
        min_length=1,
        max_length=100,
    )
    description: str = Field(
        default="",
        description="Optional description of the block's purpose",
        max_length=500,
    )
```

## Error Handling

**Patterns:**
- Uses `fastmcp.exceptions.ToolError` for MCP tool errors
- Raises `ToolError` with descriptive messages for validation failures
- Uses logging for error tracking (`logger.warning()`, `logger.exception()`)
- Example pattern:
```python
if get_mcp_lock():
    logger.warning("memblocks_create_block: blocked — MCP lock enabled")
    raise ToolError(
        "MCP lock is enabled: block creation is not permitted for this session."
    )

# Validation with tuple return
def _active_block_id_or_error() -> tuple[str | None, str | None]:
    block_id = get_active_block_id()
    if not block_id:
        return None, (
            "No active block is set. "
            "Call `memblocks_list_blocks` to see available blocks, "
            "then call `memblocks_set_block` with the desired block ID to activate one."
        )
    return block_id, None
```

**Logging:**
- Uses stdlib `logging` module
- Custom `FlushingFileHandler` for immediate file writes
- Separate log files for server vs library logs
- Logs to stderr for MCP host visibility
- Example from `mcp_server/server.py`:
```python
logger = logging.getLogger(__name__)
logger.info(f"MCP server starting — logs at {LOG_DIR.absolute()}")

# Suppress noisy third-party loggers
for name in ("httpx", "httpcore", "groq", "pymongo", "urllib3", "openinference"):
    logging.getLogger(name).setLevel(logging.WARNING)
```

## Comments

**When to Comment:**
- Module-level docstrings for files explaining purpose
- Function docstrings for tool descriptions (exposed to MCP clients)
- Inline comments for complex logic or workarounds
- Example from `mcp_server/state.py`:
```python
"""Active block state module.

Reads and writes shared CLI/server state via ~/.config/memblocks/active_block.json.

Schema: {"user_id": "<str>", "block_id": "<str>", "mcp_locked": <bool>}

The MCP server writes user_id on startup. The CLI reads it for all commands that
need to identify the current user. Both sides read/write block_id and mcp_locked.
Uses only stdlib — no external dependencies.
"""
```

**JSDoc/TSDoc:**
- Not applicable - Python codebase
- Tool docstrings are exposed via MCP protocol

## Function Design

**Size:**
- Functions tend to be focused and single-purpose
- Helper functions prefixed with underscore for internal use
- Example: `_active_block_id_or_error()`, `_dispatch_background_task()`, `_build_client()`

**Parameters:**
- Use Pydantic models for structured input
- Use type hints for all parameters
- Example: `async def memblocks_store(params: StoreInput, ctx: Context) -> str:`

**Return Values:**
- Return JSON strings for MCP tool responses
- Use `json.dumps(result, indent=2)` for formatted output
- Return `str | None` for simple queries

## Module Design

**Exports:**
- Functions decorated with `@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`
- CLI entry points in `cli.py`: `memblocks_cli`, `memblocks_mcp`
- State module functions for shared state management

**Barrel Files:**
- Not detected - no explicit `__init__.py` exports patterns
- Direct imports from modules: `from mcp_server.state import get_active_block_id`

## Async Patterns

**Background Tasks:**
- Uses `asyncio.create_task()` for fire-and-forget background operations
- Wraps coroutines with logging exception handler
- Example from `mcp_server/server.py`:
```python
def _dispatch_background_task(
    coro,
    task_name: str,
    error_logger,
):
    """Dispatch a coroutine as a background task with exception logging."""
    async def run_with_logging():
        try:
            await coro
        except Exception as e:
            error_logger.exception(f"Background task '{task_name}' failed: {e}")

    asyncio.create_task(run_with_logging())
```

**Lifespan Management:**
- Uses `@asynccontextmanager` for lifespan context
- Initializes client on startup, closes on shutdown
- Stores client and user_id in lifespan context for access by tools

---

*Convention analysis: 2026-05-04*