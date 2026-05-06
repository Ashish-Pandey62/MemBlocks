# Phase 7: LoCoMo Integration - Context

**Gathered:** 2026-05-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Integrate the `locomo-mc10` dataset to evaluate MemBlocks memory retrieval accuracy. Feed multiple conversation sessions (`haystack_sessions`) sequentially to build core and semantic memory, then evaluate the system's ability to answer multiple-choice questions based *only* on retrieved context compared to a full-history baseline.

</domain>

<decisions>
## Implementation Decisions

### Format Mapping
- **Ingestion Flow:** Feed sessions sequentially (session by session).
- **Message Format:** Use `memblocks_lib`, simulating user input as it's done in `backend/src/api/routers/chat.py` (List of dicts or standard method calls).
- **Timestamps:** Inject dataset timestamps explicitly. Mock `datetime.now()` *only* during the extraction step (e.g. inside `semantic_memory.py`) so extracted memories reflect the historical context.
- **Roles & Tags:** Map original roles to "user" and "assistant". Retain specific character tags by prepending them to the content for *both* roles (e.g. `[Caroline]: ...` for user, `[Melania]: ...` for assistant).
- **Extraction Trigger:** Use `session.flush()` to force memory extraction and summarization at the end of each session. **Note:** The pipeline must wait for the extraction to fully complete before moving on to the QA sessions to ensure all memories are processed.
- **Window Management:** Configure `memory_window_limit` high (e.g. 1000) when running in "extract per session" mode so `flush()` manages the boundaries, or use standard limits for "natural flow" mode. Both approaches should be configurable.
- **Context Isolation:** Create a new MemBlocks block per unique `haystack_session`. Feed the entire conversation, then run all associated questions against that block.
- **Summarization:** Keep recursive summaries active when windows fill up.
- **Error Handling:** If an LLM call fails during QA, log the warning, record the failure, and continue to the next question.

### Evaluation Metrics
- **Token Tracking:** Track all LLM usage, including background memory extraction (semantic extraction, conflict resolution) and the final QA retrieval step.
- **Token Reporting:** Structure the final output to clearly compare token expenditure (Full Baseline vs. MemBlocks). Token counts must include the entire haystack session + background processes + QA tokens, evaluated on a per-session basis.

### Data Subsetting
- **Subsetting Rationale:** Full dataset (1,986 items) is extremely expensive and slow.
- **Subset Scope:** For iterative development, restrict evaluation to a small number of questions drawn from only 1 or 2 unique `haystack_sessions`.
- **Configuration:** Define subset parameters (e.g. `max_sessions`, `max_questions_per_session`) directly in the runner's configuration file (e.g. `eval.py --config config.yaml`).

### Claude's Discretion
- Full baseline formatting strategy (how to present the full history to the baseline LLM).
- Filtering logic for specific question types (e.g., temporal, multi-hop) during subsetting.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `memblocks_lib/src/memblocks/services/session.py`: The `Session.add()` and `Session.flush()` methods are central to injecting the messages and triggering extraction.
- Existing metrics/token reporting from the legacy monolith (`evaluation/run_memblocks_evaluation.py`) can inform the new token analysis output structure.

### Established Patterns
- The evaluation runner uses configuration files (`--config`) to dictate execution parameters, as established in Phase 6.

### Integration Points
- The dataset parsing logic needs to map correctly into the `memblocks_lib` pipeline. The injection of the `simulated_time` requires precision mocking of `datetime.now()` in `semantic_memory.py` during the `session.flush()` or `session.add()` operations.

</code_context>

<specifics>
## Specific Ideas
- "Even though there are 1986 qa & haystack_sessions pairs, there are actually only 10 unique haystack_sessions." ?" Group the evaluation by creating 1 block per unique `haystack_session`, populating it entirely, then running all associated questions against it.
- "One user is user, and assistant is roleplaying as the other user. for example, caroline is the actual user and Melania is the AI, so you need to prepend it to both message types".

</specifics>

<deferred>
## Deferred Ideas
- None ?" discussion stayed within phase scope.

</deferred>

---

*Phase: 07-locomo-integration*
*Context gathered: 2026-05-05*