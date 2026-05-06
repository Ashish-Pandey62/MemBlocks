# Technology Stack

**Analysis Date:** 2026-05-04

## Languages

**Primary:**
- **Python** 3.11+ - Core library, backend API, MCP server
- **JavaScript/TypeScript** - Frontend web application

**Secondary:**
- None detected

## Runtime

**Environment:**
- **Python** 3.11+ - uv workspace with hatchling build system
- **Node.js** - Frontend development (via Vite)

**Package Manager:**
- **uv** - Python dependency management (workspace root)
- **npm** - Frontend package management

**Lockfile:**
- `uv.lock` (workspace), no `package-lock.json` in frontend

## Frameworks

**Core:**
- **FastAPI** 0.129.0+ - Backend REST API
- **uvicorn** 0.41.0+ - ASGI server

**Frontend:**
- **React** 18.3.1 - UI framework
- **Vite** 5.1.4 - Build tool and dev server
- **React Router** 7.13.1 - Client-side routing
- **TailwindCSS** 3.4.1 - Utility-first CSS framework

**AI/LLM Integration:**
- **LangChain** 0.1+ - LLM framework with provider abstractions
- **LangChain-Groq** 0.1+ - Groq provider
- **LangChain-OpenAI** 0.1+ - OpenAI provider
- **LangChain-Ollama** 0.1.0+ - Ollama local provider
- **LangChain-Google-GenAI** 4.2.1 - Google Gemini provider

**MCP Server:**
- **FastMCP** 3.1.0+ - Model Context Protocol server

## Key Dependencies

**Critical:**
- **Pydantic** 2.0+ - Data validation and settings
- **Motor** 3.0+ - Async MongoDB driver
- **Qdrant-client** 1.7+ - Vector database client

**Infrastructure:**
- **Clerk** - Authentication (frontend + backend API)
- **Cohere** 5.5.1+ - Reranking for search
- **FastEmbed** 0.7.4+ - Local embeddings

**Observability:**
- **OpenTelemetry** (openinference) - Tracing instrumentation
- **Arize** 0.7.0+ - ML observability platform

## Configuration

**Environment:**
- `.env` files - Configuration via environment variables
- `pydantic-settings` - Settings management with validation aliases

**Build:**
- `pyproject.toml` - UV workspace with member packages
- `frontend/vite.config.js` - Vite proxy to backend on port 8001

**Key Configs Required:**
- `LLM_PROVIDER_NAME` - "groq" (default), "gemini", "openrouter", or "ollama"
- `MONGODB_CONNECTION_STRING` - MongoDB connection
- `QDRANT_HOST` / `QDRANT_PORT` - Vector database
- `CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` - Auth

## Platform Requirements

**Development:**
- Python 3.11+
- Node.js 18+
- MongoDB running locally or remote
- Qdrant running locally on port 6333

**Production:**
- FastAPI backend (uvicorn)
- MongoDB (cluster or Atlas)
- Qdrant (cluster or Docker)
- Clerk for authentication

---

*Stack analysis: 2026-05-04*