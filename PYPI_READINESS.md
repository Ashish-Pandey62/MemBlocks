# MemBlocks — PyPI Publishing Readiness Analysis

**Date:** 2026-06-04  
**Package:** `memblocks` v0.1.0  
**Verdict: Publish — after resolving the blockers below**

---

## Summary

The core library is functionally complete, well-structured, and meaningfully differentiated. The implementation is not prototype-grade — it is a real, working system with async patterns, type hints throughout, multiple LLM provider abstractions, and a clean public API. It has genuine value to publish.

However, four things must be fixed before uploading to PyPI. None are architectural. All are resolvable in a day.

---

## Why It Has Potential

### 1. Solves a real, under-served problem
Flat RAG and full-history injection are the two dominant memory strategies in LLM apps today. MemBlocks introduces a third: domain-partitioned memory blocks with section-specific retrieval strategies (always-injected core, hybrid semantic search, recursive summary). This is a concrete, novel contribution — not a wrapper around an existing tool.

### 2. The implementation is genuinely complete
The core library (`memblocks_lib/src/memblocks/`) is ~8,500 lines of working Python. Every service that is described in the README exists and is implemented:
- `MemBlocksClient` — full lifecycle management, async, dependency injection
- `SemanticMemoryService` — hybrid dense + sparse (SPLADE) search with RRF reranking, conflict-aware deduplication (ADD/UPDATE/DELETE/NOOP)
- `CoreMemoryService` — LLM-driven extraction, always-injected persistence
- `RecursiveSummaryService` — progressive compression
- Four LLM provider adapters (Groq, Gemini, OpenRouter, Ollama) — all fully implemented
- MongoDB + Qdrant storage adapters — fully functional

There are no `NotImplementedError` stubs in the public API. The only explicitly unfinished piece is `resource_retrieve()`, which is documented as future work and does not break anything.

### 3. Packaging is modern and correct
- Uses `hatchling` with a proper `src/` layout — the recommended approach in 2025
- `pyproject.toml` is syntactically complete with pinned minimum versions
- `__version__ = "0.1.0"` defined in `__init__.py` and consistent across the workspace
- Clean `__all__` exports; users can do `from memblocks import MemBlocksClient` immediately
- No hardcoded secrets or credentials anywhere in the library code

### 4. Documentation is strong
- README is 281 lines with architecture table, quick start, API reference, and configuration docs
- All public classes and methods have docstrings
- Type hints on every public method signature

### 5. Monorepo is cleanly separated
`backend/`, `frontend/`, `mcp_server/`, and `evaluation/` are all outside the `memblocks` package. Publishing `memblocks` to PyPI does not pull in demo infrastructure. The library stands alone.

---

## What Is Blocking Publication

### Blocker 1 — No LICENSE file (hard requirement)
PyPI does not enforce a license, but the absence of one means the package is legally "all rights reserved" by default. No serious developer or organisation will take a dependency on an unlicensed package. This also means the `license` field in `pyproject.toml` is incomplete.

