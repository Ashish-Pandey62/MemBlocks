# MemBlocks

> A Python library for modular, section-aware memory management in LLM applications

## Overview

**MemBlocks** is a Python library that solves the context problem in LLM applications. Instead of dumping entire conversation histories or using flat RAG, MemBlocks organises memory into independent, attachable blocks — each scoped to a distinct knowledge domain (e.g., work, personal, academic) — with section-specific storage, retrieval, and update strategies.

This repository contains:
- **`memblocks_lib/`** — The core Python library
- **`backend/`** — FastAPI REST API demo wrapping the library
- **`frontend/`** — React web UI demo consuming the backend
- **`mcp_server/`** — MCP server integration for AI assistants (Claude Desktop, etc.)
- **`evaluation/`** — LoCoMo benchmark evaluation harness

---

## The Problem

LLMs lose context over time. Current solutions either:
- Send full chat histories — expensive, hits token limits fast
- Use flat RAG — treats all memory the same, creates retrieval noise, no domain separation

---

## The Solution

MemBlocks introduces **memory blocks** — independently attachable memory spaces, each partitioned into three structured sections:

| Section | Purpose | Retrieval |
|---|---|---|
| **Core Memory** | Persistent high-priority facts (persona, user attributes) | Always injected in full — no search needed |
| **Semantic Memory** | Extracted facts and events with conflict-aware deduplication | Hybrid dense + sparse (SPLADE) search with RRF reranking |
| **Recursive Summary** | Progressively compressed recent conversational state | Always injected in full — no search needed |

