# Feature Landscape

**Domain:** MCP Memory Server (agent-facing memory integration)
**Researched:** 2026-03-12

---

## Table Stakes

Features an MCP memory server must have. Missing = agents cannot use it meaningfully.

| Feature | Why Expected | Complexity | Library Dependency |
|---------|--------------|------------|--------------------|
| `store_semantic` — store text to semantic memory | Agents need to persist extracted facts | Medium | `SemanticMemoryService.extract_and_store(messages)` — wrap plain text as `[{"role": "user", "content": text}]` |
| `store_to_core` — store text to core memory | Agents need to persist stable/persona facts | Medium | `CoreMemoryService.update(block_id, messages)` — same wrapping |
| `store` — combined store (core + semantic) | Convenience for "remember this" calls | Low | Both of the above, run concurrently |
| `retrieve` — combined retrieve (core + semantic) | Primary memory read path before generating responses | Medium | `Block.retrieve(query)` → `RetrievalResult.to_prompt_string()` |
| `retrieve_core` — retrieve full core memory | Agents need stable facts without a query | Low | `Block.core_retrieve()` → `RetrievalResult.to_prompt_string()` |
| `retrieve_semantic` — vector search only | Targeted semantic search by agents | Low | `Block.semantic_retrieve(query)` → `RetrievalResult.to_prompt_string()` |
| `memblocks_list_blocks` — list user's blocks | Agents and CLI need to see available contexts | Low | `client.get_user_blocks(user_id)` |
| `memblocks_create_block` — create a new block | Agents or users need to scaffold new memory contexts | Low | `client.create_block(user_id, name)` |
| Active block state (shared JSON file) | MCP tools need to know which block to operate on | Low | CLI writes, MCP reads per-request — no IPC needed |
| `memblocks://tools` resource — tool usage docs | LLM clients (Claude Desktop) surface these as context | Low | Static text, auto-served via FastMCP `@mcp.resource` |

---

## Differentiators

Features that make this MCP server notably better than a minimal memory integration.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| LLM-powered PS1+PS2 extraction on store | Facts are structured, deduplicated, and conflict-resolved automatically — not just appended | Already built | `extract_and_store()` does the full pipeline internally |
| Hybrid vector search (dense + SPLADE) + HyDE + reranking on retrieve | Retrieve quality is dramatically better than cosine-only search | Already built | `Block.retrieve()` uses the full enhanced pipeline |
| Layered memory (core vs. semantic) exposed as distinct tools | Agents can precisely target fast facts (core) or searched knowledge (semantic) | Low | Distinct `retrieve_core` and `retrieve_semantic` tools |
| `memblocks://active-block` resource | Exposes active block metadata as always-available context for the LLM | Low | Reads shared state file; served via `@mcp.resource` |
| Tool description prompting ("call BEFORE generating response") | Critical for agents to know WHEN to invoke retrieve vs. store tools | Zero code | All in docstrings — FastMCP auto-generates schemas from them |
| CLI commands for active block management | Human user can switch block context; MCP server picks it up on next call | Low | `set-block`, `get-block` CLI commands write/read shared JSON |

---

## Anti-Features

Features to explicitly NOT build in this milestone.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Session / memory window / `MemoryPipeline.run()` | Agents push only distilled facts, not full conversations; pipeline is for the CLI chat loop | Wrap plain text directly as `[{"role": "user", "content": text}]` |
| OAuth / multi-user MCP | Adds massive surface area; single configured user (env var) is sufficient for personal/local use | `user_id` from env var at server startup |
| HTTP transport | stdio works with all local MCP clients (Claude Desktop, Cursor, Cline); HTTP adds deployment complexity | stdio only |
| Resource memory (document/PDF) tools | `resource_retrieve()` is a stub that always returns empty; exposing it creates a misleading tool | Defer to v1.2 when resource memory is implemented |
| Delete memory tools | Dangerous in autonomous agent context; no audit trail in scope; premature | No delete tools in MCP scope |
| Block switching via MCP tool (agent-controlled) | Agents shouldn't autonomously switch memory context; human controls this via CLI | CLI-only block switching |
| Streaming responses | MCP stdio is request/response; streaming adds complexity with no benefit for memory ops | Standard async return values |

