# Domain Pitfalls

**Domain:** MCP Memory Server over existing async Python library (FastMCP + stdio)
**Researched:** 2026-03-12
**Confidence:** HIGH — based on direct codebase inspection, FastMCP 3.1.0 official docs, MCP protocol spec

---

## Critical Pitfalls

Mistakes that cause protocol failures, silent data loss, or rewrites.

### Pitfall 1: Logging to stdout Corrupts the MCP stdio Protocol

**What goes wrong:** The MCP stdio transport uses `stdout` exclusively for JSON-RPC newline-delimited messages. Any non-JSON bytes written to stdout — a `print()` call, a `logging.StreamHandler(sys.stdout)`, or debug output from a library during a tool call — interleave with protocol messages. The MCP client receives malformed JSON and immediately disconnects or silently drops all responses.

**Why it happens:** The existing CLI (`backend/src/cli/main.py`) freely uses `print()` for status output ("🔄 Retrieving memories...", "✅ Session: ..."). Developers copy these patterns into the MCP server without realizing the terminal context has changed. The `fastembed` SPLADE model download also prints progress bars to stdout during first use.

**Consequences:** Client drops connection; all tool calls fail silently; protocol appears to work but nothing is processed.

**Prevention:**
- Never call `print()` in any code path reachable from an MCP tool.
- Configure all logging to use `stderr` only: `logging.basicConfig(stream=sys.stderr, ...)`. The MCP spec explicitly allows stderr for logging.
- Use `ctx.info()` / `ctx.debug()` (FastMCP Context methods) for client-visible messages — these go through the protocol, not stdout.
- Pre-download SPLADE model in lifespan (before server is ready) to prevent download-time stdout noise.
- Run `grep -r "print(" backend/src/` before declaring the server ready.

**Detection:** MCP client reports JSON parse error on startup or first tool call. Client drops connection immediately. Any `print()` in tool call chain.

---

### Pitfall 2: Caching Active Block State In-Memory

**What goes wrong:** The MCP server reads `active_block.json` once at startup and stores the block ID in a variable. The user runs `memblocks set-block` from the CLI to switch contexts. The MCP server continues using the old block — silently writing and reading from the wrong memory block.

**Why it happens:** Optimizing for performance (file reads feel expensive); forgetting that CLI and MCP server are separate processes sharing state via file.

**Consequences:** Memories stored in the wrong block; retrievals miss all memories in the new block; user sees confusing behavior with no error message.

**Prevention:** Read `active_block.json` on every tool call. File reads are ~1ms — negligible compared to the LLM calls that follow. Do not cache the Block object either (see Pitfall 9 below).

**Detection:** Set active block A, call `store_semantic`, switch to block B via CLI, call `store_semantic` again — verify memories went to B not A.

---

### Pitfall 3: Creating MemBlocksClient Per Tool Call

**What goes wrong:** `MemBlocksClient(config)` is constructed inside each `@mcp.tool` handler. MongoDB and Qdrant connections are opened and closed on every MCP tool invocation. `MemBlocksClient.__init__()` instantiates 6 LLM provider instances, one Motor client, one QdrantAdapter, and one EmbeddingProvider.

**Why it happens:** Simplest code path; "just works" in tests with fast local infra. Developers copy CLI patterns where `MemBlocksClient` is constructed at the top of `_run_cli()` but forget to replicate that structure.

**Consequences:** 1-5 second connection overhead per tool call; connection pool exhaustion; `EmbeddingProvider` logs "Initialising SPLADE sparse embedder" on every call.

**Prevention:** Initialize `MemBlocksClient` exactly once in the FastMCP `lifespan` context. Store in the lifespan context dict. Access in all tools via `ctx.lifespan_context["client"]`. Call `await client.close()` in lifespan `finally` block.

**Detection:** Time two consecutive `retrieve` calls — if the second is as slow as the first (1-2s overhead), the client is being reconstructed.

---

### Pitfall 4: asyncio.run() or Blocking Calls Inside FastMCP's Event Loop

**What goes wrong:** FastMCP runs its own `asyncio` event loop via `mcp.run(transport="stdio")`. Calling `asyncio.run()` anywhere in the lifespan or tool code raises `RuntimeError: This event loop is already running`. More subtly, synchronous blocking calls — like `EmbeddingProvider.embed_documents()` (blocking HTTP to Ollama) and `_get_sparse_embedder()` (downloads ~200MB SPLADE model on first call) — block the entire event loop for their duration, serializing all concurrent MCP requests.

**Why it happens:** The CLI uses `asyncio.run(_run_cli())` where it owns the event loop entirely — blocking calls are invisible in single-client context. FastMCP's shared event loop exposes them. Developers copy the `asyncio.run()` pattern from CLI code into MCP server code.

