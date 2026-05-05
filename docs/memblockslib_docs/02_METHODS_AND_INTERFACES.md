# memBlocks Library — Methods and Interfaces

This document provides a complete API reference for the `memblocks` library with practical usage examples.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [MemBlocksClient](#memblocksclient)
3. [Block](#block)
4. [Session](#session)
5. [RetrievalResult](#retrievalresult)
6. [LLM Providers](#llm-providers)
7. [LLMSettings and LLMTaskSettings](#llmsettings-and-llmtasksettings)
8. [Logger](#logger)
9. [CoreMemoryService (Internal)](#corememoryservice-internal)
10. [SemanticMemoryService (Internal)](#semanticmemoryservice-internal)
11. [Transparency Layer](#transparency-layer)
12. [Data Models](#data-models)

---

## Quick Start

```python
import asyncio
from memblocks import MemBlocksClient, MemBlocksConfig

async def main():
    # Create client (reads from .env automatically)
    config = MemBlocksConfig()
    client = MemBlocksClient(config)
    
    # Phase A — Initialization
    user = await client.get_or_create_user("alice")
    block = await client.create_block("alice", "Work Memory")
    session = await client.create_session(user_id="alice", block_id=block.id)
    
    # Phase B — Per-turn loop
    user_msg = "Hello! I'm working on a Python project."
    
    # Retrieve context
    context = await block.retrieve(user_msg)
    messages = await session.get_memory_window()
    summary = await session.get_recursive_summary()
    
    # Build prompt and call YOUR LLM
    system = "You are helpful.\n\n" + context.to_prompt_string()
    ai_response = await client.conversation_llm.chat([
        {"role": "system", "content": system},
        *messages,
        {"role": "user", "content": user_msg},
    ])
    
    # Persist the turn
    await session.add(user_msg=user_msg, ai_response=ai_response)
    print(ai_response)
    
    await client.close()

asyncio.run(main())
```

---

## MemBlocksClient

The main entry point for the library. Wires all dependencies and provides a **flat API** for users, blocks, and sessions.

### Constructor

```python
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig()

# Default setup — provider selected by LLM_PROVIDER_NAME in config
client = MemBlocksClient(config)

# With custom storage adapters (for testing)
client = MemBlocksClient(
    config,
    mongo_adapter=custom_mongo,
    qdrant_adapter=custom_qdrant,
    embedding_provider=custom_embeddings,
)
```

The active LLM provider is resolved automatically from `config.llm_provider_name` (or from `config.llm_settings` when using per-task configuration):

| `llm_provider_name` | Provider class | Required key |
|---------------------|---------------|--------------|
| `"groq"` (default) | `GroqLLMProvider` | `GROQ_API_KEY` |
| `"gemini"` | `GeminiLLMProvider` | `GEMINI_API_KEY` |
| `"openrouter"` | `OpenRouterLLMProvider` | `OPENROUTER_API_KEY` |
| `"ollama"` | `OllamaLLMProvider` | None (local server) |

Any other value raises `ValueError`.

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `mongo` | `MongoDBAdapter` | MongoDB operations |
| `qdrant` | `QdrantAdapter` | Qdrant vector operations |
| `embeddings` | `EmbeddingProvider` | Ollama embedding wrapper |
| `conversation_llm` | `LLMProvider` | Active LLM backend for conversation (primary attribute) |
| `llm` | `LLMProvider` | Alias for `conversation_llm` (backward compatible) |
| `event_bus` | `EventBus` | Pub/sub for internal events |
| `operation_log` | `OperationLog` | Database write log |
| `retrieval_log` | `RetrievalLog` | Memory retrieval log |
| `processing_history` | `ProcessingHistory` | Pipeline run history |

### User Methods

#### `create_user(user_id: str, metadata: dict = None) -> Dict[str, Any]`

Create a new user (idempotent — returns existing if found).

```python
user = await client.create_user("alice", {"role": "admin"})
print(user["user_id"])  # "alice"
```

#### `get_user(user_id: str) -> Optional[Dict[str, Any]]`

Retrieve a user by ID.

```python
user = await client.get_user("alice")
if user:
    print(user["block_ids"])  # List of block IDs
```

#### `get_or_create_user(user_id: str, metadata: dict = None) -> Dict[str, Any]`

Get existing user or create if not found.

```python
user = await client.get_or_create_user("alice")
```

#### `list_users() -> List[Dict[str, Any]]`

List all users.

```python
users = await client.list_users()
for u in users:
    print(u["user_id"])
```

### Block Methods

#### `create_block(user_id, name, description="", ...) -> Block`

Create a new memory block. Returns a stateful `Block` object.

```python
block = await client.create_block(
    user_id="alice",
    name="Work Memory",
    description="Professional context and project details",
    create_semantic=True,   # Create Qdrant collection for semantic memories
    create_core=True,       # Create MongoDB document for core memory
    create_resource=False,  # Create Qdrant collection for resources
)

print(block.id)                      # "block_xxx..."
print(block.name)                    # "Work Memory"
print(block.semantic_collection)     # "block_xxx_semantic"
print(block.core_memory_block_id)    # "block_xxx..."
```

#### `get_block(block_id: str) -> Optional[Block]`

Load a memory block by ID. Returns a stateful `Block` object.

```python
block = await client.get_block("block_abc123")
if block:
    print(block.name)
```

#### `get_user_blocks(user_id: str) -> List[Block]`

List all blocks for a user. Returns list of `Block` objects.

```python
blocks = await client.get_user_blocks("alice")
for b in blocks:
    print(f"{b.name}: {b.description}")
```

#### `delete_block(block_id: str, user_id: str) -> bool`

Delete a memory block.

```python
success = await client.delete_block("block_abc123", "alice")
```

### Session Methods

#### `create_session(user_id: str, block_id: str) -> Session`

Create a new chat session attached to a block. Returns a stateful `Session` object.

```python
session = await client.create_session(
    user_id="alice",
    block_id="block_abc123"
)
print(session.id)  # "session_xxx..."
```

#### `get_session(session_id: str) -> Optional[Session]`

Retrieve a session. Returns a stateful `Session` object.

```python
session = await client.get_session("session_xxx")
if session:
    print(session.block_id)
```

### Transparency Methods

#### `subscribe(event_name: str, callback: Callable) -> None`

Subscribe to internal library events.

```python
def on_pipeline_done(payload):
    print(f"Pipeline completed: {payload['task_id']}")

client.subscribe("on_pipeline_completed", on_pipeline_done)
```

#### `unsubscribe(event_name: str, callback: Callable) -> None`

Remove a callback from event subscriptions.

```python
client.unsubscribe("on_pipeline_completed", on_pipeline_done)
```

#### `get_operation_log() -> OperationLog`

Return the OperationLog for inspecting database writes.

```python
log = client.get_operation_log()
```

#### `get_retrieval_log() -> RetrievalLog`

Return the RetrievalLog for inspecting memory retrievals.

```python
log = client.get_retrieval_log()
```

#### `get_processing_history() -> ProcessingHistory`

Return the ProcessingHistory for inspecting pipeline runs.

```python
history = client.get_processing_history()
```

#### `close() -> None`

Gracefully close all connections.

```python
await client.close()
```

---

## Block

Stateful handle to a memory block with retrieval methods.

**Returned by:** `client.create_block()`, `client.get_block()`

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `str` | Block ID (e.g., "block_abc123") |
| `name` | `str` | Human-readable block name |
| `description` | `str` | Block description |
| `user_id` | `str` | Owner user ID |
| `semantic_collection` | `Optional[str]` | Qdrant collection name |
| `core_memory_block_id` | `Optional[str]` | MongoDB key for core memory |
| `resource_collection` | `Optional[str]` | Qdrant collection for resources |
| `created_at` | `str` | ISO 8601 creation timestamp |
| `updated_at` | `str` | ISO 8601 last-updated timestamp |

### Retrieval Methods

#### `retrieve(query: str) -> RetrievalResult`

Retrieve all available memory types relevant to *query*. Combines core memory and semantic memories.

```python
context = await block.retrieve("What projects am I working on?")

if not context.is_empty():
    print(context.to_prompt_string())
```

#### `core_retrieve() -> RetrievalResult`

Retrieve only the core memory for this block.

```python
context = await block.core_retrieve()
if context.core:
    print(f"Persona: {context.core.persona_content}")
    print(f"Human: {context.core.human_content}")
```

#### `semantic_retrieve(query: str) -> RetrievalResult`

Retrieve only semantic memories relevant to *query* via vector search.

```python
context = await block.semantic_retrieve("machine learning")
for mem in context.semantic:
    print(f"[{mem.type}] {mem.content}")
```

#### `resource_retrieve(query: str) -> RetrievalResult`

Retrieve resource memories. **Stub — always returns empty for now.**

```python
context = await block.resource_retrieve("documentation")
# context.resource is always []
```

---

## Session

Stateful handle to a conversation session with message window and summary management.

**Returned by:** `client.create_session()`, `client.get_session()`

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `id` | `str` | Session ID (e.g., "session_abc123") |
| `user_id` | `str` | Owner user ID |
| `block_id` | `str` | Associated memory block ID |
| `created_at` | `str` | ISO 8601 creation timestamp |

### Methods

#### `get_memory_window() -> List[Dict[str, Any]]`

Return the current message window from MongoDB.

```python
messages = await session.get_memory_window()
for msg in messages:
    print(f"{msg['role']}: {msg['content']}")
```

#### `get_recursive_summary() -> str`

Return the persisted rolling recursive summary for this session.

```python
summary = await session.get_recursive_summary()
if summary:
    print(f"Summary: {summary}")
```

#### `add(user_msg: str, ai_response: str) -> None`

Persist a conversation turn. Triggers memory pipeline when window is full.

```python
await session.add(
    user_msg="I'm working on a FastAPI project.",
    ai_response="That's great! FastAPI is excellent for..."
)
```

**What happens when window is full:**
1. Memory pipeline runs (semantic + core + summary)
2. New summary persisted to MongoDB
3. Messages trimmed to `keep_last_n`

**Fire-and-forget option:**

```python
import asyncio

# Option 1: Await inline (blocks until done)
await session.add(user_msg, ai_response)

# Option 2: Background task (non-blocking)
asyncio.create_task(session.add(user_msg, ai_response))
```

---

## RetrievalResult

Structured container returned by `Block.retrieve()` and friends.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `core` | `Optional[CoreMemoryUnit]` | Core memory (persona + human facts) |
| `semantic` | `List[SemanticMemoryUnit]` | Vector-searched memories |
| `resource` | `List[ResourceMemoryUnit]` | Resource memories (stub) |

### Methods

#### `to_prompt_string() -> str`

Render as a formatted string for LLM prompts.

```python
context = await block.retrieve(query)
prompt_section = context.to_prompt_string()
# Returns:
# <Core Memory>
# [PERSONA]
# ...
# [HUMAN]
# ...
# </Core Memory>
#
# <Semantic Memories>
# [EVENT] ...
#   Keywords: ...
# </Semantic Memories>
```

#### `is_empty() -> bool`

Return True if no memories were retrieved.

```python
if not context.is_empty():
    system_prompt += "\n\n" + context.to_prompt_string()
```

---

## LLM Providers

memBlocks abstracts all LLM access behind the `LLMProvider` interface. Three built-in backends are provided; you can also implement your own.

### LLMProvider Base Class

Defined in `memblocks.llm.base`. All providers must implement two methods:

```python
from memblocks.llm.base import LLMProvider
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Type

class LLMProvider:
    def create_structured_chain(
        self,
        system_prompt: str,
        pydantic_model: Type[BaseModel],
        temperature: float = 0.0,
    ) -> Any:
        """
        Return a LangChain-compatible runnable that accepts {"input": str}
        and returns a pydantic_model instance.

        Used internally for:
        - PS1 semantic memory extraction
        - PS2 conflict resolution
        - Core memory extraction
        - Recursive summary generation
        """
        ...

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a list of {"role": ..., "content": ...} messages and return
        the assistant's response as a plain string.

        Used by the caller for the main conversation turn (client.conversation_llm.chat(...)).
        """
        ...
```

### GroqLLMProvider

Default backend using [`langchain-groq`](https://pypi.org/project/langchain-groq/).

```python
from memblocks.llm.groq_provider import GroqLLMProvider
from memblocks import MemBlocksConfig

config = MemBlocksConfig(
    llm_provider_name="groq",
    groq_api_key="gsk_xxxxxxxxx",
    llm_model="moonshotai/kimi-k2-instruct-0905",
)

# Automatically instantiated by MemBlocksClient
client = MemBlocksClient(config)

# Or create directly
provider = GroqLLMProvider(config)
response = await provider.chat([{"role": "user", "content": "Hello!"}])
```

**Structured output** uses Groq's native `json_schema` mode (`method="json_schema"`).

**Key config fields:**

| Field | Description |
|-------|-------------|
| `groq_api_key` | Required. Groq API key. |
| `llm_model` | Model identifier, e.g. `moonshotai/kimi-k2-instruct-0905`. |
| `llm_convo_temperature` | Default temperature for `chat()` calls (default: `0.7`). |

### GeminiLLMProvider

Backend using [`langchain-google-genai`](https://pypi.org/project/langchain-google-genai/).

```python
from memblocks.llm.gemini_provider import GeminiLLMProvider
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig(
    llm_provider_name="gemini",
    gemini_api_key="AIzaSy_xxxxxxxxx",
    llm_model="gemini-2.0-flash",
)

# Automatically instantiated by MemBlocksClient
client = MemBlocksClient(config)

# Or create directly
provider = GeminiLLMProvider(config)
response = await provider.chat([{"role": "user", "content": "Hello!"}])
```

**Structured output** uses Gemini's native structured output mode (`llm.with_structured_output(model, include_raw=False)`).

**Response content handling:** `chat()` transparently handles both Gemini's plain-string and list-of-parts response formats, always returning a single `str`.

**Key config fields:**

| Field | Description |
|-------|-------------|
| `gemini_api_key` | Required. Google AI API key from [aistudio.google.com](https://aistudio.google.com/apikey). |
| `llm_model` | Model identifier. Recommended: `gemini-2.0-flash`. |
| `llm_convo_temperature` | Default temperature for `chat()` calls (default: `0.7`). |

**Popular Gemini models:**

| Model ID | Notes |
|----------|-------|
| `gemini-2.0-flash` | Fast, cost-efficient — recommended default |
| `gemini-2.0-flash-lite` | Lightest and fastest |
| `gemini-1.5-pro` | Highest capability, 2M token context |
| `gemini-1.5-flash` | Balanced speed/capability |

### OpenRouterLLMProvider

Backend using [`langchain-openai`](https://pypi.org/project/langchain-openai/) pointed at [OpenRouter](https://openrouter.ai/), giving access to hundreds of models from different vendors through a single API.

```python
from memblocks.llm.openrouter_provider import OpenRouterLLMProvider
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig(
    llm_provider_name="openrouter",
    openrouter_api_key="sk-or-xxxxxxxxx",
    llm_model="moonshotai/kimi-k2-instruct-0905",
)

# Automatically instantiated by MemBlocksClient
client = MemBlocksClient(config)
response = await client.conversation_llm.chat([{"role": "user", "content": "Hello!"}])
```

**Key config fields:**

| Field | Description |
|-------|-------------|
| `openrouter_api_key` | Required. OpenRouter API key from [openrouter.ai/keys](https://openrouter.ai/keys). |
| `llm_model` | Model identifier, e.g. `moonshotai/kimi-k2-instruct-0905`. |
| `openrouter_fallback_models` | Comma-separated list of fallback model IDs tried in order on failure. |
| `openrouter_enable_thinking` | `true`/`false` — enable extended thinking (reasoning models only). |

### OllamaLLMProvider

Backend using [`langchain-ollama`](https://pypi.org/project/langchain-ollama/) to run open-source models locally.

```python
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig(
    llm_provider_name="ollama",
    ollama_base_url="http://localhost:11434",
    llm_model="local-llm-model",
)

client = MemBlocksClient(config)
response = await client.conversation_llm.chat([{"role": "user", "content": "Hello!"}])
```

**Key config fields:**

| Field | Description |
|-------|-------------|
| `ollama_base_url` | Ollama server URL. Default: `http://localhost:11434` |
| `llm_model` | Local model name (e.g. `local-llm-model`, `llama3`, `mistral`) |

**Prerequisites:**
1. Install Ollama: https://ollama.com
2. Run `ollama serve`
3. Pull a model: `ollama pull <model-name>`

### Optional Arize Monitoring

All four providers (`GroqLLMProvider`, `GeminiLLMProvider`, `OpenRouterLLMProvider`, `OllamaLLMProvider`) support [Arize Phoenix](https://arize.com/) LangChain tracing. Set these fields in `MemBlocksConfig` (or the equivalent env vars) to enable it:

```python
config = MemBlocksConfig(
    llm_provider_name="gemini",
    gemini_api_key="...",
    arize_space_id="your_space_id",
    arize_api_key="your_api_key",
    arize_project_name="my-project",  # default: "memBlocks"
)
```

Required packages (optional extras):

```bash
pip install arize openinference-instrumentation-langchain
```

If the packages are not installed but the keys are set, the provider logs a `WARNING` and continues without monitoring. If neither key is set, a `DEBUG` message is emitted and monitoring is skipped silently.

### Implementing a Custom Provider

Subclass `LLMProvider` and implement both abstract methods:

```python
from memblocks.llm.base import LLMProvider
from memblocks import MemBlocksClient, MemBlocksConfig
from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Type

class MyOpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self._api_key = api_key
        self._model = model

    def create_structured_chain(
        self,
        system_prompt: str,
        pydantic_model: Type[BaseModel],
        temperature: float = 0.0,
    ) -> Any:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate

        llm = ChatOpenAI(model=self._model, temperature=temperature, api_key=self._api_key)
        structured_llm = llm.with_structured_output(pydantic_model, include_raw=False)
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{input}"),
        ])
        return prompt | structured_llm

    async def chat(self, messages: List[Dict[str, str]], temperature: Optional[float] = None) -> str:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model=self._model, temperature=temperature or 0.7, api_key=self._api_key)
        response = await llm.ainvoke(messages)
        return response.content

# Inject after client construction
config = MemBlocksConfig(llm_provider_name="groq", groq_api_key="placeholder")
client = MemBlocksClient(config)
client.conversation_llm = MyOpenAIProvider(api_key="sk-xxx")
# client.llm is an alias for client.conversation_llm — both work
```

---

## LLMSettings and LLMTaskSettings

These Pydantic models (exported from `memblocks`) enable per-task LLM routing — assigning a different provider, model, or temperature to each internal task.

### `LLMTaskSettings`

```python
from memblocks import LLMTaskSettings

task = LLMTaskSettings(
    provider="ollama",          # "groq" | "gemini" | "openrouter" | "ollama"
    model="local-llm-model",
    temperature=0.7,
    fallback_models=[               # OpenRouter only
        "anthropic/claude-3-5-haiku",
        "google/gemini-flash-1.5",
    ],
    enable_thinking=False,          # OpenRouter only
)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `str` | *required* | Provider name: `"groq"`, `"gemini"`, `"openrouter"`, or `"ollama"` |
| `model` | `str` | *required* | Model identifier |
| `temperature` | `float` | `0.0` | Sampling temperature |
| `fallback_models` | `List[str]` | `[]` | OpenRouter only — tried in order on primary model failure |
| `enable_thinking` | `bool` | `False` | OpenRouter only — enables extended reasoning |

### `LLMSettings`

```python
from memblocks import LLMSettings, LLMTaskSettings

settings = LLMSettings(
    # Required — used for any task without an explicit override
    default=LLMTaskSettings(provider="groq", model="...", temperature=0.0),

    # Optional per-task overrides
    conversation=LLMTaskSettings(...),
    ps1_semantic_extraction=LLMTaskSettings(...),
    ps2_conflict_resolution=LLMTaskSettings(...),
    retrieval=LLMTaskSettings(...),
    core_memory_extraction=LLMTaskSettings(...),
    recursive_summary=LLMTaskSettings(...),
)
```

`LLMSettings.for_task(task_name)` returns the override for `task_name` if set, otherwise returns `default`.

### Usage with `MemBlocksConfig`

```python
from memblocks import MemBlocksClient, MemBlocksConfig, LLMSettings, LLMTaskSettings

config = MemBlocksConfig(
    mongodb_connection_string="mongodb://localhost:27017",
    qdrant_host="localhost",
    ollama_base_url="http://localhost:11434",
    llm_settings=LLMSettings(
        default=LLMTaskSettings(
            provider="groq",
            model="moonshotai/kimi-k2-instruct-0905",
            temperature=0.0,
        ),
        conversation=LLMTaskSettings(
            provider="openrouter",
            model="anthropic/claude-opus-4",
            temperature=0.7,
        ),
    ),
    groq_api_key="gsk_xxx",
    openrouter_api_key="sk-or-xxx",
)

client = MemBlocksClient(config)
# client.conversation_llm → OpenRouterLLMProvider (claude-opus-4, temp=0.7)
# Internal pipeline tasks → GroqLLMProvider (kimi-k2-instruct-0905, temp=0.0)
```

When `llm_settings` is **not** set, the client auto-constructs equivalent settings from the flat legacy fields (`llm_provider_name`, `llm_model`, per-task temperature env vars). Existing code requires no changes.

---

## Logger

memBlocks uses Python's standard `logging` module. All log output is suppressed by default — the library attaches a `NullHandler` to its root logger so it is silent in any application that does not configure it.

### Getting a Logger (for Contributors)

Internal modules obtain a child logger at module level:

```python
from memblocks.logger import get_logger

logger = get_logger(__name__)
# e.g. "memblocks.llm.gemini_provider", "memblocks.services.session", etc.
```

`get_logger` is a thin wrapper over `logging.getLogger`. Using `__name__` inside any `memblocks.*` module automatically creates a child of the root `memblocks` logger, so handlers and levels propagate without extra wiring.

### Logger Hierarchy

```
memblocks                            ← root library logger (NullHandler by default)
├── memblocks.client
├── memblocks.llm.groq_provider
├── memblocks.llm.gemini_provider
├── memblocks.services.session
├── memblocks.services.session_manager
├── memblocks.services.block_manager
├── memblocks.services.core_memory
├── memblocks.services.semantic_memory
├── memblocks.services.memory_pipeline
├── memblocks.storage.mongo
├── memblocks.storage.qdrant
└── memblocks.storage.embeddings
```

### Enabling Logs in Your Application

```python
import logging

# Show all INFO+ messages from every memblocks module
logging.getLogger("memblocks").setLevel(logging.INFO)
logging.getLogger("memblocks").addHandler(logging.StreamHandler())
```

Structured / file logging:

```python
import logging

handler = logging.FileHandler("memblocks.log")
handler.setFormatter(
    logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s")
)

root = logging.getLogger("memblocks")
root.setLevel(logging.DEBUG)
root.addHandler(handler)
```

Filtering to a specific module:

```python
import logging

# Only Gemini provider logs
logging.getLogger("memblocks.llm.gemini_provider").setLevel(logging.DEBUG)
logging.getLogger("memblocks.llm.gemini_provider").addHandler(logging.StreamHandler())
```

### Log Levels Used by the Library

| Level | When emitted |
|-------|-------------|
| `DEBUG` | Provider init details, Arize disabled notice, connection info |
| `INFO` | Block created, session started, pipeline milestones |
| `WARNING` | Optional packages missing (e.g. Arize), non-fatal issues |
| `ERROR` | Storage failures, LLM errors |

### `get_logger` API

```python
from memblocks.logger import get_logger

logger = get_logger(name: str) -> logging.Logger
```

**Args:**
- `name` — Typically `__name__` of the calling module.

**Returns:**  
A `logging.Logger` instance named `name`, which is a child of `memblocks` when called from inside the library.

**Example:**

```python
from memblocks.logger import get_logger

logger = get_logger(__name__)

logger.debug("Connecting to Qdrant at %s:%s", host, port)
logger.info("Created block %s", block_id)
logger.warning("Arize monitoring disabled — keys not set")
logger.error("Failed to store vector: %s", exc)
```

---

## CoreMemoryService (Internal)

> **Note:** This service is used internally by the library. Users typically interact with core memory through `Block.retrieve()` and `Block.core_retrieve()`. Direct access is not exposed via `MemBlocksClient`.

Manage persistent "facts about the user."

Core memory consists of two sections:
- **Persona**: How the AI should behave
- **Human**: Stable facts about the user

### Methods

#### `get(block_id: str) -> Optional[CoreMemoryUnit]`

Retrieve core memory for a block.

```python
core = await core_service.get("block_abc123")
if core:
    print(f"Persona: {core.persona_content}")
    print(f"Human: {core.human_content}")
```

#### `extract(messages: List[Dict], old_core_memory: Optional[CoreMemoryUnit] = None, ...) -> CoreMemoryUnit`

Create an updated CoreMemoryUnit from conversation messages and previous state.

```python
messages = [{"role": "user", "content": "My name is Alice and I live in NYC."}]
new_core = await core_service.extract(messages, old_core_memory)
```

#### `save(block_id: str, memory_unit: CoreMemoryUnit) -> bool`

Manually save core memory.

```python
from memblocks import CoreMemoryUnit

core = CoreMemoryUnit(
    persona_content="The AI is helpful and concise.",
    human_content="User is named Alice, lives in NYC."
)
await core_service.save("block_abc123", core)
```

#### `update(block_id: str, messages: List[Dict], ...) -> CoreMemoryUnit`

Extract and immediately persist updated core memory.

```python
# Usually called automatically by MemoryPipeline
messages = [{"role": "user", "content": "My name is Alice and I live in NYC."}]
updated = await core_service.update("block_abc123", messages)
```

---

## SemanticMemoryService (Internal)

> **Note:** This service is used internally by the library. Users typically interact with semantic memory through `Block.retrieve()` and `Block.semantic_retrieve()`. Direct access is not exposed via `MemBlocksClient`.

Manage vector-searchable memories.

### Methods

#### `extract(messages: List[Dict], ps1_prompt: str = PS1_SEMANTIC_PROMPT) -> List[SemanticMemoryUnit]`

Extract semantic memories from conversation (PS1 pipeline step).

```python
from memblocks.prompts import PS1_SEMANTIC_PROMPT

messages = [
    {"role": "user", "content": "I just finished my ML certification."},
    {"role": "assistant", "content": "Congratulations!"},
]

memories = await semantic_service.extract(messages, PS1_SEMANTIC_PROMPT)
for mem in memories:
    print(f"[{mem.type}] {mem.content}")
```

#### `store(memory_unit: SemanticMemoryUnit) -> List[MemoryOperation]`

Store a memory with PS2 conflict resolution.

```python
operations = await semantic_service.store(memory)
for op in operations:
    print(f"{op.operation}: {op.content[:50]}...")
```

#### `extract_and_store(messages: List[Dict], ps1_prompt: str = PS1_SEMANTIC_PROMPT, min_confidence: float = 0.0) -> List[SemanticMemoryUnit]`

Convenience method: extract AND store semantic memories in one call.

```python
memories = await semantic_service.extract_and_store(
    messages=messages,
    min_confidence=0.7,
)
for mem in memories:
    print(f"[{mem.type}] {mem.content}")
```

#### `retrieve(query_texts: List[str], top_k: int = 5) -> List[List[SemanticMemoryUnit]]`

Retrieve semantically similar memories. **Note: This is a synchronous method.**

```python
# This is NOT async - don't use await
results = semantic_service.retrieve(
    query_texts=["machine learning projects"],
    top_k=5,
)

for query_results in results:
    for memory in query_results:
        print(f"[{memory.type}] {memory.content}")
```

---

## Transparency Layer

Observe internal library operations for debugging and monitoring.

### OperationLog

Thread-safe log of all database writes.

```python
# Get recent MongoDB operations
ops = client.operation_log.get_entries(limit=50, db_type="mongo")
for op in ops:
    print(f"{op.operation_type} on {op.collection_name}: {op.payload_summary}")

# Get summary counts
summary = client.operation_log.summary()
print(summary)  # {'insert': 10, 'update': 5, 'delete': 1}
```

### RetrievalLog

Track memory retrievals.

```python
# Get recent retrievals
retrievals = client.retrieval_log.get_entries(limit=20)
for r in retrievals:
    print(f"Query: {r.query_text}")
    print(f"Results: {r.num_results}")
```

### ProcessingHistory

Track memory pipeline runs.

```python
# Get recent pipeline runs
runs = client.processing_history.get_runs(limit=10)
for run in runs:
    print(f"Task: {run.task_id}")
    print(f"Status: {run.status}")
    print(f"Messages processed: {run.input_message_count}")
```

### EventBus

Subscribe to real-time events.

```python
def on_memory_stored(payload):
    print(f"Memory stored: {payload['content'][:50]}")

def on_pipeline_complete(payload):
    print(f"Pipeline done: {payload['task_id']}")

client.subscribe("on_memory_stored", on_memory_stored)
client.subscribe("on_pipeline_completed", on_pipeline_complete)
```

**Available Events:**

| Event | When Fired |
|-------|------------|
| `on_memory_extracted` | After PS1 extraction |
| `on_conflict_resolved` | After PS2 conflict resolution |
| `on_memory_stored` | After memory written to Qdrant |
| `on_core_memory_updated` | After core memory updated |
| `on_summary_generated` | After summary created |
| `on_pipeline_started` | When pipeline begins |
| `on_pipeline_completed` | When pipeline finishes |
| `on_pipeline_failed` | When pipeline errors |
| `on_memory_retrieved` | When memories retrieved |
| `on_db_write` | On any DB write |
| `on_message_processed` | After a chat message is fully processed |

---

## Data Models

### Block (Stateful Object)

```python
from memblocks import Block

# Returned by client.create_block() / client.get_block()
block.id                      # "block_xxx"
block.name                    # "Work Memory"
block.description             # "..."
block.user_id                 # "alice"
block.semantic_collection     # "block_xxx_semantic"
block.core_memory_block_id    # "block_xxx"
block.resource_collection     # "block_xxx_resource"
```

### Session (Stateful Object)

```python
from memblocks import Session

# Returned by client.create_session() / client.get_session()
session.id         # "session_xxx"
session.user_id    # "alice"
session.block_id   # "block_xxx"
session.created_at # "2024-01-15T10:00:00"
```

### MemoryBlock (Pydantic Model)

Internal model for MongoDB persistence. Used by `BlockManager`.

```python
from memblocks import MemoryBlock, MemoryBlockMetaData

block = MemoryBlock(
    meta_data=MemoryBlockMetaData(
        id="block_xxx",
        created_at="2024-01-15T10:00:00",
        updated_at="2024-01-15T10:00:00",
        usage=[],
        user_id="alice",
    ),
    name="Work Memory",
    description="Professional context",
    semantic_collection="block_xxx_semantic",
    core_memory_block_id="block_xxx",
    resource_collection="block_xxx_resource",
    is_active=False,
)
```

### SemanticMemoryUnit

```python
from memblocks import SemanticMemoryUnit
from memblocks.models import MemoryUnitMetaData

memory = SemanticMemoryUnit(
    content="User completed a machine learning certification.",
    type="event",
    source="conversation",
    confidence=0.95,
    memory_time="2024-01-15T10:30:00",  # Optional, mainly for "event" type
    entities=["machine learning", "certification"],
    keywords=["ML certification", "completed"],
    updated_at="2024-01-15T10:30:00",
    meta_data=MemoryUnitMetaData(usage=["2024-01-15T10:30:00"]),
)
```

### CoreMemoryUnit

```python
from memblocks import CoreMemoryUnit

core = CoreMemoryUnit(
    persona_content="The AI is helpful and concise.",
    human_content="User is named Alice, a software engineer in NYC."
)
```

### RetrievalResult

```python
from memblocks import RetrievalResult

result = RetrievalResult(
    core=CoreMemoryUnit(...),
    semantic=[SemanticMemoryUnit(...), ...],
    resource=[],
)

print(result.to_prompt_string())
print(result.is_empty())
```

### MemoryOperation

```python
from memblocks import MemoryOperation

op = MemoryOperation(
    operation="ADD",  # "ADD" | "UPDATE" | "DELETE" | "NONE"
    content="Memory content here",
    memory_id="uuid-optional",
    old_content="Previous content for UPDATE",
)
```

---

## Complete Example

```python
import asyncio
import logging
from memblocks import MemBlocksClient, MemBlocksConfig

# Optional: enable library logs
logging.getLogger("memblocks").setLevel(logging.INFO)
logging.getLogger("memblocks").addHandler(logging.StreamHandler())

async def main():
    # Use Gemini as the LLM provider
    config = MemBlocksConfig(
        llm_provider_name="gemini",
        gemini_api_key="AIzaSy_xxxxxxxxx",
        llm_model="gemini-2.0-flash",
    )
    client = MemBlocksClient(config)
    
    # --- Phase A: Initialization ---
    user = await client.get_or_create_user("alice")
    block = await client.create_block(
        user_id="alice",
        name="Personal Assistant",
        description="General-purpose memory"
    )
    session = await client.create_session(user_id="alice", block_id=block.id)
    
    # --- Phase B: Conversation Loop ---
    messages_to_send = [
        "Hi, I'm Alice. I work as a software engineer.",
        "I'm currently learning machine learning.",
        "My favorite framework is PyTorch.",
    ]
    
    for user_msg in messages_to_send:
        # 1. Retrieve context
        context = await block.retrieve(user_msg)
        memory_window = await session.get_memory_window()
        summary = await session.get_recursive_summary()
        
        # 2. Build system prompt
        system_parts = ["You are a helpful assistant."]
        if summary:
            system_parts.append(f"<Summary>\n{summary}\n</Summary>")
        if not context.is_empty():
            system_parts.append(context.to_prompt_string())
        system_prompt = "\n\n".join(system_parts)
        
        # 3. Call LLM
        messages = (
            [{"role": "system", "content": system_prompt}]
            + memory_window
            + [{"role": "user", "content": user_msg}]
        )
        ai_response = await client.conversation_llm.chat(messages=messages)
        
        print(f"User: {user_msg}")
        print(f"Assistant: {ai_response}\n")
        
        # 4. Persist turn
        await session.add(user_msg=user_msg, ai_response=ai_response)
    
    # --- Inspect Memory ---
    core_context = await block.core_retrieve()
    if core_context.core:
        print("=== Core Memory ===")
        print(f"Persona: {core_context.core.persona_content}")
        print(f"Human: {core_context.core.human_content}")
    
    await client.close()

asyncio.run(main())
```

---

## Next Steps

- [Setup Guide](./01_SETUP_GUIDE.md) — Installation and configuration
- [Deep Technical Overview](./03_TECHNICAL_OVERVIEW.md) — Architecture and data flow
