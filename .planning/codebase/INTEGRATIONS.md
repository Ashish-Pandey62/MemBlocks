# External Integrations

**Analysis Date:** 2026-05-04

## APIs & External Services

**LLM Providers:**
- **Groq** - Primary LLM provider (default)
  - SDK: LangChain-Groq
  - Auth: `GROQ_API_KEY` env var
- **OpenAI** - Alternative LLM provider
  - SDK: LangChain-OpenAI
  - Auth: `OPENAI_API_KEY` (via LangChain)
- **Ollama** - Local LLM provider
  - SDK: LangChain-Ollama
  - Auth: Local endpoint via `OLLAMA_BASE_URL`
- **Google Gemini** - Alternative provider
  - SDK: LangChain-Google-GenAI
  - Auth: `GOOGLE_API_KEY` (via LangChain)
- **OpenRouter** - Aggregate provider with fallback models
  - SDK: LangChain (custom)
  - Auth: `OPENROUTER_API_KEY` env var

**Embedding Providers:**
- **FastEmbed** - Local embeddings (default)
  - Client: fastembed library
- **Cohere** - Reranking for search results
  - Client: cohere library 5.5.1+
  - Auth: `COHERE_API_KEY` env var

## Data Storage

**Databases:**
- **MongoDB** - Primary document store
  - Connection: `MONGODB_CONNECTION_STRING` env var
  - Client: Motor async driver
  - Collections: users, blocks, core_memories, sessions
- **Qdrant** - Vector database for semantic search
  - Connection: `QDRANT_HOST`/`QDRANT_PORT` (default localhost:6333)
  - Client: qdrant-client library
  - Collections: semantic_memories with vector payloads

**File Storage:**
- Local filesystem only (no S3/cloud storage detected)

**Caching:**
- None detected (in-memory only)

## Authentication & Identity

**Auth Provider:**
- **Clerk** - Authentication and user management
  - Frontend: `@clerk/react` SDK 6.0.1
  - Backend: clerk-backend-api 4.0.0
  - Auth: JWT validation via `CLERK_SECRET_KEY`
  - OAuth: Google OAuth configured in Clerk dashboard

## Monitoring & Observability

**Error Tracking:**
- None detected explicitly

**Logs:**
- **Arize** - ML observability and tracing
  - Connection: `ARIZE_SPACE_ID`, `ARIZE_API_KEY`
  - SDK: openinference-instrumentation-langchain + arize-otel

**Tracing:**
- **OpenTelemetry** - Distributed tracing
  - Instrumentation: openinference for LangChain

## CI/CD & Deployment

**Hosting:**
- Not detected (self-hosted likely)

**CI Pipeline:**
- None detected in repository

## Environment Configuration

**Required env vars:**
- `MONGODB_CONNECTION_STRING` - MongoDB connection
- `QDRANT_HOST` / `QDRANT_PORT` - Vector database
- `CLERK_PUBLISHABLE_KEY` - Frontend auth
- `CLERK_SECRET_KEY` - Backend JWT validation
- `GROQ_API_KEY` - Primary LLM (or other provider key)

**Secrets location:**
- `.env` file at project root (not committed)

## Webhooks & Callbacks

**Incoming:**
- None detected (no webhook endpoints)

**Outgoing:**
- None detected

---

*Integration audit: 2026-05-04*