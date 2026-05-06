# Requirements: MemBlocks

**Defined:** 2026-05-05
**Core Value:** Any AI agent connected to MemBlocks can store and retrieve the right memory from the right block at the right time, with conflict resolution and source transparency.

## v1.3 Requirements

Requirements for the evaluation framework rework.

### Framework Architecture

- [x] **EVAL-01**: Refactor evaluation methods into a modular architecture (e.g., `datasets`, `runners`, `metrics`) instead of a monolithic script.
- [x] **EVAL-02**: Evaluation is configurable via clean config files or simplified CLI arguments, removing confusing flags.

### LoCoMo Integration

- [ ] **DATA-01**: System can download and parse the `locomo-mc10` dataset from HuggingFace.
- [ ] **DATA-02**: System extracts multiple conversation sessions (`haystack_sessions`), timestamps, 10 choices, correct answers, and question types.

### Evaluation Pipeline

- [x] **PIPE-01**: System ingests long-term conversation sessions sequentially into isolated MemBlocks blocks (building core/semantic memory).
- [x] **PIPE-02**: System retrieves relevant context from MemBlocks based on the multiple-choice question.
- [x] **PIPE-03**: System uses an LLM to select the correct answer from the 10 options, using only the retrieved MemBlocks context.
- [x] **PIPE-04**: System supports a baseline comparison (providing the full raw conversation history to the LLM instead of MemBlocks context).

### Metrics & Reporting

- [x] **METR-01**: System calculates and reports overall accuracy and quality of response.
- [x] **METR-02**: System breaks down accuracy by question reasoning type (single-hop, multi-hop, temporal, adversarial, open-domain).
- [x] **METR-03**: System tracks and reports token usage/cost (the old metrics) separately from accuracy/quality metrics.
- [ ] **METR-04**: System outputs clean, structured reports (JSON/CSV) for analysis.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Training/Fine-tuning | We are evaluating memory retrieval of existing agents, not training models. |
| v1.2 Final Report | Deferred to focus solely on the evaluation framework rework. |
| Full 100% Dataset Run | The initial implementation will focus on ensuring the pipeline works on a subset before running the entire expensive 1,986-item dataset. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EVAL-01 | Phase 6 | Complete |
| EVAL-02 | Phase 6 | Complete |
| DATA-01 | Phase 7 | Pending |
| DATA-02 | Phase 7 | Pending |
| PIPE-01 | Phase 8 | Complete |
| PIPE-02 | Phase 8 | Complete |
| PIPE-03 | Phase 8 | Complete |
| PIPE-04 | Phase 8 | Complete |
| METR-01 | Phase 9 | Complete |
| METR-02 | Phase 9 | Complete |
| METR-03 | Phase 9 | Complete |
| METR-04 | Phase 9 | Pending |

**Coverage:**
- v1.3 requirements: 12 total
- Mapped to phases: 12
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-05*
*Last updated: 2026-05-05 after initial definition*