---

## Feature Dependencies

```
Active block state (shared JSON)
    → store_semantic
    → store_to_core
    → store (combined)
    → retrieve
    → retrieve_core
    → retrieve_semantic

MemBlocksClient initialization (user_id via env var)
    → memblocks_list_blocks
    → memblocks_create_block
    → Active block state → all store/retrieve tools

CLI active block commands
    → set-block (write shared JSON)
    → get-block (read shared JSON)
    → Active block state consumed by MCP server
```

---

## Tool Input / Output Contract (per tool)

| Tool | Input | Output | Library Call |
|------|-------|--------|--------------|
| `store_semantic` | `text: str` | `str` — summary of ops (ADD/UPDATE) | `SemanticMemoryService.extract_and_store([{"role":"user","content":text}])` |
| `store_to_core` | `text: str` | `str` — updated core memory summary | `CoreMemoryService.update(block_id, [{"role":"user","content":text}])` |
| `store` | `text: str` | `str` — combined summary | Both above, concurrent |
| `retrieve` | `query: str` | `str` — `RetrievalResult.to_prompt_string()` | `Block.retrieve(query)` |
| `retrieve_core` | _(none)_ | `str` — `RetrievalResult.to_prompt_string()` | `Block.core_retrieve()` |
| `retrieve_semantic` | `query: str` | `str` — `RetrievalResult.to_prompt_string()` | `Block.semantic_retrieve(query)` |
| `memblocks_list_blocks` | _(none)_ | `str` — formatted list of blocks | `client.get_user_blocks(user_id)` |
| `memblocks_create_block` | `name: str`, `description: str = ""` | `str` — new block id + name | `client.create_block(user_id, name, description)` |

---

## MCP Resources

| Resource URI | Content | FastMCP decorator |
|-------------|---------|-------------------|
| `memblocks://active-block` | Active block name, ID, and description from shared state file | `@mcp.resource("memblocks://active-block")` |
| `memblocks://tools` | Plain-text usage guide: when to call each tool | `@mcp.resource("memblocks://tools")` |

---

## MVP Recommendation

Prioritize (in order):

1. **Active block state** — shared JSON file; required by all other tools
2. **`retrieve`** — primary read path; most critical for agent usefulness
3. **`store_semantic`** — PS1+PS2 extraction; primary write path
4. **`store_to_core`** — stable fact persistence
5. **`store`** — convenience wrapper (trivial after above)
6. **`retrieve_core` / `retrieve_semantic`** — targeted variants (trivial after retrieve)
7. **`memblocks_list_blocks` / `memblocks_create_block`** — scaffolding tools
8. **Resources** (`memblocks://active-block`, `memblocks://tools`) — polish
9. **CLI `set-block` / `get-block` commands** — enables block switching

Defer:
- Resource memory tools — stub returns empty; defer to v1.2
- Delete tools — out of scope
- HTTP transport — out of scope

---

## Sources

- `memblocks_lib/src/memblocks/client.py` — `MemBlocksClient` API surface (HIGH confidence, direct code read)
- `memblocks_lib/src/memblocks/services/block.py` — `Block.retrieve()`, `core_retrieve()`, `semantic_retrieve()` (HIGH confidence)
- `memblocks_lib/src/memblocks/services/semantic_memory.py` — `extract_and_store()`, `extract()`, `store()` (HIGH confidence)
- `memblocks_lib/src/memblocks/services/core_memory.py` — `update()`, `extract()`, `save()`, `get()` (HIGH confidence)
- `memblocks_lib/src/memblocks/models/retrieval.py` — `RetrievalResult.to_prompt_string()` format (HIGH confidence)
- `.planning/PROJECT.md` — Active scope, out-of-scope decisions, constraints (HIGH confidence)
- MCP official docs (tools, resources, prompts primitives) — MEDIUM confidence (fetched earlier in session)
- mem0/OpenMemory MCP server reference implementation — MEDIUM confidence (pattern reference)
