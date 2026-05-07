# MemBlocks Evaluation Framework

End-to-end evaluation of MemBlocks memory quality on the [LoCoMo](https://github.com/snap-research/locomo) benchmark. All data flows through real MemBlocks infrastructure — Qdrant (semantic vectors) and MongoDB Atlas (sessions, core memory, summaries). There are no in-memory fallbacks.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Infrastructure Requirements](#infrastructure-requirements)
- [Setup](#setup)
- [Running Evaluations](#running-evaluations)
- [Config Reference](#config-reference)
- [Output Files](#output-files)
- [Test Suite](#test-suite)
- [Metrics Explained](#metrics-explained)
- [Token Budget](#token-budget)
- [Troubleshooting](#troubleshooting)

---

## How It Works

The evaluation answers one question: **given a long conversation stored in MemBlocks, can the system answer factual questions about it?**

For each session in the LoCoMo dataset:

1. **Ingest** — every message pair `(user_msg, ai_response)` is fed into MemBlocks via `session.add()`. When the memory window fills up, the pipeline runs automatically. A final `session.flush()` processes any remaining turns.

2. **Memory Pipeline** — MemBlocks runs internally:
   - **PS1 (Extraction)** — LLM extracts semantic memory units from the conversation window
   - **PS2 (Conflict Resolution)** — checks Qdrant for contradicting memories and resolves them
   - **Core Memory** — extracts stable persona and human traits into MongoDB
   - **Recursive Summary** — compresses the conversation into a running summary

3. **Retrieval** — for each QA question, three strategies are tried independently:
   - `semantic` — vector similarity search in Qdrant
   - `core` — structured persona/human facts from MongoDB
   - `hybrid` — combined semantic + core (default score source)

4. **QA** — the retrieved context (+ memory window + summary) is assembled into a prompt and sent to an Ollama model. The model generates an answer.

5. **Judge** — a second Ollama call (LLM-as-a-judge) compares the generated answer to the expected answer and returns `Pass` or `Fail`.

6. **Report** — results are written to `evaluation/runs/<timestamp>/`.

---

## Architecture

```
evaluation/
├── eval.py                    # Entrypoint — parses config, orchestrates runs
├── configs/
│   ├── quicktest_config.yaml  # 1 session × 2 questions (~1 min smoke test)
│   ├── final_eval_config.yaml # 2 sessions × 5 questions (pre-production check)
│   └── example_config.yaml    # Full 10-session reference
├── core/
│   ├── config.py              # Pydantic models: EvalConfig, RunConfig, RunnerConfig, DatasetConfig
│   └── registry.py            # Component registry (datasets, runners, metrics)
├── datasets/
│   ├── base.py                # BaseDataset ABC
│   └── locomo.py              # LocomoDataset — loads locomo10.json, maps to sessions/questions
├── runners/
│   ├── base.py                # BaseRunner ABC
│   └── locomo.py              # LocomoRunner — full pipeline: ingest → retrieve → QA → judge
├── metrics/
│   ├── base.py                # BaseMetric ABC
│   ├── locomo.py              # LocomoEvaluator (LLM judge), TokenTracker, PipelineStage
│   └── reporter.py            # Reporter — saves report.json, report.csv, run_info.json
├── data/
│   └── locomo10.json          # Cached LoCoMo dataset (10 sessions, ~588 msgs each)
├── tests/
│   ├── test_integration.py    # 8 tests: infra connectivity + SDK lifecycle smoke test
│   └── test_real_eval.py      # 11 tests: real dataset run + Qdrant/MongoDB verification
└── runs/
    └── <timestamp>_<name>/    # One directory per run (auto-created)
        ├── report.json
        ├── report.csv
        └── run_info.json
```

### Data Flow

```
locomo10.json
     │
     ▼
LocomoDataset.load()
     │  LocomoSession (session_id, messages[], questions[])
     ▼
LocomoRunner._run_async()
     │
     ├── MemBlocksClient.get_or_create_user()    → MongoDB: users
     ├── MemBlocksClient.create_block()           → MongoDB: memory_blocks + Qdrant: <block_id>_semantic
     ├── MemBlocksClient.create_session()         → MongoDB: sessions
     │
     ├── [for each turn] session.add(user_msg, ai_response)
     │       └── auto-flush when window fills (memory_window_limit messages)
     ├── session.flush()                          → triggers PS1 + PS2 + core + summary
     │       ├── PS1 extraction  → Groq LLM
     │       ├── PS2 conflict    → Qdrant similarity check + Groq LLM
     │       ├── Core memory     → MongoDB: core_memories
     │       └── Recursive summary → MongoDB: sessions.recursive_summary
     │
     ├── [for each question]
     │   ├── block.semantic_retrieve(q)           → Qdrant vector search
     │   ├── block.core_retrieve()                → MongoDB core_memories
     │   ├── block.retrieve(q)                    → hybrid (semantic + core)
     │   ├── session.get_memory_window()          → last N messages from MongoDB
     │   ├── session.get_recursive_summary()      → summary string from MongoDB
     │   ├── _call_llm(qa_prompt)                 → Ollama: answer generation
     │   └── evaluator.evaluate_with_judge()      → Ollama: Pass/Fail
     │
     └── Reporter → report.json / report.csv / run_info.json
```

---

## Infrastructure Requirements

| Service | Where | Purpose |
|---------|-------|---------|
| Qdrant | `localhost:6333` | Semantic memory vectors |
| MongoDB Atlas | configured in `.env` | Sessions, blocks, core memories, summaries |
| Ollama | `localhost:11435` | QA answer generation + LLM judge |
| Groq API | cloud (via `.env`) | MemBlocks internal pipeline (PS1/PS2/core/summary extraction) |

**Ollama models needed:**
- `hf.co/unsloth/gemma-3n-E4B-it-GGUF:Q4_K_M` — QA generation and judge
- `nomic-embed-text:latest` — embeddings for Qdrant storage

---

## Setup

### 1. Install dependencies

```bash
pip install -e memblocks_lib
pip install pytest pytest-asyncio pymongo pydantic pyyaml python-dotenv requests
```

### 2. Configure `.env`

```env
# LLM for MemBlocks internal pipeline (PS1, PS2, core extraction, summaries)
LLM_PROVIDER_NAME=groq
LLM_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_API_KEY=<your_groq_api_key>

# MongoDB Atlas
MONGODB_CONNECTION_STRING=mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/

# Ollama (docker runs at 11435, not default 11434)
OLLAMA_BASE_URL=http://localhost:11435
OLLAMA_BASE_URL_EMBEDDINGS=http://localhost:11435

# Qdrant (local)
QDRANT_HOST=localhost
QDRANT_PORT=6333
```

> **Important:** `LLM_MODEL` must be `meta-llama/llama-4-scout-17b-16e-instruct` for Groq — it is the only Groq model that supports `json_schema` structured outputs, which MemBlocks requires for PS1/PS2 extraction.

### 3. Verify infrastructure

```bash
# Qdrant
curl http://localhost:6333/healthz

# Ollama models
curl http://localhost:11435/api/tags

# Run full infra connectivity test
python -m pytest evaluation/tests/test_integration.py::TestInfraConnectivity -v -s
```

---

## Running Evaluations

All commands run from the **project root** (`/path/to/MemBlocks`).

### Quicktest — 1 session × 2 questions (~1 minute)

Best starting point. Verifies the full pipeline end-to-end on minimal data.

```bash
python evaluation/eval.py --config evaluation/configs/quicktest_config.yaml
```

### Pre-production check — 2 sessions × 5 questions (~5–10 minutes)

```bash
python evaluation/eval.py --config evaluation/configs/final_eval_config.yaml
```

### Full evaluation — all 10 sessions (all questions)

Edit `final_eval_config.yaml`, remove the limits, then run:

```yaml
runs:
  - name: "locomo-full"
    dataset:
      name: "locomo"
      # max_sessions: omit for all 10
      # max_questions_per_session: omit for all ~199 per session
    runner:
      name: "locomo"
      model: "hf.co/unsloth/gemma-3n-E4B-it-GGUF:Q4_K_M"
      judge_model: "hf.co/unsloth/gemma-3n-E4B-it-GGUF:Q4_K_M"
    metrics:
      - "accuracy"
```

```bash
python evaluation/eval.py --config evaluation/configs/final_eval_config.yaml
```

---

## Config Reference

```yaml
runs:
  - name: "my-run"              # Used for the output directory name
    dataset:
      name: "locomo"            # Dataset identifier (only "locomo" currently)
      max_sessions: 2           # Optional: cap sessions (default: all 10)
      max_questions_per_session: 5  # Optional: cap questions per session
    runner:
      name: "locomo"            # Runner identifier
      model: "hf.co/unsloth/gemma-3n-E4B-it-GGUF:Q4_K_M"  # Ollama model for QA
      judge_model: "hf.co/unsloth/gemma-3n-E4B-it-GGUF:Q4_K_M"  # Ollama model for judge
    metrics:
      - "accuracy"
```

**model / judge_model:**
- Set to an Ollama model name for real QA + judging
- Set to `null` to skip QA (ingestion and retrieval still run — useful for testing the memory pipeline only)
- The judge falls back to string-contains matching when `null`

---

## Output Files

Each run creates a directory: `evaluation/runs/<YYYYMMDD_HHMMSS>_<run-name>/`

### `run_info.json`
The exact config used for this run (for reproducibility).

### `report.json`
Full structured results:
```json
{
  "sessions_processed": 2,
  "metrics": {
    "overall_accuracy": 0.6,
    "total_questions": 10,
    "total_passes": 6,
    "accuracy_by_category": { "1": 0.7, "2": 0.5 },
    "accuracy_by_strategy": {
      "semantic": 0.5,
      "core": 0.4,
      "hybrid": 0.6
    },
    "tokens_by_stage": { "retrieval": 700, "qa": 3000, ... },
    "total_tokens": 4100
  },
  "details": [
    {
      "session_id": "conv-26",
      "ingestion_status": "success",
      "block_id": "<uuid>",
      "messages_processed": 419,
      "questions_evaluated": 5,
      "evaluations": [
        {
          "question": "...",
          "expected_answer": "...",
          "actual_answer": "...",
          "score_semantic": "Pass",
          "score_core": "Fail",
          "score_hybrid": "Pass",
          "retrieved_context_semantic": "...",
          "retrieved_context_core": "...",
          "retrieved_context_hybrid": "...",
          "memory_window_size": 10,
          "has_summary": true,
          "status": "evaluated"
        }
      ]
    }
  ]
}
```

### `report.csv`
One row per question — `session_id, question, expected_answer, actual_answer, score, category`.

---

## Test Suite

### Integration tests (`test_integration.py`)

Verifies infra connectivity and the SDK lifecycle on a tiny synthetic conversation.

```bash
python -m pytest evaluation/tests/test_integration.py -v -s
```

| Test | What it checks |
|------|---------------|
| `test_qdrant_reachable` | Qdrant health endpoint returns 200 |
| `test_ollama_reachable` | Ollama has at least one model loaded |
| `test_mongodb_reachable` | MongoDB Atlas accepts connections |
| `test_create_user_block_session` | Full SDK lifecycle without errors |
| `test_ingestion_triggers_pipeline` | 6-turn ingestion → Qdrant collection created |
| `test_retrieval_returns_results` | All 3 strategies return non-empty context |
| `test_memory_window_and_summary` | `get_memory_window()` and `get_recursive_summary()` work |
| `test_runner_uses_real_memblocks` | LocomoRunner uses real SDK, `ingestion_status == "success"` |

### Real eval tests (`test_real_eval.py`)

Runs a real LoCoMo session (conv-26, 419 messages, 2 questions) and verifies every storage layer.

```bash
python -m pytest evaluation/tests/test_real_eval.py -v -s
```

| Test | What it checks |
|------|---------------|
| `test_01_snapshot_pre_state` | Records Qdrant + MongoDB state before run |
| `test_02_run_real_evaluation` | Full pipeline runs, ingestion succeeds, block_id returned |
| `test_03_verify_qdrant_new_collection` | `<block_id>_semantic` collection created in Qdrant |
| `test_04_verify_qdrant_vector_count` | Reports vector count (0 is valid for long sessions) |
| `test_05_verify_qdrant_memory_payloads` | If vectors exist, payloads have real content |
| `test_06_verify_mongodb_new_documents` | `memory_blocks` and `sessions` collections grew |
| `test_07_verify_mongodb_block_document` | Block doc references correct Qdrant collection |
| `test_08_verify_mongodb_session_document` | Session doc has trimmed messages + summary |
| `test_09_verify_mongodb_core_memory` | Core memory document was written |
| `test_10_verify_retrieval_used_qdrant_data` | At least one retrieval strategy returned content |
| `test_11_print_full_verification_summary` | Prints end-to-end summary of all layers |

---

## Metrics Explained

### Overall Accuracy
Pass rate using the **hybrid** strategy (semantic + core combined). This is the headline metric.

```
overall_accuracy = hybrid_passes / total_questions
```

### Accuracy by Strategy
Shows how each retrieval method performs independently:
- `semantic` — vector similarity only (Qdrant)
- `core` — structured facts only (MongoDB core_memories)
- `hybrid` — combined (primary metric)

### Accuracy by Category
LoCoMo questions are grouped by reasoning type (category 1–5). Breakdown shows which memory types benefit most from MemBlocks.

### QA categories in LoCoMo
| Category | Reasoning Type |
|----------|---------------|
| 1 | Single-session recall |
| 2 | Multi-session recall |
| 3 | Temporal reasoning |
| 4 | Commonsense + memory |
| 5 | Adversarial / distractor |

### Judge
Scoring uses an Ollama LLM judge with a strict prompt:
- `Pass` only if the actual answer contains the key facts from the expected answer
- `Fail` if the answer says "I don't know", refuses, gives wrong facts, or omits key info
- Falls back to string-contains matching when `judge_model` is `null`

---

## Token Budget

The MemBlocks internal pipeline (PS1/PS2/core/summary) uses the LLM configured via `LLM_PROVIDER_NAME` + `LLM_MODEL` in `.env`.

**Groq free tier: 500K tokens/day per organization.**

| Scope | Estimated Groq tokens |
|-------|-----------------------|
| 1 session (419 msgs, ~41 pipeline runs) | ~120K tokens |
| 2 sessions | ~240K tokens |
| Full 10-session run | ~1.47M tokens (3 days at free tier) |

**To avoid token limits** — switch MemBlocks internals to Ollama:
```env
LLM_PROVIDER_NAME=ollama
LLM_MODEL=hf.co/unsloth/gemma-3n-E4B-it-GGUF:Q4_K_M
```
This routes PS1/PS2/core/summary through local Ollama instead of Groq (slower, no quota).

---

## Troubleshooting

### `ingestion_status: memblocks_error: ...`
MemBlocks infrastructure is unreachable. Check:
```bash
curl http://localhost:6333/healthz          # Qdrant
curl http://localhost:11435/api/tags        # Ollama
python -c "from dotenv import load_dotenv; load_dotenv(); from memblocks import MemBlocksConfig; print(MemBlocksConfig().mongodb_connection_string)"
```

### `0 Qdrant vectors after ingestion`
Normal for long conversations (400+ messages). PS2 conflict resolution may merge all semantic memories. Core memory and recursive summary still capture knowledge. The evaluation continues — hybrid context falls back to core memory.

### `Groq 429 — rate limit exceeded`
Daily 500K token limit exhausted. Options:
1. Wait for reset (midnight UTC)
2. Switch to `LLM_PROVIDER_NAME=ollama` in `.env`

### `json_schema` error from Groq
Only `meta-llama/llama-4-scout-17b-16e-instruct` supports structured outputs on Groq. Other models (including `llama-3.3-70b-versatile`) return 400. Verify `.env` has:
```env
LLM_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

### `status: skipped_no_qa_template`
The QA prompt template is missing. Check:
```bash
ls .planning/phases/08-evaluation-pipeline/templates/qa_prompt.txt
```

### Ollama port mismatch
Ollama in Docker maps `11435:11434` (host:container). The `.env` must use the **host** port:
```env
OLLAMA_BASE_URL=http://localhost:11435
OLLAMA_BASE_URL_EMBEDDINGS=http://localhost:11435
```