**Consequences:** `RuntimeError` crash on startup or first tool call. First `store_semantic` call takes 30-60 seconds if SPLADE model hasn't been downloaded. Concurrent tool calls serialize on embedding computation.

**Prevention:**
- Never call `asyncio.run()` in MCP server code — use `await` only.
- Pre-warm SPLADE in lifespan: call `client.embeddings._get_sparse_embedder()` during startup.
- Pre-call `await client.get_or_create_user(user_id)` in lifespan.
- For blocking library calls in tools, use `await asyncio.to_thread(blocking_fn, *args)`.

**Detection:** `RuntimeError: This event loop is already running`. First store tool call takes 30+ seconds. Multiple tool calls complete serially.

---

### Pitfall 5: Routing MCP Store Calls Through MemoryPipeline.run()

**What goes wrong:** The session-based `MemoryPipeline.run()` (or `session.add()`) is used to handle MCP store operations, because it's what the CLI uses.

**Why it happens:** The CLI uses the full session pipeline; it's tempting to reuse the same entry point.

**Consequences:** `MemoryPipeline.run()` expects a full conversation turn (user message + AI response); creates session records; runs recursive summary; adds memory window entries — all completely unnecessary for MCP, and slow (adds 3-8s per call).

**Prevention:** Call `SemanticMemoryService.extract_and_store()` and `CoreMemoryService.update()` directly, bypassing the session layer entirely. This is explicitly documented in PROJECT.md.

**Detection:** Store tools taking > 5s; check whether the summary pipeline is being invoked.

---

### Pitfall 6: Missing Active Block State → Silent No-Op or Crash

**What goes wrong:** The MCP server starts; no active block has been set via CLI. A tool is called. The server either crashes with an unhelpful `FileNotFoundError` (exposed to the MCP client) or silently returns empty results after `get_block(None)` returns `None` and subsequent attribute access crashes with `AttributeError`.

**Why it happens:** Missing guard on state file existence; happy-path testing always has a state file present.

**Consequences:** User stores memories, gets success response, but nothing was stored. Or server crashes with an internal exception message.

**Prevention:**
- Check for missing or malformed state file at the start of every tool handler — wrap reads in `try/except (FileNotFoundError, json.JSONDecodeError, OSError)` and return `None`.
- On `None` block_id: `raise ToolError("No active block set. Run: memblocks set-block <block_id>")`.
- Also validate block exists after loading: `block = await client.get_block(block_id); if block is None: raise ToolError(...)`.

**Detection:** Start server fresh (no state file), call any store tool — must return a clear error, not a crash or silent success.

---

### Pitfall 7: Silent Extraction Failure Returned as Success

**What goes wrong:** `SemanticMemoryService.extract()` and `CoreMemoryService.extract()` both swallow exceptions internally and return empty results (graceful degradation for CLI use). A store tool checks the return code rather than the return value, returning `{"stored": true}` even when the LLM extraction failed and nothing was written to MongoDB or Qdrant.

**Why it happens:** The graceful degradation pattern (return empty rather than raise) is correct for the interactive CLI — the user can see no memory was stored and retry. For the MCP protocol, the agent treats the return value as authoritative and has no other visibility.

**Consequences:** Agent believes facts were persisted; retrieval returns nothing; agent makes decisions based on memory that was never stored.

**Prevention:**
- After `extract()`: check return value. If `SemanticMemoryService.extract()` returns an empty list, return `{"stored": false, "reason": "LLM extraction found no memorable facts in the provided text"}`.
- After `CoreMemoryService.update()`: check that returned `CoreMemoryUnit` has non-empty `human_content`. If both fields are empty, report partial failure.
- Use `ToolError` for clear failures; use `{"stored": false, "reason": "..."}` for soft failures.

**Detection:** Call `store_semantic`, get success response, then call `retrieve_semantic` on the same content — if nothing is returned, extraction silently failed.

---

## Moderate Pitfalls

### Pitfall 8: MCP Tool Errors Raised as Raw Python Exceptions

**What goes wrong:** Unhandled Python exceptions from tools expose internal stack traces (MongoDB connection strings, file paths, library versions) to the agent context. With `mask_error_details=False` (FastMCP default), all exception details are forwarded.

**Prevention:**
- Use `from fastmcp.exceptions import ToolError` for all expected failure states. `ToolError` messages always pass through regardless of `mask_error_details` setting.
- Configure `FastMCP("MemBlocks", mask_error_details=True)` — unhandled exceptions are masked to a generic message.
- Never use bare `raise Exception(...)` for "no active block", "empty input", or "block not found" states.

---

### Pitfall 9: Block Object Cached After block_id Changes

**What goes wrong:** A `Block` object is cached after `client.get_block(block_id)`. The active block changes via CLI. The cached Block still points to the old block's Qdrant collection and MongoDB document.

