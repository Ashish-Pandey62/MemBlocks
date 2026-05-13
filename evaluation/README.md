# MemBlocks Evaluation

This folder contains a transparency-driven evaluation harness for MemBlocks.

It is built to evaluate message workloads and produce comparison-ready metrics across multiple evaluation datasets and metrics using a flexible registry-based configuration system.

## Files

- `evaluation/eval.py`: Main evaluation runner entrypoint
- `evaluation/configs/`: YAML configurations defining evaluation runs
- `evaluation/core/`: Configuration schema models and component registry
- `evaluation/datasets/`: Dataset loaders (e.g. Locomo)
- `evaluation/metrics/`: Metric calculators
- `evaluation/runners/`: Evaluation execution logic

## Quick Start

### Run an Evaluation

From the repository root:

```bash
python -m evaluation.eval --config evaluation/configs/example_config.yaml
```

This will:
1. Parse the YAML configuration file using Pydantic schemas.
2. Initialize datasets, runners, and metrics via the component registry.
3. Run each configured evaluation suite.
4. Output results to a timestamped folder under `evaluation/runs/`.

## Configuration Files

The evaluation framework uses YAML files to define runs. You can define multiple runs in a single config.

Example (`evaluation/configs/example_config.yaml`):

```yaml
runs:
  - name: "locomo-baseline"
    dataset:
      name: "locomo"
      max_sessions: 10
      max_questions_per_session: 5
    runner:
      name: "locomo"
    metrics:
      - "accuracy"
```

## Adding New Components

The framework is built around three Abstract Base Classes (ABCs):
- `BaseDataset` (in `evaluation.datasets.base`)
- `BaseRunner` (in `evaluation.runners.base`)
- `BaseMetric` (in `evaluation.metrics.base`)

To add a new dataset, runner, or metric:
1. Subclass the corresponding ABC.
2. Implement the required abstract methods (e.g., `load()` for datasets, `run()` for runners, `compute()` for metrics).
3. Decorate the class with the appropriate registry decorator (e.g., `@Registry.register_dataset("my_dataset")`).
4. Ensure the new module is imported in the package `__init__.py` file so it is registered at runtime.
