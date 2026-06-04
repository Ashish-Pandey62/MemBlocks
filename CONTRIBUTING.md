# Contributing to MemBlocks

Thank you for your interest in contributing. This guide covers everything you need to get a working dev environment, run tests, and submit changes.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Dev Environment Setup](#dev-environment-setup)
3. [Running Tests](#running-tests)
4. [Project Structure](#project-structure)
5. [Code Style](#code-style)
6. [Submitting Changes](#submitting-changes)xx
7. [Reporting Issues](#reporting-issues)

---

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) — used for dependency management and running the project
- Docker — for running Qdrant and MongoDB locally (needed for integration tests only)
- Git

---

## Dev Environment Setup

```bash
# 1. Fork and clone the repo
git clone https://github.com/Ashish-Pandey62/MemBlocks.git
cd MemBlocks

# 2. Copy the example env file and fill in your API keys
cp .env.example .env

# 3. Install all workspace packages including dev dependencies
uv sync --package memblocks --group dev

# 4. Verify the setup — all tests should pass
uv run --package memblocks pytest tests/ -v
```

For integration tests that hit live MongoDB and Qdrant, start the infrastructure first:

```bash
# Start Qdrant and Ollama (MongoDB must be running separately or via Atlas)
docker-compose up -d

# Then run integration tests
uv run --package memblocks pytest -m integration -v
```

---

## Running Tests

```bash
# Unit tests only (no infrastructure needed — default)
uv run --package memblocks pytest tests/ -v

# Integration tests (requires live MongoDB + Qdrant)
uv run --package memblocks pytest -m integration -v

# All tests
uv run --package memblocks pytest tests/ -m "" -v

# Single file
uv run --package memblocks pytest tests/test_models.py -v
```

Test files and what they cover:

| File | Type | What it tests |
|---|---|---|
| `tests/test_config.py` | Unit | `MemBlocksConfig` defaults, validation, collection templates, LLM settings resolution |
| `tests/test_models.py` | Unit | All Pydantic models — instantiation, validation, serialisation, `to_prompt_string()` |
| `tests/test_store_tools.py` | Unit | `_build_provider` error paths, `MemBlocksClient` construction with mocks, event subscription |
| `tests/test_hybrid.py` | Integration | Full hybrid search pipeline against live MongoDB + Qdrant |

---

## Project Structure

The repo is a [uv workspace](https://docs.astral.sh/uv/concepts/workspaces/) with three publishable packages:

```
memblocks_lib/       # Core library — the main package published to PyPI
backend/             # FastAPI REST API demo (published separately as memblocks-backend)
mcp_server/          # MCP server integration (published separately as memblocks-mcp)
frontend/            # React web UI demo (not a Python package)
evaluation/          # LoCoMo benchmark harness (not published)
tests/               # Test suite for the core library
```

When working on the core library, all changes go under `memblocks_lib/src/memblocks/`. The key files:

| File/Dir | Purpose |
|---|---|
| `client.py` | `MemBlocksClient` — the single entry point users interact with |
| `config.py` | `MemBlocksConfig` — all configuration via Pydantic settings |
| `services/` | Business logic: block, session, semantic memory, core memory, pipeline |
| `storage/` | Infrastructure adapters: MongoDB, Qdrant, embeddings |
| `llm/` | LLM provider implementations: Groq, Gemini, OpenRouter, Ollama |
| `models/` | Pydantic schemas for all data types |
| `prompts/` | LLM prompt templates for all agentic workflows |

---

## Code Style

- **Type hints** on all public functions and methods — this is enforced by convention, not a linter
- **No comments** unless the *why* is non-obvious (a hidden constraint, a workaround, a subtle invariant)
- **No docstrings on private methods** — public API surface only
- **Async throughout** — all I/O-bound operations use `async/await`
- **Dependency injection** — services receive their dependencies via constructor args, no globals

When adding a new LLM provider:
1. Create `memblocks_lib/src/memblocks/llm/<name>_provider.py` implementing `LLMProvider`
2. Register it in `_build_provider()` in `client.py`
3. Export it from `memblocks_lib/src/memblocks/__init__.py`
4. Add the required API key field to `MemBlocksConfig`

---

## Submitting Changes

1. **Branch** off `main`: `git checkout -b your-feature-name`
2. **Make your changes** — keep commits focused; one logical change per commit
3. **Run the test suite**: `uv run --package memblocks pytest tests/ -v` — all 42 tests must pass
4. **Push and open a PR** against `main`
5. **Describe what and why** in the PR body — the diff shows the what, the description should explain the motivation

For significant changes (new memory section type, new provider, architecture change), open an issue first to discuss the approach before writing code.

---

## Reporting Issues

Open an issue at [github.com/Ashish-Pandey62/MemBlocks/issues](https://github.com/Ashish-Pandey62/MemBlocks/issues) with:

- What you expected to happen
- What actually happened
- A minimal reproduction (config + code snippet)
- Python version and OS