**Prevention:** Do not cache `Block` objects. Call `client.get_block(block_id)` fresh on each tool invocation after reading the current `block_id` from state. Block construction is cheap (no I/O) — the client already holds all infrastructure adapters.

---

### Pitfall 10: Vague Tool Descriptions

**What goes wrong:** Tool docstrings say "Store memory" or "Retrieve memory context". LLM clients (Claude Desktop, Cursor) don't know when to invoke the tools autonomously.

**Prevention:** Write docstrings as agent instructions. Include: when to call ("BEFORE generating response"), what it does ("extracts and deduplicates facts via LLM"), and what it returns ("formatted context string ready to inject into system prompt"). FastMCP uses docstrings directly as the MCP `description` field.

---

### Pitfall 11: Not Marking Retrieve Tools as readOnlyHint

**What goes wrong:** Retrieve tools are presented without `readOnlyHint=True`. Some MCP clients gate tool calls differently based on read vs. write annotations; users may be prompted for confirmation on every retrieve call.

**Prevention:** Add `annotations={"readOnlyHint": True}` to all retrieve tool decorators. `store_*` tools do NOT get this annotation (they are write operations).

---

### Pitfall 12: Returning Complex Objects Instead of Strings

**What goes wrong:** A tool returns a `dict`, `RetrievalResult`, or `CoreMemoryUnit` object. FastMCP serializes it as JSON. The LLM receives a JSON blob it must parse rather than natural-language memory context.

**Prevention:** Always call `.to_prompt_string()` on `RetrievalResult` before returning. For store operations, return a human-readable summary (e.g., `"Stored 2 memories: [PREFERENCE] Prefers dark mode. [FACT] Lives in Berlin."`).

---

### Pitfall 13: Plain Text Wrapping Produces Poor Core Memory Extraction

**What goes wrong:** `CoreMemoryService.extract()` expects conversation messages with alternating `"user"` and `"assistant"` turns. Wrapping plain text as `[{"role": "user", "content": text}]` provides no `"assistant"` content, so the LLM may extract nothing meaningful for the persona field, silently returning `CoreMemoryUnit(persona_content="", human_content="")`.

**Why it happens:** The prompt was designed and tested against full conversation windows. A single unilateral message is a degenerate input for a conversational extraction prompt.

**Prevention:**
- Frame the text as a directive: `[{"role": "user", "content": f"Please record this fact about me: {text}"}]`.
- Or add a synthetic assistant acknowledgement: `[{"role": "user", "content": text}, {"role": "assistant", "content": "Understood, I will remember this."}]`.
- Test empirically: store a fact via `store_to_core`, then call `retrieve_core` and verify the fact appears in `human_content`.

**Detection:** `retrieve_core` returns empty content after multiple `store_to_core` calls.

---

## Minor Pitfalls

### Pitfall 14: State File Race Condition on Concurrent Write/Read

**What goes wrong:** Python's default `open(..., 'w') + json.dump()` truncates the file before writing, creating a window where the file is empty. A concurrent MCP server read during that window sees empty content and raises `json.JSONDecodeError`. On Windows (this project's development platform), this window is more observable than on Unix.

**Prevention:** CLI `set-block` writes atomically: write to a temp file in the same directory, then `os.replace(tmp_path, state_path)`. `os.replace()` is atomic on both platforms within the same filesystem volume. MCP server reads always wrap in `try/except json.JSONDecodeError`.

---

### Pitfall 15: State File Path Not Cross-Platform

**What goes wrong:** State file path hardcoded as a Unix string like `/home/user/.config/memblocks/active_block.json`. Fails on Windows.

**Prevention:** Use `pathlib.Path.home() / ".config" / "memblocks" / "active_block.json"` — works on all platforms.

---

### Pitfall 16: Forgetting to Call `await client.close()` on Shutdown

**What goes wrong:** MCP server process exits without closing MongoDB connections. May leave dangling Motor connections or incomplete writes.

**Prevention:** Call `await client.close()` in the `finally` block of the FastMCP `lifespan` context manager. `MemBlocksClient.close()` calls `await self.mongo.close()`.

---

### Pitfall 17: CLI `set-block` Accepts Invalid Block IDs

**What goes wrong:** User sets a block ID that doesn't exist. MCP server reads it, calls `client.get_block(bad_id)`, gets `None`, crashes with `AttributeError: 'NoneType' has no attribute 'retrieve'`.

**Prevention:** `set-block` CLI command validates the block ID against `client.get_user_blocks()` before writing to state file. MCP tool handlers also guard against `get_block()` returning `None`.

---

### Pitfall 18: `.env` File Path Relative to cwd — Breaks When MCP Client Launches Server from Different Directory

**What goes wrong:** `MemBlocksConfig` defaults to `env_file=".env"` (cwd-relative). Claude Desktop and Cursor launch the MCP server with a cwd that may not be the project root, so the `.env` file is not found and all API keys are `None`.

