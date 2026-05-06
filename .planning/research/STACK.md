# Technology Stack

**Project:** MemBlocks MCP Server (v1.1 milestone)
**Researched:** 2026-03-12

---

## Recommended Stack

### MCP Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| FastMCP (Python MCP SDK) | Latest stable | MCP server framework | Official Python SDK; `@mcp.tool`, `@mcp.resource`, `@mcp.prompt` decorators auto-generate JSON schemas from function signatures + docstrings; minimal boilerplate; stdio transport built-in |

### Core Library (Existing — do not duplicate)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `memblocks` (local package) | v1.0 (existing) | All memory operations | Already built; `MemBlocksClient` is the single entry point; all store/retrieve paths are implemented |
| Python asyncio | stdlib | Async runtime | FastMCP is async-native; all `MemBlocksClient` methods are `async` |

### Transport

| Technology | Purpose | Why |
|------------|---------|-----|
| stdio (MCP standard) | IPC between MCP client and server | Works out-of-the-box with Claude Desktop, Cursor, Cline, and all major local MCP clients; no network config; no auth surface |

### State Sharing

| Technology | Purpose | Why |
|------------|---------|-----|
| JSON file on disk | Shared active block state between CLI and MCP server | Simple; no IPC complexity; CLI writes on `set-block`; MCP reads on every tool call; survives process restarts |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| MCP framework | FastMCP | Raw `mcp` SDK (low-level) | FastMCP is the official high-level wrapper; schema auto-generation from docstrings eliminates all boilerplate |
| Transport | stdio | HTTP (SSE / Streamable HTTP) | stdio is sufficient for local agent clients; HTTP adds deployment complexity and an auth surface |
| State sharing | JSON file | Redis / SQLite | No additional infrastructure needed; two-process coordination is trivially served by a file |
| State sharing | JSON file | Environment variable | Cannot be changed at runtime by CLI without restarting the MCP server |
| State sharing | JSON file | In-memory singleton | MCP server is a separate process from CLI; in-memory state is not shared |

---

## Installation

```bash
# Install FastMCP
pip install fastmcp

# The memblocks library is already installed as an editable package
pip install -e memblocks_lib/
```

No new language runtimes required — Python only.

---

## Key FastMCP Patterns (HIGH confidence)

```python
from fastmcp import FastMCP
from fastmcp.tools import Tool

mcp = FastMCP("MemBlocks")

@mcp.tool(annotations={"readOnlyHint": True})
async def retrieve(query: str) -> str:
    """
    Retrieve memory relevant to query from the active block.
    Call this BEFORE generating any response to ground answers in memory.
    """
    ...

@mcp.tool()
async def store_semantic(text: str) -> str:
    """
    Extract and store semantic memories from text into the active block.
    Call this AFTER a conversation turn when the user shares important facts.
    """
    ...

@mcp.resource("memblocks://active-block")
async def active_block_resource() -> str:
    """Returns the currently active memory block name and ID."""
    ...

# Run with stdio transport (default for local integrations)
mcp.run()
```

- Tool docstrings become the tool descriptions exposed to the LLM — write them as agent instructions ("Call this BEFORE…", "Call this AFTER…")
- `readOnlyHint=True` signals to MCP clients that the tool has no side effects
- Schema is auto-generated from Python type annotations — no JSON Schema writing needed
- `mcp.run()` defaults to stdio transport; no config required

---

## Sources

- `.planning/PROJECT.md` — Stack decisions and constraints (HIGH confidence, direct read)
- FastMCP official documentation — HIGH confidence (fetched in session)
- MCP official specification (transport, primitives) — HIGH confidence (fetched in session)
