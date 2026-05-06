# MILESTONES.md
## v1.1 MCP Server (Shipped: 2026-03-19)

**Phases completed:** 5 tracks (1, 2.01, 2.02, 3, 4), 7 plans, 15 tasks
**Git range:** `ba64bcc^..118b3d5`
**Diff:** 41 files changed, +5001 / -68
**Timeline:** 2026-03-12 -> 2026-03-14

**Key accomplishments:**
- Shipped FastMCP stdio server foundation with active-block state and block management tools.
- Added full store path: semantic-only, core-only, and combined `memblocks_store`.
- Added full retrieve path: combined, core-only, and semantic-only tools with LLM-ready formatting.
- Delivered CLI block switching via `memblocks-cli set-block` and `memblocks-cli get-block`.
- Added MCP resources `memblocks://active-block` and `memblocks://tools` for zero-tool-call context.
- Closed Phase 4 runtime gap by fixing `memblocks-cli` path behavior.

### Known Gaps (Accepted)

- `STOR-01`: Left unchecked in the live v1.1 requirements file at closeout, despite implementation evidence in phase summaries.
- `STOR-02`: Left unchecked in the live v1.1 requirements file at closeout, despite implementation evidence in phase summaries.

---


## v1.0 — Foundation (Existing)

**Status:** Shipped (existing codebase, pre-GSD)
**Last Phase:** 0 (no GSD phases — code predates milestone tracking)

### What Shipped

- Full `memblocks` Python library with `MemBlocksClient` entry point
- Core memory service: LLM extraction, MongoDB persistence, full retrieval
- Semantic memory service: PS1 extraction, PS2 conflict resolution, hybrid vector search (dense + SPLADE), query expansion, HyDE, Cohere reranking
- Block management: create, list, get by user
- Session management: memory window, recursive summary, MemoryPipeline
- FastAPI REST backend with Clerk authentication
- React frontend (landing + workspace with chat, memory viewer, block manager, analytics)
- CLI: interactive memory chat loop
- Multi-provider LLM support: Groq, Gemini, OpenRouter
- Transparency layer: EventBus, OperationLog, RetrievalLog, ProcessingHistory, LLMUsageTracker

---

*Milestone log initialized: 2026-03-12*
