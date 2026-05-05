# MemBlocks — Complete Project Workflow & Architecture Guide

---

## Table of Contents

1. [What is MemBlocks?](#1-what-is-memblocks)
2. [The Core Problem it Solves](#2-the-core-problem-it-solves)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Project Structure](#4-project-structure)
5. [The Four Memory Types](#5-the-four-memory-types)
6. [Component Deep-Dives](#6-component-deep-dives)
   - [memblocks_lib — The Core Engine](#61-memblocks_lib--the-core-engine)
   - [backend — FastAPI REST Server](#62-backend--fastapi-rest-server)
   - [frontend — React Web UI](#63-frontend--react-web-ui)
   - [mcp_server — AI Assistant Bridge](#64-mcp_server--ai-assistant-bridge)
7. [Data Models (All Types & Interfaces)](#7-data-models-all-types--interfaces)
8. [Storage Layer](#8-storage-layer)
9. [LLM Providers](#9-llm-providers)
10. [Complete Data Flow Walkthroughs](#10-complete-data-flow-walkthroughs)
    - [Flow A: Sending a Chat Message](#flow-a-sending-a-chat-message)
    - [Flow B: Memory Pipeline (PS1 + PS2)](#flow-b-memory-pipeline-ps1--ps2)
    - [Flow C: Memory Retrieval](#flow-c-memory-retrieval)
11. [The Memory Pipeline — Detailed](#11-the-memory-pipeline--detailed)
12. [Retrieval System — Detailed](#12-retrieval-system--detailed)
13. [Transparency & Observability](#13-transparency--observability)
14. [Authentication](#14-authentication)
15. [Infrastructure & Configuration](#15-infrastructure--configuration)
16. [How All Components Wire Together](#16-how-all-components-wire-together)
17. [Running the Project](#17-running-the-project)
18. [Conflict Management — How New Memories are Stored Safely](#18-conflict-management--how-new-memories-are-stored-safely)
19. [Glossary](#19-glossary)

---

## 1. What is MemBlocks?

MemBlocks is a **modular, intelligent memory management system for LLM applications**. Think of it as a smart, persistent long-term memory layer you attach to any LLM chat application.

The analogy the project uses is a **game cartridge**: just like a game console can swap cartridges and each cartridge holds a completely different world of state, MemBlocks lets you swap "memory blocks" to give an LLM completely different context. A "Work" block holds your work knowledge; a "Personal" block holds personal preferences; a "Team Project X" block holds everything about that project. The LLM accesses whichever block is active.

**MemBlocks does NOT run the LLM itself.** It is purely the memory + retrieval layer. You point it at an LLM API (Groq, Gemini, OpenRouter) and it manages:
- Extracting and storing memories from conversations
- Intelligently retrieving relevant memories when needed
- Compressing conversation history into rolling summaries
- Serving a clean memory context string to the LLM's system prompt

---

## 2. The Core Problem it Solves

Standard LLM chat has a **context window limit**. You can't feed the model every conversation you've ever had. Without memory, every session starts blank — the LLM has no recollection of past interactions, user preferences, or accumulated knowledge.

MemBlocks solves this with a **three-layer approach**:

| Layer | Mechanism | What it stores |
|---|---|---|
| **In-window** | Last N messages (`MEMORY_WINDOW`) | Recent conversation turns |
| **Rolling Summary** | Recursive LLM summarization | Compressed history of older turns |
| **Long-term Memory** | Vector DB (Qdrant) + MongoDB | Facts, events, opinions, profiles extracted from past conversations |

When you send a new message, MemBlocks pulls the relevant long-term memories and injects them into the system prompt alongside the rolling summary and recent window. The LLM sees a coherent, compact, relevant context even though it has "talked" to you for months.

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                              │
│                                                                   │
│   ┌──────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│   │  React Web   │   │ Claude/Cline │   │  Any Python App    │  │
│   │  Frontend    │   │  (via MCP)   │   │  (direct library)  │  │
│   └──────┬───────┘   └──────┬───────┘   └────────┬───────────┘  │
└──────────┼───────────────────┼────────────────────┼─────────────┘
           │ HTTP REST         │ MCP stdio           │ Python import
           ▼                   ▼                     ▼
┌──────────────────┐  ┌─────────────────┐           │
│  FastAPI Backend │  │   MCP Server    │           │
│  (port 8001)     │  │  (stdio JSON)   │           │
└────────┬─────────┘  └───────┬─────────┘           │
         │                    │                      │
         └──────────┬──────────┘                     │
                    ▼                                 ▼
         ┌─────────────────────────────────────────────┐
         │              memblocks_lib                   │
         │         (Core Memory Engine)                 │
         │                                              │
         │  MemBlocksClient                             │
         │    ├── UserManager                           │
         │    ├── BlockManager                          │
         │    ├── SessionManager                        │
         │    ├── MemoryPipeline                        │
         │    │     ├── SemanticMemoryService           │
         │    │     └── CoreMemoryService               │
         │    └── Transparency (EventBus + Logs)        │
         └──────────────┬──────────────────────────────┘
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ MongoDB  │  │  Qdrant  │  │  Ollama  │
    │ (meta,   │  │ (vectors)│  │ (embed.) │
    │  core,   │  │          │  │          │
    │  sessions│  │          │  │          │
    └──────────┘  └──────────┘  └──────────┘
```

---

## 4. Project Structure

```
MemBlocks/
│
├── memblocks_lib/               # Core Python library — the memory engine
│   ├── pyproject.toml
│   └── src/
│       └── memblocks/
│           ├── client.py            # Main entry point — MemBlocksClient
│           ├── config.py            # Pydantic config, reads .env
│           ├── models/              # All data models / types
│           │   ├── block.py         # MemoryBlock, MemoryBlockMetaData
│           │   ├── memory.py        # SemanticMemoryData, CoreMemoryData
│           │   ├── units.py         # Memory units, MemoryOperation, ProcessingEvent
│           │   ├── retrieval.py     # RetrievalResult
│           │   ├── llm_outputs.py   # Pydantic models for structured LLM outputs
│           │   └── transparency.py  # Logging models (OperationEntry, RetrievalEntry, etc.)
│           ├── services/            # Business logic
│           │   ├── block.py         # Block — stateful retrieval handle
│           │   ├── session.py       # Session — stateful conversation handle
│           │   ├── semantic_memory.py  # PS1 extraction, PS2 conflict res., retrieval
│           │   ├── core_memory.py      # Persona + human profile management
│           │   ├── memory_pipeline.py  # Orchestrates full memory processing
│           │   ├── block_manager.py    # Block CRUD lifecycle
│           │   ├── session_manager.py  # Session creation
│           │   ├── user_manager.py     # User management
│           │   └── transparency.py     # EventBus, logs, LLMUsageTracker
│           ├── storage/             # Database adapters
│           │   ├── mongo.py         # MongoDB async adapter (Motor)
│           │   ├── qdrant.py        # Qdrant vector DB adapter
│           │   └── embeddings.py    # Ollama dense + SPLADE sparse embeddings
│           ├── llm/                 # LLM provider abstraction
│           │   ├── base.py          # LLMProvider abstract base class
│           │   ├── groq_provider.py
│           │   ├── gemini_provider.py
│           │   ├── openrouter_provider.py
│           │   └── task_settings.py # Per-task LLM config
│           └── prompts/             # All LLM system prompts
│               ├── ps1_extraction.py
│               ├── ps2_conflict.py
│               ├── core_memory.py
│               ├── summary.py
│               ├── retrieval.py     # Query expansion + hypothetical para prompts
│               └── assistant.py     # Base assistant prompt
│
├── backend/                     # FastAPI REST API
│   ├── pyproject.toml
│   └── src/
│       └── api/
│           ├── main.py              # FastAPI app factory, lifespan, CORS
│           ├── dependencies.py      # get_client() singleton DI
│           ├── routers/
│           │   ├── auth.py          # Clerk JWT verification
│           │   ├── blocks.py        # Block CRUD routes
│           │   ├── chat.py          # Session + message routes (main chat logic)
│           │   ├── memory.py        # Manual memory operations
│           │   ├── transparency.py  # Analytics routes
│           │   └── users.py         # User management routes
│           └── models/
│               └── requests.py      # Pydantic request validation models
│
├── mcp_server/                  # MCP protocol server for AI assistants
│   ├── server.py                # FastMCP server, all tool definitions
│   ├── cli.py                   # Entry point (memblocks-mcp CLI command)
│   └── tests/
│       ├── test_store_background_tools.py
│       └── test_cli_resources.py
│
├── frontend/                    # React SPA
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx              # Router setup
│       ├── pages/
│       │   ├── Landing.jsx      # Public page with Clerk auth
│       │   └── Workspace.jsx    # Main 3-panel authenticated UI
│       ├── components/
│       │   ├── BlockManager.jsx     # Left sidebar — block list/create/delete
│       │   ├── ChatInterface.jsx    # Center — chat messages + input
│       │   ├── AnalyticsPanel.jsx   # Right sidebar — tokens, core mem, summary
│       │   └── ...              # Supporting components
│       └── api/
│           └── client.js        # Axios client with Clerk JWT interceptor
│
├── tests/                       # Integration tests
│   ├── test_hybrid.py           # Hybrid retrieval integration test
│   └── test_store_tools.py
│
├── docs/                        # Documentation
│   ├── ARCHITECTURE.md
│   ├── API.md
│   ├── LIBRARY.md
│   ├── MCP_SERVER.md
│   └── DEPLOYMENT.md
│
├── docker-compose.yml           # MongoDB + Qdrant + Ollama
├── Dockerfile.ollama
├── pyproject.toml               # UV workspace root
└── .env.example                 # All required environment variables
```

---

## 5. The Four Memory Types

MemBlocks organizes memory into four distinct types, each stored and retrieved differently:

### 5.1 Core Memory (Always Present)
- **What**: Persistent persona and human profile. Two text fields:
  - `persona_content` — what the AI "knows about itself" for this block (role, tone, expertise)
  - `human_content` — what the AI knows about the user (name, background, preferences, goals)
- **Where stored**: MongoDB (not in vector DB)
- **How retrieved**: Always fetched in full, always injected into every prompt — no search needed
- **When updated**: Every time the memory pipeline runs, LLM extracts profile updates from recent messages

### 5.2 Semantic Memory (Searchable Facts)
- **What**: Individual facts, events, and opinions extracted from conversations
  - `fact` — static facts ("User prefers Python over JavaScript")
  - `event` — timestamped occurrences ("User deployed to production on 2025-03-10")
  - `opinion` — beliefs/preferences ("User thinks microservices are overused")
- **Where stored**: Qdrant (vector database) with both dense and sparse vectors
- **How retrieved**: Hybrid vector search (dense + sparse) → Cohere reranking → top K results
- **When updated**: PS1 extraction + PS2 conflict resolution in memory pipeline

### 5.3 Episodic Memory (Conversation Window)
- **What**: The recent raw conversation messages
- **Where stored**: MongoDB (session documents)
- **How retrieved**: Last N messages fetched directly (no vector search)
- **When compressed**: When window reaches `MEMORY_WINDOW` limit, pipeline runs and messages are compressed into a rolling summary, then trimmed to last `KEEP_LAST_N`

### 5.4 Resource Memory (Documents/Links) *(Stub/Planned)*
- **What**: Documents, links, images, audio, extracted text
- **Where stored**: Qdrant (separate collection per block)
- **How retrieved**: Vector search
- **Status**: Infrastructure in place, ingestion pipeline is planned/partial

---

## 6. Component Deep-Dives

### 6.1 memblocks_lib — The Core Engine

This is the heart of the project. Everything else delegates to this library.

#### `MemBlocksClient` (`client.py`)

The single entry point for all operations. It wires everything together via dependency injection at initialization time.

```python
client = MemBlocksClient()   # reads config from .env
await client.create_user("user_123")
block = await client.create_block("user_123", "Work", "My work context")
session = await client.create_session("user_123", block.id)
```

Key responsibilities:
- Instantiates and holds references to all managers and services
- Exposes a clean, high-level API hiding internal complexity
- Manages a shared `conversation_llm` for the main chat response
- Exposes transparency methods to read logs and analytics

#### `config.py`

Pydantic Settings class that reads all configuration from `.env`. Key config groups:
- **LLM task settings**: Which model/provider/temperature to use for each task (PS1, PS2, retrieval, core memory, summary, conversation)
- **Database settings**: MongoDB URI, Qdrant host/port, Ollama URL
- **Retrieval settings**: `MEMORY_WINDOW`, `KEEP_LAST_N`, `TOP_K_RETRIEVAL`, toggle for query expansion, hypothetical paragraphs, reranking

#### Services

**`Block` service** (`services/block.py`)
- A stateful handle returned after you call `client.get_block()` or `client.create_block()`
- Holds all metadata about the block
- Primary public method: `retrieve(query)` — runs concurrent core + semantic retrieval
- Returns a `RetrievalResult` you can call `.to_prompt_string()` on

**`Session` service** (`services/session.py`)
- A stateful handle for one conversation thread
- Tracks message count relative to `MEMORY_WINDOW`
- `add(user_msg, ai_response)` — persists the turn; if window is full, fires the memory pipeline
- `get_memory_window()` — returns the last N messages formatted for LLM
- `get_recursive_summary()` — returns the rolling compressed summary
- `flush()` — manually triggers pipeline without waiting for window to fill

**`SemanticMemoryService`** (`services/semantic_memory.py`)
- The most complex service in the library
- Three main operations:
  1. **`extract(messages)`** — PS1: LLM reads conversation, returns list of `SemanticMemoryUnit`
  2. **`store(unit)`** — PS2: LLM compares new unit with existing similar memories, resolves conflicts (update/keep/merge), then stores vectors in Qdrant
  3. **`retrieve(queries)`** — multi-strategy search: query expansion → hypothetical paragraphs → dense+sparse hybrid search → Cohere reranking → top K

**`CoreMemoryService`** (`services/core_memory.py`)
- Simpler than semantic service
- `update(block_id, messages)` — LLM extracts updated persona and human profile, saves to MongoDB
- `get(block_id)` — fetch current core memory (always full retrieval, no vectors)

**`MemoryPipeline`** (`services/memory_pipeline.py`)
- Orchestrator called when session window fills up
- Runs three steps in sequence:
  1. Semantic extraction (PS1 → PS2 for each extracted unit)
  2. Core memory update
  3. Recursive summary generation
- Supports background task execution (non-blocking)
- Emits `ProcessingEvent` updates via EventBus

---

### 6.2 backend — FastAPI REST Server

Bridges the React frontend (and any HTTP client) to `memblocks_lib`.

**App Factory** (`main.py`):
- Creates FastAPI instance
- CORS middleware for `localhost:5173` (Vite dev server)
- Lifespan: initializes `MemBlocksClient` singleton on startup, closes it on shutdown
- Clerk JWT middleware protects all routes except `/health`

**Routers**:

| Router | Path prefix | Purpose |
|---|---|---|
| `auth.py` | `/api/auth` | Verify Clerk token, extract current user |
| `users.py` | `/api/users` | Create/get users |
| `blocks.py` | `/api/blocks` | Block CRUD |
| `chat.py` | `/api/chat` | Sessions + message sending (main flow) |
| `memory.py` | `/api/memory` | Manual memory search/view |
| `transparency.py` | `/api/transparency` | Logs, analytics, usage stats |

**The critical chat flow** (`routers/chat.py`, `POST /api/chat/sessions/{session_id}/message`):

```
1. Validate JWT, identify user
2. Load block and session
3. block.retrieve(user_message) → RetrievalResult
4. session.get_memory_window() → recent messages
5. session.get_recursive_summary() → rolling summary
6. Build system prompt = BASE_PROMPT + summary + memory context
7. Build message list = [system] + memory_window + [user_message]
8. client.conversation_llm.chat(messages) → ai_response
9. session.add(user_message, ai_response) as background task
10. Return: { response, core_memory, summary, pipeline_history, stats }
```

---

### 6.3 frontend — React Web UI

A React 18 SPA using Vite for fast development builds.

**Authentication**: Clerk SDK handles login — no custom auth code in the frontend. Clerk issues JWTs that are attached to every API call via an Axios request interceptor.

**Layout** (three panels in `Workspace.jsx`):

```
┌────────────────────────────────────────────────────────┐
│                     Header                              │
│         (Active block name + session info)              │
├────────────┬─────────────────────┬──────────────────────┤
│            │                     │                      │
│   Block    │   Chat Interface    │  Analytics Panel     │
│  Manager   │                     │                      │
│            │  - Message history  │  - Token usage       │
│  - List    │  - Input box        │  - Core memory       │
│  - Create  │  - Memory window    │    (persona/human)   │
│  - Delete  │    counter          │  - Rolling summary   │
│  - Toggle  │                     │  - Pipeline history  │
│            │                     │                      │
└────────────┴─────────────────────┴──────────────────────┘
```

**`BlockManager.jsx`**: Lists all user blocks from `/api/blocks/user/{userId}`. Creating a block hits `POST /api/blocks`. Active block stored in React state and localStorage.

**`ChatInterface.jsx`**: Sends messages to `POST /api/chat/sessions/{sessionId}/message`. Displays the response. Tracks memory window usage (e.g., "6/10 messages"). Session ID persisted in localStorage.

**`AnalyticsPanel.jsx`**: After each message, the response includes updated `core_memory`, `summary`, `pipeline_history`, and token stats. This panel renders all of them in real time.

---

### 6.4 mcp_server — AI Assistant Bridge

Exposes MemBlocks as an **MCP (Model Context Protocol) server** so AI assistants like Claude Desktop, Cline, OpenCode, or any MCP-compatible client can use MemBlocks as tools.

**Protocol**: stdio JSON (standard MCP protocol). The MCP host (e.g., Claude Desktop) launches the server as a subprocess and communicates over stdin/stdout.

**Initialization** (lifespan):
1. Creates `MemBlocksClient` singleton
2. Gets-or-creates the configured user
3. Auto-selects default block (creates one if none exists)
4. Logs to `memblocks_mcp.log` and `memblocks.log`

**Exposed Tools**:
- `memblocks_list_blocks` — list all memory blocks for the user
- `memblocks_set_block` — set which block is active for subsequent operations
- Memory retrieval and storage tools (delegates to `client`)

Background tasks are dispatched with exception logging so MCP tool calls return quickly without waiting for memory processing.

---

## 7. Data Models (All Types & Interfaces)

### Memory Block

```python
class MemoryBlockMetaData(BaseModel):
    id: str                          # UUID
    created_at: str                  # ISO 8601
    updated_at: str                  # ISO 8601
    usage: List[str]                 # List of usage timestamps
    user_id: Optional[str]           # Owning user
    llm_usage: Dict[str, Any]        # Aggregated token counts per task type

class MemoryBlock(BaseModel):
    meta_data: MemoryBlockMetaData
    name: str                        # Human-readable name ("Work", "Personal")
    description: str                 # What this block is for
    semantic_collection: Optional[str]      # Qdrant collection name for semantic memory
    core_memory_block_id: Optional[str]     # MongoDB document key for core memory
    resource_collection: Optional[str]      # Qdrant collection for resource memory
    is_active: bool
```

### Memory Units

```python
class SemanticMemoryUnit(BaseModel):
    content: str                     # The memory text
    type: Literal["event", "fact", "opinion"]
    memory_id: Optional[str]         # Qdrant point ID (set after storage)
    source: Optional[str]            # Where this memory came from
    confidence: float                # 0.0 to 1.0
    memory_time: Optional[str]       # ISO 8601, only for events
    updated_at: str                  # ISO 8601, when last updated
    meta_data: Optional[MemoryUnitMetaData]
    keywords: Optional[List[str]]    # Tags for sparse search
    embedding_text: str              # Optimized text used for embedding generation
    entities: Optional[List[str]]    # Named entities in this memory

class CoreMemoryUnit(BaseModel):
    persona_content: str             # AI persona for this block
    human_content: str               # User profile

class ResourceMemoryUnit(BaseModel):
    content: str
    resource_type: Literal["document", "image", "video", "audio", "link", "extracted"]
    resource_link: Optional[str]
```

### Retrieval Result

```python
class RetrievalResult(BaseModel):
    core: Optional[CoreMemoryUnit]
    semantic: List[SemanticMemoryUnit]
    resource: List[ResourceMemoryUnit]

    def to_prompt_string(self) -> str:
        # Returns formatted string:
        # <Core Memory>
        #   Persona: ...
        #   Human: ...
        # </Core Memory>
        # <Semantic Memories>
        #   - [fact] User prefers Python (confidence: 0.95)
        #   ...
        # </Semantic Memories>

    def is_empty(self) -> bool:
        # Returns True if no core, semantic, or resource memories
```

### LLM Output Models (`models/llm_outputs.py`)

Pydantic models that structure LLM JSON responses for each task:

- `PS1ExtractionOutput` — list of `SemanticMemoryUnit` objects extracted from conversation
- `PS2ConflictOutput` — decision: `update` / `keep` / `merge` + optionally updated memory
- `CoreMemoryExtractionOutput` — updated `persona_content` and `human_content`
- `SummaryOutput` — new summary text
- `QueryExpansionOutput` — list of alternative query phrasings
- `HypotheticalParagraphOutput` — hypothetical text that would answer the query

### Transparency Models (`models/transparency.py`)

```python
class OperationEntry(BaseModel):
    db_type: DBType                  # MONGO | QDRANT
    collection_name: str
    operation_type: OperationType    # insert | update | delete
    document_id: Optional[str]
    payload_summary: str
    success: bool
    error: Optional[str]
    timestamp: datetime

class RetrievalEntry(BaseModel):
    timestamp: datetime
    query: str
    source: str                      # "dense", "sparse", "cohere", etc.
    num_results: int
    block_id: str

class PipelineRunEntry(BaseModel):
    task_id: str
    status: str                      # "running" | "completed" | "failed"
    trigger_event: str
    input_message_count: int
    extracted_semantic_count: int
    conflicts_resolved_count: int
    core_memory_updated: bool
    summary_generated: bool
    timestamp_started: datetime
    timestamp_completed: Optional[datetime]

class LLMUsageEntry(BaseModel):
    task_type: str                   # "ps1", "ps2", "retrieval", etc.
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    timestamp: datetime
```

---

## 8. Storage Layer

### MongoDB (`storage/mongo.py`) — `MongoDBAdapter`

Used for **structured, non-vector data**. Stores:
- Users and their block references
- Block metadata
- Core memory (persona + human content per block)
- Session messages and rolling summaries

All operations are **async** using Motor (async MongoDB driver). The adapter is **non-singleton** — each component creates its own instance but they share the same underlying connection pool.

Collections (approximate):
- `users` — user documents with block ID lists
- `blocks` — block metadata
- `core_memories` — indexed by `block_id`
- `sessions` — message arrays + summary field per session

Key operations:
```
create_user / get_user / list_users
save_block / get_block / list_blocks_for_user / delete_block
save_core_memory / get_core_memory
create_session / get_session
add_message_to_session / get_session_messages / get_session_message_count
trim_session_messages / get_session_summary / set_session_summary
update_block_llm_usage
```

### Qdrant (`storage/qdrant.py`) — `QdrantAdapter`

Used for **vector search** on semantic memories (and resources). Each block gets its own Qdrant collection.

**Hybrid vectors**: Every memory is stored with **two vectors**:
1. **Dense vector** — from `nomic-embed-text` via Ollama (768 or 1536 dimensions)
2. **Sparse vector** — from SPLADE (`Prithivida/Splade_PP_en_v1`) via FastEmbed — token-importance weights for keyword-aware search

**Retrieval**: Uses **Reciprocal Rank Fusion (RRF)** to merge results from dense and sparse search before reranking.

Key operations:
```
create_collection(name, vector_size)
store_vector(collection, dense_vec, payload, point_id, sparse_vec)
search_vectors(collection, dense_vec, top_k)
search_sparse_vectors(collection, sparse_vec, top_k)
hybrid_search(collection, dense_vec, sparse_vec, top_k)
get_all_points(collection)
delete_point(collection, point_id)
delete_collection(collection)
```

### Ollama (`storage/embeddings.py`) — `EmbeddingProvider`

Runs locally (via Docker). Generates embeddings for memory storage and retrieval.

- **Dense embeddings** — `nomic-embed-text` model — captures semantic meaning
- **Sparse embeddings** — SPLADE model via FastEmbed — captures keyword importance

Both are generated at storage time and at query time to enable hybrid matching.

---

## 9. LLM Providers

### Abstract Base (`llm/base.py`)

```python
class LLMProvider(ABC):
    @abstractmethod
    def create_structured_chain(
        system_prompt: str,
        pydantic_model: Type[BaseModel],
        temperature: float
    ) -> Runnable:
        # Returns a LangChain Runnable that accepts {"input": str}
        # and returns an instance of pydantic_model (structured output)

    @abstractmethod
    async def chat(
        messages: List[Dict[str, str]],
        temperature: Optional[float]
    ) -> str:
        # Free-form chat, returns assistant response text
```

### Implementations

| Provider | Class | Use |
|---|---|---|
| **Groq** | `GroqLLMProvider` | Fast inference, good for extraction tasks |
| **Gemini** | `GeminiLLMProvider` | Google Gemini models |
| **OpenRouter** | `OpenRouterLLMProvider` | Route to many models via one API |

### Per-Task LLM Configuration

The key design decision: **different LLM models can be used for different tasks**. This lets you use a cheap, fast model for extraction and a more powerful model for conversation.

Tasks:
- `conversation` — Main chat response to user
- `ps1_semantic_extraction` — Extract memories from messages (PS1)
- `ps2_conflict_resolution` — Resolve conflicts when storing memories (PS2)
- `retrieval` — Query expansion and hypothetical paragraph generation
- `core_memory_extraction` — Extract persona/human profile updates
- `recursive_summary` — Generate rolling summaries

Each task has independent `provider`, `model`, and `temperature` settings in `.env`.

---

## 10. Complete Data Flow Walkthroughs

### Flow A: Sending a Chat Message

This is the end-to-end flow when a user types a message in the chat interface.

```
User types: "What did we discuss about my Python project last week?"
                                    │
                                    ▼
[Frontend: ChatInterface.jsx]
POST /api/chat/sessions/{sessionId}/message
  Body: { user_id, block_id, message: "What did we discuss..." }
                                    │
                                    ▼
[Backend: routers/chat.py]
1. Verify Clerk JWT
2. Load Block object for block_id
3. Load Session object for session_id
                                    │
                                    ▼
4. block.retrieve("What did we discuss about my Python project last week?")
   ┌──────────────────────────────────────────────────────────┐
   │  Concurrent fetch:                                        │
   │  ├── CoreMemoryService.get(block_id)                     │
   │  │   └── MongoDB lookup → CoreMemoryUnit                 │
   │  └── SemanticMemoryService.retrieve([query])             │
   │       ├── Retrieval LLM: expand query to 3 variations    │
   │       ├── EmbeddingProvider: embed all query variations  │
   │       ├── Qdrant hybrid search per query variation       │
   │       ├── Merge results with RRF                         │
   │       └── Cohere reranking → top K SemanticMemoryUnits   │
   └──────────────────────────────────────────────────────────┘
   Returns: RetrievalResult { core, semantic: [...] }
                                    │
                                    ▼
5. session.get_memory_window()
   └── MongoDB: last N messages from session
       Returns: [{"role": "user", "content": "..."}, ...]
                                    │
                                    ▼
6. session.get_recursive_summary()
   └── MongoDB: session.summary field
       Returns: "In previous conversations, user discussed..."
                                    │
                                    ▼
7. Build system prompt:
   = ASSISTANT_BASE_PROMPT
   + "<Conversation Summary>\n" + rolling_summary
   + retrieval_result.to_prompt_string()

   (to_prompt_string() formats as:)
   <Core Memory>
     Persona: You are a helpful assistant...
     Human: User is a senior Python developer...
   </Core Memory>
   <Semantic Memories>
     - [event] User started a FastAPI project on 2025-03-01 (confidence: 0.92)
     - [fact] User prefers async Python patterns (confidence: 0.88)
   </Semantic Memories>
                                    │
                                    ▼
8. Build messages:
   = [{"role": "system", "content": system_prompt}]
   + memory_window (recent messages)
   + [{"role": "user", "content": user_message}]
                                    │
                                    ▼
9. client.conversation_llm.chat(messages)
   └── Calls configured LLM API (Groq/Gemini/OpenRouter)
       Returns: ai_response string
                                    │
                                    ▼
10. Background task: session.add(user_message, ai_response)
    └── MongoDB: append both messages to session
        └── Check: message_count >= MEMORY_WINDOW ?
            └── Yes → spawn MemoryPipeline.run() as background task
                                    │
                                    ▼
11. Return response to frontend:
    {
      "response": "Last week we discussed your FastAPI project...",
      "core_memory": { persona_content, human_content },
      "summary": "Running summary text...",
      "pipeline_history": [...],
      "token_usage": { prompt_tokens, completion_tokens }
    }
                                    │
                                    ▼
[Frontend]
- Display AI response in chat
- Update AnalyticsPanel with core memory, summary, stats
```

---

### Flow B: Memory Pipeline (PS1 + PS2)

Triggered when session message count reaches `MEMORY_WINDOW` (default: 10).

```
Trigger: Session has 10 messages, session.add() fires pipeline
                                    │
                                    ▼
MemoryPipeline.run(user_id, block_id, messages, current_summary)

STEP 1 — Semantic Memory Extraction (PS1)
──────────────────────────────────────────
PS1 LLM receives:
  System: [PS1 extraction prompt — instructions to extract facts/events/opinions]
  User: [All 10 conversation messages formatted as transcript]

PS1 LLM returns (structured JSON):
  [
    { content: "User is building a FastAPI app", type: "fact", confidence: 0.9,
      keywords: ["FastAPI", "Python", "backend"], entities: ["FastAPI"] },
    { content: "User deployed to Heroku on 2025-03-15", type: "event",
      memory_time: "2025-03-15", confidence: 0.85, ... },
    { content: "User dislikes ORMs", type: "opinion", confidence: 0.75, ... }
  ]

STEP 2 — Conflict Resolution & Storage (PS2) — for each extracted unit:
──────────────────────────────────────────────────────────────────────────
For each SemanticMemoryUnit from PS1:

  2a. Generate embedding_text embedding (dense + sparse vectors via Ollama)

  2b. Search Qdrant for similar existing memories (top 5)

  2c. If similar memories found:
      PS2 LLM receives:
        System: [PS2 conflict resolution prompt]
        User: [New memory] + [Existing similar memories]

      PS2 LLM returns one of:
        { action: "keep" }           → existing memory stays, new one discarded
        { action: "update", updated_content: "..." } → update existing
        { action: "merge", merged_content: "..." }   → combine into one
        { action: "add" }            → no conflict, add as new

  2d. Based on PS2 decision:
      - "add"    → store new vector in Qdrant with all fields as payload
      - "update" → delete old Qdrant point, store updated version
      - "merge"  → delete old, store merged version
      - "keep"   → do nothing

STEP 3 — Core Memory Update
─────────────────────────────
Core Memory LLM receives:
  System: [Core memory extraction prompt]
  User: [Conversation messages] + [Current persona + human content]

Core Memory LLM returns:
  { persona_content: "Updated persona...", human_content: "Updated human profile..." }

Save to MongoDB (core_memories collection, keyed by block_id)

STEP 4 — Recursive Summary Generation
───────────────────────────────────────
Summary LLM receives:
  System: [Summary generation prompt]
  User: [Existing summary] + [10 conversation messages to compress]

Summary LLM returns:
  "New rolling summary that incorporates old summary + new messages..."

Save to MongoDB (session document, summary field)

STEP 5 — Cleanup
──────────────────
Trim session messages in MongoDB:
  Keep only the last KEEP_LAST_N messages (default: 4)
  (The rest are "archived" in the summary and semantic memories)

Emit PipelineRunEntry to EventBus with all stats
```

---

### Flow C: Memory Retrieval

Detailed walkthrough of `SemanticMemoryService.retrieve()`.

```
Input: queries = ["Python project discussion", "FastAPI deployment"]
                                    │
                                    ▼
STEP 1 — Query Expansion (if enabled)
───────────────────────────────────────
Retrieval LLM generates 3 alternative phrasings per query:
  "Python project discussion" →
    1. "Python backend project conversation"
    2. "discussing Python application development"
    3. "Python software project talked about"
                                    │
                                    ▼
STEP 2 — Hypothetical Paragraphs (if enabled)
────────────────────────────────────────────────
Retrieval LLM generates a hypothetical paragraph that would answer each query:
  "Python project discussion" →
    "In a previous conversation, the user mentioned they were building a
     Python FastAPI application for a data pipeline project..."

This hypothetical text is embedded and used as an additional search query
(the intuition: a good answer is similar to good matching memories)
                                    │
                                    ▼
STEP 3 — Hybrid Vector Search
───────────────────────────────
For each query (original + expansions + hypotheticals):
  a. EmbeddingProvider.embed_query(query) → dense_vector (float[])
  b. EmbeddingProvider.embed_sparse(query) → sparse_vector ({token_id: weight})
  c. QdrantAdapter.hybrid_search(collection, dense_vector, sparse_vector, top_k)
     └── Qdrant runs:
           - Dense ANN search (cosine similarity)
           - Sparse search (dot product on SPLADE vectors)
           - RRF (Reciprocal Rank Fusion) to merge both result sets
     Returns: List of {payload: SemanticMemoryUnit fields, score: float}
                                    │
                                    ▼
STEP 4 — Result Aggregation
─────────────────────────────
- Collect all results across all query variations
- Deduplicate by memory_id
- Keep top candidates (e.g., top 20)
                                    │
                                    ▼
STEP 5 — Cohere Reranking (if enabled)
───────────────────────────────────────
Send to Cohere API:
  query = original user query
  documents = [memory.content for memory in candidates]

Cohere returns relevance scores → reorder candidates

Return top_k (e.g., top 5) most relevant SemanticMemoryUnits
```

---

## 11. The Memory Pipeline — Detailed

The memory pipeline is the mechanism by which conversations are converted into persistent long-term memories. It is the most important process in the system.

### When it Runs

1. **Automatically** — when `session.add()` detects the message count has reached `MEMORY_WINDOW`
2. **Manually** — when `session.flush()` is called explicitly
3. **As a background task** — the backend dispatches it via FastAPI's background tasks to keep the HTTP response fast

### The Two-Stage Semantic Memory System

**PS1 (Phase 1 — Extraction)**: The LLM acts as a "memory extractor". It reads the raw conversation and identifies what is worth remembering, classifying each item as a fact, event, or opinion with metadata.

**PS2 (Phase 2 — Conflict Resolution)**: Before storing any extracted memory, the system checks if similar information already exists. The LLM then decides whether to add, update, merge, or discard the new memory. This prevents duplicate or contradictory memories from accumulating over time.

This two-stage design is the key innovation — naive memory systems just append everything, leading to bloat and contradictions. PS2 keeps the memory store clean and consistent.

### Background Task Support

The pipeline can run as a Python background task. When running in the backend context, FastAPI's `BackgroundTasks` is used. The pipeline emits status events via `EventBus` throughout execution, allowing real-time monitoring.

---

## 12. Retrieval System — Detailed

### Why Hybrid Search?

**Dense vectors** (from nomic-embed-text) capture semantic meaning — they understand that "Python backend" and "server-side development in Python" mean similar things.

**Sparse vectors** (SPLADE) capture keyword importance — they ensure exact terms like specific library names, version numbers, or proper nouns are matched even if semantically distant.

**Neither alone is sufficient**:
- Dense search misses exact keyword matches
- Sparse search misses semantic paraphrases

**RRF (Reciprocal Rank Fusion)** merges both ranked lists by summing reciprocal ranks: `score = 1/(k + rank_dense) + 1/(k + rank_sparse)`. This is Qdrant's built-in hybrid fusion.

### Query Enhancement

**Query Expansion**: A single user query is rewritten into 3 variations to improve recall. Different phrasings cast a wider net over the vector space.

**Hypothetical Paragraphs (HyDE)**: Generate a hypothetical ideal-memory text and embed it. The intuition is that a good hypothetical answer is likely embedded near good actual memories in vector space.

### Cohere Reranking

After vector search returns many candidates, Cohere's reranking model (a cross-encoder) scores each candidate against the original query. Cross-encoders are more accurate than bi-encoders (used for embedding) because they process query and document together. This gives precise relevance ordering for the final top K results.

---

## 13. Transparency & Observability

Every operation in MemBlocks is logged through a central `EventBus` and dedicated log stores.

### EventBus (`services/transparency.py`)

A simple pub/sub mechanism:
- Components `emit(event_type, data)` as they operate
- External code can `subscribe(event_type, callback)` to react
- Used by `OperationLog`, `RetrievalLog`, `ProcessingHistory`, and `LLMUsageTracker`

### Log Types

| Log | What it captures |
|---|---|
| `OperationLog` | Every DB read/write (collection, operation type, document ID, success/failure) |
| `RetrievalLog` | Every vector search (query, source, num results, block ID) |
| `ProcessingHistory` | Every pipeline run (stats: extracted count, conflicts resolved, etc.) |
| `LLMUsageTracker` | Every LLM call (model, task, token counts, latency) |

### Frontend Access

The `AnalyticsPanel` in the frontend shows:
- **Token usage** — prompt + completion tokens per message and cumulative
- **Core Memory** — current persona and human content
- **Rolling Summary** — current compressed history
- **Pipeline History** — list of past pipeline runs with stats

The backend exposes these via `GET /api/transparency/*` routes.

---

## 14. Authentication

**Clerk** handles all authentication. Clerk is a third-party auth service.

**Flow**:
1. User logs in via Clerk modal on the Landing page
2. Clerk issues a JWT token
3. React frontend attaches the JWT as `Authorization: Bearer <token>` header on every API call (via Axios interceptor in `src/api/client.js`)
4. Backend `auth.py` router verifies the JWT signature using Clerk's public keys
5. The Clerk user ID is extracted and used as `user_id` throughout the system

**MCP server**: Uses a configured `user_id` directly (no web auth, it's a local tool).

---

## 15. Infrastructure & Configuration

### Docker Services (`docker-compose.yml`)

| Service | Port | Purpose |
|---|---|---|
| MongoDB | 27017 | Structured data (users, blocks, sessions, core memory) |
| Qdrant | 6333 | Vector database (semantic + resource memories) |
| Ollama | 11434 | Local embedding models (nomic-embed-text + SPLADE) |

### Environment Variables (`.env.example`)

**LLM APIs** (at least one required):
```
GROQ_API_KEY=...
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
```

**Per-task LLM settings** (one per task type):
```
CONVERSATION_PROVIDER=groq
CONVERSATION_MODEL=llama-3.3-70b-versatile
CONVERSATION_TEMPERATURE=0.7

PS1_PROVIDER=groq
PS1_MODEL=llama-3.1-8b-instant
...
```

**Databases**:
```
MONGODB_CONNECTION_STRING=mongodb://localhost:27017
MONGODB_DATABASE_NAME=memblocks
QDRANT_HOST=localhost
QDRANT_PORT=6333
OLLAMA_BASE_URL=http://localhost:11434
```

**Memory settings**:
```
MEMORY_WINDOW=10          # Messages before pipeline triggers
KEEP_LAST_N=4             # Messages kept after pipeline
TOP_K_RETRIEVAL=5         # Number of semantic memories to retrieve
```

**Retrieval toggles**:
```
ENABLE_QUERY_EXPANSION=true
ENABLE_HYPOTHETICAL_PARAGRAPHS=false
ENABLE_COHERE_RERANKING=true
COHERE_API_KEY=...
```

**Auth**:
```
CLERK_PUBLISHABLE_KEY=...
CLERK_SECRET_KEY=...
```

**Optional monitoring**:
```
ARIZE_API_KEY=...
ARIZE_SPACE_KEY=...
```

### Python Workspace

The project uses **UV workspaces** (`pyproject.toml` at root). Three packages:
- `memblocks` (the core lib)
- `backend` (depends on `memblocks`)
- `mcp_server` (depends on `memblocks`)

---

## 16. How All Components Wire Together

```
┌─────────────────────────────────────────────────────────────────────┐
│ MemBlocksClient (wired at startup)                                   │
│                                                                       │
│  self.mongo = MongoDBAdapter()           # shared MongoDB connection  │
│  self.qdrant = QdrantAdapter()           # shared Qdrant connection   │
│  self.embeddings = EmbeddingProvider()   # Ollama embeddings          │
│                                                                       │
│  self.semantic_svc = SemanticMemoryService(                           │
│      mongo, qdrant, embeddings,                                       │
│      ps1_llm, ps2_llm, retrieval_llm,                                 │
│      event_bus                                                        │
│  )                                                                    │
│  self.core_svc = CoreMemoryService(                                   │
│      mongo,                                                           │
│      core_memory_llm,                                                 │
│      event_bus                                                        │
│  )                                                                    │
│  self.pipeline = MemoryPipeline(                                      │
│      semantic_svc, core_svc,                                          │
│      summary_llm,                                                     │
│      mongo, event_bus                                                 │
│  )                                                                    │
│  self.block_mgr = BlockManager(mongo, qdrant)                         │
│  self.session_mgr = SessionManager(mongo, pipeline)                   │
│  self.user_mgr = UserManager(mongo)                                   │
│                                                                       │
│  self.conversation_llm = ConversationLLMProvider()                    │
│                                                                       │
│  # Transparency                                                       │
│  self.event_bus = EventBus()                                          │
│  self.op_log = OperationLog(event_bus)                                │
│  self.retrieval_log = RetrievalLog(event_bus)                         │
│  self.pipeline_history = ProcessingHistory(event_bus)                 │
│  self.llm_usage = LLMUsageTracker(event_bus)                          │
└─────────────────────────────────────────────────────────────────────┘

Block (returned by client.get_block())
  ↳ holds references to: semantic_svc, core_svc, block metadata

Session (returned by client.get_session())
  ↳ holds references to: mongo (for messages), pipeline, session metadata

Backend FastAPI app
  ↳ holds one MemBlocksClient singleton (initialized in lifespan)
  ↳ all routers receive it via get_client() dependency injection

MCP Server
  ↳ holds one MemBlocksClient singleton (initialized in lifespan)
  ↳ all tool functions close over the client
```

---

## 17. Running the Project

### 1. Start Infrastructure
```bash
docker-compose up -d
# Starts MongoDB (27017), Qdrant (6333), Ollama (11434)
```

### 2. Install Dependencies
```bash
uv sync --all-packages
# Installs all three Python packages in UV workspace
```

### 3. Configure Environment
```bash
cp .env.example .env
# Fill in API keys and configuration
```

### 4. Start Backend
```bash
uv run uvicorn backend.src.api.main:app --reload --port 8001
```

### 5. Start Frontend
```bash
cd frontend
npm install
npm run dev
# Vite dev server at http://localhost:5173
```

### 6. (Optional) MCP Server
Configure in your MCP host (e.g., Claude Desktop `claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "memblocks": {
      "command": "uv",
      "args": ["run", "-d", "mcp_server", "memblocks-mcp"]
    }
  }
}
```

### 7. (Optional) Run Tests
```bash
uv run pytest tests/
uv run pytest mcp_server/tests/
```

---

## 18. Conflict Management — How New Memories are Stored Safely

This is one of the most critical and nuanced parts of MemBlocks. Every time a new memory is about to be stored, it goes through a two-stage process specifically designed to prevent the memory store from accumulating duplicates, contradictions, and redundant noise over time.

---

### Why Conflict Management is Necessary

Without conflict resolution, a naive memory system would just append everything. After a few weeks of conversations, you'd have:
- "User is a student" (from week 1)
- "User is a computer engineering student" (from week 2)
- "User studies computer science at college" (from week 3)
- "User moved from Delhi to Mumbai" (new)
- "User lives in Delhi" (old — now wrong)

This creates **contradictions** (wrong location), **duplicates** (same fact phrased differently), and **bloat** (weaker facts that are fully subsumed by richer ones). Retrieval quality degrades badly because these redundant results crowd out diverse, relevant memories.

MemBlocks solves this through **PS2 — Phase 2 Conflict Resolution**, which runs for every single memory unit before it is stored.

---

### The Full Store Pipeline (`semantic_memory.py → store()`)

```
Input: One SemanticMemoryUnit from PS1 extraction
                        │
                        ▼
STEP 1 — Embed the new memory
─────────────────────────────
Generate embedding_text = content + "\nKeywords: ..." + "\nEntities: ..."
Embed with Ollama (dense vector)
Optionally embed with SPLADE (sparse vector) if config.retrieval_enable_sparse=true
                        │
                        ▼
STEP 2 — Find semantically similar existing memories
─────────────────────────────────────────────────────
QdrantAdapter.retrieve_from_vector(collection, new_dense_vector, top_k=5)
Returns up to 5 existing ScoredPoint objects closest in embedding space

Decision fork:
  ├── No similar memories found?
  │     → Store directly as new (no conflict possible)
  │     → Append MemoryOperation(operation="ADD") and return
  │
  └── Similar memories found? → Continue to PS2
                        │
                        ▼
STEP 3 — Build ID mapping (internal detail)
─────────────────────────────────────────────
Each Qdrant point has a long UUID. To keep LLM context clean, they are
remapped to simple sequential IDs: "0", "1", "2", ...

id_mapping = { "0": "<real-qdrant-uuid-A>", "1": "<real-qdrant-uuid-B>", ... }
point_mapping = { "0": ScoredPoint, ... }      # needed for UPDATE reconstruction
existing_contents = { "0": "original content text", ... }  # for MemoryOperation logging
                        │
                        ▼
STEP 4 — PS2 LLM Conflict Resolution
──────────────────────────────────────
Calls create_structured_chain(PS2_MEMORY_UPDATE_PROMPT, PS2MemoryUpdateOutput)
Sends:
  NEW MEMORY: { content, type, keywords, entities, confidence, memory_time, ... }
  EXISTING MEMORIES: [ { id: "0", content, type, ... }, { id: "1", ... }, ... ]

LLM returns PS2MemoryUpdateOutput (strict JSON):
  {
    "new_memory_operation": { "operation": "ADD" | "NONE", "reason": "..." },
    "existing_memory_operations": [
      { "id": "0", "operation": "UPDATE" | "DELETE" | "NONE", "updated_memory": {...}, "reason": "..." },
      { "id": "1", "operation": "NONE", "reason": "..." }
    ]
  }
                        │
                        ▼
STEP 5 — Execute decisions
───────────────────────────
Process new_memory_operation first, then each existing_memory_operation.
Map simple IDs back to real Qdrant UUIDs using id_mapping.
```

---

### The Four Operations in Detail

#### Operation 1: ADD (New Memory)

**When**: The new memory contains genuinely novel information not covered by any existing memory.

**What happens in code**:
```python
payload = memory_unit.model_dump(exclude={"memory_id"})
qdrant.store_vector(collection, new_dense_vector, payload, sparse_vector=new_sparse_vector)
operations.append(MemoryOperation(operation="ADD", content=memory_unit.content))
```

A brand new Qdrant point is created with:
- Dense vector (from `embed_text(embedding_text)`)
- Sparse vector (from `embed_sparse_text(embedding_text)`) — if enabled
- Full payload: all fields of `SemanticMemoryUnit` except `memory_id` (Qdrant assigns the ID)

**Example**:
- New: `"User prefers PyTorch over TensorFlow"` (type: opinion)
- Existing similar: `"User is a machine learning engineer"` (type: fact)
- Decision: ADD — different aspect (preference vs occupation), no semantic overlap

---

#### Operation 2: NONE on New Memory (Discard)

**When**: The new memory is a duplicate, near-duplicate, or fully subsumed by an existing memory.

**What happens in code**:
```python
operations.append(MemoryOperation(operation="NONE", content=memory_unit.content))
# No Qdrant write occurs
```

The new memory is simply discarded. Nothing is written to the database.

**PS2 guideline — when to discard**:
- **Duplicate** (>90% semantic overlap): `"User is studying computer engineering"` vs existing `"User is a computer engineering student"`
- **Subsumed**: Existing memory already captures the information more completely
- **Redundant**: No meaningful new dimension is added

**Example**:
- New: `"User studies computer engineering"` (confidence: 0.8)
- Existing [0]: `"User is a computer engineering student"` (confidence: 0.95)
- Decision: new → NONE (90% semantic overlap, existing is equally or more complete)

---

#### Operation 3: UPDATE on Existing Memory

**When**: The new memory refines, extends, or provides additional context to an existing memory — making the existing memory more accurate or complete.

**What happens in code** (the most complex operation):
```python
# 1. Build updated embedding_text from new content/keywords/entities
new_embedding_text = f"{updated_mem.content}\nKeywords: ...\nEntities: ..."

# 2. Preserve and extend meta_data.usage (append current_time to existing usage history)
original_usage = original_point.payload["meta_data"]["usage"]
updated_usage = original_usage + [current_time]
updated_meta = MemoryUnitMetaData(usage=updated_usage, ...)

# 3. Reconstruct the full SemanticMemoryUnit with LLM-provided updated fields
updated_unit = SemanticMemoryUnit(
    content=updated_mem.content,       # LLM may have merged/refined content
    type=updated_mem.type,
    keywords=updated_mem.keywords,     # LLM may have merged keywords from both
    entities=updated_mem.entities,     # LLM may have merged entities from both
    confidence=updated_mem.confidence,
    memory_time=updated_mem.memory_time,
    updated_at=current_time,
    embedding_text=new_embedding_text,
    source=original_point.payload["source"],  # preserve original source
    meta_data=updated_meta,
    memory_id=real_id,
)

# 4. Re-embed with new content (content changed → new vector)
updated_dense_vector = embed_text(updated_unit.embedding_text)
updated_sparse_vector = embed_sparse_text(...)  # if enabled

# 5. Store with the SAME point_id (overwrites the existing Qdrant point)
qdrant.store_vector(collection, updated_dense_vector, payload, point_id=real_id, ...)
operations.append(MemoryOperation(operation="UPDATE", memory_id=real_id,
                                  content=updated_unit.content, old_content=old_content))
```

**Key detail**: The existing Qdrant point is **overwritten in-place** using the same UUID (`point_id=real_id`). This is Qdrant's upsert behavior — same ID = replace. The vector is also re-generated because the content may have changed.

**Usage history is preserved**: The `meta_data.usage` list accumulates timestamps of every update, creating an audit trail of when the memory was reinforced or refined.

**PS2 guideline — when to update**:
- New memory refines specificity: `"User is a student"` → `"User is a computer engineering student"`
- New memory adds context to same core fact
- New memory is a more comprehensive version

**Example**:
- New: `"User is a computer engineering student seeking help with minor project"`
- Existing [0]: `"User is a computer engineering student"`
- Decision: existing[0] → UPDATE (add context about project help), new → NONE (covered by updated existing)
- Updated content: `"User is a computer engineering student currently working on a minor project"`

---

#### Operation 4: DELETE on Existing Memory

**When**: An existing memory is contradicted by the new memory, superseded by it, or becomes a weaker partial version that an UPDATE of another memory already covers.

**What happens in code**:
```python
old_content = existing_contents[op.id]
qdrant.delete_vector(collection, real_id)
operations.append(MemoryOperation(operation="DELETE", memory_id=real_id, content=old_content))
```

The Qdrant point is permanently removed. There is no soft-delete or archive — it is a **hard delete** from the vector store.

**PS2 guideline — when to delete**:
- **Contradiction**: `"User lives in Delhi"` is deleted when new memory says `"User moved to Mumbai"`
- **Superseded**: `"User is a student"` is deleted when an UPDATE already merges it into `"User is a computer engineering student seeking project help"`
- A weaker partial version that is made fully redundant by another UPDATE operation

**Example**:
- New: `"User moved to Berlin in 2024"`
- Existing [0]: `"User lives in Kathmandu"`
- Decision: new → ADD (location change is new info), existing[0] → DELETE (contradicted)

---

### PS2 Decision Matrix (Summary)

| Scenario | New Memory | Existing Memory |
|---|---|---|
| Completely new information | ADD | NONE |
| Exact duplicate | NONE | NONE |
| New is subsumed by existing | NONE | NONE |
| New refines/extends existing | NONE | UPDATE |
| New is more comprehensive than existing | NONE | UPDATE (merge) |
| New contradicts existing | ADD | DELETE |
| New supersedes existing | ADD | DELETE |
| New and existing are distinct aspects | ADD | NONE |

---

### The ID Mapping System

Qdrant stores memories under long UUIDs (e.g., `"a3f2c901-4b8e-47d2-bc5e-..."`). Passing these directly to the LLM would:
1. Waste context tokens
2. Risk the LLM hallucinating or corrupting the IDs

**The solution**: Before calling PS2, the code maps Qdrant UUIDs to simple sequential integers (`"0"`, `"1"`, `"2"`, ...). The LLM works with these clean IDs. After the LLM responds, the code maps back:

```python
# Build before calling PS2:
id_mapping = { "0": "a3f2c901-...", "1": "7e1d4b22-..." }

# After PS2 responds:
for op in result.existing_memory_operations:
    real_id = id_mapping.get(op.id)   # "0" → "a3f2c901-..."
    # now perform UPDATE/DELETE on real_id
```

---

### Fallback Behavior

If the PS2 LLM call itself fails (network error, malformed JSON, timeout), the system falls back gracefully:

```python
except Exception as e:
    logger.warning("PS2 conflict resolution failed: %s", e)
    logger.debug("Fallback: Adding memory without conflict check")
    # Just store the new memory without conflict resolution
    qdrant.store_vector(collection, new_dense_vector, payload, ...)
    operations.append(MemoryOperation(operation="ADD", content=memory_unit.content))
    return operations
```

**This means**: On PS2 failure, the new memory is stored as-is (potential duplicate), but no existing memory is modified or deleted. **Safety is preferred over correctness** — it's better to have a temporary duplicate than to incorrectly delete a valid memory.

---

### What the PS2 LLM Receives and Returns — Concrete Example

**LLM Input**:
```json
NEW MEMORY:
{
  "content": "User is a computer engineering student seeking help with a minor project",
  "type": "fact",
  "keywords": ["computer engineering", "student", "minor project", "help"],
  "entities": ["computer engineering"],
  "confidence": 0.88,
  "memory_time": null,
  "updated_at": "2025-03-29T10:00:00Z",
  "embedding_text": "User is a computer engineering student seeking help with a minor project\nKeywords: computer engineering, student, minor project, help\nEntities: computer engineering"
}

EXISTING MEMORIES:
[
  {
    "id": "0",
    "content": "User is a computer engineering student",
    "type": "fact",
    "keywords": ["computer engineering", "student"],
    "entities": ["computer engineering"],
    "confidence": 0.95,
    "memory_time": null,
    "updated_at": "2025-03-20T08:00:00Z"
  },
  {
    "id": "1",
    "content": "User is seeking project help",
    "type": "fact",
    "keywords": ["project", "help", "assistance"],
    "entities": [],
    "confidence": 0.7,
    "memory_time": null,
    "updated_at": "2025-03-22T09:00:00Z"
  }
]
```

**LLM Output** (`PS2MemoryUpdateOutput`):
```json
{
  "new_memory_operation": {
    "operation": "NONE",
    "reason": "New memory is fully covered by updating existing[0] to include project context"
  },
  "existing_memory_operations": [
    {
      "id": "0",
      "operation": "UPDATE",
      "updated_memory": {
        "id": "0",
        "content": "User is a computer engineering student currently seeking help with a minor project",
        "type": "fact",
        "keywords": ["computer engineering", "student", "minor project", "help", "assistance"],
        "entities": ["computer engineering"],
        "confidence": 0.92,
        "memory_time": null,
        "updated_at": "2025-03-29T10:00:00Z"
      },
      "reason": "Merges new context (project help) into the existing comprehensive fact about user identity"
    },
    {
      "id": "1",
      "operation": "DELETE",
      "updated_memory": null,
      "reason": "Subsumed by updated existing[0] which now includes the project help context"
    }
  ]
}
```

**Net result**: 2 Qdrant points → 1 Qdrant point (richer, more accurate). Zero redundancy.

---

### MemoryOperation Return Value

Every call to `store()` returns `List[MemoryOperation]`, which records exactly what happened:

```python
class MemoryOperation(BaseModel):
    operation: str           # "ADD" | "UPDATE" | "DELETE" | "NONE"
    memory_id: Optional[str] # Qdrant UUID (for UPDATE/DELETE)
    content: str             # New or updated content
    old_content: Optional[str]  # Previous content (for UPDATE/DELETE, for audit)
```

This list flows back through `MemoryPipeline.run()` → `ProcessingHistory` → frontend `AnalyticsPanel`, giving you full visibility into what the pipeline actually changed in the memory store for each run.

---

### Configuration

Two config values affect PS2 behavior:

| Config Key | Default | Effect |
|---|---|---|
| `llm_memory_update_temperature` | 0.1 (low) | Low temperature = deterministic, consistent conflict decisions |
| `PS2_PROVIDER` / `PS2_MODEL` | same as PS1 | Can use a different (e.g., more capable) model for conflict resolution |

Using a low temperature for PS2 is intentional — conflict resolution requires precise, repeatable decisions, not creative variation.

---

## 19. Glossary

| Term | Definition |
|---|---|
| **Block** | A modular memory cartridge — an isolated context container with its own core memory, semantic memories, and sessions |
| **Session** | A single conversation thread associated with one block |
| **Core Memory** | Always-present profile: AI persona + user description (stored in MongoDB) |
| **Semantic Memory** | Individual facts, events, opinions extracted from conversations (stored in Qdrant) |
| **Episodic Memory** | The raw recent conversation window (stored in MongoDB, compressed into summary) |
| **Resource Memory** | Documents, links, and external content (Qdrant, planned/partial) |
| **PS1** | Phase 1 — LLM extraction of semantic memories from conversation text |
| **PS2** | Phase 2 — LLM conflict resolution before storing a memory |
| **Memory Pipeline** | The full PS1 → PS2 → Core Update → Summary process triggered when window fills |
| **Memory Window** | The buffer of recent raw messages (size controlled by `MEMORY_WINDOW`) |
| **Rolling Summary** | Recursively compressed conversation history stored per session |
| **RRF** | Reciprocal Rank Fusion — algorithm to merge dense and sparse search results |
| **SPLADE** | Sparse Lexical and Dense Expansion — sparse vector embedding model for keyword-aware retrieval |
| **HyDE** | Hypothetical Document Embeddings — generate a hypothetical answer to use as a search vector |
| **Query Expansion** | Rewriting one query into multiple phrasings to improve retrieval recall |
| **Cohere Reranking** | Cross-encoder model that rescores retrieved candidates for more accurate relevance ordering |
| **EventBus** | Internal pub/sub system for operational transparency |
| **MCP** | Model Context Protocol — standard for connecting AI assistants to external tools |
| **Clerk** | Third-party authentication service providing JWT-based auth |
| **UV Workspace** | Python monorepo management using the `uv` package manager |
