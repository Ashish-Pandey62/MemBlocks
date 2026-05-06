# Phase 8: Evaluation Pipeline - Context

**Gathered:** 2026-05-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the evaluation pipeline that ingests long-term conversation sessions (from LoCoMo) into MemBlocks, and runs QA evaluations using different memory retrieval strategies. The QA step evaluates MemBlocks' ability to answer open-ended questions based solely on retrieved context.

</domain>

<decisions>
## Implementation Decisions

### QA Prompt Design
- Use **Chain of Thought (CoT)** reasoning before outputting the final answer to improve accuracy.
- MemBlocks retrieved context should be enclosed in **`<context>` XML tags**.
- The QA agent should use a **Standard Assistant** persona ("Answer the user's question using the provided context.").

### Baseline Strategy
- **Do not run baseline for now.** (This modifies the original PIPE-04 requirement).

### Retrieval Strategy
- **Run all three strategies** (Semantic only, Core only, Hybrid) for the QA step and produce 3 separate sets of metrics.

### Answer Parsing & Evaluation
- Since LoCoMo is an open-ended generation task (no multiple choices), use **LLM-as-a-Judge** to grade the QA output against the expected answer.

### Claude's Discretion
- Judge Setup: Model selection for the LLM judge and the specific grading scale (e.g., Pass/Fail or 1-5 scale).
- Retrieval Parameters: Specific `top_k` values or limits for the Semantic/Hybrid queries.
- Execution Parallelism: Whether to run QA queries sequentially or concurrently.
- Format of the final token tracking / token comparison output.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `LocomoRunner._run_async()` skeleton exists in `evaluation/runners/locomo.py`.
- `memblocks_lib` provides `session.add()` and `session.flush()` for sequential ingestion.

### Established Patterns
- Phase 7 established that the `locomo10.json` dataset is loaded and subsets are configurable via `max_sessions`.
- Context Isolation: A separate MemBlocks block is created per unique `haystack_session`.

### Integration Points
- Runner must integrate with `memblocks` library to inject context and then perform the `retrieve()` operations based on the 3 chosen strategies (Semantic, Core, Hybrid).
- Requires updating the dataset ingestion logic to handle open-ended questions instead of multiple-choice.

</code_context>

<specifics>
## Specific Ideas

- The original `locomo-mc10` requirement was incorrect; the dataset `locomo10.json` actually contains open-ended questions. The pipeline must be adapted to evaluate open-ended text answers.

</specifics>

<deferred>
## Deferred Ideas

- Full baseline history comparison is skipped/deferred.

</deferred>

---

*Phase: 08-evaluation-pipeline*
*Context gathered: 2026-05-05*