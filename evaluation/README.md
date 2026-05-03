# MemBlocks Evaluation

This folder contains a transparency-driven evaluation harness for MemBlocks.

It is built to evaluate message workloads (10, 30, or 100+ messages) and produce comparison-ready metrics across multiple method variants.

## What It Tracks

- Per-turn metrics (for each message):
  - turn latency (total, retrieval stage, conversation stage)
  - token usage deltas during that turn
  - process-level token/timing split:
    - `ps1_extraction`
    - `ps2_conflict`
    - `retrieval`
    - `core_memory`
    - `summary`
    - `conversation`
- Full transparency artifacts:
  - retrieval log
  - processing history
  - operation log
  - event stream + event counts
- Aggregated stats for comparison:
  - min / max / avg / p50 / p95 for timings
  - total tokens and tokens-per-turn
  - per-process token totals and average latency
- Optional full-history baseline:
  - runs the main conversation LLM with full chat history every turn
  - reports token deltas and savings versus this baseline
- User-path vs background split:
  - user-path = retrieval + conversation for a single user message turn
  - background = PS1/PS2/core/summary pipeline calls (triggered on flush windows)

## Files

- `evaluation/run_memblocks_evaluation.py`: main evaluation runner
- `evaluation/datasets/default_30_messages.json`: default 30-message dataset
- `evaluation/methods/default_methods.json`: example methods to compare

## Quick Start

### Run Full Evaluation (MemBlocks + Baseline)

From repository root:

```bash
# 10 messages (fast)
uv run python evaluation/run_memblocks_evaluation.py \
  --dataset evaluation/datasets/test_10_messages.json \
  --methods evaluation/methods/test_single_method.json \
  --out-dir evaluation/runs \
  --turn-delay-seconds 1.5 \
  --method-delay-seconds 2.0 \
  --memory-window-limit 20 \
  --keep-last-n 10 \
  --session-add-background \
  --no-flush-at-end \
  --use-reference-task-models

# 30 messages (default)
uv run python evaluation/run_memblocks_evaluation.py \
  --dataset evaluation/datasets/default_30_messages.json \
  --methods evaluation/methods/test_single_method.json \
  --out-dir evaluation/runs \
  --turn-delay-seconds 1.5 \
  --method-delay-seconds 2.0 \
  --memory-window-limit 20 \
  --keep-last-n 10 \
  --session-add-background \
  --no-flush-at-end \
  --use-reference-task-models

# 100 messages (comprehensive)
uv run python evaluation/run_memblocks_evaluation.py \
  --dataset evaluation/datasets/test_100_messages.json \
  --methods evaluation/methods/test_single_method.json \
  --out-dir evaluation/runs \
  --turn-delay-seconds 1.5 \
  --method-delay-seconds 2.0 \
  --memory-window-limit 20 \
  --keep-last-n 10 \
  --session-add-background \
  --no-flush-at-end \
  --use-reference-task-models
```

This will:

1. Load the dataset (10/30/100 messages)
2. Run the MemBlocks method variant in `test_single_method.json`
3. Run `full_history_baseline` for comparison
4. Write a new run directory under `evaluation/runs/run_YYYYMMDD_HHMMSS`

### Re-run Only Baseline (Update Existing Run)

If you need to re-run just the baseline (e.g., after fixing num_ctx or changing models):

```bash
# Re-run baseline for existing run_20260329_020528
uv run python evaluation/rerun_baseline.py \
  --dataset evaluation/datasets/test_100_messages.json \
  --methods evaluation/methods/test_single_method.json \
  --out-dir evaluation/runs \
  --turn-delay-seconds 1.5 \
  --method-delay-seconds 2.0 \
  --memory-window-limit 20 \
  --keep-last-n 10 \
  --session-add-background \
  --no-flush-at-end \
  --use-reference-task-models
```

**Note:** Edit the run directory name in `rerun_baseline.py` line 26 to match your target run.

The script will:
1. Re-run only the baseline evaluation
2. Update `full_history_baseline/method_report.json`
3. Regenerate all comparison files (`comparison.csv`, `comparison.md`, etc.)

### Fix Timing Anomalies

If timing data was corrupted (e.g., computer sleep during evaluation):

```bash
# Fix timing anomalies > 120 seconds, replace with 20 seconds
python evaluation/fix_timing.py \
  evaluation/runs/run_20260329_020528/memblocks_full/method_report.json \
  120000 \
  20000
```

This will:
1. Create backup: `method_report.json.backup`
2. Replace anomalous timing values
3. Recalculate aggregated metrics (avg, p95, high, low)

To disable baseline:

```bash
uv run python evaluation/run_memblocks_evaluation.py --no-full-history-baseline
```

## Configuration Flags

### Required Flags

- `--dataset <path>`: Path to dataset JSON file (array of message strings)
- `--methods <path>`: Path to methods JSON file (array of method configs)
- `--use-reference-task-models`: Use task-specific model routing (ollama for retrieval/PS2, groq for PS1/core/summary)

### Dataset Options

- `--enforce-30`: Enforce exactly 30 messages in dataset (legacy validation)
- `--out-dir <path>`: Output directory for run results (default: `evaluation/runs`)

### Model Configuration

Models are configured in `evaluation/run_memblocks_evaluation.py` in `build_reference_llm_settings()`:

