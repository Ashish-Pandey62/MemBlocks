# Codebase Structure

**Analysis Date:** 2026-05-04

## Directory Layout

```
MemBlocks/                           # UV workspace root
├── pyproject.toml                   # Workspace configuration
├── uv.lock                          # Dependency lock file
│
├── memblocks_lib/                   # Core memory management library
│   ├── pyproject.toml               # Library package config
│   └── src/memblocks/               # Source code
│       ├── __init__.py              # Public API exports
│       ├── client.py                # MemBlocksClient entry point
│       ├── config.py                # MemBlocksConfig
│       ├── llm/                     # LLM provider implementations
│       ├── models/                  # Data models and DTOs
│       ├── services/                # Business logic services
│       ├── storage/                 # Storage adapters
│       ├── logger/                  # Logging utilities
│       └── prompts/                 # Prompt templates
│
├── mcp_server/                      # MCP server for AI agents
│   ├── pyproject.toml               # Server package config
│   ├── server.py                    # FastMCP server + tools
│   ├── cli.py                      # CLI entry point
│   ├── state.py                    # User/block state management
│   └── tests/                       # Server tests
│
├── backend/                         # FastAPI REST API
│   ├── pyproject.toml               # Backend package config
│   └── src/
│       ├── api/
│       │   ├── main.py              # FastAPI app factory
│       │   ├── dependencies.py      # Dependency injection
│       │   ├── routers/             # API route modules
│       │   │   ├── auth.py
│       │   │   ├── users.py
│       │   │   ├── blocks.py
│       │   │   ├── chat.py
│       │   │   ├── memory.py
│       │   │   └── transparency.py
│       │   └── models/              # Request/response models
│       └── cli/                     # CLI tools
│
├── frontend/                        # React web UI
│   ├── package.json
│   ├── vite.config.js               # Vite build config
│   ├── tailwind.config.js           # Tailwind CSS config
│   └── src/
│       ├── main.jsx                 # React entry point
│       ├── App.jsx                  # Main app component
│       ├── api/
│       │   └── client.js            # Backend API client
│       ├── pages/                   # Page components
│       │   ├── Landing.jsx
│       │   ├── Login.jsx
│       │   └── Workspace.jsx
│       └── components/              # Reusable components
│           ├── AnalyticsPanel.jsx
│           ├── BlockManager.jsx
│           ├── BlockSelector.jsx
│           ├── ChatInterface.jsx
│           ├── ChatPanel.jsx
│           ├── MemoryViewer.jsx
│           ├── OptionsPanel.jsx
│           ├── ProcessingHistoryViewer.jsx
│           ├── SummaryViewer.jsx
│           └── UserSelector.jsx
│
├── evaluation/                      # Evaluation scripts
│   └── run_memblocks_evaluation.py
│
├── docs/                           # Documentation
│   └── memblockslib_docs/           # Library documentation
│       ├── 01_SETUP_GUIDE.md
│       ├── 02_METHODS_AND_INTERFACES.md
│       └── 03_TECHNICAL_OVERVIEW.md
│
├── docker-compose.yml              # Docker Compose for infra
├── Dockerfile.ollama               # Ollama container
└── opencode.json                   # OpenCode configuration
```

## Directory Purposes

**memblocks_lib/src/memblocks/:**
- Purpose: Core memory management library
- Contains: Client, services, models, storage adapters, LLM providers
- Key files: `client.py`, `config.py`, `services/block.py`, `services/session.py`

**memblocks_lib/src/memblocks/llm/:**
- Purpose: Pluggable LLM provider implementations
- Contains: Base class + provider implementations (Groq, Gemini, Ollama, OpenRouter)
- Key files: `base.py`, `groq_provider.py`, `gemini_provider.py`, `ollama_provider.py`

**memblocks_lib/src/memblocks/models/:**
- Purpose: Data models and DTOs
- Contains: Pydantic models for blocks, sessions, memory units, retrieval results
- Key files: `block.py`, `memory.py`, `retrieval.py`, `units.py`

**memblocks_lib/src/memblocks/services/:**
- Purpose: Business logic orchestration
- Contains: BlockManager, SessionManager, UserManager, CoreMemoryService, SemanticMemoryService
- Key files: `block_manager.py`, `session_manager.py`, `core_memory.py`, `semantic_memory.py`

