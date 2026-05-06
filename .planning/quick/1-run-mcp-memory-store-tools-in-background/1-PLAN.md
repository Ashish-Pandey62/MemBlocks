---
phase: quick-1-run-mcp-memory-store-tools-in-background
plan: 1
type: execute
wave: 1
depends_on: []
files_modified:
  - mcp_server/server.py
  - mcp_server/tests/test_store_background_tools.py
autonomous: true
requirements: [STOR-01, STOR-02, STOR-03]
must_haves:
  truths:
    - "Calling memblocks_store_semantic returns immediately with an accepted response instead of waiting for PS1+PS2 completion."
    - "Calling memblocks_store_to_core returns immediately with an accepted response instead of waiting for core extraction/save completion."
    - "Calling memblocks_store schedules both semantic and core writes in the background and returns without blocking on LLM/storage latency."
  artifacts:
    - path: "mcp_server/server.py"
      provides: "Background-dispatch implementation for store tools using semantic extract_and_store and core update convenience methods."
      contains: "asyncio.create_task"
    - path: "mcp_server/tests/test_store_background_tools.py"
      provides: "Automated regression tests proving non-blocking store tool behavior and correct service method dispatch."
      contains: "memblocks_store_semantic"
  key_links:
    - from: "mcp_server/server.py::memblocks_store_semantic"
      to: "block._semantic.extract_and_store"
      via: "background task"
      pattern: "extract_and_store\(messages"
    - from: "mcp_server/server.py::memblocks_store_to_core"
      to: "block._core.update"
      via: "background task"
      pattern: "update\(block_id=core_block_id"
    - from: "mcp_server/server.py::memblocks_store"
      to: "semantic+core background tasks"
      via: "single tool call dispatch"
      pattern: "create_task"
---

<objective>
Make MCP store tools non-blocking so agents get immediate responses while semantic/core persistence runs in the background.

Purpose: Reduce tool-call latency and prevent long-running LLM/storage operations from blocking MCP client interaction.
Output: Updated store tool execution path + targeted automated tests.
</objective>

<execution_context>
@C:/Users/Lenovo/.config/opencode/get-shit-done/workflows/execute-plan.md
@C:/Users/Lenovo/.config/opencode/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@mcp_server/server.py
@memblocks_lib/src/memblocks/services/semantic_memory.py
@memblocks_lib/src/memblocks/services/core_memory.py

<interfaces>
From memblocks_lib/src/memblocks/services/semantic_memory.py:
```python
async def extract_and_store(
    self,
    messages: List[Dict[str, str]],
    ps1_prompt: str = PS1_SEMANTIC_PROMPT,
    min_confidence: float = 0.0,
) -> List[SemanticMemoryUnit]:
```

From memblocks_lib/src/memblocks/services/core_memory.py:
```python
async def update(
    self,
    block_id: str,
    messages: List[Dict[str, str]],
    core_creation_prompt: str = CORE_MEMORY_PROMPT,
) -> CoreMemoryUnit:
```

From mcp_server/server.py:
```python
async def memblocks_store_semantic(params: StoreSemanticInput, ctx: Context) -> str
async def memblocks_store_to_core(params: StoreToCoreInput, ctx: Context) -> str
async def memblocks_store(params: StoreInput, ctx: Context) -> str
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add non-blocking store tool regression tests</name>
  <files>mcp_server/tests/test_store_background_tools.py</files>
  <behavior>
    - Test 1: `memblocks_store_semantic` returns an accepted payload quickly and dispatches `block._semantic.extract_and_store(messages)` in a background task.
    - Test 2: `memblocks_store_to_core` returns an accepted payload quickly and dispatches `block._core.update(block_id=core_block_id, messages=...)` in a background task.
    - Test 3: `memblocks_store` dispatches both semantic and core background work from one call and returns immediate acknowledgement.
    - Edge: no-active-block path still raises `ToolError` immediately (no background task scheduled).
  </behavior>
  <action>Create focused async unit tests that mock client/block services and assert call timing + dispatch targets. Do not rely on live MongoDB/Qdrant/LLM; use AsyncMock and event-loop-safe assertions. Keep tests isolated to server tool behavior (dispatch + response contract), not downstream service internals.</action>
  <verify>
    <automated>pytest mcp_server/tests/test_store_background_tools.py -q</automated>
  </verify>
  <done>New test file exists, fails before implementation changes, and explicitly validates background dispatch + immediate return behavior for all three store tools.</done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Refactor store tools to background execution using service convenience methods</name>
  <files>mcp_server/server.py</files>
  <behavior>
    - `memblocks_store_semantic` uses `extract_and_store` in background and returns immediate accepted JSON.
    - `memblocks_store_to_core` uses `update` in background and returns immediate accepted JSON.
    - `memblocks_store` triggers both semantic + core background operations in one call and returns immediate accepted JSON.
  </behavior>
  <action>Replace synchronous/awaited semantic-core pipelines in the three store tools with an internal background-dispatch pattern (`asyncio.create_task` + robust exception logging). Keep existing locked behavior: plain text fact wrapped as `[{"role":"user","content":fact}]`, active-block validation, and block-exists checks must remain synchronous preconditions. Use `block._semantic.extract_and_store(...)` and `block._core.update(...)` directly (do not hand-roll PS1/PS2/core sequencing in tool code). Return a consistent accepted response shape including status/message and block context; avoid claiming persistence is already complete.</action>
  <verify>
    <automated>pytest mcp_server/tests/test_store_background_tools.py -q</automated>
  </verify>
  <done>All store tools return without waiting on LLM/storage operations, background tasks call the correct service methods, and tests pass.</done>
</task>

</tasks>

<verification>
- Run: `pytest mcp_server/tests/test_store_background_tools.py -q`
- Spot-check: `python -m py_compile mcp_server/server.py`
</verification>

<success_criteria>
- All three MCP store tools respond immediately with accepted/non-blocking status.
- Semantic path uses `extract_and_store`; core path uses `update`; combined tool dispatches both.
- No regression to active block error behavior.
- New automated tests pass in under 60 seconds.
</success_criteria>

<output>
After completion, create `.planning/quick/1-run-mcp-memory-store-tools-in-background/1-SUMMARY.md`
</output>
