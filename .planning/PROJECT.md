# MemBlocks

## What This Is

MemBlocks is a modular memory management platform where AI agents and users manage multiple independent memory blocks, each with layered memory types (core, semantic, resources), and now a shipped MCP server interface for agent-native memory operations.

## Core Value

Any AI agent connected to MemBlocks can store and retrieve the right memory from the right block at the right time, with conflict resolution and source transparency.

## Current Milestone: v1.3 Evaluation Framework Rework

**Goal:** Completely overhaul the evaluation methods to be modular, simplified (fewer flags), and focused on memory retrieval accuracy using the LoCoMo long-term conversational memory benchmark.

**Target features:**
- Modularize the `evaluation/` directory architecture
- Remove complex and confusing CLI flags in favor of clean configuration/execution
- Integrate the `locomo-mc10` dataset for evaluating memory retrieval
- Implement metrics for single-hop, multi-hop, temporal, open-domain, and adversarial reasoning

## Current State

- **Shipped milestone:** v1.1 MCP Server (2026-03-19)
- **Delivered surface area:** MCP stdio server, block management tools, store tools (semantic/core/combined), retrieve tools (semantic/core/combined), CLI block switching, MCP resources
- **Codebase status:** Foundation + v1.1 MCP integration complete; v1.2 Final Report is tracked separately; ready to define v1.3 Evaluation requirements.

## Next Milestone Goals

- Clean up the `evaluation/` directory
- Establish baseline accuracy on LoCoMo MC10
- Evaluate different memory retrieval strategies (core vs semantic vs hybrid)

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Core memory extraction from conversation via LLM — v1.0 (existing)
- ✓ Semantic memory extraction (PS1) + conflict resolution (PS2) — v1.0 (existing)
- ✓ Hybrid vector search (dense + SPLADE) with query expansion, HyDE, and Cohere reranking — v1.0 (existing)
- ✓ Block management (create, list, retrieve by user) — v1.0 (existing)
- ✓ Session-based chat loop with memory window + recursive summary — v1.0 (existing)
- ✓ FastAPI REST backend with Clerk auth — v1.0 (existing)
- ✓ React frontend (workspace + chat interface) — v1.0 (existing)
- ✓ CLI for interactive memory chat — v1.0 (existing)
- ✓ Multi-provider LLM support (Groq, Gemini, OpenRouter) — v1.0 (existing)
- ✓ Transparency layer (event bus, operation log, retrieval log, LLM usage tracking) — v1.0 (existing)
- ✓ MCP server exposing MemBlocks memory via stdio Model Context Protocol — v1.1
- ✓ MCP block management tools (`memblocks_list_blocks`, `memblocks_create_block`) — v1.1
- ✓ MCP store tools (`memblocks_store_semantic`, `memblocks_store_to_core`, `memblocks_store`) — v1.1
- ✓ MCP retrieve tools (`memblocks_retrieve`, `memblocks_retrieve_core`, `memblocks_retrieve_semantic`) — v1.1
- ✓ MCP resources (`memblocks://active-block`, `memblocks://tools`) — v1.1
- ✓ CLI active block commands (`memblocks-cli set-block`, `memblocks-cli get-block`) — v1.1

### Active

<!-- Current scope. Building toward these. -->

- [ ] Modularize evaluation methods and remove confusing flags
- [ ] Implement LoCoMo dataset integration for multiple-choice QA evaluation
- [ ] Track retrieval accuracy and reasoning performance (not just token counts)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Training/Fine-tuning models — We are only evaluating the memory retrieval performance of existing agents
- v1.2 Final Report tasks — Deferred to focus solely on the evaluation framework rework

## Context

- **Existing library**: `memblocks_lib/src/memblocks/` — full Python library with `MemBlocksClient` as the single entry point
- **Existing CLI**: `backend/src/cli/main.py` — interactive chat loop using the library; demonstrates how to initialize client, select blocks, and run the memory pipeline
- **Key services**: `SemanticMemoryService.extract_and_store()` and `CoreMemoryService.update()` are the core store paths
- **Key gap**: Current `extract()` and `update()` expect `List[Dict[str, str]]` (role/content messages); MCP will wrap plain text as `[{"role": "user", "content": text}]`
- **Active block state**: Shared JSON state file on disk; CLI writes it, MCP server reads it per request
- **Stack**: Python, FastMCP (MCP Python SDK), stdio transport
- **Report baseline source**: `docs/project_report/MemBlocks_Proposal_Defense/main.tex`
- **Target structure source**: `docs/project_report/recommedned_format/main.tex`
- **Milestone writing constraint**: change only what drifted from reality, then extend to cover missing final-report sections

## Constraints

- **Tech stack**: Python — must use the existing `memblocks` library; no new language runtimes
- **MCP framework**: FastMCP (Python MCP SDK) — standard, well-documented, compatible with all major MCP clients
- **Single user**: MCP server is single-user; user_id configured via env var or config
- **No session pipeline**: MCP tools bypass session/memory_window/MemoryPipeline.run() entirely

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Plain text input wrapped as `[{"role": "user", "content": text}]` | Minimal change to existing LLM pipelines; extract() and update() already handle single-message inputs | ✓ Good (v1.1) |
| Shared state file for active block | Simple, robust, no IPC complexity; CLI and MCP server are separate processes | ✓ Good (v1.1) |
| stdio transport | Standard for local MCP integrations; works with Claude Desktop, Cursor, and most MCP clients out of the box | ✓ Good (v1.1) |
| FastMCP framework | Official Python SDK; auto-generates schemas from docstrings; minimal boilerplate | ✓ Good (v1.1) |
| CLI entry point name `memblocks-cli` | Avoids import conflict with existing `memblocks` package namespace | ✓ Good (v1.1) |

## Previous Snapshot

<details>
<summary>Pre-v1.1 planning snapshot</summary>

The earlier version of this file tracked v1.1 MCP Server as active, with MCP capabilities listed under Active requirements before shipment.

</details>

---
*Last updated: 2026-05-05 after starting v1.3 milestone planning*
