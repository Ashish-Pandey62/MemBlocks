---
phase: 06
slug: framework-architecture
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-05
---

# Phase 06 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none - Wave 0 installs/creates |
| **Quick run command** | `pytest tests/test_evaluation/ -v` |
| **Full suite command** | `pytest tests/` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_evaluation/`
- **After every plan wave:** Run `pytest tests/`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | EVAL-01 | unit | `pytest tests/test_evaluation/test_config.py` | ❌ W0 | ⏳ pending |
| 06-02-01 | 02 | 2 | EVAL-01 | unit | `pytest tests/test_evaluation/test_datasets.py` | ❌ W0 | ⏳ pending |
| 06-02-02 | 02 | 2 | EVAL-01 | unit | `pytest tests/test_evaluation/test_metrics.py` | ❌ W0 | ⏳ pending |
| 06-03-01 | 03 | 3 | EVAL-01 | unit | `pytest tests/test_evaluation/test_runners.py` | ❌ W0 | ⏳ pending |
| 06-03-02 | 03 | 3 | EVAL-02 | integration | `pytest tests/test_evaluation/test_eval_cli.py` | ❌ W0 | ⏳ pending |

*Status: ⏳ pending / ✅ green / ❌ red / ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_evaluation/test_config.py` - stubs for EVAL-01
- [ ] `tests/test_evaluation/test_datasets.py` - stubs for EVAL-01
- [ ] `tests/test_evaluation/test_metrics.py` - stubs for EVAL-01
- [ ] `tests/test_evaluation/test_runners.py` - stubs for EVAL-01
- [ ] `tests/test_evaluation/test_eval_cli.py` - stubs for EVAL-02

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| None | All | N/A | All phase behaviors have automated verification. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