Memory updates are driven by background agentic workflows triggered when the sliding message window reaches its configured limit (default: 10 messages). Three workflows run in parallel: Core Memory extraction, Semantic Memory extraction with conflict resolution (ADD / UPDATE / DELETE / NOOP), and Recursive Summary regeneration.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- [UV package manager](https://github.com/astral-sh/uv)

### Setup

```bash
git clone https://github.com/Ashish-Pandey62/MemBlocks.git
cd MemBlocks

# Copy and fill in your API keys
cp .env.example .env

# Install all packages
uv sync --all-packages

# Start infrastructure (Qdrant on :6333, Ollama on :11434)
docker-compose up -d
```

### Basic Usage

```python
import asyncio
from memblocks import MemBlocksClient, MemBlocksConfig

async def main():
    config = MemBlocksConfig()           # reads from .env
    client = MemBlocksClient(config)

    # --- One-time setup ---
    user    = await client.get_or_create_user("alice")
    block   = await client.create_block(user_id="alice", name="Work Memory")
    session = await client.create_session(user_id="alice", block_id=block.id)

    # --- Per-turn loop ---
    user_msg = "What did we decide about the API design?"

    context  = await block.retrieve(user_msg)          # hybrid retrieval across all sections
    messages = await session.get_memory_window()       # last N conversation turns
    summary  = await session.get_recursive_summary()   # compressed recent context

    # Assemble prompt and call your own LLM
    system   = "You are a helpful assistant.\n\n" + context.to_prompt_string()
    response = my_llm.chat(system, messages + [{"role": "user", "content": user_msg}])

    # Persist the turn — triggers background memory workflows automatically
    await session.add(user_msg=user_msg, ai_response=response)

    await client.close()

asyncio.run(main())
```

---

## Repository Structure

```
memblocks_lib/               # Core Python library
├── src/memblocks/
│   ├── client.py            # MemBlocksClient — main API entry point
│   ├── config.py            # MemBlocksConfig (Pydantic settings)
│   ├── services/            # block, session, core_memory, semantic_memory, memory_pipeline
│   ├── storage/             # MongoDBAdapter, QdrantAdapter, EmbeddingProvider
│   ├── llm/                 # Provider integrations: Groq, OpenRouter, Gemini, Ollama
│   ├── models/              # Pydantic schemas (block, memory, retrieval, llm_outputs)
│   └── prompts/             # Agentic workflow prompts (PS1 extraction, PS2 resolution, summary)

backend/                     # FastAPI REST API demo
├── src/api/
│   ├── main.py              # FastAPI app entrypoint
│   ├── routers/             # blocks, chat, memory, users, auth, transparency
│   └── models/requests.py   # Request schemas

mcp_server/                  # MCP server for AI assistant integration
├── src/server.py
└── src/cli.py

frontend/                    # React web UI demo
├── src/components/          # ChatInterface, BlockManager
└── src/api/                 # API client

evaluation/                  # LoCoMo benchmark harness
├── eval.py / locomo_eval.py
├── runners/
├── metrics/
└── datasets/

tests/                       # Integration tests
docker-compose.yml           # Qdrant + Ollama services
pyproject.toml               # UV workspace config
```

---

## API Reference

### Initialization

```python
from memblocks import MemBlocksClient, MemBlocksConfig

config = MemBlocksConfig()        # reads .env; all fields have sensible defaults
client = MemBlocksClient(config)
```

### User & Block Management

```python
user  = await client.get_or_create_user(user_id="alice")
block = await client.create_block(user_id="alice", name="Work", description="Work context")
blocks = await client.get_user_blocks(user_id="alice")
await client.delete_block(block_id=block.id, user_id="alice")
```

### Session & Conversation

```python
session = await client.create_session(user_id="alice", block_id=block.id)

context  = await block.retrieve(user_msg)         # full hybrid retrieval
messages = await session.get_memory_window()      # sliding window of recent turns
summary  = await session.get_recursive_summary()  # compressed context

await session.add(user_msg=user_msg, ai_response=response)  # persist + trigger pipeline
await session.flush()                              # force pipeline run immediately
```

### Isolated Retrieval

```python
core_ctx     = await block.core_retrieve()          # Core Memory only, no vector search
semantic_ctx = await block.semantic_retrieve(query) # Semantic Memory only
```

### Transparency & Observability

```python
client.subscribe("on_memory_extracted", callback)
client.subscribe("on_conflict_resolved", callback)
client.subscribe("on_core_memory_updated", callback)

client.get_retrieval_log()       # per-query retrieval details
client.get_processing_history()  # pipeline run history
client.get_llm_usage()           # token usage + latency per task type
```

---

## Configuration

Key environment variables (see `.env.example` for the full list):

```bash
# LLM provider (groq | openrouter | gemini | ollama)
LLM_PROVIDER_NAME=groq
GROQ_API_KEY=your_groq_key
OPENROUTER_API_KEY=your_openrouter_key
GEMINI_API_KEY=your_gemini_key

# Vector database
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Embeddings (local)
OLLAMA_BASE_URL=http://localhost:11434

# Reranking
COHERE_API_KEY=your_cohere_key

# Memory pipeline behaviour
MEMORY_WINDOW=10      # messages before pipeline triggers
KEEP_LAST_N=4         # messages to retain after pipeline flush

# MongoDB
MONGO_URI=mongodb://localhost:27017
```

Per-task LLM configuration (optional):

```python
from memblocks.llm.task_settings import LLMSettings, LLMTaskSettings

config = MemBlocksConfig(
    llm_settings=LLMSettings(
        default=LLMTaskSettings(provider="openrouter", model="meta-llama/llama-4-maverick"),
        retrieval=LLMTaskSettings(provider="groq", model="llama-3.1-8b-instant"),
    )
)
```

---

## Running the Demo Applications

**Backend API:**
```bash
uv run python -m uvicorn backend.src.api.main:app --reload
```

**Frontend:**
```bash
cd frontend && npm install && npm run dev
```

**MCP Server** (configure in your AI assistant):
```json
{
  "mcp": {
    "memblocks": {
      "type": "local",
      "command": ["uv", "run", "python", "-m", "mcp_server.server"],
      "environment": {"MEMBLOCKS_USER_ID": "your_user_id"}
    }
  }
}
```

**Evaluation:**
```bash
uv run python evaluation/locomo_eval.py
```

---

## Running Tests

```bash
uv run pytest tests/
```

---

## Project Repository

[https://github.com/Ashish-Pandey62/MemBlocks](https://github.com/Ashish-Pandey62/MemBlocks)
