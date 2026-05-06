# Codebase Concerns

**Analysis Date:** 2026-05-04

## Security Considerations

**JWT Authentication Not Verified (HIGH PRIORITY):**
- Risk: The backend auth router (`backend/src/api/routers/auth.py`) decodes Clerk JWT tokens with signature verification disabled (`options={"verify_signature": False}`), allowing anyone to craft a valid-looking token without proper Clerk public key verification.
- Files: `backend/src/api/routers/auth.py` (lines 51-62)
- Current mitigation: None - tokens are not cryptographically verified
- Recommendations:
  - Implement proper JWT verification using Clerk's public keys (JWKS endpoint)
  - Add token expiration validation
  - Consider adding Clerk's userinfo endpoint verification for sensitive operations
  - Enable signature verification in production immediately

**Sensitive Data Logging:**
- Risk: The auth router logs token prefixes (`Token received: {token[:50]}...`) which may expose token fragments in server logs.
- Files: `backend/src/api/routers/auth.py` (line 40)
- Current mitigation: Token is truncated to 50 chars
- Recommendations: Remove token logging entirely or use a correlation ID instead

**MCP Server Default User:**
- Risk: The MCP server uses a "default_user" fallback when no user_id is configured, which could lead to data isolation issues in multi-user deployments.
- Files: `mcp_server/server.py` (lines 90-99)
- Current mitigation: User ID can be set via environment variable
- Recommendations: Enforce explicit user_id configuration; fail startup if not provided

**Missing Authorization Checks:**
- Risk: The `get_current_user` function in auth.py creates users on first login but there's no verification that the authenticated user has access to requested resources beyond the initial user creation.
- Files: `backend/src/api/routers/auth.py`, `backend/src/api/routers/blocks.py`, `backend/src/api/routers/memory.py`
- Current mitigation: User ID is extracted from token, but resource-level authorization is not consistently enforced
- Recommendations: Add explicit ownership verification for all resource access operations

## Tech Debt

**Multiple API Key Configurations Without Validation:**
- Issue: The config accepts multiple LLM provider API keys (groq, gemini, openrouter) but doesn't validate that at least one is properly configured before attempting operations. Users only discover missing keys at runtime.
- Files: `memblocks_lib/src/memblocks/config.py` (lines 54-116)
- Impact: Runtime failures when attempting LLM operations without configured keys
- Fix approach: Add config validation at client initialization to verify required credentials

**Hardcoded Model Names:**
- Issue: Default model names in config (e.g., `moonshotai/kimi-k2-instruct-0905`) are hardcoded and may become unavailable or deprecated.
- Files: `memblocks_lib/src/memblocks/config.py` (line 101), `mcp_server/server.py` (lines 103-117), `backend/src/api/dependencies.py` (lines 16-42)
- Impact: Production failures if default models become unavailable
- Fix approach: Make default models configurable via environment, add fallback logic

**Legacy Field Migration Incomplete:**
- Issue: Config has both flat legacy fields (`llm_provider_name`, `llm_model`, etc.) and new per-task `LLMSettings`. While there's a `resolved_llm_settings` property, the dual-path code adds complexity.
- Files: `memblocks_lib/src/memblocks/config.py` (lines 133-165)
- Impact: Confusion about which configuration path to use, potential for conflicting settings
- Fix approach: Deprecate legacy fields and migrate fully to LLMSettings

## Fragile Areas

**MongoDB Session Message Retrieval:**
- Issue: `get_session_messages` in `mongo.py` loads all session messages into memory then slices. For sessions with many messages, this causes memory bloat.
- Files: `memblocks_lib/src/memblocks/storage/mongo.py` (lines 423-443)
- Why fragile: Will fail with memory exhaustion on long-running sessions with thousands of messages
- Safe modification: Use MongoDB's `$slice` projection operator to limit results at query level
- Test coverage: No load testing with large message counts

**Background Task Error Handling:**
- Issue: MCP server's `_dispatch_background_task` creates asyncio tasks without tracking completion or propagating errors to the caller. Errors in background storage operations are silently lost.
- Files: `mcp_server/server.py` (lines 181-201)
- Why fragile: Users believe storage succeeded when it may have failed; no retry mechanism
- Safe modification: Add task tracking, implement retry queue, add notification mechanism for failures
- Test coverage: No tests for background task failure scenarios

**Client Singleton in Backend:**
- Issue: The backend uses `@lru_cache(maxsize=1)` for client singleton, which may not properly handle async cleanup or connection pool management across multiple requests.
- Files: `backend/src/api/dependencies.py` (lines 45-49)
- Why fragile: Single cached client may become stale or consume resources unbounded
- Safe modification: Implement proper lifecycle management with explicit close handling
- Test coverage: No integration tests for client lifecycle

