# Phase 6: Framework Architecture - Research

**Researched:** 2026-05-05
**Domain:** Python Evaluation Architecture & Configuration
**Confidence:** HIGH

## Summary

This research establishes the standard stack and architectural patterns for the MemBlocks evaluation framework rework. The goal is to move from a monolithic script (`run_memblocks_evaluation.py`) to a modular, configuration-driven system (datasets, runners, metrics).

**Primary recommendation:** Use `PyYAML` for configuration files paired with `pydantic` for strong typed config validation. Implement an object-oriented architecture with abstract base classes (`abc`) defining the interfaces for Datasets, Runners, and Metrics.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Entrypoint:** Use a single entrypoint script (e.g., `eval.py`) that accepts a `--config` flag.
- **Config Capability:** A single configuration file can define multiple evaluation runs (multi-run config).
- **Output Management:** Results will be written to unique timestamped directories (e.g., `evaluation/runs/YYYYMMDD_HHMMSS/`).
- **Error Handling:** If a run fails within a multi-run config, the framework should catch the error, log it, and continue to the next run (continue on error).

### Claude's Discretion
- The specific configuration file format (e.g., YAML, JSON, TOML).
- The internal modularity pattern (OOP vs Functional) for datasets, runners, and metrics.
- Exact naming conventions for internal modules and classes.

### Deferred Ideas (OUT OF SCOPE)
- None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| EVAL-01 | Refactor evaluation methods into a modular architecture (e.g., `datasets`, `runners`, `metrics`) instead of a monolithic script. | Architecture Patterns section detailing OOP modules. |
| EVAL-02 | Evaluation is configurable via clean config files or simplified CLI arguments, removing confusing flags. | Standard Stack recommending YAML + Pydantic for config management. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyYAML | >=6.0 | Config parsing | De facto standard for readable, hierarchical configuration files. |
| Pydantic | >=2.0 | Config validation | Ensures configs match expected schemas, providing excellent error messages and type safety out of the box. |
| argparse | Standard | CLI arguments | Built-in Python library perfectly suited for the single `--config` flag requirement. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyYAML | TOML | TOML is great for flat configs (like pyproject.toml) but gets verbose for deeply nested multi-run configurations compared to YAML. |
| Pydantic | Dataclasses | Dataclasses lack built-in robust validation and coercion features that Pydantic provides for config parsing. |

**Installation:**
```bash
uv add pyyaml pydantic
```

## Architecture Patterns

### Recommended Project Structure
```text
evaluation/
├── eval.py                 # Single entrypoint script
├── core/
│   ├── config.py           # Pydantic models for config parsing
│   └── registry.py         # Factory/registry for dynamically loading modules
├── datasets/
│   ├── base.py             # Abstract base class for datasets
│   └── memblocks_dataset.py# Specific dataset implementations
├── runners/
│   ├── base.py             # Abstract base class for runners
│   └── default_runner.py   # Runner execution logic
├── metrics/
│   ├── base.py             # Abstract base class for metrics
│   └── accuracy.py         # Metric calculation implementations
└── configs/
    └── example_config.yaml # Example multi-run config
```

### Pattern 1: Abstract Base Classes (OOP)
**What:** Define interfaces using Python's `abc` module.
**When to use:** For standardizing the `Dataset`, `Runner`, and `Metric` contracts.
**Example:**
```python
from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseDataset(ABC):
    @abstractmethod
    def load(self) -> Any:
        pass

class BaseMetric(ABC):
    @abstractmethod
    def compute(self, results: Dict) -> Dict:
        pass
```

### Pattern 2: Component Registry
**What:** A central registry mapping string names (from the config) to class implementations.
**When to use:** When translating a config string like `dataset: "locomo"` into the corresponding `LocomoDataset` class instantiation.

### Anti-Patterns to Avoid
- **God Objects:** Avoid putting all logic in the Runner. The Runner should orchestrate, while Datasets fetch/parse data, and Metrics calculate scores.
- **Global State:** Avoid using global variables for configuration. Pass the parsed configuration object down to the components.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Config Validation | Custom dictionary checking | `Pydantic` | Pydantic handles type coercion, default values, and missing key errors automatically with clear error messages. |
| Config File Parsing | Custom text parsing | `PyYAML` | YAML syntax is robust and PyYAML is heavily tested against edge cases. |

**Key insight:** Writing custom config parsers usually leads to brittle code that fails silently or produces cryptic errors on typos.

## Common Pitfalls

### Pitfall 1: Fragile Error Handling in Multi-Run
**What goes wrong:** One failed run crashes the entire evaluation suite.
**Why it happens:** Exceptions in a runner aren't caught at the orchestration level.
**How to avoid:** Wrap the runner execution loop in a broad `try/except Exception as e`, log the traceback using Python's `logging` module, and `continue` to the next run.

### Pitfall 2: Hardcoded Paths
**What goes wrong:** File paths are absolute or assume the script is run from a specific working directory.
**Why it happens:** Using `open("datasets/file.json")`.
**How to avoid:** Use `pathlib.Path` relative to the `eval.py` file or accept explicit input/output directory paths in the configuration file.

## Code Examples

### Multi-Run Configuration YAML
```yaml
runs:
  - name: "baseline_run"
    dataset: 
      type: "locomo"
      path: "data/locomo.json"
    runner:
      type: "baseline"
    metrics:
      - "accuracy"
  - name: "memblocks_run"
    dataset:
      type: "locomo"
      path: "data/locomo.json"
    runner:
      type: "memblocks"
      block_strategy: "semantic"
    metrics:
      - "accuracy"
      - "token_cost"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Complex CLI flags (`argparse` with 20 args) | Config-driven execution (YAML/Pydantic) | Industry shift over last 5 years | Reproducibility is trivially handled by version-controlling config files. |

## Open Questions

1. **Specific Runner Configurations**
   - What we know: Runners need to handle baseline vs MemBlocks evaluations.
   - What's unclear: What exact parameters the MemBlocks runner will need in the YAML (e.g., specific memory thresholds).
   - Recommendation: Start with a flexible Pydantic model (`Dict[str, Any]` for kwargs) for runner configurations, then strictify it as the runner implementations solidify.

## Sources

### Primary (HIGH confidence)
- Python Official Docs (`abc`, `pathlib`, `logging`)
- Pydantic and PyYAML documentation
- General Software Engineering best practices for evaluation frameworks

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - PyYAML and Pydantic are industry standards for configuration.
- Architecture: HIGH - OOP with ABCs and Registries is the proven pattern for pluggable frameworks.
- Pitfalls: HIGH - Multi-run fault tolerance is a common requirement with known solutions.

**Research date:** 2026-05-05
**Valid until:** Stable indefinitely for this specific architectural transition.
