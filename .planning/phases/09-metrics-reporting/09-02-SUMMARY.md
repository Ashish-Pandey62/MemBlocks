---
phase: 09-metrics-reporting
plan: 02
subsystem: metrics
tags: [llm-as-judge, accuracy-tracking, token-metrics, aggregation]

# Dependency graph
requires:
  - phase: 09-metrics-reporting
    provides: LocomoEvaluator, TokenTracker, judge_model config
provides:
  - LocomoRunner integration with LLM judge evaluation
  - Accuracy statistics (overall and by reasoning type)
  - Stage-based token metrics aggregation
affects: [evaluation, metrics]

# Tech tracking
tech-stack:
  added: []
  patterns: [LLM-as-Judge evaluation, accuracy aggregation by category, stage-based token tracking]

key-files:
  created: []
  modified:
    - evaluation/runners/locomo.py

key-decisions:
  - "Integrated LocomoEvaluator directly into runner loop for immediate scoring"
  - "Used stub token values for demonstration; real values would come from LLM API responses"

patterns-established:
  - "Runner evaluates generated answers using the LocomoEvaluator"
  - "Run results aggregate accuracy globally and by reasoning type"
  - "Token tracking collected for every evaluation across stages"

requirements-completed: [METR-01, METR-02, METR-03]

# Metrics
duration: 3 min
completed: 2026-05-06T11:11:44Z
---

# Phase 09 Plan 02: Locomo Runner Metrics Integration

**Integrated LLM-as-Judge evaluation into LocomoRunner, with accuracy aggregation by reasoning type and stage-based token metrics**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-06T11:08:52Z
- **Completed:** 2026-05-06T11:11:44Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Integrated LocomoEvaluator into LocomoRunner._run_async for Pass/Fail grading
- Added prompt/response trace capture for debugging and qualitative review
- Added stub token metrics per evaluation (retrieval, extraction, qa, judge stages)
- Implemented _aggregate_metrics method calculating overall accuracy and accuracy by category

## Task Commits

Each task was committed atomically:

1. **Task 1: Integrate LocomoEvaluator** - `234544c` (feat)
2. **Task 2: Aggregate Stats by Reasoning Type** - `444afbe` (feat)

**Plan metadata:** `444afbe` (docs: complete plan)

## Files Created/Modified
- `evaluation/runners/locomo.py` - Added LocomoEvaluator integration, token metrics, and metrics aggregation

## Decisions Made
- Integrated evaluator directly into runner loop for immediate per-question scoring
- Used stub token values to demonstrate the structure; production would populate from actual LLM API responses

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- LocomoRunner now produces comprehensive metrics alongside raw details
- Accuracy by reasoning type enables targeted analysis of retrieval strategies
- Token tracking enables cost and performance analysis per stage
- Ready for any downstream analysis or reporting

---
*Phase: 09-metrics-reporting*
*Completed: 2026-05-06*