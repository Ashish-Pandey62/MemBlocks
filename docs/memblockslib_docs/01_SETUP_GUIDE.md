# memBlocks Library — Setup Guide

This guide covers installation, prerequisites, configuration, and first-run setup for the `memblocks` library.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [LLM Providers](#llm-providers)
5. [Per-Task LLM Configuration](#per-task-llm-configuration)
6. [Logging](#logging)
7. [First Run](#first-run)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Infrastructure

The library requires three services to be running:

| Service | Default Port | Purpose |
|---------|--------------|---------|
| **MongoDB** | 27017 | User data, blocks, core memories, sessions |
| **Qdrant** | 6333 (REST), 6334 (gRPC) | Vector storage for semantic memories |
| **Ollama** | 11434 | Local embeddings (nomic-embed-text model) |

### Quick Start with Docker

```bash
# From the project root
docker-compose up -d
```

This starts all three services. Verify they're running:

```bash
docker ps
```

### Pull the Embedding Model

```bash
docker exec -it ollama ollama pull nomic-embed-text
```

---

## Installation

### Using UV (Recommended)

The project uses [UV](https://astral.sh/uv/) as its package manager:

```bash
# Install UV if not already installed
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell):
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Sync all workspace packages
uv sync --all-packages
```

### Using pip

```bash
pip install memblocks
```

### Requirements

- **Python**: 3.11 or higher
- **Operating System**: macOS, Linux, or Windows

---

## Configuration

### Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```env
# === LLM Provider Selection (Required) ===
# Choose your provider: "groq" (default), "gemini", "openrouter", or "ollama"
LLM_PROVIDER_NAME=groq

# === Groq API (Required if using Groq) ===
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxx
LLM_MODEL=moonshotai/kimi-k2-instruct-0905

# === Google Gemini API (Required if using Gemini) ===
# GEMINI_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxx
# LLM_MODEL=gemini-2.0-flash

# === OpenRouter API (Required if using OpenRouter) ===
# OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxx
# LLM_MODEL=moonshotai/kimi-k2-instruct-0905
# OPENROUTER_FALLBACK_MODELS=anthropic/claude-3-5-haiku,google/gemini-flash-1.5
# OPENROUTER_ENABLE_THINKING=false

# === Ollama (Local) ===
# OLLAMA_BASE_URL=http://localhost:11434
# LLM_MODEL=llama3.2:3b

# === MongoDB (Required) ===
MONGODB_CONNECTION_STRING=mongodb://localhost:27017
MONGODB_DATABASE_NAME=memblocks_v2
MONGO_COLLECTION_USERS=users
MONGO_COLLECTION_BLOCKS=memory_blocks
MONGO_COLLECTION_CORE_MEMORIES=core_memories

# === Qdrant (Required) ===
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_PREFER_GRPC=true

# === Ollama / Embeddings (Required) ===
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDINGS_MODEL=nomic-embed-text

# === Memory Pipeline Behavior (Optional) ===
MEMORY_WINDOW=10          # Messages before triggering pipeline
KEEP_LAST_N=4             # Messages retained after flush

# === LLM Temperatures (Optional) ===
LLM_CONVO_TEMPERATURE=0.7
LLM_SEMANTIC_EXTRACTION_TEMPERATURE=0.0
LLM_CORE_EXTRACTION_TEMPERATURE=0.0
LLM_RECURSIVE_SUMMARY_GEN_TEMPERATURE=0.3
LLM_MEMORY_UPDATE_TEMPERATURE=0.0
```

### Configuration via Code

You can also configure programmatically:

```python
from memblocks import MemBlocksClient, MemBlocksConfig

# Option 1: Load from .env (automatic)
config = MemBlocksConfig()

# Option 2: Groq — explicit values
config = MemBlocksConfig(
    llm_provider_name="groq",
    groq_api_key="gsk_xxxxxxxxx",
    mongodb_connection_string="mongodb://localhost:27017",
    qdrant_host="localhost",
    qdrant_port=6333,
    ollama_base_url="http://localhost:11434",
    memory_window_limit=10,
    keep_last_n=4,
)

# Option 3: Gemini — explicit values
config = MemBlocksConfig(
    llm_provider_name="gemini",
    gemini_api_key="AIzaSy_xxxxxxxxx",
    llm_model="gemini-2.0-flash",
    mongodb_connection_string="mongodb://localhost:27017",
    qdrant_host="localhost",
    qdrant_port=6333,
    ollama_base_url="http://localhost:11434",
)

# Option 4: OpenRouter — explicit values
config = MemBlocksConfig(
    llm_provider_name="openrouter",
    openrouter_api_key="sk-or-xxxxxxxxx",
    llm_model="moonshotai/kimi-k2-instruct-0905",
    mongodb_connection_string="mongodb://localhost:27017",
    qdrant_host="localhost",
    qdrant_port=6333,
    ollama_base_url="http://localhost:11434",
)

# Create client — provider is wired automatically
client = MemBlocksClient(config)
```

---

## Configuration Reference

### Core Settings

| Setting | Environment Variable | Default | Description |
|---------|---------------------|---------|-------------|
| `llm_provider_name` | `LLM_PROVIDER_NAME` | `groq` | Active LLM provider (`"groq"`, `"gemini"`, `"openrouter"`, or `"ollama"`) |
| `groq_api_key` | `GROQ_API_KEY` | `None` | API key for Groq (required when provider is `"groq"`) |
| `gemini_api_key` | `GEMINI_API_KEY` | `None` | API key for Google Gemini (required when provider is `"gemini"`) |
| `openrouter_api_key` | `OPENROUTER_API_KEY` | `None` | API key for OpenRouter (required when provider is `"openrouter"`) |
| `cohere_api_key` | `COHERE_API_KEY` | `None` | API key for Cohere re-ranker (required when using Cohere-based reranking) |
| `ollama_base_url` | `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL (required when provider is `"ollama"`) |
| `llm_model` | `LLM_MODEL` | `moonshotai/kimi-k2-instruct-0905` | Model identifier (provider-specific) |
| `mongodb_connection_string` | `MONGODB_CONNECTION_STRING` | *required* | MongoDB connection URI |
| `mongodb_database_name` | `MONGODB_DATABASE_NAME` | `memblocks_v2` | Database name |
| `qdrant_host` | `QDRANT_HOST` | `localhost` | Qdrant server host |
| `qdrant_port` | `QDRANT_PORT` | `6333` | Qdrant REST port |
| `qdrant_prefer_grpc` | `QDRANT_PREFER_GRPC` | `true` | Use gRPC for Qdrant |
| `ollama_base_url` | `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `embeddings_model` | `EMBEDDINGS_MODEL` | `nomic-embed-text` | Embedding model name |

### Pipeline Settings

| Setting | Environment Variable | Default | Description |
|---------|---------------------|---------|-------------|
| `memory_window_limit` | `MEMORY_WINDOW` | `10` | Messages to accumulate before processing |
| `keep_last_n` | `KEEP_LAST_N` | `4` | Messages kept after pipeline flush |

### Temperature Settings

| Setting | Environment Variable | Default | Purpose |
|---------|---------------------|---------|---------|
| `llm_convo_temperature` | `LLM_CONVO_TEMPERATURE` | `0.7` | Chat responses |
| `llm_semantic_extraction_temperature` | `LLM_SEMANTIC_EXTRACTION_TEMPERATURE` | `0.0` | PS1 memory extraction |
| `llm_core_extraction_temperature` | `LLM_CORE_EXTRACTION_TEMPERATURE` | `0.0` | Core memory updates |
| `llm_recursive_summary_gen_temperature` | `LLM_RECURSIVE_SUMMARY_GEN_TEMPERATURE` | `0.3` | Summary generation |
| `llm_memory_update_temperature` | `LLM_MEMORY_UPDATE_TEMPERATURE` | `0.0` | PS2 conflict resolution |

---

## LLM Providers

memBlocks ships three built-in LLM provider backends. The active provider is selected via `LLM_PROVIDER_NAME` and instantiated automatically by `MemBlocksClient`.

### Groq (Default)

Uses [`langchain-groq`](https://pypi.org/project/langchain-groq/) to call Groq's hosted inference API.

**Required env var:** `GROQ_API_KEY`

```env
LLM_PROVIDER_NAME=groq
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxx
LLM_MODEL=moonshotai/kimi-k2-instruct-0905
```

```python
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig(
    llm_provider_name="groq",
    groq_api_key="gsk_xxxxxxxxx",
    llm_model="moonshotai/kimi-k2-instruct-0905",
)
client = MemBlocksClient(config)
```

### Gemini

Uses [`langchain-google-genai`](https://pypi.org/project/langchain-google-genai/) to call Google's Gemini API.

**Required env var:** `GEMINI_API_KEY`

Get your key from [Google AI Studio](https://aistudio.google.com/apikey).

```env
LLM_PROVIDER_NAME=gemini
GEMINI_API_KEY=AIzaSy_xxxxxxxxxxxxxxxxxx
LLM_MODEL=gemini-2.0-flash
```

```python
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig(
    llm_provider_name="gemini",
    gemini_api_key="AIzaSy_xxxxxxxxx",
    llm_model="gemini-2.0-flash",
)
client = MemBlocksClient(config)
```

### OpenRouter

Uses [`langchain-openai`](https://pypi.org/project/langchain-openai/) against the [OpenRouter](https://openrouter.ai/) API, which provides unified access to hundreds of models from different providers.

**Required env var:** `OPENROUTER_API_KEY`

Get your key from [openrouter.ai/keys](https://openrouter.ai/keys).

```env
LLM_PROVIDER_NAME=openrouter
OPENROUTER_API_KEY=sk-or-xxxxxxxxxxxxxxxxxx
LLM_MODEL=moonshotai/kimi-k2-instruct-0905

# Optional: comma-separated fallback models tried in order on failure
OPENROUTER_FALLBACK_MODELS=anthropic/claude-3-5-haiku,google/gemini-flash-1.5

# Optional: enable extended thinking (supported models only)
OPENROUTER_ENABLE_THINKING=false
```

```python
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig(
    llm_provider_name="openrouter",
    openrouter_api_key="sk-or-xxxxxxxxx",
    llm_model="moonshotai/kimi-k2-instruct-0905",
)
client = MemBlocksClient(config)
```

**OpenRouter-specific features:**

| Feature | Env Var / Config Field | Description |
|---------|----------------------|-------------|
| Fallback models | `OPENROUTER_FALLBACK_MODELS` / `openrouter_fallback_models` | Comma-separated list of model IDs tried in sequence if the primary model fails |
| Enable thinking | `OPENROUTER_ENABLE_THINKING` / `openrouter_enable_thinking` | Pass `enable_thinking: true` to the OpenRouter API (requires a reasoning-capable model) |

### Ollama (Local)
Uses [`langchain-ollama`](https://pypi.org/project/langchain-ollama/) to run open-source models locally.

**Required:** Ollama must be installed and running.

1. Install: https://ollama.com
2. Start: `ollama serve`
3. Pull model: `ollama pull <model-name>`

```env
LLM_PROVIDER_NAME=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=local-llm-model
```

```python
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig(
    llm_provider_name="ollama",
    llm_model="local-llm-model",
)
client = MemBlocksClient(config)
```

**Note:** No API key is required. Set `OLLAMA_BASE_URL` if your Ollama server is not at the default `http://localhost:11434`.

### Using a Custom Provider

You can bypass the built-in providers entirely by passing your own `LLMProvider` instance directly:

```python
from memblocks.llm.base import LLMProvider
from memblocks import MemBlocksClient, MemBlocksConfig

class MyOpenAIProvider(LLMProvider):
    def create_structured_chain(self, system_prompt, pydantic_model, temperature=0.0):
        ...  # return a LangChain-compatible runnable

    async def chat(self, messages, temperature=None) -> str:
        ...  # return assistant response string

config = MemBlocksConfig(llm_provider_name="groq")  # provider_name is ignored when injecting
client = MemBlocksClient(config)
client.conversation_llm = MyOpenAIProvider(...)   # override after construction
# client.llm is an alias for client.conversation_llm (backward compatible)
```

> See [Methods and Interfaces](./02_METHODS_AND_INTERFACES.md#llmprovider-base-class) for the full `LLMProvider` interface.

### Optional Arize Monitoring

All three providers support [Arize Phoenix](https://arize.com/) tracing via `openinference`. Set the following env vars to enable it:

```env
ARIZE_SPACE_ID=your_space_id
ARIZE_API_KEY=your_api_key
ARIZE_PROJECT_NAME=memBlocks
```

Install the optional dependencies:

```bash
pip install arize openinference-instrumentation-langchain
```

If the packages are absent but the keys are set, the provider logs a warning and continues without monitoring.

---

## Per-Task LLM Configuration

By default, the same provider and model handle all internal LLM tasks (conversation, memory extraction, conflict resolution, etc.). The `LLMSettings` / `LLMTaskSettings` system lets you assign a **different provider, model, or temperature to each task** — for example, using a cheap fast model for extraction while routing conversation through a premium model.

### Task Names

| Task name | What it does |
|-----------|-------------|
| `conversation` | The main `client.conversation_llm.chat(...)` call (your per-turn LLM) |
| `ps1_semantic_extraction` | PS1 — extract memories from conversation |
| `ps2_conflict_resolution` | PS2 — deduplicate / merge memories |
| `retrieval` | Retrieval-time reranking (if applicable) |
| `core_memory_extraction` | Update core memory persona + human facts |
| `recursive_summary` | Generate recursive conversation summaries |

### Basic Usage — `LLMSettings`

```python
from memblocks import MemBlocksClient, MemBlocksConfig
from memblocks import LLMSettings, LLMTaskSettings

config = MemBlocksConfig(
    # Infrastructure settings (still required)
    mongodb_connection_string="mongodb://localhost:27017",
    qdrant_host="localhost",
    ollama_base_url="http://localhost:11434",

    # Per-task LLM settings
    llm_settings=LLMSettings(
        # Default applies to every task that has no explicit override
        default=LLMTaskSettings(
            provider="groq",
            model="moonshotai/kimi-k2-instruct-0905",
            temperature=0.0,
        ),
        # Override just the conversation task
        conversation=LLMTaskSettings(
            provider="openrouter",
            model="anthropic/claude-opus-4",
            temperature=0.7,
        ),
        # Override summary generation
        recursive_summary=LLMTaskSettings(
            provider="gemini",
            model="gemini-2.0-flash",
            temperature=0.3,
        ),
    ),
    # API keys for every provider you reference above
    groq_api_key="gsk_xxx",
    openrouter_api_key="sk-or-xxx",
    gemini_api_key="AIzaSy_xxx",
)

client = MemBlocksClient(config)
```

### `LLMTaskSettings` Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `str` | *required* | `"groq"`, `"gemini"`, `"openrouter"`, or `"ollama"` |
| `model` | `str` | *required* | Model identifier for the chosen provider |
| `temperature` | `float` | `0.0` | Sampling temperature for this task |
| `fallback_models` | `List[str]` | `[]` | OpenRouter only — fallback model IDs tried in order |
| `enable_thinking` | `bool` | `False` | OpenRouter only — enable extended thinking |

### Backward Compatibility

If you do **not** set `llm_settings`, the client falls back to the flat legacy fields (`LLM_PROVIDER_NAME`, `LLM_MODEL`, per-task temperature env vars). No existing code needs to change.

---

## Logging

memBlocks uses Python's standard `logging` module with a single root logger named **`memblocks`**. By default all log output is suppressed (a `NullHandler` is attached), so the library is silent inside your application.

### Logger Hierarchy

Every internal module follows the `memblocks.<module>` naming convention:

```
memblocks                          ← root library logger
├── memblocks.client
├── memblocks.llm.groq_provider
├── memblocks.llm.gemini_provider
├── memblocks.services.session
├── memblocks.services.block_manager
├── memblocks.storage.mongo
├── memblocks.storage.qdrant
└── ...
```

Child loggers inherit handlers and level from the parent `memblocks` logger automatically.

### Enabling Logs in Your Application

```python
import logging

# Show all INFO and above from the entire library
logging.getLogger("memblocks").setLevel(logging.INFO)
logging.getLogger("memblocks").addHandler(logging.StreamHandler())
```

For structured output or file logging:

```python
import logging

handler = logging.FileHandler("memblocks.log")
handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))

logger = logging.getLogger("memblocks")
logger.setLevel(logging.DEBUG)
logger.addHandler(handler)
```

### Filtering to a Specific Module

```python
import logging

# Only show Gemini provider logs
logging.getLogger("memblocks.llm.gemini_provider").setLevel(logging.DEBUG)
logging.getLogger("memblocks.llm.gemini_provider").addHandler(logging.StreamHandler())
```

### Log Levels Used by the Library

| Level | When emitted |
|-------|-------------|
| `DEBUG` | Provider initialisation details, Arize disabled notice |
| `INFO` | Block created, session started, pipeline milestones |
| `WARNING` | Optional packages missing (e.g. Arize), non-fatal issues |
| `ERROR` | Storage failures, LLM errors |

### Using the Logger Inside the Library (for Contributors)

Internal modules obtain a logger at module level using `get_logger`:

```python
from memblocks.logger import get_logger

logger = get_logger(__name__)   # e.g. "memblocks.services.session"

logger.debug("Connecting to Qdrant at %s:%s", host, port)
logger.info("Created block %s", block_id)
logger.warning("Arize monitoring disabled — keys not set")
logger.error("Failed to store vector: %s", exc)
```

Because `__name__` inside any `memblocks.*` module always starts with `memblocks.`, all child loggers propagate to the root `memblocks` logger automatically — no extra wiring required.

---

## First Run

### Quick Test

```python
import asyncio
from memblocks import MemBlocksClient, MemBlocksConfig

async def main():
    # Initialize
    config = MemBlocksConfig()
    client = MemBlocksClient(config)
    
    # Phase A — Initialization (once per run/user/session)
    user = await client.get_or_create_user("alice")
    print(f"User: {user['user_id']}")
    
    block = await client.create_block(
        user_id="alice",
        name="Work Memory",
        description="Professional context and project details"
    )
    print(f"Created block: {block.name} ({block.id})")
    
    session = await client.create_session(user_id="alice", block_id=block.id)
    print(f"Created session: {session.id}")
    
    # Phase B — Per-turn loop
    user_msg = "Hello! I'm working on a machine learning project."
    
    # 1. Retrieve memory context
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
    
    # 3. Call LLM (you control this!)
    messages = (
        [{"role": "system", "content": system_prompt}]
        + memory_window
        + [{"role": "user", "content": user_msg}]
    )
    ai_response = await client.conversation_llm.chat(messages=messages)
    print(f"Response: {ai_response}")
    
    # 4. Persist the turn
    await session.add(user_msg=user_msg, ai_response=ai_response)
    
    # Cleanup
    await client.close()

asyncio.run(main())
```

### Expected Output

```
User: alice
   ✓ Created semantic collection: block_xxx_semantic
   ✓ Created core memory document: block_xxx
✅ Created memory block: block_xxx
✅ Created session: session_yyy (block: block_xxx)
Response: Hello! I'd be happy to help with your machine learning project...
```

---

## Library Philosophy

**memBlocks is a memory management library — not an inference engine.**

You control the LLM calls. The library handles:
- Memory retrieval (semantic, core, resource)
- Memory storage and deduplication
- Conversation window management
- Recursive summary generation

This design gives you maximum flexibility:
- Use any LLM provider
- Use any prompting strategy
- Use any conversation format
- The library stays out of your way

---

## Troubleshooting

### "GROQ_API_KEY not found"

**Solution**: Set `LLM_PROVIDER_NAME=groq` and provide the key:

```python
config = MemBlocksConfig(llm_provider_name="groq", groq_api_key="gsk_xxx")
```

### "GEMINI_API_KEY not found — set it in .env or pass to MemBlocksConfig"

**Solution**: Set `LLM_PROVIDER_NAME=gemini` and provide the key:

```python
config = MemBlocksConfig(llm_provider_name="gemini", gemini_api_key="AIzaSy_xxx")
```

Get a key at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey).

### "OPENROUTER_API_KEY not found"

**Solution**: Set `LLM_PROVIDER_NAME=openrouter` and provide the key:

```python
config = MemBlocksConfig(llm_provider_name="openrouter", openrouter_api_key="sk-or-xxx")
```

Get a key at [https://openrouter.ai/keys](https://openrouter.ai/keys).

### "Unknown LLM provider: …"

`LLM_PROVIDER_NAME` must be exactly `"groq"`, `"gemini"`, `"openrouter"`, or `"ollama"` (case-sensitive).

```env
LLM_PROVIDER_NAME=openrouter   # correct
LLM_PROVIDER_NAME=OpenRouter   # incorrect — will raise ValueError
```

### "MONGODB_CONNECTION_STRING not found"

**Solution**: Ensure MongoDB is running and the connection string is set:

```bash
# Check MongoDB is running
docker ps | grep mongo

# Start if needed
docker-compose up -d mongodb
```

### "Connection refused" to Qdrant

**Solution**: Verify Qdrant is accessible:

```bash
curl http://localhost:6333/collections
```

### "Ollama embedding error"

**Solution**: Ensure Ollama is running and the model is pulled:

```bash
# Check Ollama
curl http://localhost:11434/api/tags

# Pull model if missing
docker exec -it ollama ollama pull nomic-embed-text
```

### Import errors after installation

**Solution**: Ensure you're using UV to run scripts:

```bash
# Wrong
python my_script.py

# Correct
uv run python my_script.py
```

### Session state not persisting

The library persists sessions to MongoDB. If sessions disappear:

1. Check MongoDB is running
2. Verify `mongodb_connection_string` is correct
3. Check the `sessions` collection exists

### Library is completely silent / no log output

By default memBlocks attaches a `NullHandler` and produces no output. Enable logging explicitly:

```python
import logging
logging.getLogger("memblocks").setLevel(logging.DEBUG)
logging.getLogger("memblocks").addHandler(logging.StreamHandler())
```

---

## Next Steps

- [Methods and Interfaces](./02_METHODS_AND_INTERFACES.md) — API reference with examples
- [Deep Technical Overview](./03_TECHNICAL_OVERVIEW.md) — Architecture and data flow
