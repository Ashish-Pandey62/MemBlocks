# Research Summary: MemBlocks MCP Server

**Domain:** MCP Memory Server — agent-facing integration over existing Python library
**Researched:** 2026-03-12
**Overall confidence:** HIGH

---

## Executive Summary

MemBlocks v1.1 adds an MCP server that exposes the existing `memblocks` library to AI agents (Claude Desktop, Cursor, Cline, etc.) via the Model Context Protocol. The MCP server is a thin FastMCP layer — it does NOT contain business logic; all memory operations are delegated to the already-built `MemBlocksClient`.

The core insight for implementation is that MCP agents push distilled facts rather than full conversations. This means the MCP server bypasses the session/memory pipeline entirely and calls `SemanticMemoryService.extract_and_store()` and `CoreMemoryService.update()` directly. Plain text input from agents is wrapped as `[{"role": "user", "content": text}]` inline — a one-liner that requires no changes to the existing library.

Active block state (which block an agent is currently operating on) is managed via a shared JSON file on disk. The CLI writes it; the MCP server reads it on every tool call. This two-process design requires reading the file per-request (not caching) to avoid operating on the wrong block after a user switches contexts.

The technology choice is straightforward and locked: FastMCP (official Python MCP SDK), stdio transport, single user configured via environment variable. All alternatives were explicitly ruled out in PROJECT.md for good reasons (simplicity, compatibility, no new runtimes).

---

## Key Findings

**Stack:** FastMCP + existing `memblocks` library + stdio transport + shared JSON state file — no new infrastructure.

**Architecture:** Thin MCP facade over `MemBlocksClient`; singleton client; per-request state file read; direct service calls bypassing session pipeline.

**Critical pitfall:** Caching active block state in-memory — silently operates on the wrong block after CLI switches context. Read the file on every tool call.

---

## Implications for Roadmap

Based on research, suggested phase structure:

1. **MCP Server Foundation** — FastMCP server scaffold, singleton `MemBlocksClient`, shared state file read/write, active block management, `memblocks_list_blocks`, `memblocks_create_block`
   - Addresses: client init, block scaffolding tools, state file infrastructure
   - Avoids: per-request client construction (Pitfall 2), missing state guard (Pitfall 4)

2. **Store Tools** — `store_semantic`, `store_to_core`, `store` (combined)
   - Addresses: all write paths; PS1+PS2 extraction pipeline wired to MCP
   - Avoids: session pipeline routing (Pitfall 3), missing block guard (Pitfall 4)
   - Depends on: Phase 1 (active block state + singleton client)

3. **Retrieve Tools** — `retrieve`, `retrieve_core`, `retrieve_semantic`
   - Addresses: all read paths; `readOnlyHint` annotations; string return via `.to_prompt_string()`
   - Avoids: returning complex objects (Pitfall 7), missing `readOnlyHint` (Pitfall 6)
   - Depends on: Phase 1 (active block state + singleton client)

4. **Resources + CLI Commands** — `memblocks://active-block`, `memblocks://tools` resources; `set-block`, `get-block` CLI commands
   - Addresses: agent-visible context; human-controlled block switching
   - Avoids: invalid block ID stored in state (Pitfall 11)
   - Depends on: Phases 1-3 (all tools must exist before documenting them in resources)

**Phase ordering rationale:**
- Foundation first (Phase 1): all other tools depend on client init and state file
- Store before retrieve (Phase 2 before 3): no value in reading what hasn't been stored yet, but either order technically works
- Resources last (Phase 4): tool usage docs reference all tools by name; write them after tools are finalized

**Research flags for phases:**
- Phase 1: Standard FastMCP patterns — unlikely to need additional research
- Phase 2: `extract_and_store()` is well-understood from code read — no research needed
- Phase 3: `Block.retrieve()` pipeline is well-understood — no research needed
- Phase 4: FastMCP resource patterns are documented — may need quick verification of `@mcp.resource` URI format

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Locked decisions in PROJECT.md; FastMCP docs verified |
| Features | HIGH | All tool signatures derived from direct library code reads |
| Architecture | HIGH | Data flow traced through actual service code; state file pattern is simple |
| Pitfalls | HIGH | Critical pitfalls derived from architectural analysis; moderate pitfalls from MCP patterns |

---

## Gaps to Address

- **FastMCP `@mcp.resource` URI format**: Verify exact syntax for parameterized vs. static resource URIs before Phase 4. The `memblocks://active-block` pattern is standard but worth a quick doc check.
- **`client.close()` in FastMCP shutdown**: Verify FastMCP exposes a lifecycle hook for graceful shutdown. If not, the MongoDB connection will be abandoned (minor, not critical for local use).
- **State file location convention**: The path `~/.config/memblocks/active_block.json` is proposed but not yet defined. Decide and document it in Phase 1; both CLI and MCP server must agree on the path.
