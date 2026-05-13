# Step-wise Guide — Run LOCOMO Evaluation for MemBlocks

This guide explains how to set up and run `evaluation/locomo_eval.py` to evaluate MemBlocks on LOCOMO-style long-conversation QA.

The script will:

1. Load LOCOMO conversations and QA pairs.
2. Replay each conversation into the real MemBlocks memory pipeline.
3. Run `block.retrieve(question)` for each question.
4. Generate an answer using `client.conversation_llm.chat(...)` with retrieved memory context.
5. Score the answer against the gold answer.
6. Report overall score and scores by reasoning type: `single-hop`, `multi-hop`, `temporal`, `preference`, `attribute`, `open-domain`, and `other`.

---

## 1. Prerequisites

You need:

- Python `>=3.11`
- `uv`
- Docker running
- A configured MemBlocks LLM provider key: Groq, Gemini, or OpenRouter
- Ollama available locally or at `OLLAMA_BASE_URL`
- LOCOMO data as either local `.json` / `.jsonl` or a HuggingFace dataset

---

## 2. Start Required Services

From the repository root:

```bash evaluation/start_services.sh
docker compose up -d mongodb qdrant ollama
```

Pull the embedding model:

```bash evaluation/pull_embeddings.sh
ollama pull nomic-embed-text
```

Check containers:

```bash evaluation/check_services.sh
docker compose ps
```

---

## 3. Install Dependencies

From the repository root:

```bash evaluation/install_dependencies.sh
uv sync
uv pip install datasets pandas tqdm rapidfuzz anthropic
```

Notes:

- `datasets` is only needed for HuggingFace loading.
- `anthropic` is only needed when using `--judge`.

---

## 4. Configure `.env`

Create or update `.env` in the repository root.

Recommended config:

```bash evaluation/.env.locomo.example
MONGODB_CONNECTION_STRING=mongodb://localhost:27017
MONGODB_DATABASE_NAME=memblocks_locomo_eval
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_PREFER_GRPC=true
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDINGS_MODEL=nomic-embed-text

LLM_PROVIDER_NAME=groq
GROQ_API_KEY=your_groq_key_here
LLM_MODEL=llama-3.1-70b-versatile

LLM_CONVO_TEMPERATURE=0.0
LLM_SEMANTIC_EXTRACTION_TEMPERATURE=0.0
LLM_MEMORY_UPDATE_TEMPERATURE=0.0
LLM_CORE_EXTRACTION_TEMPERATURE=0.0
LLM_RECURSIVE_SUMMARY_GEN_TEMPERATURE=0.0

MEMORY_WINDOW=10
KEEP_LAST_N=4

RETRIEVAL_ENABLE_QUERY_EXPANSION=true
RETRIEVAL_ENABLE_HYPOTHETICAL_PARAGRAPHS=false
RETRIEVAL_ENABLE_RERANKING=true
RETRIEVAL_ENABLE_SPARSE=true
RETRIEVAL_TOP_K_PER_QUERY=5
RETRIEVAL_FINAL_TOP_K=10
```

For OpenRouter, replace the LLM section with:

```bash evaluation/.env.openrouter.example
LLM_PROVIDER_NAME=openrouter
OPENROUTER_API_KEY=your_openrouter_key_here
LLM_MODEL=anthropic/claude-3.5-sonnet
```

For Gemini, replace the LLM section with:

```bash evaluation/.env.gemini.example
LLM_PROVIDER_NAME=gemini
GEMINI_API_KEY=your_gemini_key_here
LLM_MODEL=gemini-1.5-pro
```

---

## 5. Prepare LOCOMO Data

The safest input format is:

```json evaluation/normalized_locomo_example.json
[
  {
    "conversation_id": "locomo_0001",
    "messages": [
      {"role": "user", "content": "I moved to Berlin last month.", "timestamp": "2023-01-01T10:00:00"},
      {"role": "assistant", "content": "How are you liking Berlin?", "timestamp": "2023-01-01T10:00:05"}
    ],
    "qa": [
      {
        "question_id": "locomo_0001_q001",
        "question": "Where did I move last month?",
        "answer": "Berlin",
        "reasoning_type": "single-hop",
        "evidence": ["I moved to Berlin last month."]
      }
    ]
  }
]
```

`evaluation/locomo_eval.py` also tries to convert common LOCOMO field names automatically:

