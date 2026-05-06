# Architecture Patterns

**Domain:** MCP Memory Server — agent-facing integration over existing memblocks library
**Researched:** 2026-03-12

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────┐
│                  MCP Client                         │
│  (Claude Desktop / Cursor / Cline / any MCP client) │
└──────────────────────┬──────────────────────────────┘
                       │ stdio (JSON-RPC)
┌──────────────────────▼──────────────────────────────┐
│              MCP Server (FastMCP)                   │
│                                                     │
│  Tools:                   Resources:                │
│  ├─ store_semantic         ├─ memblocks://active-block│
│  ├─ store_to_core          └─ memblocks://tools      │
│  ├─ store                                           │
│  ├─ retrieve                                        │
│  ├─ retrieve_core                                   │
│  ├─ retrieve_semantic                               │
│  ├─ memblocks_list_blocks                           │
│  └─ memblocks_create_block                          │
│                                                     │
│  Lazy client init: MemBlocksClient per-request      │
│  (or singleton with connection reuse)               │
└──────────────────────┬──────────────────────────────┘
                       │ Python function calls (async)
┌──────────────────────▼──────────────────────────────┐
│           memblocks library (v1.0)                  │
│                                                     │
│  MemBlocksClient                                    │
│  ├─ SemanticMemoryService.extract_and_store()       │
│  ├─ CoreMemoryService.update()                      │
│  ├─ Block.retrieve() / core_retrieve() / semantic_retrieve()│
│  ├─ BlockManager.get_user_blocks() / create_block() │
│  ├─ MongoDB (core memory, block metadata)           │
│  └─ Qdrant (semantic vector store)                  │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              Shared State File                      │
│  ~/.config/memblocks/active_block.json              │
│  { "block_id": "...", "name": "...", "user_id": ... }│
│                                                     │
│  Written by: CLI `set-block` command                │
│  Read by:    MCP server on every tool call          │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│              CLI (existing + new commands)           │
│  memblocks set-block <block_id>   → writes state    │
│  memblocks get-block              → reads state     │
│  memblocks list-blocks            → calls client    │
└─────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| FastMCP server (`mcp/server.py`) | Exposes tools/resources; handles MCP protocol; reads active block state | MCP client (stdio), `MemBlocksClient`, shared state file |
| Shared state file (`active_block.json`) | Single source of truth for active block selection | Written by CLI; read by MCP server |
| `MemBlocksClient` | All memory I/O (extract, store, retrieve, block management) | MongoDB, Qdrant, LLM providers |
| CLI new commands (`set-block`, `get-block`) | Human-controlled block switching; writes state file | Shared state file, existing `MemBlocksClient` |

---

## Patterns to Follow

### Pattern 1: Lazy / Singleton Client Initialization

**What:** Create `MemBlocksClient` once at server startup (not per-request), but initialize lazily (on first tool call) to avoid blocking startup.

**When:** Always — `MemBlocksClient.__init__` connects to MongoDB and Qdrant; doing this per-request would be too slow and exhaust connection pools.

**Example:**
```python
_client: Optional[MemBlocksClient] = None

async def get_client() -> MemBlocksClient:
    global _client
    if _client is None:
        config = MemBlocksConfig()
        _client = MemBlocksClient(config)
        await _client.get_or_create_user(USER_ID)
    return _client
```

### Pattern 2: Read Active Block State Per-Request

**What:** Read the shared JSON state file on every tool call (not cached in memory).

**When:** Always — the CLI may change the active block between tool calls; stale in-memory state would cause tools to operate on the wrong block.

**Example:**
```python
def get_active_block_id() -> str:
    state_path = Path.home() / ".config" / "memblocks" / "active_block.json"
    if not state_path.exists():
        raise McpError("No active block set. Run: memblocks set-block <block_id>")
    data = json.loads(state_path.read_text())
    return data["block_id"]
```

### Pattern 3: Wrap Plain Text as Message List

**What:** MCP tools accept plain `text: str`; the library expects `List[Dict[str, str]]`. Wrap inline.

**When:** All store tools.

**Example:**
```python
messages = [{"role": "user", "content": text}]
await semantic_service.extract_and_store(messages)
```

### Pattern 4: Descriptive Tool Docstrings (Agent Instructions)

**What:** Tool docstrings are the descriptions the LLM sees. Write them as behavioral instructions, not API docs.

**Why:** This is what determines WHEN the agent calls the tool. Without clear "when to call" language, agents under-use memory tools.