**Prevention:** Pass environment variables as real env vars in the MCP client's server configuration (Claude Desktop `env` block), not via `.env` file. Or set an absolute path: `MemBlocksConfig(_env_file="/absolute/path/.env")`.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| MCP server scaffolding | stdout corruption (Pitfall 1) | Zero `print()` calls; stderr-only logging; grep check |
| MCP server scaffolding | Client constructed per-request (Pitfall 3) | Lifespan pattern from day one; never in tool function |
| MCP server scaffolding | asyncio.run() in event loop (Pitfall 4) | Review: no `asyncio.run()` in any MCP file |
| MCP server scaffolding | SPLADE blocking first call (Pitfall 4) | Pre-warm `_get_sparse_embedder()` in lifespan |
| MCP server scaffolding | State file missing → crash (Pitfall 6) | Guard at top of every tool handler before wiring tools |
| Active block state | Caching state in memory (Pitfall 2) | Read file per call; test switching blocks mid-run |
| Active block state | Race condition on write (Pitfall 14) | Atomic `os.replace()` write in `set-block` command |
| Store tools | Using session pipeline (Pitfall 5) | Call service methods directly; no `MemoryPipeline.run()` |
| Store tools | Silent extraction failure (Pitfall 7) | Check empty-list return; return `stored: false` not `stored: true` |
| Store tools | Raw exceptions leaking (Pitfall 8) | All tools use `ToolError`; `mask_error_details=True` |
| Store tools | Plain text wrapping for core (Pitfall 13) | Test `retrieve_core` post-store; verify non-empty content |
| Retrieve tools | Complex object returned (Pitfall 12) | Always `.to_prompt_string()` on RetrievalResult |
| Retrieve tools | Missing readOnlyHint (Pitfall 11) | Add annotation to all retrieve decorators |
| All tools | Vague docstrings (Pitfall 10) | Review: "would an LLM know when to call this?" |
| CLI set-block | Invalid block ID stored (Pitfall 17) | Validate against user's block list before writing |

---

## "Looks Done But Isn't" Checklist

- [ ] **stdio logging**: Server starts — run MCP inspector and confirm no non-JSON bytes on stdout for any tool call
- [ ] **store_semantic success**: Tool returns success — verify memories appear in Qdrant by calling `retrieve_semantic` on same content
- [ ] **store_to_core success**: Tool returns success — verify `human_content` is non-empty via `retrieve_core`
- [ ] **no active block**: Delete state file, call any tool — must get `ToolError` with actionable message, not a crash
- [ ] **lifespan init**: Server starts — verify `MemBlocksClient` is NOT re-created on second tool call (time two calls)
- [ ] **SPLADE pre-warm**: First `store_semantic` completes in < 5s — verify SPLADE downloaded during lifespan, not on first tool call
- [ ] **stale block_id**: Put a deleted block ID in state file, call a tool — must get `ToolError`, not `AttributeError` on `None`
- [ ] **block switch**: Set block A, store, switch to B via CLI, store again — verify memories went to correct blocks
- [ ] **empty extraction**: Call `store_semantic` with "ok" (too short to extract) — verify `stored: false` not `stored: true`
- [ ] **env file path**: Launch server from a different cwd than project root — verify config loads correctly

---

## Sources

- FastMCP 3.1.0 official documentation: https://gofastmcp.com/servers/tools, /servers/lifespan, /servers/context, /servers/logging (HIGH confidence)
- MCP Protocol Specification — stdio transport: https://modelcontextprotocol.io/docs/concepts/transports — "The server MUST NOT write anything to its stdout that is not a valid MCP message." (HIGH confidence)
- MemBlocks codebase direct inspection:
  - `memblocks_lib/src/memblocks/client.py` — `MemBlocksClient.__init__()` construction cost (HIGH)
  - `memblocks_lib/src/memblocks/services/core_memory.py` — `extract()` graceful degradation on failure (HIGH)
  - `memblocks_lib/src/memblocks/services/semantic_memory.py` — `extract_and_store()` graceful degradation; synchronous blocking embedding (HIGH)
  - `memblocks_lib/src/memblocks/storage/embeddings.py` — synchronous `embed_documents()`, lazy SPLADE init (HIGH)
  - `memblocks_lib/src/memblocks/storage/mongo.py` — Motor `AsyncIOMotorClient` lazy connection (HIGH)
  - `backend/src/cli/main.py` — `print()` usage, `asyncio.run()` pattern, file logging (HIGH)
- FastMCP 3.1.0 verified installed in project environment (`fastmcp.__version__ == "3.1.0"`)
- MCP official docs — Tool annotations (`readOnlyHint`) (HIGH confidence)
- `.planning/PROJECT.md` — Shared state file decision, out-of-scope session pipeline (HIGH confidence)
