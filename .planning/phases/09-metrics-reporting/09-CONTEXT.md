# Phase 9: Metrics & Reporting - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Generate comprehensive accuracy (quality of response) and token usage reports based on the LoCoMo QA evaluation. This phase focuses on calculating metrics, breaking them down by reasoning type, tracking costs, and outputting the data in structured formats for analysis.

</domain>

<decisions>
## Implementation Decisions

### Output Formats
- Output both JSON (machine-readable) and CSV (spreadsheet-ready) formats.
- The CSV export should be granular: one row per question.
- The JSON export should include the full prompt and model response trace of the QA evaluation for debugging and qualitative review.
- The runner should print a summary to the console when the evaluation finishes.

### Cost Tracking (Tokens)
- Track raw token counts only (do not calculate dollar costs).
- Token counts must be broken down explicitly by pipeline stage per session: Retrieval, Conflict Management (PS2), Semantic Extraction (PS1), Summary Generation, Core Memory Generation, QA, etc.
- Represent token breakdowns using nested objects/columns (e.g., `tokens.extraction`, `tokens.qa`).
- Track LLM Judge tokens separately from the system's runtime tokens.

### Scoring Approach
- Use LLM-as-a-Judge with a Strict Pass/Fail grading scale.
- The judge should just output the score without preceding it with a Chain of Thought explanation.
- The judge should grade 'Pass' if the answer is factually correct, ignoring whether it hallucinated using outside knowledge instead of the retrieved context.
- The specific model used for the judge should be configurable in the runner's configuration file.

### Report Structure
- We are evaluating the system using only the combined retrieval strategy (core+semantic+summary) per the system's architecture, not split by separate strategies.
- Console summaries and final aggregations should group the data by Reasoning Type (e.g., temporal, multi-hop).
- Write a `run_info.json` file in the results directory containing the exact configuration used to generate the run for reproducibility.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- The existing monolithic `evaluation/run_memblocks_evaluation.py` contains legacy token extraction parsing that could be adapted for the new modular stage-based token tracking.
- The framework architecture established in Phase 6 provides the `evaluation/runs/YYYYMMDD_HHMMSS/` directory pattern.

### Established Patterns
- Phase 6 established using `--config` for runner execution. The Judge model selection will be added to this config.
- Phase 8 established the QA execution loop, which this phase will wrap with the LLM-as-a-Judge logic.

### Integration Points
- Metrics generation needs to hook into the `LocomoRunner` introduced in Phase 8.
- Token tracking needs to pull data from the `LLMService` abstractions or wherever usage is emitted during the various MemBlocks pipeline stages.

</code_context>

<specifics>
## Specific Ideas

- Token tracking explicitly requires breakdown per stage: "retrival, conflict management(PS2), extraction (PS1), summary genertation, core memory generation, qn, etc".

</specifics>

<deferred>
## Deferred Ideas

- None — discussion stayed within phase scope.

</deferred>

---

*Phase: 09-metrics-reporting*
*Context gathered: 2026-05-06*
