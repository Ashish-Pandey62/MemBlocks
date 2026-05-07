# Evaluation Framework Issues Report

The following problems and inconsistencies were found in the `evaluation/` directory regarding logic, typing, and `memblocks` SDK usage. These inconsistencies arise mainly because the evaluation runners assume an outdated or incorrect synchronous API for `memblocks` instead of its current asynchronous API.

## 1. Invalid `MemBlocksConfig` Initialization
**File:** `evaluation/runners/locomo.py`  
**Line:** `block_config = MemBlocksConfig(block_id=block_id)`  
**Problem:** `MemBlocksConfig` does not accept a `block_id` as an argument. Block identifiers are created or specified when instantiating blocks using the client (i.e. `await client.create_block(user_id=..., name=...)`). Modern `MemBlocksConfig` instead expects configuration values like `llm_settings=LLMSettings(...)`. 

## 2. Sync Operations on Async SDK
**File:** `evaluation/runners/locomo.py`  
**Line:** Various (e.g., `block_client.session.add(message)`, `block_client.retrieve(...)`)  
**Problem:** All interactions with `MemBlocksClient`, `Block`, and `Session` in the `memblocks` library are strictly asynchronous and must be awaited. The evaluation runner's `_run_async` method handles them sequentially as if they were synchronous functions. 
Correct SDK usage requires:
- `await client.create_block(...)`
- `await client.create_session(...)`
- `await session.add(...)`
- `await block.retrieve(...)`

## 3. Invalid Attribute Access: `.session`
**File:** `evaluation/runners/locomo.py`  
**Line:** `block_client.session.add(message)`  
**Problem:** The `MemBlocksClient` instance does not have a `.session` attribute exposed directly. Sessions must be explicitly created or fetched via the SDK (e.g., `session = await client.create_session(user_id, block_id)`).

## 4. Incorrect Parameters for `.add()`
**File:** `evaluation/runners/locomo.py`  
**Line:** `block_client.session.add(message)`  
**Problem:** The SDK's session object expects distinct user queries and assistant responses using keyword arguments: `await session.add(user_msg=..., ai_response=...)`. Calling it with a single `message` object will result in a `TypeError`.

## 5. Non-existent Method `.flush()`
**File:** `evaluation/runners/locomo.py`  
**Line:** `block_client.session.flush()`  
**Problem:** The SDK's `Session` interface does not implement a `.flush()` method. The `session.add(...)` method persists the turn inherently.

## 6. Invalid Method Call: `block_client.retrieve(...)`
**File:** `evaluation/runners/locomo.py`  
**Line:** `block_client.retrieve(question_text, strategy=strategy, top_k=5)`  
**Problem:** `MemBlocksClient` does not have a `.retrieve()` method. Retrieval methods are scoped to a specific block instance (`Block`). The correct usage is to call retrieval on a block variable, like `await block.retrieve(...)`.

## 7. Invalid Retrieval Parameters: `strategy` and `top_k`
**File:** `evaluation/runners/locomo.py`  
**Line:** `return block_client.retrieve(question_text, strategy=strategy, top_k=5)`  
**Problem:** The SDK's generic `block.retrieve(...)` method does not take `strategy` or `top_k` string parameters. Instead, `Block` provides explicitly separated retrieval strategies:
- `await block.semantic_retrieve(query)`
- `await block.core_retrieve()`
- `await block.retrieve(query)` (Returns both)

## 8. Misaligned Mock/Fallback Classes
**File:** `evaluation/runners/locomo.py`  
**Line:** `class _InMemorySession`, `class _InMemoryBlockClient`  
**Problem:** The fallback `_InMemoryBlockClient` and `_InMemorySession` explicitly mock the erroneous synchronous interface used by the rest of `locomo.py` instead of modeling the actual `MemBlocksClient` structure (`create_session`, `create_block`, and async awaitables). This buries the errors when the tests run without `memblocks` installed.

## 9. Type Mismatch in `Reporter.save_run_info`
**File:** `evaluation/runners/locomo.py` and `evaluation/metrics/reporter.py`  
**Line:** `reporter.save_run_info(self.run_config, output_dir)`  
**Problem:** In `locomo.py`, `self.run_config` is defined as a `RunConfig` (or `RunnerConfig`). However, the definition of `save_run_info` in `reporter.py` uses the type hint `config: EvalConfig`. `EvalConfig` is the top-level configuration wrapper that contains a `runs: List[RunConfig]`. While it may succeed dynamically (both are Pydantic classes with a `.model_dump()` method), it's fundamentally a type mismatch.