- Conversation fields: `messages`, `conversation`, `dialogue`, `dialog`, `turns`, `transcript`
- Message text fields: `content`, `text`, `utterance`, `message`, `value`, `body`
- Message role fields: `role`, `speaker`, `sender`, `from`, `author`, `participant`
- QA fields: `qa`, `qas`, `questions`, `question_answers`
- Question fields: `question`, `query`, `q`, `input`
- Answer fields: `answer`, `gold_answer`, `target`, `output`, `a`
- Type fields: `reasoning_type`, `type`, `category`, `question_type`, `qa_type`, `label`

If your LOCOMO file uses different field names, edit these functions in `evaluation/locomo_eval.py`:

- `normalize_record(...)`
- `normalize_message(...)`
- `normalize_qa(...)`

---

## 6. Verify the Script Loads

Run:

```bash evaluation/check_script.sh
uv run python evaluation/locomo_eval.py --help
```

You should see CLI options such as `--dataset-path`, `--hf-dataset`, `--run-baseline`, and `--output-dir`.

---

## 7. Run a Smoke Test

Use one conversation and one or two questions before a full run.

For a local JSON/JSONL file:

```bash evaluation/smoke_test_local.sh
uv run python evaluation/locomo_eval.py \
  --dataset-path path/to/locomo_normalized.json \
  --limit-conversations 1 \
  --limit-questions-per-conversation 2 \
  --run-baseline \
  --output-dir evaluation/results
```

For HuggingFace:

```bash evaluation/smoke_test_hf.sh
uv run python evaluation/locomo_eval.py \
  --hf-dataset your_locomo_dataset_name \
  --hf-split test \
  --limit-conversations 1 \
  --limit-questions-per-conversation 2 \
  --run-baseline \
  --output-dir evaluation/results
```

Expected terminal output:

```text evaluation/expected_smoke_output.txt
Evaluating conversation locomo_0001 with 2 questions

Wrote rows: evaluation/results/locomo_eval_YYYYMMDD_HHMMSS_rows.jsonl
Wrote report: evaluation/results/locomo_eval_YYYYMMDD_HHMMSS_report.json
{
  "memblocks_mean_score": ...,
  "baseline_mean_score": ...,
  "memory_lift": ...
}
```

---

## 8. Run the Full Evaluation

Local dataset:

```bash evaluation/run_full_local.sh
uv run python evaluation/locomo_eval.py \
  --dataset-path path/to/locomo_normalized.json \
  --run-baseline \
  --output-dir evaluation/results
```

HuggingFace dataset:

```bash evaluation/run_full_hf.sh
uv run python evaluation/locomo_eval.py \
  --hf-dataset your_locomo_dataset_name \
  --hf-split test \
  --run-baseline \
  --output-dir evaluation/results
```

Optional oracle-evidence upper bound:

```bash evaluation/run_with_oracle.sh
uv run python evaluation/locomo_eval.py \
  --dataset-path path/to/locomo_normalized.json \
  --run-baseline \
  --run-oracle \
  --output-dir evaluation/results
```

Optional Anthropic judge:

```bash evaluation/run_with_judge.sh
export ANTHROPIC_API_KEY=your_anthropic_key_here

uv run python evaluation/locomo_eval.py \
  --dataset-path path/to/locomo_normalized.json \
  --run-baseline \
  --judge \
  --judge-model claude-3-5-sonnet-20241022 \
  --output-dir evaluation/results
```

---

## 9. Output Files

The script writes two files per run.

### Per-question rows

Pattern:

```text evaluation/output_rows_pattern.txt
evaluation/results/locomo_eval_YYYYMMDD_HHMMSS_rows.jsonl
```

Each line contains one evaluated QA row:

```json evaluation/result_row_example.json
{
  "conversation_id": "locomo_0001",
  "question_id": "locomo_0001_q001",
  "reasoning_type": "single-hop",
  "mode": "memblocks",
  "question": "Where did I move last month?",
  "gold_answer": "Berlin",
  "predicted_answer": "Berlin.",
  "score": 1.0,
  "automatic_score": 1.0,
  "exact_match": true,
  "contains_gold": true,
  "token_f1": 1.0,
  "retrieval_contains_gold": true,
  "retrieval_contains_evidence": true,
  "retrieved_semantic_count": 3,
  "retrieved_semantic_contents": ["User moved to Berlin last month."],
  "recursive_summary_chars": 512,
  "memory_window_messages": 4,
  "latency_ms": 2200,
  "judge": null
}
```

### Aggregate report

Pattern:

```text evaluation/output_report_pattern.txt
evaluation/results/locomo_eval_YYYYMMDD_HHMMSS_report.json
```

Important fields:

