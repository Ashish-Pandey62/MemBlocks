# ROADMAP.md

## Phases
- [x] **Phase 6: Framework Architecture** - Modularize evaluation methods and configuration (COMPLETE)
- [x] **Phase 7: LoCoMo Integration** - Ingest and parse the locomo-mc10 dataset
- [ ] **Phase 8: Evaluation Pipeline** - Implement MemBlocks ingestion, retrieval, and LLM answering
- [ ] **Phase 9: Metrics & Reporting** - Calculate accuracy, break down by reasoning type, and track costs

## Phase Details

### Phase 6: Framework Architecture
**Goal**: Establish a modular evaluation architecture configured via clean files/arguments rather than complex flags.
**Depends on**: None
**Requirements**: EVAL-01, EVAL-02
**Success Criteria**:
  1. Developers can run evaluation scripts using simplified configuration files or basic CLI arguments instead of complex flags.
  2. The evaluation codebase is separated into independent modules (e.g., datasets, runners, metrics).
**Plans**: 3 plans
- [x] 06-01-PLAN.md — Core architecture interfaces & config parser (2026-05-05)
- [x] 06-02-PLAN.md — Component abstractions and implementation (Datasets & Metrics) (2026-05-05)
- [x] 06-03-PLAN.md — Runners & Entrypoint Wiring (2026-05-05)

### Phase 7: LoCoMo Integration
**Goal**: System can automatically download and accurately parse the LoCoMo dataset into structured sessions and multiple-choice questions.
**Depends on**: Phase 6
**Requirements**: DATA-01, DATA-02
**Success Criteria**:
  1. System successfully downloads the `locomo-mc10` dataset from HuggingFace without manual intervention.
  2. System accurately parses conversation histories, 10 choices, correct answers, and reasoning types for each question.
**Plans**: 2 plans
- [x] 07-01-PLAN.md — Implement LocomoDataset and HF parsing logic (2026-05-05)
- [x] 07-02-PLAN.md - Fix LoCoMo Dataset Choices and Answer Parsing (Gap Closure)

### Phase 8: Evaluation Pipeline
**Goal**: Execute the QA pipeline including MemBlocks ingestion, multi-strategy context retrieval, and LLM-based answering with Chain of Thought reasoning (baseline comparison deferred per user decision).
**Depends on**: Phase 7
**Requirements**: PIPE-01, PIPE-02, PIPE-03, PIPE-04
**Success Criteria**:
  1. System sequentially ingests long-term conversation sessions into isolated MemBlocks memory blocks.
  2. System retrieves context using 3 strategies (Semantic, Core, Hybrid) and prompts LLM with CoT reasoning to answer questions.
  3. Baseline comparison (raw history to LLM) is deferred per user decision (PIPE-04 modified).
**Plans**: 2 plans
- [x] 08-01-PLAN.md — MemBlocks ingestion & multi-strategy retrieval (PIPE-01, PIPE-02) (2026-05-05)
- [x] 08-02-PLAN.md — LLM QA with CoT & baseline deferral (PIPE-03, PIPE-04) (2026-05-06)

### Phase 9: Metrics & Reporting
**Goal**: Generate comprehensive accuracy (quality of response) and token usage reports segmented by reasoning types.
**Depends on**: Phase 8
**Requirements**: METR-01, METR-02, METR-03, METR-04
**Success Criteria**:
  1. System calculates overall accuracy (quality of response) for a subset of the dataset.
  2. System outputs a structured breakdown (JSON/CSV) of accuracy by question reasoning type.
  3. System reports token usage and estimated cost (the old metrics) separate from accuracy metrics.
**Plans**: 3 plans
- [x] 09-01-PLAN.md — Metric Evaluator & Config Updates (2026-05-06)
- [x] 09-02-PLAN.md — Evaluation Runner Integration & Aggregation (2026-05-06)
- [x] 09-03-PLAN.md — Report Generators & Console Summary (2026-05-06)

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 6. Framework Architecture | 3/3 | Complete    | 2026-05-05 |
| 7. LoCoMo Integration | 1/1 | Complete | 2026-05-05 |
| 8. Evaluation Pipeline | 2/2 | Complete | 2026-05-06 |
| 9. Metrics & Reporting | 3/3 | Complete | 2026-05-06 |