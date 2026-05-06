# Architecture

**Analysis Date:** 2026-05-04

## Pattern Overview

**Overall:** Layered Service-Oriented Architecture with Dependency Injection

**Key Characteristics:**
- Single entry point (`MemBlocksClient`) wiring all dependencies together
- Pluggable LLM providers with task-specific configurations
- Dual storage strategy (MongoDB for documents, Qdrant for vector search)
- Transparency layer for observability (logging, metrics, tracing)
- Async-first design throughout

## Layers

**Client Layer:**
- Purpose: Single entry point for the memBlocks library
- Location: `memblocks_lib/src/memblocks/client.py`
- Contains: `MemBlocksClient` class
- Depends on: Config, storage adapters, LLM providers, services
- Used by: MCP server, backend API, CLI tools

**Service Layer:**
- Purpose: Core business logic for memory management
- Location: `memblocks_lib/src/memblocks/services/`
- Contains:
  - `BlockManager` - Create, retrieve, delete memory blocks
  - `SessionManager` - Manage conversation sessions within blocks
  - `UserManager` - User lifecycle management
  - `CoreMemoryService` - Persona and human facts storage
  - `SemanticMemoryService` - Vector-searchable memory storage
- Depends on: Storage adapters, LLM providers
- Used by: Client, transparency services

**Storage Layer:**
- Purpose: Persistence abstraction for documents and vectors
- Location: `memblocks_lib/src/memblocks/storage/`
- Contains:
  - `MongoDBAdapter` - Document storage (blocks, sessions, users, core memory)
  - `QdrantAdapter` - Vector storage (semantic memories)
  - `EmbeddingProvider` - Text-to-vector conversion
- Depends on: Configuration
- Used by: Service layer

**LLM Layer:**
- Purpose: Pluggable LLM integration with task-specific configurations
- Location: `memblocks_lib/src/memblocks/llm/`
- Contains:
  - `LLMProvider` (base class)
  - `GroqLLMProvider`, `GeminiLLMProvider`, `OllamaLLMProvider`, `OpenRouterLLMProvider`
- Depends on: API keys, task settings
- Used by: Service layer for extraction, retrieval, summarization

**Transparency Layer:**
- Purpose: Observability and auditability
- Location: `memblocks_lib/src/memblocks/services/transparency.py`
- Contains: `EventBus`, `LLMUsageTracker`, `OperationLog`, `RetrievalLog`, `ProcessingHistory`
- Depends on: Service operations
- Used by: Client for external monitoring

**API Layer (Backend):**
- Purpose: REST API for web client
- Location: `backend/src/api/`
- Contains: FastAPI application with routers (`auth`, `users`, `blocks`, `chat`, `memory`, `transparency`)
- Depends on: MemBlocksClient, Pydantic models
- Used by: Frontend

**MCP Server Layer:**
- Purpose: Expose memory tools to AI agents via Model Context Protocol
- Location: `mcp_server/server.py`
- Contains: FastMCP server with tools (`memblocks_store`, `memblocks_retrieve`, etc.)
- Depends on: MemBlocksClient, state management
- Used by: AI agents and coding assistants

## Data Flow

**Memory Storage Flow:**

1. User calls `client.create_block()` or `client.get_block()`
2. BlockManager creates MongoDB document + Qdrant collection(s)
3. Returns stateful `Block` object with retrieval methods
4. Agent calls `block.retrieve(query)` or `block._semantic.extract_and_store(messages)`

**Memory Retrieval Flow:**

1. Agent calls `memblocks_retrieve` with query
2. Block.retrieve() fetches core memory (full) + semantic memories (vector search) concurrently
3. Results combined into `RetrievalResult`
4. `to_prompt_string()` formats for LLM injection

**Session Flow:**

1. `client.create_session(user_id, block_id)` creates session
2. Session provides `get_memory_window()`, `get_recursive_summary()`, `add()`
3. User adds messages, session manages rolling summary and message history

## Key Abstractions

**MemBlocksClient:**
- Purpose: Single entry point wiring all dependencies
- Examples: `memblocks_lib/src/memblocks/client.py`
- Pattern: Factory pattern for LLM providers, dependency injection for services

**Block:**
- Purpose: Stateful handle to memory block with retrieval methods
- Examples: `memblocks_lib/src/memblocks/services/block.py`
- Pattern: Active Record pattern combining data + behavior

**Session:**
- Purpose: Stateful handle to conversation session
- Examples: `memblocks_lib/src/memblocks/services/session.py`
- Pattern: Active Record pattern

**LLMProvider:**
- Purpose: Pluggable LLM interface
- Examples: `memblocks_lib/src/memblocks/llm/base.py`
- Pattern: Strategy pattern with task-specific configurations

**RetrievalResult:**
- Purpose: Combined retrieval result container
- Examples: `memblocks_lib/src/memblocks/models/retrieval.py`
- Pattern: Data Transfer Object (DTO)

## Entry Points

**Library Entry:**
- Location: `memblocks_lib/src/memblocks/client.py`
- Triggers: Direct import and instantiation
- Responsibilities: Wire dependencies, expose public API

**MCP Server Entry:**
- Location: `mcp_server/server.py:1026` (main function)
- Triggers: CLI invocation (`memblocks-mcp` or Python module)
- Responsibilities: Parse args, configure transport, start FastMCP

**Backend API Entry:**
- Location: `backend/src/api/main.py:105` (app)
- Triggers: Uvicorn run or import
- Responsibilities: FastAPI factory, router registration, CORS

**Frontend Entry:**
- Location: `frontend/src/main.jsx`
- Triggers: Vite dev server or build
- Responsibilities: React app mount, router setup

## Error Handling

**Strategy:** Async exception propagation with tool error wrapping

**Patterns:**
- MCP tools raise `ToolError` for user-facing errors
- Async exceptions logged and optionally dispatched to background
- Storage errors propagate as is (connection failures, validation errors)
- LLM errors wrapped with context (provider, model, task type)

## Cross-Cutting Concerns

**Logging:** Centralized to stderr + file (`memblocks_mcp_logs/`), per-component loggers

**Validation:** Pydantic models for all tool inputs (`mcp_server/server.py`)

**Authentication:** Token-based in backend (`backend/src/api/routers/auth.py`), state-based in MCP

**Configuration:** `MemBlocksConfig` reads from `.env` + constructor args

---

*Architecture analysis: 2026-05-04*