**Current Configuration:**
- **Conversation:** `hf.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-GGUF:Q4_K_M` (ollama, fast)
- **Retrieval:** `hf.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M` (ollama)
- **PS1 Extraction:** `openai/gpt-oss-120b` (groq)
- **PS2 Conflict:** `hf.co/bartowski/Meta-Llama-3.1-8B-Instruct-GGUF:Q4_K_M` (ollama)
- **Core Memory:** `openai/gpt-oss-120b` (groq)
- **Summary:** `openai/gpt-oss-120b` (groq)

Edit lines 359-387 to change models.

### Memory Window Settings

Controls when background memory pipeline runs fire:

- `--memory-window-limit <int>`: Trigger pipeline flush after N messages (default: 20)
- `--keep-last-n <int>`: Messages kept in session after flush (default: 10)

**Example:** With 100 messages, `--memory-window-limit 20 --keep-last-n 10` will:
- Flush pipeline at message 20, 40, 60, 80, 100
- Keep last 10 messages in window after each flush

### Background Processing

Controls async execution of session.add (PS1, PS2, core memory, summary):

- `--session-add-background`: Run session.add in background (default: on)
- `--no-session-add-background`: Run session.add inline (blocks user-facing flow)

**Recommendation:** Always use `--session-add-background` to match production behavior.

### Pipeline Flush Control

- `--flush-at-end`: Run final pipeline flush after all messages (default: on)
- `--no-flush-at-end`: Skip final flush (faster, for scaling analysis)

**Use `--no-flush-at-end` when:**
- Testing scaling patterns across message counts
- You don't need final summary generation
- Reducing evaluation time

### Rate Limiting

Built-in delays to avoid model RPM limits:

- `--turn-delay-seconds <float>`: Delay after each turn (default: 3.25)
- `--method-delay-seconds <float>`: Delay between method variants (default: 8.0)

**For faster local testing:** Use `--turn-delay-seconds 1.5 --method-delay-seconds 2.0`

### Baseline Options

- `--full-history-baseline`: Run full-chat-history baseline (default: on)
- `--no-full-history-baseline`: Skip baseline
- `--baseline-system-prompt <str>`: System prompt for baseline (default: "You are a helpful assistant with memory of past conversations.")

### Error Handling

- `--continue-on-error`: Continue evaluation if a turn fails (default: off)
- `--user-prefix <str>`: Prefix for generated user IDs (default: "evaluation_user")

## Available Datasets

- `evaluation/datasets/test_10_messages.json` - 10 messages (fast testing)
- `evaluation/datasets/default_30_messages.json` - 30 messages (default)
- `evaluation/datasets/test_100_messages.json` - 100 messages (comprehensive scaling analysis)

## Available Method Configurations

- `evaluation/methods/default_methods.json` - 3 method variants (full, no-rerank, sparse-only)
- `evaluation/methods/test_single_method.json` - Single method (memblocks_full) for faster testing

## Rate-Limit Safety

The runner includes built-in delays to avoid model RPM limits:

- `--turn-delay-seconds` (default `3.25`)
- `--method-delay-seconds` (default `8.0`)

For a 20 requests/minute/model limit, `3.25s` per turn keeps the effective
rate under the cap with small buffer.

Example:

```bash
uv run python evaluation/run_memblocks_evaluation.py --enforce-30 --use-reference-task-models --turn-delay-seconds 3.25 --method-delay-seconds 8
```

## Session Window Settings

You can control when background memory pipeline runs fire:

- `--memory-window-limit` (default `20`)
- `--keep-last-n` (default `10`)

With the default 30-message dataset, this causes fewer flush-trigger pipeline runs
than a window size of 10, and gives a cleaner separation between user-path and
background costs.

By default, turn persistence runs in background to match production style:

- `--session-add-background` (default on)
- `--no-session-add-background`

When background mode is on, each "turn" captures user-path cost only, while
pipeline/storage work is tracked separately via background processing metrics.

## Output Structure

Each run folder contains:

- `comparison.csv`: compact table for spreadsheet analysis
- `comparison.md`: human-readable comparison table
- `comparison_summary.json`: full method summaries
- `comparison_rows.json`: flattened comparison rows
- `run_metadata.json`: run metadata
- `messages.json`: messages used in run
- `methods.json`: evaluated methods

Each method subfolder contains:

- `method_report.json`: full per-method report
- `turns.json`: per-message metrics
- `turns.csv`: per-message metrics in tabular format
- `llm_call_type_summary.csv`: process-level token/timing summary
- `llm_records.json`: raw LLM call records
- `retrieval_log.json`: raw retrieval entries
- `processing_history.json`: raw pipeline runs
- `operation_log.json`: raw DB operation log
- `events.json`: raw event stream

If baseline is enabled, run folder also includes:

- `full_history_baseline/` method artifacts with the same key files

## Comparing Additional Methods

Edit `evaluation/methods/default_methods.json` and add new variants by changing:

- `config_overrides` (retrieval flags, top-k, etc.)
- `llm_task_overrides` (provider/model/temperature by task)

Then rerun with:

```bash
uv run python evaluation/run_memblocks_evaluation.py --methods evaluation/methods/default_methods.json --enforce-30
```

## Key Baseline Comparison Columns

In `comparison.csv` and `comparison.md`:

- `vs_full_history_total_token_delta`
- `vs_full_history_total_token_savings_pct`
- `vs_full_history_conversation_token_delta`
- `vs_full_history_conversation_token_savings_pct`

These quantify savings relative to sending full chat history each turn.

## Notes

- This script requires the same infrastructure/services as normal MemBlocks usage (MongoDB, Qdrant, embedding service, and configured LLM keys).
- `evaluation/runs/` is gitignored to keep output artifacts local.
