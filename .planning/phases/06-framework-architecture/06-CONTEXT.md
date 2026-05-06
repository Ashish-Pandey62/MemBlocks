# Phase 6: Framework Architecture - Context

**Gathered:** 2026-05-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Refactor the evaluation methods into a modular architecture. This phase focuses on the structural overhaul (datasets, runners, metrics) and creating a clean configuration-driven execution system, replacing the existing monolithic script and confusing flags.

</domain>

<decisions>
## Implementation Decisions

### Runner Execution
- **Entrypoint:** Use a single entrypoint script (e.g., `eval.py`) that accepts a `--config` flag.
- **Config Capability:** A single configuration file can define multiple evaluation runs (multi-run config).
- **Output Management:** Results will be written to unique timestamped directories (e.g., `evaluation/runs/YYYYMMDD_HHMMSS/`).
- **Error Handling:** If a run fails within a multi-run config, the framework should catch the error, log it, and continue to the next run (continue on error).

### Claude's Discretion
- The specific configuration file format (e.g., YAML, JSON, TOML).
- The internal modularity pattern (OOP vs Functional) for datasets, runners, and metrics.
- Exact naming conventions for internal modules and classes.

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- The existing monolithic `evaluation/run_memblocks_evaluation.py` contains the core logic that needs to be modularized into datasets, runners, and metrics.

### Established Patterns
- Existing evaluations output to timestamped directories (e.g., `evaluation/runs/run_YYYYMMDD_HHMMSS/`). This pattern will be formalized and maintained.

### Integration Points
- The new `eval.py` (or similar entrypoint) will reside in the `evaluation/` directory and act as the new primary interface, orchestrating the newly modularized components.

</code_context>

<specifics>
## Specific Ideas
- Configuration files should be clean and readable, significantly simplifying the current CLI flag complexity.

</specifics>

<deferred>
## Deferred Ideas
- None — discussion stayed within phase scope.

</deferred>

---

*Phase: 06-framework-architecture*
*Context gathered: 2026-05-05*