**Example:**
```python
@mcp.tool(annotations={"readOnlyHint": True})
async def retrieve(query: str) -> str:
    """
    Retrieve memory from the active MemBlocks block relevant to the query.

    Call this BEFORE generating any response to ground your answer in stored memory.
    Returns formatted core facts and semantically similar memories.
    """
```

### Pattern 5: Return Strings (Not Dicts) from Tools

**What:** MCP tools should return `str`. `RetrievalResult.to_prompt_string()` already provides the formatted string.

**Why:** LLM clients inject tool results into the conversation as text. A plain string is the correct type.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Per-Request Client Construction

**What:** Creating `MemBlocksClient(config)` inside each tool handler.

**Why bad:** Reconnects to MongoDB and Qdrant on every call; each LLM provider is reconstructed; connection pool exhaustion; 1-3 second latency per tool call.

**Instead:** Singleton client initialized once at startup (see Pattern 1).

### Anti-Pattern 2: Caching Active Block State In-Memory

**What:** Reading `active_block.json` once at startup and caching in a global variable.

**Why bad:** CLI `set-block` changes the file while the MCP server is running; cached state becomes stale; tools operate on the wrong block.

**Instead:** Read the file on every tool call (Pattern 2). File reads are cheap (~1ms).

### Anti-Pattern 3: Calling `MemoryPipeline.run()` or `session.add()`

**What:** Routing MCP store calls through the full session/memory pipeline.

**Why bad:** Session pipeline expects full conversations, maintains memory windows, runs recursive summaries — all unnecessary overhead when an agent is pushing a single extracted fact.

**Instead:** Call `SemanticMemoryService.extract_and_store()` and `CoreMemoryService.update()` directly (bypasses session layer entirely).

### Anti-Pattern 4: Vague Tool Descriptions

**What:** Docstrings like "Store memory" or "Retrieve memory".

**Why bad:** LLMs don't know when to call the tool, so they rarely do.

**Instead:** Include "Call this BEFORE generating responses" or "Call this AFTER the user shares a preference" (Pattern 4).

---

## Data Flow: Store Path

```
Agent calls store_semantic("User prefers Python over JS")
    → MCP server reads active_block.json → block_id
    → get_client() → MemBlocksClient singleton
    → client.get_block(block_id) → Block object
    → Wrap: messages = [{"role": "user", "content": text}]
    → block._semantic.extract_and_store(messages)
        → PS1: LLM extracts structured SemanticMemoryUnit
        → PS2: Vector similarity check + conflict resolution (ADD/UPDATE/DELETE)
        → Qdrant upsert
    → Return: "Stored 1 memory: [PREFERENCE] User prefers Python over JS"
```

## Data Flow: Retrieve Path

```
Agent calls retrieve("What languages does the user prefer?")
    → MCP server reads active_block.json → block_id
    → get_client() → MemBlocksClient singleton
    → client.get_block(block_id) → Block object
    → block.retrieve(query)
        → Core memory: MongoDB fetch (always full)
        → Semantic memory: query expansion + HyDE + hybrid vector search + Cohere reranking
        → RetrievalResult assembled
    → result.to_prompt_string()
    → Return: "<Core Memory>...<Semantic Memories>..."
```

---

## Scalability Considerations

This is a local single-user server — scalability is not a concern for v1.1. The architecture naturally constrains scope:

| Concern | Current (single user, stdio) | Future (if multi-user/HTTP) |
|---------|------------------------------|------------------------------|
| Client connections | 1 singleton | Connection pool per user |
| Active block state | JSON file | DB-backed per-user state |
| Transport | stdio | HTTP with auth |

All of these are explicit out-of-scope decisions for v1.1.

---

## Sources

- `memblocks_lib/src/memblocks/client.py` — Client initialization and API surface (HIGH confidence)
- `memblocks_lib/src/memblocks/services/block.py` — Block retrieval methods (HIGH confidence)
- `memblocks_lib/src/memblocks/services/semantic_memory.py` — extract_and_store pipeline (HIGH confidence)
- `memblocks_lib/src/memblocks/services/core_memory.py` — update pipeline (HIGH confidence)
- `.planning/PROJECT.md` — Shared state file decision, constraints, out-of-scope items (HIGH confidence)
- mem0/OpenMemory MCP server — Lazy initialization and per-request patterns (MEDIUM confidence)
- FastMCP official docs — Tool/resource decorator patterns (HIGH confidence)