### Blocker 2 — `pyproject.toml` is missing required PyPI metadata
The current file has `name`, `version`, `description`, `requires-python`, and `dependencies`. That is enough to *build* a wheel, but the PyPI listing will be bare and unprofessional:
- No `authors`
- No `readme` pointer (README.md won't render on PyPI)
- No `license` field
- No `keywords`
- No `classifiers` (Python version, topic, development status)
- No `[project.urls]` (homepage, repository, documentation)

### Blocker 3 — Test suite has hollow stubs
`tests/test_store_tools.py` defines 6 test methods — every single one is `pass`. They will all "pass" trivially, giving a false green signal. Before publishing, you need at least a minimal set of tests that actually assert something, to give users and contributors confidence the library doesn't silently break.

`tests/test_hybrid.py` is a real integration test but requires live MongoDB and Qdrant, making it impossible to run in CI without infrastructure setup.

### Blocker 4 — No CI/CD pipeline
There is no `.github/workflows/` directory. Without automated testing on push and a publish workflow on release tags, the project cannot sustain itself as an open package. A human can publish once manually, but the second release will be error-prone without automation.

---

## Step-by-Step Resolution

### Step 1 — Add a LICENSE file
**Time: 5 minutes**

Create a file at the repo root: `/Users/ashish/asisified/MemBlocks/LICENSE`

Use MIT unless you have a specific reason not to. Paste this content and replace the year and name:

```
MIT License

Copyright (c) 2026 <Your Name or Organisation>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

### Step 2 — Complete `pyproject.toml` metadata
**Time: 15 minutes**

Replace the `[project]` section in `memblocks_lib/pyproject.toml` with:

```toml
[project]
name = "memblocks"
version = "0.1.0"
description = "Intelligent modular memory management system for LLMs"
readme = "README.md"
license = { file = "../LICENSE" }
requires-python = ">=3.11"
authors = [
  { name = "Your Name", email = "your@email.com" }
]
keywords = ["llm", "memory", "rag", "langchain", "ai", "context-management", "vector-search"]
classifiers = [
  "Development Status :: 4 - Beta",
  "Intended Audience :: Developers",
  "License :: OSI Approved :: MIT License",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Topic :: Scientific/Engineering :: Artificial Intelligence",
  "Topic :: Software Development :: Libraries :: Python Modules",
  "Framework :: AsyncIO",
]
dependencies = [
    # ... keep existing dependencies unchanged ...
]

[project.urls]
Homepage = "https://github.com/Ashish-Pandey62/MemBlocks"
Repository = "https://github.com/Ashish-Pandey62/MemBlocks"
"Bug Tracker" = "https://github.com/Ashish-Pandey62/MemBlocks/issues"
```

Also, because `README.md` is at `memblocks_lib/README.md` (or the root), verify the path is correct relative to the `pyproject.toml`. If the README is at the repo root (`/MemBlocks/README.md`) and `pyproject.toml` is at `/MemBlocks/memblocks_lib/pyproject.toml`, set `readme = "../README.md"`. If there is no `README.md` inside `memblocks_lib/`, copy or symlink the root one:

```bash
cp /Users/ashish/asisified/MemBlocks/README.md /Users/ashish/asisified/MemBlocks/memblocks_lib/README.md
```

Then keep `readme = "README.md"` in `pyproject.toml`.

---

### Step 3 — Replace hollow tests with real minimal tests
**Time: 1–2 hours**

The goal is not full coverage — it is eliminating the all-`pass` tests so that a broken import or API surface change is caught. Replace the contents of `tests/test_store_tools.py` with tests that use mocks (the file already imports `AsyncMock` and `MagicMock`):

The key tests to implement (using mocks, no live infrastructure):
- `TestStoreSemantic::test_extracts_and_stores_fact` — mock `MemBlocksClient`, verify `store_semantic()` calls the underlying service with the right args
- `TestStoreSemantic::test_returns_error_when_no_active_block` — verify a `ValueError` or appropriate error is raised when no block is active
- Same pattern for `TestStoreToCore` and `TestStoreCombined`

Also add a `tests/test_config.py` that tests `MemBlocksConfig` can be instantiated with required fields — this has no external dependencies and takes 10 minutes:

```python
from memblocks import MemBlocksConfig

def test_config_instantiation():
    config = MemBlocksConfig(
        MONGODB_URI="mongodb://localhost:27017",
        QDRANT_URL="http://localhost:6333",
    )
    assert config.MONGODB_URI == "mongodb://localhost:27017"

def test_config_defaults():
    config = MemBlocksConfig(
        MONGODB_URI="mongodb://localhost:27017",
        QDRANT_URL="http://localhost:6333",
    )
    assert config.SEMANTIC_SEARCH_TOP_K > 0
    assert config.MESSAGE_WINDOW_SIZE > 0
```

Mark the integration tests that need live infrastructure with `@pytest.mark.integration` and add a `pytest.ini` or `pyproject.toml` section to exclude them by default:

```toml
[tool.pytest.ini_options]
markers = ["integration: requires live MongoDB and Qdrant"]
addopts = "-m 'not integration'"
```

---

### Step 4 — Add GitHub Actions CI/CD
**Time: 30 minutes**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --project memblocks_lib
      - name: Run tests
        run: uv run --project memblocks_lib pytest tests/ -v
```

Create `.github/workflows/publish.yml` for automated PyPI releases:

```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - "v*"

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - name: Build package
        run: uv build --project memblocks_lib
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: memblocks_lib/dist/
```

For the publish workflow, configure PyPI trusted publisher: go to PyPI → your account → Publishing → Add a new publisher → enter your GitHub username, repo name, workflow filename `publish.yml`, and environment name `pypi`.

---

### Step 5 — Verify the build before uploading
**Time: 10 minutes**

Run these commands from inside `memblocks_lib/`:

```bash
cd /Users/ashish/asisified/MemBlocks/memblocks_lib

# Build the wheel and sdist
uv build

# Inspect what's in the wheel
unzip -l dist/memblocks-0.1.0-py3-none-any.whl | head -40

# Check the metadata renders correctly
uv run twine check dist/*
```

If `twine check` passes with no warnings, the package is ready to upload.

---

### Step 6 — First upload to PyPI
**Time: 5 minutes**

```bash
# Upload to TestPyPI first to verify the listing looks correct
uv run twine upload --repository testpypi dist/*

# Browse https://test.pypi.org/project/memblocks/ — verify README renders, metadata is correct

# Then upload to the real PyPI
uv run twine upload dist/*
```

Or use `uv publish` if using uv 0.4+:
```bash
uv publish --project memblocks_lib
```

---

## Optional but Recommended Before v1.0.0

These are not blockers for the initial publish but should be done before a stable release:

- **CHANGELOG.md** — document what changed between versions; follow Keep a Changelog format
- **OpenRouter LLM provider** — not exported in `__init__.py`; either add it to `__all__` or document it as internal
- **`resource_retrieve()` stub** — either implement it or raise `NotImplementedError` with a clear message instead of silently returning nothing
- **Pinned dev dependencies** — add a `[dependency-groups]` or `[project.optional-dependencies]` for `dev` with `pytest`, `pytest-asyncio`, `twine`
- **Python version badge + CI badge** in README

---

## Final Checklist Before Upload

- [ ] `LICENSE` file exists at repo root
- [ ] `pyproject.toml` has `authors`, `readme`, `license`, `keywords`, `classifiers`, `[project.urls]`
- [ ] `README.md` is reachable from `pyproject.toml`'s `readme` path
- [ ] `uv build` succeeds without errors
- [ ] `twine check dist/*` passes with no warnings
- [ ] At least one test file has real assertions (not all `pass`)
- [ ] Uploaded to TestPyPI and the listing looks correct
- [ ] GitHub Actions CI workflow is in place and green on `main`
