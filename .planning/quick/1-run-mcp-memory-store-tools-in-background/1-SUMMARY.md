---
phase: quick-1-run-mcp-memory-store-tools-in-background
plan: 1
subsystem: MCP Server
tags: [mcp, background-tasks, non-blocking, async]
dependency_graph:
  requires: []
  provides: [mcp-server-store-non-blocking]
  affects: [mcp_server/server.py]
tech_stack:
  added: [asyncio.create_task, pytest-asyncio]
  patterns: [background-dispatch, fire-and-forget-tasks]
key_files:
  created:
    - mcp_server/tests/test_store_background_tools.py
  modified:
    - mcp_server/server.py
    - mcp_server/pyproject.toml
decisions:
  - "Used extract_and_store convenience method instead of manual extract + store pipeline"
  - "Used update convenience method for core memory instead of manual get + extract + save"
  - "Returned 'status: accepted' response to indicate background processing"
  - "Kept active block validation synchronous as precondition check"
metrics:
  duration: 5min
  completed_date: 2026-03-16
  tasks: 2
  files: 3
---

# Quick Task 1: Run MCP Memory Store Tools in Background Summary

## One-Liner

Implemented non-blocking MCP store tools using background task dispatch with asyncio.create_task.

## What Was Built

- **Background-dispatch pattern** for all three store tools:
  - `memblocks_store_semantic` — dispatches `extract_and_store` in background
  - `memblocks_store_to_core` — dispatches `update` in background
  - `memblocks_store` — dispatches both semantic and core in background

- **Immediate response contract**: All tools return within <1 second with:
  ```json
  {
    "status": "accepted",
    "message": "Storage to both semantic and core memory accepted - processing in background"
  }
  ```

- **Helper function**: `_dispatch_background_task` wraps asyncio.create_task with exception logging

- **Regression tests**: 7 tests covering:
  - Immediate return for all three store tools
  - Background dispatch verification for extract_and_store and update
  - Edge case: no active block raises ToolError immediately

## Key Changes

### mcp_server/server.py
- Added `import asyncio` at top
- Added `_dispatch_background_task` helper after active block guard
- Refactored `memblocks_store_semantic`: now uses `extract_and_store` in background task
- Refactored `memblocks_store_to_core`: now uses `update` in background task
- Refactored `memblocks_store`: now dispatches both semantic + core in background tasks

### mcp_server/tests/test_store_background_tools.py (new)
- 7 async tests using pytest-asyncio
- Mocks for MockBlock, MockSemantic, MockCore
- Timing assertions (< 1 second return)
- Dispatch verification tests

### mcp_server/pyproject.toml
- Added `pytest-asyncio>=0.25.2` to dev dependencies

## Deviation from Plan

None - plan executed exactly as written.

## Auth Gates

None.

## Self-Check

- [x] Test file exists: `mcp_server/tests/test_store_background_tools.py`
- [x] Server compiles: `python -m py_compile mcp_server/server.py`
- [x] All 7 tests pass: `pytest mcp_server/tests/test_store_background_tools.py`
- [x] Commit exists: `4aec663`

## Self-Check: PASSED