## 10. Memory Pipeline Triggered Per Message (Premature Flush)
**File:** `evaluation/runners/locomo.py#L105`  
**Line:** `block_client.session.add(message)` + `block_client.session.flush()` inside the per-message ingestion loop  
**Problem:** The ingestion loop explicitly flushes on every single message, which (if `Session.flush()` were used) triggers the full memory pipeline and trims the message window to `keep_last_n` each time. This means the pipeline repeatedly processes tiny windows instead of the intended full conversation window, and trims away earlier context before it can be incorporated. In `memblocks`, `Session.flush()` is a *manual* full-window pipeline run designed for session end, not per-message ingestion.
**Relevant SDK:** `memblocks_lib/src/memblocks/services/session.py#L181` (flush) and `memblocks_lib/src/memblocks/services/session.py#L108` (add)

## 11. Message-Level Ingestion Breaks Turn Semantics
**File:** `evaluation/runners/locomo.py#L105`  
**Line:** `block_client.session.add(message)` where `message` is a `LocomoMessage`  
**Problem:** `Session.add()` expects a *turn* (`user_msg`, `ai_response`) and internally writes two messages in order. The dataset provides single role-tagged messages, but the evaluation runner passes them one-by-one, which cannot map correctly to the SDK's turn-based memory window. This breaks summary generation and memory extraction logic that assume alternating user/assistant turns.  
**Relevant SDK:** `memblocks_lib/src/memblocks/services/session.py#L108`

## 12. Missing Block/Session Lifecycle (No `create_block` or `create_session`)
**File:** `evaluation/runners/locomo.py#L83`  
**Line:** The runner creates `MemBlocksClient` and immediately calls `.session.add(...)` without ever creating a user, block, or session.  
**Problem:** The SDK requires `await client.get_or_create_user(...)`, `await client.create_block(...)`, and `await client.create_session(...)` to establish persistence and wire a block for retrieval. The evaluation code skips these steps entirely, so there is no actual block, session, or user context attached to the ingestion.  
**Correct pattern:** `backend/src/cli/main.py#L312` through `backend/src/cli/main.py#L344`

## 13. QA Uses Retrieval Only (No Memory Window or Summary)
**File:** `evaluation/runners/locomo.py#L166`  
**Line:** QA prompt is built solely from `retrieved_context_*` and `question.question`  
**Problem:** The evaluation never pulls `session.get_memory_window()` or `session.get_recursive_summary()`, which are core to how the SDK is used in actual chat (`main.py`). This means QA does not include the recent memory window or rolling summary, so the evaluation does not reflect real-world memory usage.
**Correct pattern:** `backend/src/cli/main.py#L387` through `backend/src/cli/main.py#L403`

## 14. Retrieval Happens During Ingestion via Conflict Resolution
**File:** `evaluation/runners/locomo.py#L105` plus `memblocks_lib/src/memblocks/services/semantic_memory.py#L223`  
**Problem:** Because ingestion flushes on every message, the memory pipeline runs repeatedly. Each pipeline run executes PS2 conflict resolution, which internally performs vector retrieval from Qdrant to fetch similar memories. This means retrieval is happening during ingestion, which contradicts the evaluation assumption that retrieval should only occur during QA.

## 15. Strategy Evaluation Is Not Actually Measured
**File:** `evaluation/runners/locomo.py#L166` and `evaluation/runners/locomo.py#L342`  
**Problem:** The runner generates answers for `semantic`, `core`, and `hybrid` strategies, but only the `hybrid` answer is ever judged (`score_hybrid`) and counted in aggregate metrics. The accuracy report therefore does not compare strategies despite collecting them.

## 16. QA Can Succeed Without Any Answer Generation
**File:** `evaluation/runners/locomo.py#L72` and `evaluation/runners/locomo.py#L167`  
**Problem:** If the QA prompt template is missing, the runner skips answer generation entirely but still marks each question as `retrieval_success`. The aggregator still counts those questions, which results in an accuracy of 0% without explicitly flagging that QA never executed.

## 17. Hardcoded LLM Port Conflicts With Default MemBlocks Config
**File:** `evaluation/runners/locomo.py#L287` and `evaluation/metrics/locomo.py#L140`  
**Problem:** QA and judge calls go to `http://localhost:11435/api/generate`, but in `MemBlocksConfig` that port is reserved for embeddings (`OLLAMA_BASE_URL_EMBEDDINGS`). The default generation endpoint is `11434`. This is a strong assumption about the local setup and will fail on default memblocks configurations.
**Relevant SDK:** `memblocks_lib/src/memblocks/config.py#L205`

## 18. Client Lifecycle Not Closed (Resource Leak)
**File:** `evaluation/runners/locomo.py`  
**Problem:** A new `MemBlocksClient` is created for each session, but the evaluation runner never calls `await client.close()`. In the real SDK this leaves MongoDB connections open and can exhaust resources over multiple runs.