## Performance Bottlenecks

**N+1 Query in User Block Retrieval:**
- Issue: `list_user_blocks` in `mongo.py` performs two queries - first to get user, then to get blocks. This could be combined into a single aggregation.
- Files: `memblocks_lib/src/memblocks/storage/mongo.py` (lines 275-287)
- Current capacity: Fine for small user bases
- Limit: Will degrade with many users doing simultaneous block list operations
- Scaling path: Use MongoDB aggregation with `$lookup` to fetch user and blocks in one query

**Qdrant Collection Per Block:**
- Issue: Each memory block gets its own Qdrant collection. Qdrant has overhead per collection (connection pools, metadata). Creating many blocks leads to many collections.
- Files: `memblocks_lib/src/memblocks/services/block_manager.py`, `memblocks_lib/src/memblocks/storage/qdrant.py`
- Current capacity: Works for <50 blocks per user
- Limit: Performance degrades past ~100 collections due to resource contention
- Scaling path: Consider namespace-based multi-tenancy within single collection using filtering

**LLM Provider Instantiation Overhead:**
- Issue: `MemBlocksClient.__init__` builds 6 separate LLM providers (conversation, ps1, ps2, retrieval, core, summary) even if some tasks aren't used.
- Files: `memblocks_lib/src/memblocks/client.py` (lines 234-272)
- Current capacity: Acceptable for single-session apps
- Limit: In long-running servers, unused providers consume memory unnecessarily
- Scaling path: Implement lazy provider initialization

## Test Coverage Gaps

**No Unit Tests for Core Services:**
- Issue: Only two test files exist (`tests/test_hybrid.py`, `tests/test_store_tools.py`), both appear to be integration/smoke tests. No unit tests for individual services like `SessionManager`, `BlockManager`, `CoreMemoryService`.
- What's not tested: Service logic, error handling paths, edge cases
- Files: `memblocks_lib/src/memblocks/services/*.py`
- Risk: Logic bugs in memory pipeline, session management, or block operations go undetected
- Priority: HIGH

**No Authentication/Authorization Tests:**
- Issue: No tests verify that unauthenticated requests are rejected, that users can only access their own resources, or that the JWT verification actually works.
- Files: `backend/src/api/routers/auth.py`, `backend/src/api/routers/blocks.py`
- Risk: Authorization bypasses could go unnoticed
- Priority: HIGH

**No Error Path Tests:**
- Issue: No tests verify behavior when external services fail (MongoDB unavailable, Qdrant unavailable, LLM API errors, network timeouts).
- What's not tested: Graceful degradation, error messages returned to users, retry behavior
- Files: All service and adapter files
- Risk: Users see unhelpful error messages or crashes in failure scenarios
- Priority: MEDIUM

**No Concurrent Operation Tests:**
- Issue: No tests verify behavior when multiple requests modify the same session or block simultaneously.
- Risk: Race conditions, lost updates, inconsistent state
- Priority: MEDIUM

## Dependencies at Risk

**FastMCP/uvicorn Version Pinning:**
- Risk: No version constraints in pyproject.toml for MCP server dependencies (fastmcp, uvicorn, starlette). Future updates could break the server.
- Impact: Runtime crashes or API changes without warning
- Migration plan: Add version constraints to pyproject.toml, use pip-compile or similar for lockfile management

**Motor (MongoDB Async Driver):**
- Risk: Uses `motor` for async MongoDB, but version is not pinned. Motor has had breaking changes between major versions.
- Impact: Async operations may fail silently or throw unexpected errors
- Migration plan: Pin motor version, add test matrix for at least two recent versions

## Missing Critical Features

**No Connection Retry/Resilience:**
- Problem: No built-in retry logic for transient failures (network timeouts, temporary service unavailability). First failure is often fatal.
- Blocks: Production deployment with reliability requirements

**No Request Rate Limiting:**
- Problem: No rate limiting on API endpoints. Could lead to quota exhaustion or resource starvation.
- Blocks: Multi-user production deployment

**No Data Export/Migration:**
- Problem: No way to export user data from the system. Users cannot migrate their memories or back them up.
- Blocks: User trust, ability to leave platform

**No Input Sanitization:**
- Problem: User-provided content (messages, facts) is not sanitized before storage or processing. Could lead to injection attacks in LLM prompts.
- Blocks: Security audit passing

---

*Concerns audit: 2026-05-04*