```json evaluation/report_key_fields.json
{
  "overall": {
    "memblocks_mean_score": 0.71,
    "baseline_mean_score": 0.22,
    "memory_lift": 0.49
  },
  "by_reasoning_type": {
    "single-hop": {"count": 100, "mean_score": 0.82},
    "multi-hop": {"count": 100, "mean_score": 0.61},
    "temporal": {"count": 100, "mean_score": 0.56}
  },
  "retrieval_diagnostics": {
    "retrieval_contains_gold_rate": 0.64,
    "retrieval_contains_evidence_rate": 0.58,
    "avg_retrieved_semantic_count": 7.1
  }
}
```

---

## 10. Interpret the Results

Main numbers to check:

1. `overall.memblocks_mean_score`
2. `overall.memory_lift`
3. `by_reasoning_type.single-hop.mean_score`
4. `by_reasoning_type.multi-hop.mean_score`
5. `by_reasoning_type.temporal.mean_score`
6. `retrieval_diagnostics.retrieval_contains_gold_rate`
7. `retrieval_diagnostics.retrieval_contains_evidence_rate`

Suggested initial thresholds:

| Metric | Threshold |
|---|---:|
| `memblocks_mean_score` | `>= 0.55` |
| `memory_lift` over baseline | `>= 0.20` |
| `single-hop.mean_score` | `>= 0.65` |
| `multi-hop.mean_score` | `>= 0.45` |
| `temporal.mean_score` | `>= 0.40` |
| `retrieval_contains_gold_rate` | `>= 0.50` |

Common interpretations:

| Observation | Likely meaning |
|---|---|
| High oracle score, low MemBlocks score | Memory extraction/retrieval is likely failing |
| Low oracle score too | Conversation LLM cannot answer well even with evidence |
| High single-hop, low multi-hop | Retrieved facts are okay, multi-fact reasoning is weak |
| High retrieval_contains_gold but low answer score | Answer-generation prompt/model is the bottleneck |
| Low retrieval_contains_gold | Retrieval or memory storage is the bottleneck |
| Temporal questions are much worse | Event timestamps/order are not preserved or not used well |

---

## 11. Troubleshooting

### `ModuleNotFoundError: No module named 'memblocks'`

Run from the repository root:

```bash evaluation/fix_import.sh
uv sync
uv run python evaluation/locomo_eval.py --help
```

If needed:

```bash evaluation/install_workspace.sh
uv pip install -e memblocks_lib
```

### MongoDB connection error

```bash evaluation/debug_mongo.sh
docker compose ps mongodb
docker compose logs mongodb --tail=50
grep MONGODB_CONNECTION_STRING .env
```

### Qdrant connection error

```bash evaluation/debug_qdrant.sh
docker compose ps qdrant
docker compose logs qdrant --tail=50
grep QDRANT .env
```

### Ollama embedding error

```bash evaluation/debug_ollama.sh
ollama list
ollama pull nomic-embed-text
```

### LLM provider API error

Check your provider/key combination:

```bash evaluation/debug_llm_env.sh
grep LLM_PROVIDER_NAME .env
grep GROQ_API_KEY .env
grep GEMINI_API_KEY .env
grep OPENROUTER_API_KEY .env
```

### Dataset normalization produced zero records

Minimum required shape:

```json evaluation/minimum_dataset_shape.json
[
  {
    "conversation_id": "example_1",
    "messages": [{"role": "user", "content": "..."}],
    "qa": [{"question": "...", "answer": "..."}]
  }
]
```

If your LOCOMO file uses custom field names, update the normalization functions in `evaluation/locomo_eval.py`.

### Evaluation is slow or expensive

Use limits first:

```bash evaluation/run_limited.sh
uv run python evaluation/locomo_eval.py \
  --dataset-path path/to/locomo_normalized.json \
  --limit-conversations 3 \
  --limit-questions-per-conversation 3 \
  --run-baseline
```

Then scale up.

---

## 12. Recommended Run Order

Follow this exact sequence:

1. `docker compose up -d mongodb qdrant ollama`
2. `ollama pull nomic-embed-text`
3. `uv sync`
4. `uv pip install datasets pandas tqdm rapidfuzz anthropic`
5. Configure `.env`
6. Prepare LOCOMO data
7. `uv run python evaluation/locomo_eval.py --help`
8. Run smoke test with `--limit-conversations 1 --limit-questions-per-conversation 2`
9. Inspect `evaluation/results/*_report.json`
10. Run full evaluation
11. Compare `memblocks_mean_score`, `memory_lift`, and `by_reasoning_type`
