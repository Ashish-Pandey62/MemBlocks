---
phase: 07-locomo-integration
plan: 02
subsystem: evaluation
tags: [locomo, dataset, open-ended, fix]

# Dependency graph
requires:
  - phase: 07-locomo-integration
    provides: LoCoMo loading and session structure
provides:
  - Open-ended generation question parsing
  - Answer field alignment (handling category 5 quirks)
  - Evaluation runner template
affects: [evaluation]

# Tech tracking
tech-stack:
  added: []
  patterns: [conditional field mapping based on data category]
  
key-files:
  created: [evaluation/runners/locomo.py]
  modified: [evaluation/datasets/locomo.py, evaluation/eval.py, evaluation/runners/__init__.py]

key-decisions:
  - "Pivoted from Multiple Choice to Open-Ended Generation evaluation format"
  - "Updated LocomoQuestion dataclass to track `answer` and `adversarial_answer` instead of `choices` and `answer_idx`"
  - "Created LocomoRunner to execute the evaluation logic for the newly shaped data"

patterns-established:
  - "Dataset parsing accurately reflects the original GitHub repository format (not the HuggingFace MC10 derived dataset)"
  
requirements-completed: [DATA-02]

# Metrics
duration: 25min
completed: 2026-05-05
---

# Phase 7 Plan 2: LoCoMo Open-Ended Generation Format Update

**Redesigned LocomoDataset parsing to correctly support the dataset's native open-ended format.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-05-05T19:30:00Z
- **Completed:** 2026-05-05T19:55:00Z
- **Tasks:** 2 (Update data structure, Implement evaluation runner)
- **Files modified:** 4

## Accomplishments

- Analyzed discrepancies between the original `snap-research/locomo` GitHub dataset (mostly open-ended) and the derived `Percena/locomo-mc10` HuggingFace dataset (multiple-choice).
- Updated `LocomoQuestion` dataclass to reflect open-ended properties (`answer`, `adversarial_answer`) instead of multiple-choice properties (`choices`, `answer_idx`).
- Simplified `LocomoDataset` parsing logic to directly assign correct fields, accounting for Category 5 where the true answer resides in the `adversarial_answer` field.
- Implemented `LocomoRunner` class scaffolding to handle the new open-ended generation evaluation format.
- Integrated `LocomoRunner` with the main `evaluation/eval.py` execution script.

## Deviations from Original 07-02 Plan

### Original Plan Said:
- "Implement choices parsing in LoCoMo dataset"
- "Build a list of up to 10 choices"

### What Actually Happened:
The codebase was correctly pointing to the original Snap Research GitHub dataset. This dataset is built for open-ended generation and lacks "distractors" (wrong answers) for 75% of the questions. The original plan mistakenly assumed the dataset was the derived multiple-choice version from HuggingFace. We pivoted the implementation to properly support the open-ended format natively.

## Next Phase Readiness

- Dataset successfully loads all 1,986 questions natively.
- Evaluation runner is wired into the pipeline and ready for the LLM scoring implementation.