**memblocks_lib/src/memblocks/storage/:**
- Purpose: Persistence adapters
- Contains: MongoDB, Qdrant, Embedding providers
- Key files: `mongo.py`, `qdrant.py`, `embeddings.py`

**mcp_server/:**
- Purpose: MCP server exposing memory tools to AI agents
- Contains: FastMCP server, tool definitions, state management
- Key files: `server.py`, `state.py`, `cli.py`

**backend/src/api/:**
- Purpose: REST API for web client
- Contains: FastAPI app, routers, request/response models
- Key files: `main.py`, `dependencies.py`, `routers/`

**frontend/src/:**
- Purpose: React web interface
- Contains: Components, pages, API client
- Key files: `main.jsx`, `App.jsx`, `api/client.js`, `pages/Workspace.jsx`

## Key File Locations

**Entry Points:**
- `memblocks_lib/src/memblocks/client.py`: Library entry point (MemBlocksClient)
- `mcp_server/server.py:1026`: MCP server entry (main function)
- `backend/src/api/main.py:105`: Backend API entry (app factory)
- `frontend/src/main.jsx`: Frontend entry point

**Configuration:**
- `pyproject.toml` (root): UV workspace configuration
- `memblocks_lib/pyproject.toml`: Library package config
- `memblocks_lib/src/memblocks/config.py`: Config class (reads .env)
- `frontend/vite.config.js`: Vite build config
- `frontend/tailwind.config.js`: Tailwind CSS config

**Core Logic:**
- `memblocks_lib/src/memblocks/services/block_manager.py`: Block CRUD operations
- `memblocks_lib/src/memblocks/services/session_manager.py`: Session lifecycle
- `memblocks_lib/src/memblocks/services/core_memory.py`: Core memory extraction/storage
- `memblocks_lib/src/memblocks/services/semantic_memory.py`: Semantic memory extraction/storage
- `memblocks_lib/src/memblocks/storage/qdrant.py`: Vector database operations

**Testing:**
- `mcp_server/tests/`: MCP server tests
- `tests/`: Library tests (test_hybrid.py, test_store_tools.py)

## Naming Conventions

**Files:**
- Python: snake_case (e.g., `block_manager.py`, `core_memory.py`)
- React/JSX: PascalCase (e.g., `ChatPanel.jsx`, `Workspace.jsx`)
- Config: kebab-case or snake_case (e.g., `vite.config.js`, `pyproject.toml`)

**Directories:**
- Python packages: snake_case (e.g., `memblocks_lib/`, `services/`)
- Frontend: PascalCase for components (e.g., `components/`, `pages/`)

**Classes:**
- PascalCase (e.g., `MemBlocksClient`, `BlockManager`, `QdrantAdapter`)
- Suffix patterns: `*Service`, `*Manager`, `*Adapter`, `*Provider`

**Functions/Methods:**
- snake_case (e.g., `create_block`, `get_user_blocks`, `retrieve`)

## Where to Add New Code

**New LLM Provider:**
- Implementation: `memblocks_lib/src/memblocks/llm/{provider}_provider.py`
- Pattern: Inherit from `LLMProvider` base class, implement `complete()` method
- Export: Add to `memblocks_lib/src/memblocks/__init__.py`

**New MCP Tool:**
- Implementation: `mcp_server/server.py` (add @mcp.tool decorated function)
- Pattern: Follow existing tool patterns with Pydantic input models

**New Backend API Endpoint:**
- Implementation: `backend/src/api/routers/{domain}.py`
- Register: Add to `backend/src/api/main.py` router inclusion

**New Frontend Component:**
- Implementation: `frontend/src/components/{ComponentName}.jsx`
- Usage: Import in `App.jsx` or parent component

**New Service:**
- Implementation: `memblocks_lib/src/memblocks/services/{service_name}.py`
- Wiring: Add to `MemBlocksClient.__init__()` constructor

## Special Directories

**memblocks_mcp_logs/:**
- Purpose: MCP server runtime logs
- Generated: Yes (created at runtime)
- Committed: No (in .gitignore)

**memblocks_cli_output/:**
- Purpose: CLI execution logs and history
- Generated: Yes (created at runtime)
- Committed: No

**evaluation/run_*/:**
- Purpose: Evaluation run artifacts (JSON, CSV)
- Generated: Yes (created at runtime)
- Committed: No

**__pycache__/:**
- Purpose: Python bytecode cache
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-05-04*