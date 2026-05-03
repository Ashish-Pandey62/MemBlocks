# memBlocks Library — Deep Technical Overview

This document provides an in-depth technical explanation of the memBlocks library architecture, data flow, and implementation details.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Configuration System](#2-configuration-system)
3. [Data Models & Relationships](#3-data-models--relationships)
4. [Storage Layer](#4-storage-layer)
5. [LLM Interface & Prompts](#5-llm-interface--prompts)
6. [Memory Pipeline](#6-memory-pipeline)
7. [Chat Engine & Session Flow](#7-chat-engine--session-flow)
8. [Transparency & Observability](#8-transparency--observability)
9. [Data Flow Diagrams](#9-data-flow-diagrams)
10. [Database Schemas & Collection Reference](#10-database-schemas--collection-reference)

---

## 1. Architecture Overview

### Design Philosophy

The memBlocks library is built on these core principles:

1. **No Global State** — All dependencies are injected via constructor; no singletons
2. **Layered Architecture** — Clear separation between models, storage, services, and client
3. **Config-Driven** — All external connections and behaviors configured via `MemBlocksConfig`
4. **Async-First** — All I/O operations are async for non-blocking performance
5. **Transparency Built-In** — Every operation is loggable and observable

### Package Structure

```
memblocks_lib/
└── src/memblocks/
    ├── __init__.py          # Public API exports
    ├── client.py            # MemBlocksClient (entry point)
    ├── config.py            # MemBlocksConfig (settings)
    │
    ├── models/              # Pure Pydantic data models
    │   ├── __init__.py
    │   ├── block.py         # MemoryBlock, MemoryBlockMetaData
    │   ├── memory.py        # (reserved)
    │   ├── units.py         # SemanticMemoryUnit, CoreMemoryUnit, etc.
    │   ├── retrieval.py     # RetrievalResult
    │   ├── llm_outputs.py   # LLM output schemas (PS1, PS2, etc.)
    │   └── transparency.py  # OperationEntry, RetrievalEntry, etc.
    │
    ├── storage/             # Database adapters
    │   ├── __init__.py
    │   ├── mongo.py         # MongoDBAdapter
    │   ├── qdrant.py        # QdrantAdapter
    │   └── embeddings.py    # EmbeddingProvider (Ollama)
    │
    ├── llm/                 # LLM abstraction
    │   ├── __init__.py
    │   ├── base.py              # LLMProvider (ABC)
    │   ├── task_settings.py     # LLMTaskSettings, LLMSettings
    │   ├── groq_provider.py     # GroqLLMProvider
    │   ├── gemini_provider.py   # GeminiLLMProvider
    │   ├── openrouter_provider.py # OpenRouterLLMProvider
    │   └── ollama_provider.py   # OllamaLLMProvider
    │
    ├── services/            # Business logic
    │   ├── __init__.py
    │   ├── user_manager.py      # User CRUD
    │   ├── block_manager.py     # Block lifecycle
    │   ├── block.py             # Block (stateful retrieval object)
    │   ├── session_manager.py   # Chat sessions
    │   ├── session.py           # Session (stateful session object)
    │   ├── semantic_memory.py   # Semantic memory (PS1 + PS2)
    │   ├── core_memory.py       # Core memory
    │   ├── memory_pipeline.py   # Background processing
    │   └── transparency.py      # Logging & events
    │
    └── prompts/             # LLM prompt templates
        └── __init__.py      # All 5 prompts
```

**Key Design Change:** The library no longer includes a `ChatEngine` or inference logic. Instead:
- `Block` — stateful object with retrieval methods (`retrieve()`, `core_retrieve()`, etc.)
- `Session` — stateful object with window management (`get_memory_window()`, `add()`)
- User controls their own LLM calls

### Architectural Layers

```
┌─────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              MemBlocksClient                         │    │
│  │  (wires everything together, flat API:               │    │
│  │   get_or_create_user, create_block, create_session)  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                          │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐ │
│  │UserManager │ │BlockManager│ │Block       │ │Session   │ │
│  │            │ │            │ │(retrieve)  │ │(add)     │ │
│  │SemMemory   │ │CoreMemory  │ │SessionMgr  │ │Pipeline  │ │
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       STORAGE LAYER                          │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │MongoDB     │ │Qdrant      │ │Embedding   │              │
│  │Adapter     │ │Adapter     │ │Provider    │              │
│  └────────────┘ └────────────┘ └────────────┘              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     INFRASTRUCTURE                           │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐              │
│  │MongoDB     │ │Qdrant      │ │Ollama      │              │
│  │(motor)     │ │(qdrant-cli)│ │(HTTP API)  │              │
│  └────────────┘ └────────────┘ └────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

**Key Change:** No more `ChatEngine` layer. The user calls `block.retrieve()` and `session.add()` directly, then makes their own LLM calls.

### Dependency Injection Pattern

The library uses constructor injection throughout. No globals, no module-level singletons.

**Example: How MemBlocksClient wires dependencies:**

```python
class MemBlocksClient:
    def __init__(self, config: MemBlocksConfig, ...):
        # 1. Infrastructure adapters
        self.mongo = MongoDBAdapter(config)
        self.embeddings = EmbeddingProvider(config)
        self.qdrant = QdrantAdapter(config, self.embeddings)

        # 2. Per-task LLM providers (resolved from config.resolved_llm_settings)
        llm_settings = config.resolved_llm_settings
        self.conversation_llm = self._build_provider(llm_settings.for_task("conversation"), config)
        self._ps1_llm  = self._build_provider(llm_settings.for_task("ps1_semantic_extraction"), config)
        self._ps2_llm  = self._build_provider(llm_settings.for_task("ps2_conflict_resolution"), config)
        self._core_llm = self._build_provider(llm_settings.for_task("core_memory_extraction"), config)
        self._summary_llm = self._build_provider(llm_settings.for_task("recursive_summary"), config)
        # self.llm is a property alias for self.conversation_llm (backward compatible)

        # 3. Transparency objects
        self.event_bus = EventBus()
        self.operation_log = OperationLog()
        self.retrieval_log = RetrievalLog()

        # 4. Services (receive their specific per-task providers)
        self._users = UserManager(self.mongo)
        self._core = CoreMemoryService(
            core_llm=self._core_llm, mongo=self.mongo, config=config,
            operation_log=self.operation_log, event_bus=self.event_bus
        )
        self._blocks = BlockManager(
            mongo=self.mongo, qdrant=self.qdrant, embeddings=self.embeddings,
            ps1_llm=self._ps1_llm, ps2_llm=self._ps2_llm,
            core_memory_service=self._core, config=config,
            operation_log=self.operation_log, retrieval_log=self.retrieval_log
        )
        self._sessions = SessionManager(
            mongo=self.mongo, ps1_llm=self._ps1_llm, ps2_llm=self._ps2_llm,
            summary_llm=self._summary_llm, qdrant=self.qdrant,
            embeddings=self.embeddings, core_memory_service=self._core,
            config=config, ...
        )
```

**Flat API (public methods):**

```python
# User management (flat, not sub-manager)
await client.get_or_create_user("alice")
await client.get_user("alice")

# Block management (flat, returns Block objects)
block = await client.create_block(user_id="alice", name="Work")
block = await client.get_block(block_id)

# Session management (flat, returns Session objects)
session = await client.create_session(user_id="alice", block_id=block.id)
session = await client.get_session(session_id)
```

**Benefits:**
- Easy to mock for testing
- Multiple clients can coexist with different configs
- No hidden state or import-time side effects

### Public API Surface

The `__init__.py` exports a minimal, stable API:

```python
from memblocks import (
    # Entry point
    MemBlocksClient,
    MemBlocksConfig,

    # Stateful objects (returned by client methods)
    Block,        # block.retrieve(), block.core_retrieve(), etc.
    Session,      # session.get_memory_window(), session.add()
    RetrievalResult,  # context.to_prompt_string(), context.is_empty()

    # LLM (for custom providers or per-task config)
    LLMProvider,
    GroqLLMProvider,
    GeminiLLMProvider,
    # OpenRouterLLMProvider is exported from memblocks.llm
    LLMTaskSettings,
    LLMSettings,

    # Models (for type hints)
    MemoryBlock,
    MemoryBlockMetaData,
    SemanticMemoryUnit,
    CoreMemoryUnit,
    ResourceMemoryUnit,
    MemoryOperation,
)
```

**New Design Pattern:**

```python
# Library gives you tools, YOU control the LLM
block = await client.create_block(user_id="alice", name="Memory")
session = await client.create_session(user_id="alice", block_id=block.id)

# Per-turn loop
context = await block.retrieve(user_msg)        # Get memories
messages = await session.get_memory_window()    # Get history
summary = await session.get_recursive_summary() # Get summary

# Build prompt and call YOUR LLM
system = "You are helpful.\n\n" + context.to_prompt_string()
response = await client.conversation_llm.chat([...])

# Persist the turn
await session.add(user_msg=user_msg, ai_response=response)
```

Internal modules (`services.*`, `storage.*`) are accessible but not part of the stable API.

---

## 2. Configuration System

### MemBlocksConfig Overview

The `MemBlocksConfig` class is a Pydantic `BaseSettings` model that centralizes all configuration. It reads from:

1. **Constructor arguments** (highest priority)
2. **Environment variables**
3. **`.env` file** in the current working directory
4. **Default values** (lowest priority)

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class MemBlocksConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,  # allow field name as well as alias
        extra="ignore",         # silently ignore unknown env vars
    )
```

### Configuration Categories

#### LLM Configuration

| Field | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `llm_provider_name` | `LLM_PROVIDER_NAME` | `groq` | Active provider: `"groq"`, `"gemini"`, `"openrouter"`, or `"ollama"` (used when `llm_settings` is not set) |
| `groq_api_key` | `GROQ_API_KEY` | `None` | Groq API key |
| `gemini_api_key` | `GEMINI_API_KEY` | `None` | Google Gemini API key |
| `openrouter_api_key` | `OPENROUTER_API_KEY` | `None` | OpenRouter API key |
| `ollama_base_url` | `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `llm_model` | `LLM_MODEL` | `moonshotai/kimi-k2-instruct-0905` | Model identifier (used when `llm_settings` is not set) |
| `llm_settings` | *(code only)* | `None` | `LLMSettings` object for per-task provider routing; when set, takes precedence over flat fields |
| `openrouter_fallback_models` | `OPENROUTER_FALLBACK_MODELS` | `""` | Comma-separated fallback model IDs for OpenRouter |
| `openrouter_enable_thinking` | `OPENROUTER_ENABLE_THINKING` | `false` | Enable extended thinking for OpenRouter |
| `llm_convo_temperature` | `LLM_CONVO_TEMPERATURE` | `0.7` | Chat response temperature (legacy flat config) |
| `llm_semantic_extraction_temperature` | `LLM_SEMANTIC_EXTRACTION_TEMPERATURE` | `0.0` | PS1 extraction temp (legacy flat config) |
| `llm_core_extraction_temperature` | `LLM_CORE_EXTRACTION_TEMPERATURE` | `0.0` | Core memory temp (legacy flat config) |
| `llm_recursive_summary_gen_temperature` | `LLM_RECURSIVE_SUMMARY_GEN_TEMPERATURE` | `0.3` | Summary temp (legacy flat config) |
| `llm_memory_update_temperature` | `LLM_MEMORY_UPDATE_TEMPERATURE` | `0.0` | PS2 conflict temp (legacy flat config) |

**`resolved_llm_settings` property:**

`MemBlocksConfig.resolved_llm_settings` returns:
- `llm_settings` as-is when set
- An auto-constructed `LLMSettings` from the flat legacy fields when `llm_settings` is `None`

This means existing code that uses flat env vars continues to work without any changes.

**Temperature Rationale:**
- `0.0` for extraction tasks → deterministic, consistent outputs
- `0.3` for summaries → slight variation acceptable
- `0.7` for chat → natural, varied conversation

#### MongoDB Configuration

| Field | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `mongodb_connection_string` | `MONGODB_CONNECTION_STRING` | *required* | Connection URI |
| `mongodb_database_name` | `MONGODB_DATABASE_NAME` | `memblocks_v2` | Database name |
| `mongo_collection_users` | `MONGO_COLLECTION_USERS` | `users` | Users collection |
| `mongo_collection_blocks` | `MONGO_COLLECTION_BLOCKS` | `memory_blocks` | Blocks collection |
| `mongo_collection_core_memories` | `MONGO_COLLECTION_CORE_MEMORIES` | `core_memories` | Core memories collection |

#### Qdrant Configuration

| Field | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `qdrant_host` | `QDRANT_HOST` | `localhost` | Qdrant server host |
| `qdrant_port` | `QDRANT_PORT` | `6333` | REST API port |
| `qdrant_prefer_grpc` | `QDRANT_PREFER_GRPC` | `true` | Use gRPC when available |
| `semantic_collection_template` | `SEMANTIC_COLLECTION_TEMPLATE` | `{block_id}_semantic` | Semantic collection naming |
| `resource_collection_template` | `RESOURCE_COLLECTION_TEMPLATE` | `{block_id}_resource` | Resource collection naming |

#### Ollama / Embeddings Configuration

| Field | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `ollama_base_url` | `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `embeddings_model` | `EMBEDDINGS_MODEL` | `nomic-embed-text` | Model for embeddings |

#### Pipeline Behavior

| Field | Env Var | Default | Description |
|-------|---------|---------|-------------|
| `memory_window_limit` | `MEMORY_WINDOW` | `10` | Messages before pipeline trigger |
| `keep_last_n` | `KEEP_LAST_N` | `4` | Messages retained after flush |

### Dynamic Collection Naming

The config provides helper methods for generating Qdrant collection names:

```python
config = MemBlocksConfig()

# Returns "block_abc123_semantic"
semantic_col = config.semantic_collection("block_abc123")

# Returns "block_abc123_resource"
resource_col = config.resource_collection("block_abc123")
```

Templates can be customized:

```python
config = MemBlocksConfig(
    semantic_collection_template="user_{user_id}_block_{block_id}_memories"
)
```

### Usage Patterns

#### Pattern 1: Environment Variables (Recommended for Production)

```bash
# .env or system environment
export GROQ_API_KEY=gsk_xxx
export MONGODB_CONNECTION_STRING=mongodb://prod-server:27017
export QDRANT_HOST=qdrant.prod.internal
```

```python
from memblocks import MemBlocksConfig

config = MemBlocksConfig()  # Reads from environment
```

#### Pattern 2: Explicit Constructor (Recommended for Testing)

```python
config = MemBlocksConfig(
    groq_api_key="gsk_test_key",
    mongodb_connection_string="mongodb://localhost:27017",
    qdrant_host="localhost",
    memory_window_limit=5,
)
```

#### Pattern 3: Override Specific Values

```python
# Load from .env, but override one value
config = MemBlocksConfig(
    memory_window_limit=20,  # Larger window for this instance
)
```

### Validation

Pydantic validates all fields at construction time:

```python
# Missing required field raises ValidationError
config = MemBlocksConfig()  # Error if GROQ_API_KEY not set

# Invalid type raises ValidationError  
config = MemBlocksConfig(memory_window_limit="invalid")  # Error: must be int
```

---

## 3. Data Models & Relationships

The library uses Pydantic v2 models for all data structures. Models are organized into three categories:

### Model Categories

```
models/
├── block.py        # MemoryBlock, MemoryBlockMetaData
├── units.py        # SemanticMemoryUnit, CoreMemoryUnit, ResourceMemoryUnit
├── llm_outputs.py  # Structured outputs for LLM calls
└── transparency.py # OperationEntry, RetrievalEntry, PipelineRunEntry
```

---

### Core Domain Models

#### MemoryBlock

A memory block is the primary container for user memory. Each block has:
- A unique ID and metadata
- Optional Qdrant collections for semantic/resource memories
- A core memory reference in MongoDB

```python
class MemoryBlock(BaseModel):
    meta_data: MemoryBlockMetaData     # ID, timestamps, user_id
    name: str                          # Human-readable name
    description: str                   # Purpose/domain description
    semantic_collection: Optional[str] # Qdrant collection name
    core_memory_block_id: Optional[str]# MongoDB key for core memory
    resource_collection: Optional[str] # Qdrant collection for resources
    is_active: bool = False            # Current active status
```

**Relationship Diagram:**

```
┌─────────────────────────────────────────────────────────────┐
│                      MemoryBlock                             │
│  meta_data.id: "block_abc123"                                │
│  name: "Work Memory"                                         │
│  user_id: "alice"                                            │
├─────────────────────────────────────────────────────────────┤
│  semantic_collection ──► Qdrant: "block_abc123_semantic"    │
│  core_memory_block_id ─► MongoDB: core_memories collection  │
│  resource_collection ──► Qdrant: "block_abc123_resource"    │
└─────────────────────────────────────────────────────────────┘
```

#### MemoryUnitMetaData

Shared metadata for individual memory units:

```python
class MemoryUnitMetaData(BaseModel):
    usage: List[str] = []              # Access timestamps
    status: Literal["active", "archived", "deleted"] = "active"
    message_ids: List[str] = []        # Source message references
```

---

### Memory Unit Types

#### SemanticMemoryUnit

Stored in Qdrant for vector similarity search. Contains episodic and factual memories.

```python
class SemanticMemoryUnit(BaseModel):
    content: str                       # The memory statement
    type: Literal["fact", "event", "opinion"]
    source: Optional[str]              # "conversation", "document", etc.
    confidence: float                  # 0.0 to 1.0
    memory_time: Optional[str]         # ISO timestamp for events
    updated_at: str                    # Last modification time
    meta_data: Optional[MemoryUnitMetaData]
    keywords: List[str] = []           # For retrieval optimization
    embedding_text: Optional[str]      # Text used for embedding
    entities: List[str] = []           # Named entities
```

**Memory Types:**

| Type | Description | Example |
|------|-------------|---------|
| `fact` | Objective, verifiable knowledge | "User is a software engineer" |
| `event` | Time-bound occurrence | "User deployed the API yesterday" |
| `opinion` | Subjective preference | "User prefers PostgreSQL over MySQL" |

#### CoreMemoryUnit

Stored in MongoDB. Contains stable, persistent facts about the user and AI persona.

```python
class CoreMemoryUnit(BaseModel):
    persona_content: str  # How the AI should behave (2-3 sentences)
    human_content: str    # Stable facts about the user (5-7 sentences)
```

**Example:**

```python
CoreMemoryUnit(
    persona_content="The AI is helpful and concise. It provides technical "
                    "explanations when appropriate.",
    human_content="User is named Alice, a software engineer in NYC. "
                  "She is learning machine learning and prefers PyTorch."
)
```

#### ResourceMemoryUnit

For external resources (documents, images, links).

```python
class ResourceMemoryUnit(BaseModel):
    content: str
    resource_type: Literal["document", "image", "video", "audio", "link", "extracted"]
    resource_link: Optional[str]
```

---

### LLM Output Models

These models define the structured output schemas for LLM calls.

#### PS1: Semantic Extraction

```python
class SemanticExtractionOutput(BaseModel):
    keywords: List[str]
    content: str
    type: str           # "fact" | "event" | "opinion"
    entities: List[str]
    confidence: float

class SemanticMemoriesOutput(BaseModel):
    memories: List[SemanticExtractionOutput]
```

Used by: `SemanticMemoryService.extract()` with `PS1_SEMANTIC_PROMPT`

#### PS2: Conflict Resolution

```python
class PS2NewMemoryOperation(BaseModel):
    operation: Literal["ADD", "NONE"]
    reason: Optional[str]

class PS2ExistingMemoryOperation(BaseModel):
    id: str
    operation: Literal["UPDATE", "DELETE", "NONE"]
    updated_memory: Optional[Dict]
    reason: Optional[str]

class PS2MemoryUpdateOutput(BaseModel):
    new_memory_operation: PS2NewMemoryOperation
    existing_memory_operations: List[PS2ExistingMemoryOperation]
```

Used by: `SemanticMemoryService.store()` with `PS2_MEMORY_UPDATE_PROMPT`

#### Core Memory Extraction

```python
class CoreMemoryOutput(BaseModel):
    persona_content: str
    human_content: str
```

Used by: `CoreMemoryService.extract()` with `CORE_MEMORY_PROMPT`

#### Summary Generation

```python
class SummaryOutput(BaseModel):
    summary: str
```

Used by: `MemoryPipeline._generate_summary()` with `SUMMARY_SYSTEM_PROMPT`

---

### Operation Tracking Models

#### MemoryOperation

Tracks individual memory operations during pipeline processing.

```python
class MemoryOperation(BaseModel):
    operation: Literal["ADD", "UPDATE", "DELETE", "NONE"]
    memory_id: Optional[str]   # Qdrant point ID
    content: str
    old_content: Optional[str] # Previous content for UPDATE
```

#### ProcessingEvent

Records a complete pipeline run.

```python
class ProcessingEvent(BaseModel):
    event_id: str
    timestamp: str
    messages_processed: int
    operations: List[MemoryOperation]
```

---

### Model Relationships Summary

```
User (MongoDB: users)
  │
  ├── has many ──► MemoryBlock (MongoDB: memory_blocks)
  │                    │
  │                    ├── has one ──► CoreMemoryUnit (MongoDB: core_memories)
  │                    │
  │                    └── has many ──► SemanticMemoryUnit (Qdrant: {block_id}_semantic)
  │
  └── has many ──► Session (MongoDB: sessions)
                       │
                       └── belongs to ──► MemoryBlock
```

---

## 4. Storage Layer

The storage layer provides adapters for MongoDB, Qdrant, and Ollama embeddings. All adapters are:

- **Non-singleton** — instantiated with config
- **Async** — use motor for MongoDB, async HTTP for embeddings
- **Config-driven** — connection details from `MemBlocksConfig`

---

### MongoDBAdapter

Manages persistent storage for users, blocks, core memories, and sessions.

**Location:** `storage/mongo.py`

#### Constructor

```python
class MongoDBAdapter:
    def __init__(
        self,
        config: MemBlocksConfig,
        operation_log: Optional[OperationLog] = None,
    ):
        self._client = AsyncIOMotorClient(config.mongodb_connection_string)
        self._db = self._client[config.mongodb_database_name]
        
        # Collections
        self.users = self._db[config.mongo_collection_users]
        self.blocks = self._db[config.mongo_collection_blocks]
        self.core_memories = self._db[config.mongo_collection_core_memories]
        self.sessions = self._db["sessions"]
```

#### Method Categories

**User Operations:**

| Method | Description |
|--------|-------------|
| `create_user(user_id, metadata)` | Insert new user document |
| `get_user(user_id)` | Find user by ID |
| `add_block_to_user(user_id, block_id)` | Add block reference to user |
| `list_users()` | Return all users |

**Block Operations:**

| Method | Description |
|--------|-------------|
| `create_memory_block(user_id, block_data)` | Insert block document |
| `get_memory_block(block_id)` | Find block by ID |
| `list_user_blocks(user_id)` | Get all blocks for a user |
| `delete_memory_block(block_id)` | Remove block document |
| `save_block(block_data)` | Upsert block |

**Core Memory Operations:**

| Method | Description |
|--------|-------------|
| `save_core_memory(block_id, persona, human)` | Upsert core memory |
| `get_core_memory(block_id)` | Get core memory for block |
| `delete_core_memory(block_id)` | Remove core memory |

**Session Operations:**

| Method | Description |
|--------|-------------|
| `create_session(session_data)` | Insert session document |
| `get_session(session_id)` | Find session by ID |
| `update_session(session_id, update_data)` | Update session fields |
| `add_message_to_session(session_id, message)` | Append message to history |
| `get_session_messages(session_id, limit)` | Get recent messages |
| `get_session_message_count(session_id)` | Count messages |
| `clear_session_messages(session_id)` | Clear message history |

#### Serialization

MongoDB `ObjectId` fields are converted to strings for JSON compatibility:

```python
@staticmethod
def _serialize_doc(doc):
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc
```

---

### QdrantAdapter

Manages vector storage for semantic memories with similarity search.

**Location:** `storage/qdrant.py`

#### Constructor

```python
class QdrantAdapter:
    def __init__(
        self,
        config: MemBlocksConfig,
        embeddings: Optional[EmbeddingProvider] = None,
        operation_log: Optional[OperationLog] = None,
    ):
        self._client = QdrantClient(
            host=config.qdrant_host,
            port=config.qdrant_port,
            prefer_grpc=config.qdrant_prefer_grpc,
        )
        self._embeddings = embeddings
        self._vector_size = None  # Resolved lazily
```

#### Lazy Vector Dimension Resolution

Vector size is determined on first `create_collection` call:

```python
def _get_vector_size(self) -> int:
    if self._vector_size is None:
        if self._embeddings is None:
            raise RuntimeError("Need EmbeddingProvider for vector dimension")
        self._vector_size = self._embeddings.get_dimension()
    return self._vector_size
```

This avoids import-time HTTP calls (a bug in the original `VectorDBManager`).

#### Method Categories

**Collection Management:**

| Method | Description |
|--------|-------------|
| `create_collection(name, vector_size)` | Create collection if not exists |

**Vector Operations:**

| Method | Description |
|--------|-------------|
| `store_vector(collection, vector, payload, point_id)` | Upsert single vector |
| `retrieve_from_vector(collection, query_vector, top_k)` | Similarity search |
| `retrieve_from_payload(collection, filter, top_k)` | Filter by metadata |
| `delete_vector(collection, point_id)` | Remove vector |
| `get_all_points(collection, limit)` | List all points (debug) |

#### Collection Creation

```python
def create_collection(self, collection_name: str, vector_size: int = None) -> bool:
    resolved_size = vector_size or self._get_vector_size()
    
    # Check if exists
    collections = self._client.get_collections().collections
    if any(col.name == collection_name for col in collections):
        return True
    
    # Create with COSINE distance
    self._client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=resolved_size,
            distance=Distance.COSINE,
        ),
    )
    return True
```

#### Vector Storage

```python
def store_vector(self, collection_name, vector, payload, point_id=None) -> bool:
    resolved_id = point_id or str(uuid4())
    self._client.upsert(
        collection_name=collection_name,
        points=[
            PointStruct(
                id=resolved_id,
                vector=vector,
                payload=payload,
            )
        ],
        wait=False,  # Async write
    )
    return True
```

---

### EmbeddingProvider

Wraps Ollama's embedding API for text vectorization.

**Location:** `storage/embeddings.py`

#### Constructor

```python
class EmbeddingProvider:
    def __init__(self, config: MemBlocksConfig):
        self._model = config.embeddings_model
        self._base_url = config.ollama_base_url
        self._endpoint = f"{config.ollama_base_url}/api/embeddings"
```

#### Methods

| Method | Description |
|--------|-------------|
| `embed_text(text) -> List[float]` | Embed single text |
| `embed_documents(texts) -> List[List[float]]` | Embed multiple texts in parallel |
| `get_dimension() -> int` | Return embedding dimension |

#### Single Text Embedding

```python
def embed_text(self, text: str) -> List[float]:
    payload = {"model": self._model, "prompt": text}
    response = requests.post(self._endpoint, json=payload, timeout=30)
    response.raise_for_status()
    return response.json().get("embedding")
```

#### Parallel Document Embedding

```python
def embed_documents(self, texts: List[str]) -> List[List[float]]:
    with ThreadPoolExecutor(max_workers=min(10, len(texts))) as executor:
        return list(executor.map(self.embed_text, texts))
```

#### Dimension Detection

```python
def get_dimension(self) -> int:
    sample = self.embed_text("test")
    return len(sample)
```

---

### Storage Layer Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        MemBlocksClient                           │
│                                                                  │
│  mongo ────────────► MongoDBAdapter ──────► MongoDB              │
│  (users, blocks,    (motor async)           (users, blocks,      │
│   core_memories,                              core_memories,      │
│   sessions)                                   sessions)           │
│                                                                  │
│  embeddings ──────► EmbeddingProvider ────► Ollama               │
│  (text → vector)    (HTTP/REST)             (nomic-embed-text)   │
│         │                                                        │
│         ▼                                                        │
│  qdrant ──────────► QdrantAdapter ─────────► Qdrant              │
│  (semantic          (qdrant-client)         ({block_id}_semantic)│
│   memories)                                                      │
└─────────────────────────────────────────────────────────────────┘
```

---

### Key Design Decisions

1. **No singletons** — Old code used `__new__` to enforce singletons; this caused issues with async event loops

2. **Lazy connections** — Connections are created in constructor, not at import time

3. **Config-driven collection names** — No hardcoded collection names

4. **Operation logging** — Optional `OperationLog` parameter for transparency

5. **Graceful error handling** — Errors are caught and logged, not silently swallowed

---

## 5. LLM Interface & Prompts

The LLM layer provides an abstraction over LLM providers, with a default implementation using Groq via LangChain.

---

### LLMProvider (Abstract Base Class)

The `LLMProvider` abstract class defines a minimal, generic interface. Services compose prompts and call these methods.

**Location:** `llm/base.py`

```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    
    @abstractmethod
    def create_structured_chain(
        self,
        system_prompt: str,
        pydantic_model: Type[BaseModel],
        temperature: float = 0.0,
    ) -> Any:
        """Return a runnable that outputs a Pydantic model."""
        ...
    
    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> str:
        """Send messages and return assistant response text."""
        ...
```

**Design Rationale:**

The interface is intentionally minimal (2 methods). An earlier design had 5+ domain-specific methods like `extract_semantic_memories()`, but those are *service* responsibilities. The LLM interface is generic so any backend (OpenAI, Anthropic, local models, mocks) can implement it without understanding memBlocks internals.

---

### GroqLLMProvider (Default Implementation)

Uses `langchain_groq.ChatGroq` for structured outputs and chat.

**Location:** `llm/groq_provider.py`

**Structured output** uses Groq's native `json_schema` mode.

**Factory:** `GroqLLMProvider.from_task_settings(task_settings, api_key)` — used internally when building per-task providers.

### GeminiLLMProvider

Uses `langchain_google_genai.ChatGoogleGenerativeAI` for structured outputs and chat.

**Location:** `llm/gemini_provider.py`

**Structured output** uses Gemini's native structured output mode (`llm.with_structured_output(model, include_raw=False)`).

**Factory:** `GeminiLLMProvider.from_task_settings(task_settings, api_key)`.

### OpenRouterLLMProvider

Uses `langchain_openai.ChatOpenAI` pointed at the OpenRouter API base URL.

**Location:** `llm/openrouter_provider.py`

**Unique features:**
- `fallback_models` — list of model IDs tried in order when the primary model fails
- `enable_thinking` — passes `extra_body={"enable_thinking": True}` to the API for reasoning models

**Factory:** `OpenRouterLLMProvider.from_task_settings(task_settings, api_key)`.

### OllamaLLMProvider

Uses `langchain_ollama.ChatOllama` to run open-source models locally.

**Location:** `llm/ollama_provider.py`

**Structured output** uses Ollama's JSON mode (`format="json"`).

**Factory:** `OllamaLLMProvider.from_task_settings(task_settings, base_url)`.

**Prerequisites:**
1. Install Ollama: https://ollama.com
2. Run `ollama serve`
3. Pull a model: `ollama pull llama3.2:3b`

### Per-Task LLM System

**Location:** `llm/task_settings.py`

```python
class LLMTaskSettings(BaseModel):
    provider: str                        # "groq" | "gemini" | "openrouter" | "ollama"
    model: str
    temperature: float = 0.0
    fallback_models: List[str] = []      # OpenRouter only
    enable_thinking: bool = False        # OpenRouter only

class LLMSettings(BaseModel):
    default: LLMTaskSettings             # Required; fallback for all tasks
    conversation: Optional[LLMTaskSettings] = None
    ps1_semantic_extraction: Optional[LLMTaskSettings] = None
    ps2_conflict_resolution: Optional[LLMTaskSettings] = None
    retrieval: Optional[LLMTaskSettings] = None
    core_memory_extraction: Optional[LLMTaskSettings] = None
    recursive_summary: Optional[LLMTaskSettings] = None

    def for_task(self, task_name: str) -> LLMTaskSettings:
        """Return the override for task_name, or default."""
        return getattr(self, task_name, None) or self.default
```

`MemBlocksClient._build_provider(task_settings, config)` instantiates the correct provider class based on `task_settings.provider` and reads the API key from `config`.

---

### Prompt Templates

All 5 prompts are centralized in `prompts/__init__.py`.

#### PS1_SEMANTIC_PROMPT

**Purpose:** Extract structured semantic memories from conversation.

**Used by:** `SemanticMemoryService.extract()`

**Output model:** `SemanticMemoriesOutput`

**Key instructions:**
- Extract **atomic** memories (one fact per unit)
- No duplicates within batch
- Self-contained, readable content
- 3-6 keywords ranked by importance
- Classify as `fact`, `event`, or `opinion`

```
┌─────────────────────────────────────────────────────────────┐
│ PS1: Semantic Memory Extraction                              │
├─────────────────────────────────────────────────────────────┤
│ Input:  Conversation messages                                │
│ Output: { "memories": [ {content, type, keywords, ...} ] }   │
└─────────────────────────────────────────────────────────────┘
```

#### PS2_MEMORY_UPDATE_PROMPT

**Purpose:** Resolve conflicts between new and existing memories.

**Used by:** `SemanticMemoryService.store()`

**Output model:** `PS2MemoryUpdateOutput`

**Key instructions:**
- Decide ADD or NONE for new memory
- Decide UPDATE, DELETE, or NONE for each existing memory
- Aggressive deduplication (>80% overlap → merge/discard)
- Hard DELETE (not soft delete)

```
┌─────────────────────────────────────────────────────────────┐
│ PS2: Memory Conflict Resolution                              │
├─────────────────────────────────────────────────────────────┤
│ Input:  New memory + existing similar memories               │
│ Output: { new_memory_operation, existing_memory_operations } │
└─────────────────────────────────────────────────────────────┘
```

#### CORE_MEMORY_PROMPT

**Purpose:** Update AI persona and user facts.

**Used by:** `CoreMemoryService.extract()`

**Output model:** `CoreMemoryOutput`

**Key instructions:**
- Two sections: PERSONA (AI behavior) and HUMAN (user facts)
- Preserve existing information unless contradicted
- Minimal updates only for stable facts
- Ignore temporary details

```
┌─────────────────────────────────────────────────────────────┐
│ Core Memory Extraction                                       │
├─────────────────────────────────────────────────────────────┤
│ Input:  Old core memory + recent conversation                │
│ Output: { persona_content, human_content }                   │
└─────────────────────────────────────────────────────────────┘
```

#### SUMMARY_SYSTEM_PROMPT

**Purpose:** Generate recursive conversation summaries.

**Used by:** `MemoryPipeline._generate_summary()`

**Output model:** `SummaryOutput`

**Key instructions:**
- Incremental: build on previous summary
- Capture topics, decisions, constraints
- Maintain temporal ordering
- Concise but complete

```
┌─────────────────────────────────────────────────────────────┐
│ Recursive Summary Generation                                 │
├─────────────────────────────────────────────────────────────┤
│ Input:  Previous summary + new messages                      │
│ Output: { "summary": "..." }                                 │
└─────────────────────────────────────────────────────────────┘
```

#### ASSISTANT_BASE_PROMPT

**Purpose:** Base system prompt for chat responses.

**Used by:** The caller — include in your system prompt as a starting point for the conversation LLM.

```python
ASSISTANT_BASE_PROMPT = """You are a helpful AI assistant with access to persistent memory.

When using context:
- Synthesize information rather than repeating it
- If semantic memories and resources overlap, cite the resource as primary source
- Provide concise, informed responses based on available context"""
```

---

### Prompt Usage Map

| Prompt | Service | Method | Output Model |
|--------|---------|--------|--------------|
| `PS1_SEMANTIC_PROMPT` | SemanticMemoryService | `extract()` | `SemanticMemoriesOutput` |
| `PS2_MEMORY_UPDATE_PROMPT` | SemanticMemoryService | `store()` | `PS2MemoryUpdateOutput` |
| `CORE_MEMORY_PROMPT` | CoreMemoryService | `extract()` | `CoreMemoryOutput` |
| `SUMMARY_SYSTEM_PROMPT` | MemoryPipeline | `_generate_summary()` | `SummaryOutput` |
| `ASSISTANT_BASE_PROMPT` | *(user-controlled)* | *(included in system prompt by user)* | (plain text) |

---

### Custom LLM Provider

To use a different LLM backend, implement `LLMProvider`:

```python
from memblocks.llm.base import LLMProvider

class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4"):
        self._client = OpenAI(api_key=api_key)
        self._model = model
    
    def create_structured_chain(self, system_prompt, pydantic_model, temperature=0.0):
        # Return a LangChain Runnable or compatible object
        ...
    
    async def chat(self, messages, temperature=None):
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature or 0.7,
        )
        return response.choices[0].message.content
```

Then inject into `MemBlocksClient` after construction:

```python
client = MemBlocksClient(config)
client.conversation_llm = OpenAIProvider(api_key="sk-xxx")
# client.llm is a property alias for client.conversation_llm
```

> **Note:** `conversation_llm` only overrides the conversation provider. Internal pipeline tasks (PS1, PS2, core memory, summary) continue using the providers resolved from config. To override those too, use `LLMSettings` / `LLMTaskSettings` in the config instead.

---

## 6. Memory Pipeline

The memory pipeline is the heart of memBlocks. It processes accumulated conversation messages and extracts/updates all memory types.

**Location:** `services/memory_pipeline.py`

---

### Pipeline Overview

The pipeline runs **asynchronously in the background** when the message window is full:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Memory Pipeline Flow                          │
│                                                                  │
│  1. Semantic Extraction (PS1)                                    │
│     └── Extract atomic memories from conversation                │
│                                                                  │
│  2. Conflict Resolution (PS2) + Storage                          │
│     └── For each memory: deduplicate, update, or delete          │
│                                                                  │
│  3. Core Memory Update                                           │
│     └── Update persona + human facts                             │
│                                                                  │
│  4. Recursive Summary Generation                                 │
│     └── Merge into running summary                               │
│                                                                  │
│  5. Message History Flush                                        │
│     └── Keep last N messages, discard processed ones             │
└─────────────────────────────────────────────────────────────────┘
```

---

### Triggering the Pipeline

The pipeline is triggered by `Session.add()` when message count reaches `memory_window_limit`:

```python
# In Session.add()
msg_count = await self._mongo.get_session_message_count(self.id)

if msg_count >= self._memory_window:
    messages = await self._mongo.get_session_messages(self.id, limit=msg_count)
    current_summary = await self._mongo.get_session_summary(self.id)
    
    new_summary = await self._pipeline.run(
        user_id=self.user_id,
        block_id=self.block_id,
        messages=messages,
        current_summary=current_summary,
    )
    
    # Persist updated summary and trim messages
    await self._mongo.set_session_summary(self.id, new_summary)
    await self._mongo.trim_session_messages(self.id, self._keep_last_n)
```

**Key points:**
- `pipeline.run()` is a plain async function (not fire-and-forget)
- User decides whether to await inline or use `asyncio.create_task()`
- Summary is persisted to MongoDB (survives restarts)
- Messages are trimmed in MongoDB after pipeline runs

---

### MemoryPipeline Class

#### Constructor

```python
class MemoryPipeline:
    def __init__(
        self,
        semantic_memory_service: SemanticMemoryService,
        core_memory_service: CoreMemoryService,
        summary_llm: LLMProvider,
        config: MemBlocksConfig,
        keep_last_n: int = 4,
        processing_history: Optional[ProcessingHistory] = None,
        operation_log: Optional[OperationLog] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self._semantic = semantic_memory_service
        self._core = core_memory_service
        self._llm = summary_llm
        self._config = config
        self._keep_last_n = keep_last_n
```

#### run() Method

```python
async def run(
    self,
    user_id: str,
    block_id: str,
    messages: List[Dict[str, str]],
    current_summary: str,
) -> str:
    """Run pipeline and return new summary. Plain async function."""
    # ... run all steps ...
    return new_summary
```

**Key change from old design:**
- `trigger()` (fire-and-forget) → `run()` (plain async)
- No more `task_id` tracking
- No more `_TaskRecord` / `TaskStatus`
- No more internal `asyncio.Lock` / `Semaphore`
- Returns the new summary directly

---

### Step-by-Step Pipeline Execution

#### Step 1: Semantic Memory Extraction (PS1)

```python
print("   → STEP 1: Semantic Extraction...")
semantic_memories = await self._semantic.extract(messages)
print(f"   ✓ Extracted {len(semantic_memories)} semantic memories")
```

**What happens:**
1. Conversation text is formatted for LLM
2. LLM receives `PS1_SEMANTIC_PROMPT`
3. Returns `SemanticMemoriesOutput` with list of memories
4. Each memory gets `embedding_text` generated

#### Step 2: Conflict Resolution & Storage (PS2)

```python
for mem in semantic_memories:
    ops = await self._semantic.store(mem)
    all_operations.extend(ops)
```

**For each extracted memory:**

1. **Embed** the memory content
2. **Search Qdrant** for similar existing memories (top 5)
3. **LLM conflict resolution** with `PS2_MEMORY_UPDATE_PROMPT`
4. **Execute operations:**
   - `ADD` — store new vector in Qdrant
   - `UPDATE` — replace existing vector with merged content
   - `DELETE` — remove existing vector
   - `NONE` — skip (redundant)

**PS2 Decision Flow:**

```
┌─────────────────┐
│ New Memory      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│ Similar found?  │──NO─►│ ADD new memory  │
└────────┬────────┘     └─────────────────┘
         │YES
         ▼
┌─────────────────────────────────────────┐
│ LLM compares new vs existing             │
│                                          │
│ New memory: ADD or NONE?                 │
│ Each existing: UPDATE, DELETE, or NONE?  │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Execute ops in  │
│ Qdrant          │
└─────────────────┘
```

#### Step 3: Core Memory Update

```python
print("   → STEP 2: Core Memory Update...")
await self._core.update(block_id=block_id, messages=messages)
print("   ✓ Updated core memory")
```

**What happens:**
1. Load existing core memory from MongoDB
2. Format with conversation for LLM
3. LLM receives `CORE_MEMORY_PROMPT`
4. Returns updated `persona_content` and `human_content`
5. Upsert to MongoDB

**Core Memory Structure:**

```
┌──────────────────────────────────────────────────────────────┐
│ Core Memory                                                   │
├──────────────────────────────────────────────────────────────┤
│ persona_content: "The AI is helpful and concise. It focuses  │
│                   on technical accuracy..."                  │
├──────────────────────────────────────────────────────────────┤
│ human_content: "User is named Alice, a software engineer    │
│                 in NYC. She is learning ML and prefers       │
│                 PyTorch. She values clear explanations..."   │
└──────────────────────────────────────────────────────────────┘
```

#### Step 4: Recursive Summary Generation

```python
print("   → STEP 3: Recursive Summary...")
new_summary = await self._generate_summary(messages, current_summary)
print("   ✓ Summary updated")
```

**What happens:**
1. Combine previous summary with new messages
2. LLM receives `SUMMARY_SYSTEM_PROMPT`
3. Returns consolidated summary
4. Update `summary_ref_holder["summary"]`

**Note:** This step was a bug in the original code — it was literally `pass`. The refactored pipeline fully implements it.

#### Step 5: Message History Flush

```python
# In Session.add(), after pipeline.run() returns:
await self._mongo.set_session_summary(self.id, new_summary)
await self._mongo.trim_session_messages(self.id, self._keep_last_n)
print(f"   ✓ Session {self.id}: flushed ({msg_count} → {self._keep_last_n} messages)")
```

**What happens:**
1. New summary is persisted to MongoDB `sessions.recursive_summary`
2. Messages in MongoDB are trimmed to last `keep_last_n`
3. Retained messages form context for next window

**Bug fixed:** The old code only trimmed an in-memory list reference, not the actual MongoDB documents. Now both are trimmed.

---

### User Control of Pipeline Execution

Since `pipeline.run()` is a plain async function, the user decides how to call it:

```python
# Option 1: Await inline (blocks until done)
await session.add(user_msg, ai_response)

# Option 2: Background task (non-blocking)
import asyncio
asyncio.create_task(session.add(user_msg, ai_response))
```

**Why this design?**
- No hidden fire-and-forget inside the library
- User can await and handle errors explicitly
- User can schedule background tasks when appropriate
- Simpler mental model — no task tracking complexity

---

### Pipeline Timing Diagram

```
Time ──────────────────────────────────────────────────────────►

User Message 1   ──┐
User Message 2   ──┤
User Message 3   ──┤
...               ├── Messages accumulate (count < memory_window)
User Message 10  ──┴─► session.add() calls pipeline.run()
                            │
                            ├── PS1: Extract (2s)
                            ├── PS2: Store each (1s × N)
                            ├── Core Memory Update (1s)
                            ├── Summary Generation (1s)
                            ├── Persist summary to MongoDB
                            └── Trim messages in MongoDB
                            
User Message 11  ────────► Next turn begins (if user awaited)
```

**User controls timing:**
- If user awaits `session.add()`: next turn waits for pipeline
- If user uses `asyncio.create_task()`: next turn starts immediately

---

### Configuration Parameters

| Parameter | Config Field | Default | Description |
|-----------|--------------|---------|-------------|
| Window size | `memory_window_limit` | 10 | Messages before trigger |
| Keep last N | `keep_last_n` | 5 | Messages retained after flush |


---

## 7. Per-Turn Loop & Session Management

The library no longer includes a `ChatEngine`. Instead, users implement their own per-turn loop using `Block` and `Session` objects.

---

### Design Philosophy

**Old Design (ChatEngine):**
- Library controlled the entire conversation flow
- `send_message()` handled retrieval, LLM call, persistence, and pipeline trigger
- User had no control over LLM provider or prompting strategy

**New Design (Per-Turn Loop):**
- Library provides memory retrieval and persistence tools
- User controls LLM calls, prompting, and conversation format
- Maximum flexibility for different use cases

---

### Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      User's Per-Turn Loop                        │
│                                                                  │
│  1. RETRIEVE CONTEXT                                             │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ context = await block.retrieve(user_msg)                │ │
│     │   ├── Core memory (MongoDB)                             │ │
│     │   └── Semantic memories (Qdrant vector search)          │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
│  2. GET WINDOW & SUMMARY                                         │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ messages = await session.get_memory_window()            │ │
│     │ summary  = await session.get_recursive_summary()        │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
│  3. BUILD PROMPT & CALL LLM (USER CONTROLS THIS)                │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ system_prompt = build_prompt(context, summary)          │ │
│     │ response = await client.conversation_llm.chat(messages)  │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
│  4. PERSIST TURN                                                 │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │ await session.add(user_msg, ai_response)                │ │
│     │   ├── Persist to MongoDB                                │ │
│     │   └── Trigger pipeline if window full                   │ │
│     └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

### Block Class

Stateful handle to a memory block with retrieval methods.

**Location:** `services/block.py`

```python
class Block:
    def __init__(
        self,
        block_id: str,
        name: str,
        description: str,
        user_id: str,
        semantic_memory_service: SemanticMemoryService,
        core_memory_service: CoreMemoryService,
        semantic_collection: Optional[str] = None,
        core_memory_block_id: Optional[str] = None,
        resource_collection: Optional[str] = None,
        retrieval_top_k: int = 5,
    ):
        self.id = block_id
        self.name = name
        self.description = description
        self.user_id = user_id
        # ...
```

#### Retrieval Methods

```python
# Retrieve all memory types
context = await block.retrieve(user_query)

# Retrieve only core memory
context = await block.core_retrieve()

# Retrieve only semantic memories
context = await block.semantic_retrieve(user_query)

# Resource memories (stub)
context = await block.resource_retrieve(user_query)
```

---

### Session Class

Stateful handle to a conversation session with window management.

**Location:** `services/session.py`

```python
class Session:
    def __init__(
        self,
        session_id: str,
        user_id: str,
        block_id: str,
        mongo: MongoDBAdapter,
        pipeline: MemoryPipeline,
        memory_window: int = 10,
        keep_last_n: int = 5,
    ):
        self.id = session_id
        self.user_id = user_id
        self.block_id = block_id
        # ...
```

#### Methods

```python
# Get message window from MongoDB
messages = await session.get_memory_window()

# Get persisted summary from MongoDB
summary = await session.get_recursive_summary()

# Persist a turn (triggers pipeline if window full)
await session.add(user_msg="...", ai_response="...")
```

---

### Session.add() Flow

The `add()` method handles turn persistence and pipeline triggering:

```python
async def add(self, user_msg: str, ai_response: str) -> None:
    now = datetime.utcnow().isoformat()
    
    # 1. Persist messages to MongoDB
    await self._mongo.add_message_to_session(
        self.id,
        {"role": "user", "content": user_msg, "timestamp": now},
    )
    await self._mongo.add_message_to_session(
        self.id,
        {"role": "assistant", "content": ai_response, "timestamp": now},
    )
    
    # 2. Check if window is full
    msg_count = await self._mongo.get_session_message_count(self.id)
    
    if msg_count >= self._memory_window:
        # 3. Get messages and current summary
        messages = await self._mongo.get_session_messages(self.id, limit=msg_count)
        current_summary = await self._mongo.get_session_summary(self.id)
        
        # 4. Run pipeline
        new_summary = await self._pipeline.run(
            user_id=self.user_id,
            block_id=self.block_id,
            messages=messages,
            current_summary=current_summary,
        )
        
        # 5. Persist summary and trim messages
        await self._mongo.set_session_summary(self.id, new_summary)
        await self._mongo.trim_session_messages(self.id, self._keep_last_n)
```

---

### Session Document Schema

Sessions are persisted in MongoDB:

```json
{
  "_id": ObjectId("..."),
  "session_id": "session_xyz789",
  "user_id": "alice",
  "block_id": "block_abc123",
  "created_at": "2024-01-15T10:00:00",
  "messages": [
    {"role": "user", "content": "Hello!", "timestamp": "..."},
    {"role": "assistant", "content": "Hi there!", "timestamp": "..."}
  ],
  "recursive_summary": "User discussed machine learning projects..."
}
```

**New field:** `recursive_summary` — persisted rolling summary (survives restarts).

---

### Complete Per-Turn Example

```python
import asyncio
from memblocks import MemBlocksClient, MemBlocksConfig

async def main():
    config = MemBlocksConfig()
    client = MemBlocksClient(config)
    
    # Phase A — Initialization (once)
    user = await client.get_or_create_user("alice")
    block = await client.create_block(user_id="alice", name="Assistant")
    session = await client.create_session(user_id="alice", block_id=block.id)
    
    # Phase B — Per-turn loop
    while True:
        user_msg = input("You: ")
        
        # 1. Retrieve context
        context = await block.retrieve(user_msg)
        messages = await session.get_memory_window()
        summary = await session.get_recursive_summary()
        
        # 2. Build system prompt
        system_parts = ["You are a helpful assistant."]
        if summary:
            system_parts.append(f"<Summary>\n{summary}\n</Summary>")
        if not context.is_empty():
            system_parts.append(context.to_prompt_string())
        system_prompt = "\n\n".join(system_parts)
        
        # 3. Call LLM
        llm_messages = (
            [{"role": "system", "content": system_prompt}]
            + messages
            + [{"role": "user", "content": user_msg}]
        )
        ai_response = await client.conversation_llm.chat(messages=llm_messages)
        
        print(f"Assistant: {ai_response}")
        
        # 4. Persist turn
        await session.add(user_msg=user_msg, ai_response=ai_response)
    
    await client.close()

asyncio.run(main())
```

---

### Fire-and-Forget Pattern

For non-blocking persistence:

```python
import asyncio

# Inline (blocks)
await session.add(user_msg, ai_response)

# Background (non-blocking)
asyncio.create_task(session.add(user_msg, ai_response))
```

---

## 8. Transparency & Observability

The library includes built-in observability through four components that are always-on (no opt-in flag required). The overhead is negligible for in-memory append-only lists.

**Location:** `services/transparency.py`

---

### Components Overview

| Component | Purpose | Thread-Safe |
|-----------|---------|-------------|
| `OperationLog` | Database write operations | ✅ |
| `RetrievalLog` | Memory retrieval events | ✅ |
| `ProcessingHistory` | Pipeline run tracking | ✅ |
| `EventBus` | Real-time pub/sub | ✅ |

---

### OperationLog

Thread-safe log of all database write operations.

#### Entry Model

```python
class OperationEntry(BaseModel):
    timestamp: datetime
    db_type: DBType              # MONGO | QDRANT
    collection_name: str
    operation_type: OperationType  # insert | update | delete | upsert
    document_id: Optional[str]
    payload_summary: str
    success: bool
    error: Optional[str]
```

#### Usage

```python
# Access via client
log = client.operation_log

# Get recent entries
entries = log.get_entries(limit=50, db_type="mongo")
for entry in entries:
    print(f"{entry.operation_type} on {entry.collection_name}")
    print(f"  Document: {entry.document_id}")
    print(f"  Summary: {entry.payload_summary}")

# Get summary counts
summary = log.summary()  # {'insert': 10, 'update': 5, 'delete': 1}

# Get entries since a time
from datetime import datetime, timedelta
since = datetime.utcnow() - timedelta(hours=1)
recent = log.get_entries_since(since)

# Clear log
log.clear()
```

#### Where It's Used

```python
# In MongoDBAdapter
def _record_op(self, collection_name, operation_type, ...):
    if self._log is None:
        return
    self._log.record(OperationEntry(...))

# In QdrantAdapter
def store_vector(self, ...):
    ...
    self._record_op(collection_name, "upsert", ...)
```

---

### RetrievalLog

Thread-safe log of memory retrieval events.

#### Entry Model

```python
class RetrievalEntry(BaseModel):
    timestamp: datetime
    query_text: str
    source: str              # "semantic" | "core" | "resource"
    num_results: int
    top_scores: List[float]
    memory_ids: List[str]
    memory_summaries: List[str]
```

#### Usage

```python
log = client.retrieval_log

# Get recent retrievals
entries = log.get_entries(limit=20, source="semantic")
for entry in entries:
    print(f"Query: {entry.query_text}")
    print(f"Results: {entry.num_results}")
    print(f"Summaries: {entry.memory_summaries[:3]}")

# Get last retrieval
last = log.get_last_retrieval()
```

#### Where It's Used

```python
# In SemanticMemoryService.retrieve()
def retrieve(self, query_texts, top_k=5):
    ...
    if self._retrieval_log is not None:
        self._retrieval_log.record(RetrievalEntry(
            query_text=query_texts[0],
            source="semantic",
            num_results=len(results),
            memory_summaries=[m.content[:80] for m in flat_memories[:5]],
        ))
```

---

### ProcessingHistory

Thread-safe log of all pipeline runs with full lifecycle tracking.

#### Entry Model

```python
class PipelineRunEntry(BaseModel):
    task_id: str
    timestamp_started: datetime
    timestamp_completed: Optional[datetime]
    status: str              # "running" | "success" | "failure"
    trigger_event: str       # e.g., "message_window_full"
    input_message_count: int
    extracted_semantic_count: int
    conflicts_resolved_count: int
    core_memory_updated: bool
    summary_generated: bool
    error_details: Optional[str]
```

#### Usage

```python
history = client.processing_history

# Get recent runs
runs = history.get_runs(limit=10, status="success")
for run in runs:
    print(f"Task: {run.task_id[:12]}...")
    print(f"  Messages: {run.input_message_count}")
    print(f"  Extracted: {run.extracted_semantic_count} memories")
    print(f"  Duration: {run.timestamp_completed - run.timestamp_started}")

# Get specific run
run = history.get_run("mem_proc_abc123")

# Get last run
last = history.get_last_run()

# Get failed runs
failed = history.get_runs(status="failure")
```

#### Where It's Used

```python
# In MemoryPipeline.trigger()
def trigger(self, ...):
    async def _run_with_tracking():
        if self._history:
            self._history.record_start(
                task_id=task_id,
                trigger_event="message_window_full",
                message_count=len(messages),
            )
        
        try:
            new_summary = await self._run(...)
            if self._history:
                self._history.record_complete(task_id, {
                    "summary_generated": bool(new_summary),
                    "core_memory_updated": True,
                })
        except Exception as exc:
            if self._history:
                self._history.record_failure(task_id, str(exc))
```

---

### EventBus

Synchronous publish/subscribe event bus for real-time notifications.

#### Valid Events

```python
VALID_EVENTS = [
    "on_memory_extracted",      # After PS1 extraction
    "on_conflict_resolved",     # After PS2 resolution
    "on_memory_stored",         # After memory written to Qdrant
    "on_core_memory_updated",   # After core memory updated
    "on_summary_generated",     # After summary created
    "on_pipeline_started",      # When pipeline begins
    "on_pipeline_completed",    # When pipeline finishes successfully
    "on_pipeline_failed",       # When pipeline errors
    "on_memory_retrieved",      # When memories retrieved
    "on_db_write",              # On any database write
    "on_message_processed",     # After chat message processed
]
```

#### Usage

```python
# Subscribe to events
def on_pipeline_done(payload):
    print(f"Pipeline completed: {payload['task_id']}")
    print(f"Time: {payload.get('message_count')} messages processed")

def on_memory_stored(payload):
    print(f"New memory: {payload['content'][:50]}...")

client.subscribe("on_pipeline_completed", on_pipeline_done)
client.subscribe("on_memory_stored", on_memory_stored)

# Unsubscribe
client.unsubscribe("on_pipeline_completed", on_pipeline_done)

# Via MemBlocksClient shortcuts
client.subscribe("on_pipeline_started", lambda p: print("Pipeline started"))
```

#### Where Events Are Published

```python
# In MemoryPipeline
if self._bus:
    self._bus.publish("on_pipeline_started", {
        "task_id": task_id,
        "message_count": len(messages),
    })
    
    # On completion
    self._bus.publish("on_pipeline_completed", {"task_id": task_id})
    
    # On failure
    self._bus.publish("on_pipeline_failed", {
        "task_id": task_id,
        "error": str(exc),
    })

# In SemanticMemoryService.retrieve()
if self._bus:
    self._bus.publish("on_memory_retrieved", {
        "source": "semantic",
        "collection": self._collection,
        "num_results": len(results),
    })
```

---

### Complete Observability Example

```python
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig()
client = MemBlocksClient(config)

# Set up event handlers
def on_pipeline_start(payload):
    print(f"🔄 Pipeline started: {payload['message_count']} messages")

def on_pipeline_done(payload):
    print(f"✅ Pipeline completed: {payload['task_id'][:12]}...")

def on_pipeline_fail(payload):
    print(f"❌ Pipeline failed: {payload['error']}")

client.subscribe("on_pipeline_started", on_pipeline_start)
client.subscribe("on_pipeline_completed", on_pipeline_done)
client.subscribe("on_pipeline_failed", on_pipeline_fail)

# ... run conversations ...

# After conversation, inspect logs
print("\n=== Operation Log ===")
for op in client.operation_log.get_entries(limit=10):
    print(f"{op.operation_type}: {op.collection_name}")

print("\n=== Retrieval Log ===")
for r in client.retrieval_log.get_entries(limit=5):
    print(f"Query: {r.query_text[:30]}... → {r.num_results} results")

print("\n=== Processing History ===")
for run in client.processing_history.get_runs(limit=5):
    print(f"Task {run.task_id[:12]}...: {run.status}")
    if run.status == "success":
        print(f"  Extracted: {run.extracted_semantic_count} memories")
```

---

### Thread Safety

All transparency components use `threading.Lock` for thread-safe operations:

```python
class OperationLog:
    def __init__(self, max_entries: int = 1000):
        self._entries: List[OperationEntry] = []
        self._lock = threading.Lock()
    
    def record(self, entry: OperationEntry):
        with self._lock:
            if len(self._entries) >= self._max:
                self._entries.pop(0)
            self._entries.append(entry)
```

---

## 9. Data Flow Diagrams

This section provides visual representations of how data flows through the system.

---

### Full System Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER                                            │
│                              │                                               │
│                              ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                          API / CLI                                  │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                       MemBlocksClient                               │     │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │     │
│  │  │  users   │ │  blocks  │ │ sessions │ │   core   │ │event_bus │ │     │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────────┘ │     │
│  └───────┼────────────┼────────────┼────────────┼────────────────────┘     │
│          │            │            │            │                           │
│          ▼            ▼            ▼            ▼                           │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                      STORAGE LAYER                                  │     │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │     │
│  │  │  MongoDBAdapter  │  │   QdrantAdapter  │  │ EmbeddingProvider│  │     │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  │     │
│  └───────────┼─────────────────────┼─────────────────────┼────────────┘     │
│              ▼                       ▼                       ▼               │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐          │
│  │     MongoDB      │  │     Qdrant       │  │     Ollama       │          │
│  │  ┌────────────┐  │  │  ┌────────────┐  │  │  ┌────────────┐  │          │
│  │  │   users    │  │  │  │ block_xxx_ │  │  │  │nomic-embed │  │          │
│  │  │   blocks   │  │  │  │  semantic  │  │  │  │   -text    │  │          │
│  │  │   core_    │  │  │  └────────────┘  │  │  └────────────┘  │          │
│  │  │  memories  │  │  │  ┌────────────┐  │  │                  │          │
│  │  │  sessions  │  │  │  │ block_yyy_ │  │  │                  │          │
│  │  └────────────┘  │  │  │  semantic  │  │  │                  │          │
│  └──────────────────┘  │  └────────────┘  │  └──────────────────┘          │
│                        └──────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Per-Turn Message Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     PER-TURN LOOP (User Controlled)                          │
│                                                                              │
│  1. USER INPUT                                                               │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 2. RETRIEVE CONTEXT                                                   │   │
│  │    ┌─────────────────────────────────────────────────────────────┐   │   │
│  │    │ context = await block.retrieve(user_msg)                    │   │   │
│  │    │         │                                                   │   │   │
│  │    │         ├── CoreMemoryService.get() → MongoDB              │   │   │
│  │    │         └── SemanticMemoryService.retrieve() → Qdrant      │   │   │
│  │    └─────────────────────────────────────────────────────────────┘   │   │
│  │    ┌─────────────────────────────────────────────────────────────┐   │   │
│  │    │ messages = await session.get_memory_window()                │   │   │
│  │    │         │                                                   │   │   │
│  │    │         └── MongoDB: find session, return messages         │   │   │
│  │    └─────────────────────────────────────────────────────────────┘   │   │
│  │    ┌─────────────────────────────────────────────────────────────┐   │   │
│  │    │ summary = await session.get_recursive_summary()             │   │   │
│  │    │         │                                                   │   │   │
│  │    │         └── MongoDB: get session.recursive_summary         │   │   │
│  │    └─────────────────────────────────────────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 3. BUILD SYSTEM PROMPT (USER CONTROLS THIS)                          │   │
│  │    system_prompt = "You are helpful.\n\n"                            │   │
│  │    if summary: system_prompt += f"<Summary>{summary}</Summary>"      │   │
│  │    if not context.is_empty():                                        │   │
│  │        system_prompt += context.to_prompt_string()                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 4. CALL LLM (USER CONTROLS THIS)                                      │   │
│  │    messages = [                                                       │   │
│  │        {"role": "system", "content": system_prompt},                 │   │
│  │        *memory_window,                                                │   │
│  │        {"role": "user", "content": user_msg},                        │   │
│  │    ]                                                                  │   │
│  │    response = await client.conversation_llm.chat(messages=messages)    │   │
│  │         │                                                             │   │
│  │         └── LLM API: generate response                               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 5. PERSIST TURN                                                       │   │
│  │    await session.add(user_msg=user_msg, ai_response=response)        │   │
│  │         │                                                             │   │
│  │         ├── MongoDB: $push user message                              │   │
│  │         ├── MongoDB: $push assistant message                         │   │
│  │         └── Check window count                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 6. CHECK WINDOW & RUN PIPELINE                                        │   │
│  │    if message_count >= memory_window:                                │   │
│  │        new_summary = await pipeline.run(...)                         │   │
│  │        await mongo.set_session_summary(session_id, new_summary)      │   │
│  │        await mongo.trim_session_messages(session_id, keep_last_n)    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  NEXT TURN                                                                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Memory Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MEMORY PIPELINE (Background)                            │
│                                                                              │
│  TRIGGER: message_count >= memory_window                                    │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 1: SEMANTIC EXTRACTION (PS1)                                     │   │
│  │                                                                        │   │
│  │    messages ──► format conversation ──► LLM (PS1_SEMANTIC_PROMPT)    │   │
│  │                                              │                        │   │
│  │                                              ▼                        │   │
│  │                              SemanticMemoriesOutput                   │   │
│  │                              [SemanticMemoryUnit, ...]                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 2: CONFLICT RESOLUTION + STORAGE (PS2)                           │   │
│  │                                                                        │   │
│  │    FOR EACH extracted_memory:                                         │   │
│  │                                                                        │   │
│  │    ┌─────────────────────────────────────────────────────────────┐    │   │
│  │    │ embed memory  ──► Ollama: embed_text(memory.content)       │    │   │
│  │    └─────────────────────────────────────────────────────────────┘    │   │
│  │                          │                                            │   │
│  │                          ▼                                            │   │
│  │    ┌─────────────────────────────────────────────────────────────┐    │   │
│  │    │ find similar ──► Qdrant: retrieve_from_vector(embedding)   │    │   │
│  │    └─────────────────────────────────────────────────────────────┘    │   │
│  │                          │                                            │   │
│  │                          ▼                                            │   │
│  │    ┌─────────────────────────────────────────────────────────────┐    │   │
│  │    │ resolve conflict ──► LLM (PS2_MEMORY_UPDATE_PROMPT)        │    │   │
│  │    │                              │                              │    │   │
│  │    │                              ▼                              │    │   │
│  │    │                 PS2MemoryUpdateOutput                       │    │   │
│  │    │                 { ADD | UPDATE | DELETE | NONE }            │    │   │
│  │    └─────────────────────────────────────────────────────────────┘    │   │
│  │                          │                                            │   │
│  │                          ▼                                            │   │
│  │    ┌─────────────────────────────────────────────────────────────┐    │   │
│  │    │ execute ops ──► Qdrant: upsert / delete                    │    │   │
│  │    └─────────────────────────────────────────────────────────────┘    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 3: CORE MEMORY UPDATE                                            │   │
│  │                                                                        │   │
│  │    get old core ──► MongoDB: get_core_memory(block_id)               │   │
│  │                          │                                            │   │
│  │                          ▼                                            │   │
│  │    LLM (CORE_MEMORY_PROMPT) ──► CoreMemoryOutput                     │   │
│  │                          │                                            │   │
│  │                          ▼                                            │   │
│  │    save core ──► MongoDB: save_core_memory(block_id, persona, human) │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 4: RECURSIVE SUMMARY                                             │   │
│  │                                                                        │   │
│  │    old_summary + messages ──► LLM (SUMMARY_SYSTEM_PROMPT)            │   │
│  │                                      │                                │   │
│  │                                      ▼                                │   │
│  │                            SummaryOutput { summary: "..." }           │   │
│  │                                      │                                │   │
│  │                                      ▼                                │   │
│  │                            _summary_ref["summary"] = new_summary      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ STEP 5: FLUSH HISTORY                                                 │   │
│  │                                                                        │   │
│  │    message_history = message_history[-keep_last_n:]                  │   │
│  │    (retain last N messages, discard processed ones)                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  DONE                                                                        │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Block Creation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      BLOCK CREATION                                          │
│                                                                              │
│  client.blocks.create_block(user_id, name, description, ...)                │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 1. GENERATE IDs & TIMESTAMPS                                          │   │
│  │    block_id = "block_{uuid.hex[:12]}"                                │   │
│  │    current_time = datetime.utcnow().isoformat()                      │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 2. CREATE QDRANT COLLECTIONS (if requested)                           │   │
│  │                                                                        │   │
│  │    if create_semantic:                                                │   │
│  │        qdrant.create_collection(f"{block_id}_semantic")              │   │
│  │                                                                        │   │
│  │    if create_resource:                                                │   │
│  │        qdrant.create_collection(f"{block_id}_resource")              │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 3. CREATE CORE MEMORY (if requested)                                  │   │
│  │                                                                        │   │
│  │    if create_core:                                                    │   │
│  │        mongo.save_core_memory(block_id, persona="", human="")        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 4. CREATE BLOCK DOCUMENT                                              │   │
│  │                                                                        │   │
│  │    block_dict = {                                                     │   │
│  │        "block_id": block_id,                                          │   │
│  │        "user_id": user_id,                                            │   │
│  │        "name": name,                                                  │   │
│  │        "description": description,                                    │   │
│  │        "meta_data": {...},                                            │   │
│  │        "semantic_collection": f"{block_id}_semantic",                 │   │
│  │        "core_memory_block_id": block_id,                              │   │
│  │    }                                                                  │   │
│  │    mongo.create_memory_block(user_id, block_dict)                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 5. LINK BLOCK TO USER                                                 │   │
│  │    mongo.add_block_to_user(user_id, block_id)                        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  RETURN MemoryBlock                                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### Retrieval Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      MEMORY RETRIEVAL                                        │
│                                                                              │
│  semantic_service.retrieve([query], top_k=5)                                │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 1. EMBED QUERY                                                        │   │
│  │    embeddings.embed_documents([query]) → [query_vector]              │   │
│  │         │                                                             │   │
│  │         └── Ollama: POST /api/embeddings {"prompt": query}           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 2. VECTOR SEARCH                                                      │   │
│  │    qdrant.retrieve_from_vector(collection, query_vector, top_k)      │   │
│  │         │                                                             │   │
│  │         └── Qdrant: query_points(collection, query=vector, limit=k)  │   │
│  │         → [ScoredPoint(id, score, payload), ...]                     │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 3. DESERIALIZE                                                        │   │
│  │    [SemanticMemoryUnit(**point.payload) for point in results]        │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 4. DEDUPLICATE                                                        │   │
│  │    seen_contents = set()                                              │   │
│  │    unique = [m for m in memories if m.content not in seen]           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ 5. LOG (transparency)                                                 │   │
│  │    retrieval_log.record(RetrievalEntry(...))                         │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│     │                                                                        │
│     ▼                                                                        │
│  RETURN [[SemanticMemoryUnit, ...]]                                         │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Database Schemas & Collection Reference

This section documents the exact schema of each MongoDB collection and Qdrant collection used by the library.

---

### MongoDB Collections

MongoDB is used for structured document storage: users, blocks, core memories, and sessions.

#### Collection: `users`

Stores user accounts and their associated block IDs.

```javascript
{
  "_id": ObjectId("..."),
  "user_id": "alice",                    // Unique user identifier (string)
  "block_ids": [                         // Array of block IDs owned by user
    "block_abc123",
    "block_def456"
  ],
  "created_at": "2024-01-15T10:00:00",   // ISO timestamp
  "metadata": {                          // Optional user-defined metadata
    "role": "admin",
    "preferences": { ... }
  }
}
```

**Indexes:**
- `{ "user_id": 1 }` (unique) — for `get_user()` lookups

**Operations:**
- `create_user` → `insert_one`
- `get_user` → `find_one({ user_id })`
- `add_block_to_user` → `update_one({ $addToSet: { block_ids } })`
- `list_users` → `find({})`

---

#### Collection: `memory_blocks`

Stores memory block metadata and collection references.

```javascript
{
  "_id": ObjectId("..."),
  "block_id": "block_abc123",            // Unique block identifier
  "user_id": "alice",                    // Owner user ID
  "name": "Work Memory",                 // Human-readable name
  "description": "Professional context", // Purpose description
  "is_active": false,                    // Active status flag
  "created_at": "2024-01-15T10:00:00",
  "updated_at": "2024-01-15T10:30:00",
  "meta_data": {
    "id": "block_abc123",
    "created_at": "2024-01-15T10:00:00",
    "updated_at": "2024-01-15T10:30:00",
    "usage": [],                         // Access timestamps
    "user_id": "alice"
  },
  "semantic_collection": "block_abc123_semantic",   // Qdrant collection
  "core_memory_block_id": "block_abc123",           // Core memory key
  "resource_collection": "block_abc123_resource"    // Optional resource collection
}
```

**Indexes:**
- `{ "block_id": 1 }` (unique) — for `get_memory_block()` lookups
- `{ "meta_data.id": 1 }` — alternative lookup by metadata ID
- `{ "user_id": 1 }` — for listing user's blocks

**Operations:**
- `create_memory_block` → `insert_one`
- `get_memory_block` → `find_one({ block_id })`
- `list_user_blocks` → `find({ "meta_data.id": { $in: block_ids } })`
- `delete_memory_block` → `delete_one({ block_id })`

---

#### Collection: `core_memories`

Stores the persistent persona and human facts for each block.

```javascript
{
  "_id": ObjectId("..."),
  "block_id": "block_abc123",            // Key: matches block's core_memory_block_id
  "persona_content": "The AI is helpful and concise. It provides technical explanations when appropriate.",
  "human_content": "User is named Alice, a software engineer in NYC. She is learning machine learning and prefers PyTorch.",
  "updated_at": "2024-01-15T11:00:00"
}
```

**Indexes:**
- `{ "block_id": 1 }` (unique) — one core memory per block

**Operations:**
- `save_core_memory` → `replace_one({ block_id }, { ... }, { upsert: true })`
- `get_core_memory` → `find_one({ block_id })`
- `delete_core_memory` → `delete_one({ block_id })`

---

#### Collection: `sessions`

Stores chat sessions with full message history and persisted summary.

```javascript
{
  "_id": ObjectId("..."),
  "session_id": "session_xyz789",        // Unique session identifier
  "user_id": "alice",                    // Owner user ID
  "block_id": "block_abc123",            // Attached memory block
  "created_at": "2024-01-15T10:00:00",
  "messages": [                          // Chronological message array
    {
      "role": "user",
      "content": "Hello!",
      "timestamp": "2024-01-15T10:01:00"
    },
    {
      "role": "assistant",
      "content": "Hi there! How can I help?",
      "timestamp": "2024-01-15T10:01:05"
    }
  ],
  "recursive_summary": "User discussed machine learning..."  // Persisted summary
}
```

**New field:** `recursive_summary` — persisted rolling summary. Survives process restarts (was previously in-memory only).

**Indexes:**
- `{ "session_id": 1 }` (unique) — for session lookups

**Operations:**
- `create_session` → `insert_one`
- `get_session` → `find_one({ session_id })`
- `add_message_to_session` → `update_one({ session_id }, { $push: { messages } })`
- `get_session_messages` → `find_one({ session_id }, { messages: 1 })`
- `get_session_message_count` → `find_one({ session_id }, { messages: 1 })`
- `trim_session_messages` → `update_one({ session_id }, { $set: { messages: messages[-N:] } })`
- `set_session_summary` → `update_one({ session_id }, { $set: { recursive_summary } })`
- `get_session_summary` → `find_one({ session_id }, { recursive_summary: 1 })`
- `clear_session_messages` → `update_one({ session_id }, { $set: { messages: [] } })`

---

### Qdrant Collections

Qdrant stores vector embeddings for semantic similarity search. Collections are created dynamically per block.

#### Collection Naming Convention

```
{block_id}_semantic   — Semantic memories (created when create_semantic=True)
{block_id}_resource   — Resource memories (created when create_resource=True)
```

**Example:**
- Block `block_abc123` → Collections `block_abc123_semantic`, `block_abc123_resource`

---

#### Vector Configuration

All collections use the same vector configuration:

```python
VectorParams(
    size=768,              # nomic-embed-text dimension
    distance=Distance.COSINE,
)
```

**Note:** Vector size is determined by the embedding model. `nomic-embed-text` produces 768-dimensional vectors.

---

#### Point Schema (Semantic Memory)

Each point in a semantic collection stores a full `SemanticMemoryUnit`:

```json
{
  "id": "uuid-v4-string",
  "vector": [0.1, 0.2, ...],  // 768 floats
  "payload": {
    "content": "User completed a machine learning certification covering neural networks.",
    "type": "event",
    "source": "conversation",
    "confidence": 0.95,
    "memory_time": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00",
    "keywords": ["ML certification", "neural networks", "completed"],
    "entities": ["machine learning", "certification"],
    "meta_data": {
      "usage": ["2024-01-15T10:30:00"],
      "status": "active",
      "message_ids": []
    },
    "embedding_text": "User completed a machine learning certification...\nKeywords: ML certification..."
  }
}
```

**Key Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `content` | string | The memory statement |
| `type` | string | `"fact"` \| `"event"` \| `"opinion"` |
| `source` | string | Where the memory came from |
| `confidence` | float | 0.0 to 1.0 |
| `memory_time` | string | ISO timestamp (for events) |
| `keywords` | array | Ranked keywords for retrieval |
| `entities` | array | Named entities mentioned |
| `embedding_text` | string | Text used to generate the embedding |

---

#### CRUD Operations

**Create (Upsert):**
```python
qdrant.store_vector(
    collection_name="block_abc123_semantic",
    vector=embedding,
    payload=memory_unit.model_dump(),
    point_id="optional-uuid",  # Auto-generated if None
)
```

**Read (Search):**
```python
results = qdrant.retrieve_from_vector(
    collection_name="block_abc123_semantic",
    query_vector=query_embedding,
    top_k=5,
)
# Returns: [ScoredPoint(id, score, payload), ...]
```

**Update (Upsert with ID):**
```python
qdrant.store_vector(
    collection_name="block_abc123_semantic",
    vector=updated_embedding,
    payload=updated_payload,
    point_id=existing_point_id,  # Overwrites existing
)
```

**Delete:**
```python
qdrant.delete_vector(
    collection_name="block_abc123_semantic",
    point_id="uuid-to-delete",
)
```

---

### Collection Lifecycle

```
┌─────────────────────────────────────────────────────────────────┐
│                    Collection Lifecycle                          │
│                                                                  │
│  1. CREATE                                                       │
│     BlockManager.create_block(create_semantic=True)             │
│     └── qdrant.create_collection(f"{block_id}_semantic")        │
│                                                                  │
│  2. POPULATE                                                     │
│     Memory pipeline stores extracted memories                    │
│     └── qdrant.store_vector(...)                                │
│                                                                  │
│  3. QUERY                                                        │
│     Block.retrieve() retrieves context                           │
│     └── qdrant.retrieve_from_vector(...)                        │
│                                                                  │
│  4. UPDATE / DELETE                                              │
│     PS2 conflict resolution                                      │
│     └── qdrant.store_vector(point_id=...) # Update              │
│     └── qdrant.delete_vector(...)           # Delete            │
│                                                                  │
│  5. DROP (manual, not automatic)                                │
│     When block is deleted, collections remain                    │
│     └── Manual cleanup via Qdrant dashboard or API              │
└─────────────────────────────────────────────────────────────────┘
```

**Note:** Block deletion (`BlockManager.delete_block()`) removes the MongoDB document but does NOT delete the corresponding Qdrant collections. This is intentional to allow recovery. Manual cleanup is required.

---

### Schema Summary

| Storage | Collection/Type | Purpose | Key |
|---------|-----------------|---------|-----|
| MongoDB | `users` | User accounts | `user_id` |
| MongoDB | `memory_blocks` | Block metadata | `block_id` |
| MongoDB | `core_memories` | Core memory | `block_id` |
| MongoDB | `sessions` | Chat sessions | `session_id` |
| Qdrant | `{block_id}_semantic` | Vector memories | point `id` (UUID) |
| Qdrant | `{block_id}_resource` | Resource vectors | point `id` (UUID) |

---

## Summary

This technical overview covered the complete architecture of the memBlocks library:

1. **Architecture** — Layered design with dependency injection, flat client API
2. **Configuration** — Environment-driven settings via Pydantic
3. **Data Models** — Pure Pydantic models for all data structures
4. **Storage Layer** — MongoDB, Qdrant, and Ollama adapters
5. **LLM Interface** — Abstract provider with Groq implementation
6. **Memory Pipeline** — PS1, PS2, core memory, and summary generation
7. **Per-Turn Loop** — Block/Session objects for retrieval and persistence (user controls LLM)
8. **Transparency** — Built-in logging and event publishing
9. **Data Flow** — Visual diagrams of data movement
10. **Schemas** — MongoDB and Qdrant collection structures

**Key Design Change:** The library is now a **memory management** library, not an inference engine. Users control their own LLM calls using `Block` and `Session` objects.

For implementation details, refer to the source code in `memblocks_lib/src/memblocks/`.
