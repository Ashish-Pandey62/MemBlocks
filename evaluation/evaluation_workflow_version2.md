# MemBlocks Evaluation Workflow Version 2 — LOCOMO Reasoning Benchmark

This workflow replaces the component-by-component evaluation in `evaluation_workflow.md` with one practical end-to-end benchmark: **run MemBlocks on the LOCOMO long-conversation dataset and evaluate answer quality by reasoning type**.

Use this file as the source of truth for the current simplified evaluation target:

> Build memory from each LOCOMO conversation, ask LOCOMO questions, and measure how well MemBlocks answers single-hop, multi-hop, temporal, and other long-memory reasoning questions.

This workflow is intentionally focused. It does **not** separately score PS1 extraction, PS2 conflict resolution, core memory, or summary quality. Those internals are only inspected through their downstream effect on final answer correctness.

---

## Table of Contents

1. [Evaluation Goal](#1-evaluation-goal)
2. [What This Tests in MemBlocks](#2-what-this-tests-in-memblocks)
3. [Required Services and Environment](#3-required-services-and-environment)
4. [LOCOMO Data Contract](#4-locomo-data-contract)
5. [Evaluation Modes](#5-evaluation-modes)
6. [End-to-End Evaluation Flow](#6-end-to-end-evaluation-flow)
7. [Prompt Used for Answer Generation](#7-prompt-used-for-answer-generation)
8. [Scoring](#8-scoring)
9. [Report Format](#9-report-format)
10. [Reference Script Structure](#10-reference-script-structure)
11. [Run Commands](#11-run-commands)
12. [Pass/Fail Criteria](#12-passfail-criteria)
13. [Appendix — Copy-Paste Judge Prompt](#appendix--copy-paste-judge-prompt)

---

## 1. Evaluation Goal

The goal is to answer one question:

> After MemBlocks has processed a long LOCOMO conversation, can it answer memory-dependent questions correctly?

For each conversation in LOCOMO:

1. Replay the conversation into a real `MemBlocksClient` session.
2. Let `Session.add()` and/or `Session.flush()` run the actual memory pipeline.
3. For every LOCOMO QA item attached to that conversation:
   - call `await block.retrieve(question)`
   - build a normal MemBlocks conversation prompt from retrieved memory, rolling summary, and current window
   - ask `client.conversation_llm.chat(...)`
   - compare the answer against the LOCOMO gold answer
4. Aggregate results by question/reasoning type:
   - `single-hop`
   - `multi-hop`
   - `temporal`
   - `open-domain / preference / attribute / other`, depending on the LOCOMO labels available in the dataset file

This gives a direct measure of whether the memory system helps long-conversation reasoning.

---

## 2. What This Tests in MemBlocks

This workflow tests the actual project runtime path:

| Step | MemBlocks method used | Why it matters |
|---|---|---|
| Create user/block/session | `MemBlocksClient.get_or_create_user`, `create_block`, `create_session` | Same setup as production |
| Save conversation turns | `Session.add(user_msg, ai_response)` | Triggers real persistence and memory pipeline |
| Force final memory processing | `Session.flush()` | Ensures all remaining LOCOMO messages are written to memory |
| Retrieve memory for question | `Block.retrieve(question)` | Tests semantic retrieval + core memory retrieval |
| Build memory prompt | `RetrievalResult.to_prompt_string()`, `Session.get_recursive_summary()`, `Session.get_memory_window()` | Same context injection mechanism used by apps |
| Generate answer | `client.conversation_llm.chat(messages)` | Tests final reasoning over retrieved memory |
| Evaluate answer | exact/F1/LLM judge | Measures practical QA quality |

This is an **end-to-end reasoning benchmark**, not a unit test suite.

---

## 3. Required Services and Environment

Run the normal local infrastructure used by this project:

```bash eval/locomo/commands.sh
# from repo root
cp .env.example .env

docker compose up -d mongodb qdrant ollama

# make sure the embedding model exists in Ollama
ollama pull nomic-embed-text
```

Recommended `.env` for LOCOMO evaluation:

```bash eval/locomo/.env.example
MONGODB_CONNECTION_STRING=mongodb://localhost:27017
MONGODB_DATABASE_NAME=memblocks_locomo_eval
QDRANT_HOST=localhost
QDRANT_PORT=6333
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDINGS_MODEL=nomic-embed-text

# Pick one supported MemBlocks LLM provider.
# Groq example:
LLM_PROVIDER_NAME=groq
GROQ_API_KEY=your_key_here
LLM_MODEL=llama-3.1-70b-versatile

# Keep memory tasks deterministic.
LLM_SEMANTIC_EXTRACTION_TEMPERATURE=0.0
LLM_MEMORY_UPDATE_TEMPERATURE=0.0
LLM_CORE_EXTRACTION_TEMPERATURE=0.0
LLM_RECURSIVE_SUMMARY_GEN_TEMPERATURE=0.0

# Conversation answer generation can be deterministic for evaluation.
LLM_CONVO_TEMPERATURE=0.0

# Make flushing frequent enough for long conversations.
MEMORY_WINDOW=10
KEEP_LAST_N=4

# Retrieval settings to benchmark as the default full MemBlocks configuration.
RETRIEVAL_ENABLE_QUERY_EXPANSION=true
RETRIEVAL_ENABLE_HYPOTHETICAL_PARAGRAPHS=false
RETRIEVAL_ENABLE_RERANKING=true
RETRIEVAL_ENABLE_SPARSE=true
RETRIEVAL_TOP_K_PER_QUERY=5
RETRIEVAL_FINAL_TOP_K=10
```

Install evaluation dependencies:

```bash eval/locomo/install.sh
uv sync
uv pip install datasets evaluate rapidfuzz pandas tqdm scikit-learn anthropic
```

`anthropic` is only needed if you use the optional LLM judge. You may replace it with any judge provider, but keep judge temperature at `0`.

---

## 4. LOCOMO Data Contract

LOCOMO releases may appear in slightly different JSON/HuggingFace shapes. The evaluation script should normalize them into this internal format before running MemBlocks.

### 4.1 Normalized conversation record

```json eval/locomo/schemas/normalized_locomo_record.json
{
  "conversation_id": "locomo_0001",
  "messages": [
    {"role": "user", "content": "I moved to Berlin last month.", "timestamp": "2023-01-01T10:00:00"},
    {"role": "assistant", "content": "How are you liking Berlin so far?", "timestamp": "2023-01-01T10:00:05"}
  ],
  "qa": [
    {
      "question_id": "locomo_0001_q001",
      "question": "Where did I move last month?",
      "answer": "Berlin",
      "reasoning_type": "single-hop",
      "evidence": ["I moved to Berlin last month."],
      "metadata": {}
    }
  ]
}
```

### 4.2 Message requirements

MemBlocks only requires:

```json eval/locomo/schemas/message_minimum.json
{"role": "user", "content": "..."}
```

But preserve `timestamp` when LOCOMO provides it. Temporal questions often depend on order/time.

Valid message roles for replay:

- LOCOMO speaker representing the human/user → `user`
- LOCOMO speaker representing assistant/agent/other participant → `assistant`

If LOCOMO has two human speakers rather than `user`/`assistant`, choose one speaker as the evaluated user and map the other speaker to `assistant`. The important thing is consistency within one conversation.

### 4.3 QA reasoning type normalization

Normalize LOCOMO question labels into these buckets:

| Normalized type | Use when LOCOMO label means |
|---|---|
| `single-hop` | Answer is found from one explicit memory/fact/event |
| `multi-hop` | Answer requires combining two or more memories/events |
| `temporal` | Answer depends on order, recency, date, before/after, or duration |
| `preference` | User likes/dislikes/preferences/habits |
| `attribute` | Stable user profile fact: job, location, family, name, etc. |
| `open-domain` | General answer grounded in conversation but not covered above |
| `other` | Unknown/missing label |

If a LOCOMO item has multiple labels, use the most specific one in this priority order:

```text eval/locomo/type_priority.txt
temporal > multi-hop > preference > attribute > single-hop > open-domain > other
```

---

## 5. Evaluation Modes

Run at least two modes.

### 5.1 MemBlocks mode

This is the main evaluation.

- Replay conversation into MemBlocks.
- Use `block.retrieve(question)`.
- Include retrieved memory in the answer prompt.
- Score final answer.

### 5.2 No-memory baseline mode

This measures whether MemBlocks is actually useful.

- Replay may be skipped or still performed for parity.
- Do **not** include `block.retrieve(question)` output.
- Do **not** include recursive summary or memory window, except optionally the current question.
- Ask the same conversation LLM the same question.
- Score final answer.

The key number is **memory lift**:

```text eval/locomo/formulas.txt
memory_lift = memblocks_score - no_memory_baseline_score
```

### 5.3 Optional oracle-context mode

This is an upper bound.

- Do not use MemBlocks retrieval.
- Inject LOCOMO gold evidence snippets into the prompt.
- Ask the same conversation LLM.
- Score final answer.

If oracle-context scores are low, the answer-generation LLM is weak. If oracle-context is high but MemBlocks is low, retrieval/memory is the bottleneck.

---

## 6. End-to-End Evaluation Flow

For each normalized LOCOMO conversation:

1. Create a unique MemBlocks user:
   - `user_id = f"locomo_user_{conversation_id}"`
2. Create one block:
   - `block = await client.create_block(user_id=user_id, name=f"LOCOMO {conversation_id}")`
3. Create one session:
   - per session window must be large becuase only that makes sense.
   - fallback resume if context window hits  
   - `session = await client.create_session(user_id=user_id, block_id=block.id)`
4. Replay messages as turns:
   - pair each `user` message with the next `assistant` message where possible
   - call `await session.add(user_msg, ai_response)`
   - if there are consecutive user messages, use an empty assistant response or combine adjacent same-role messages before replay
5. After the conversation is replayed, call:
   - `await session.flush()`
6. For each QA item:
   - call `retrieval = await block.retrieve(question)`
   - call `summary = await session.get_recursive_summary()`
   - call `window = await session.get_memory_window()`
   - build answer-generation messages using the prompt in Section 7
   - call `answer = await client.conversation_llm.chat(messages)`
   - score answer against LOCOMO gold answer
7. Write one JSONL row per question.
8. Aggregate by reasoning type.

Important: use **fresh user/block/session IDs per conversation** so Qdrant collections and MongoDB documents do not leak memory across LOCOMO conversations.

---

## 7. Prompt Used for Answer Generation

Use this exact answer prompt for MemBlocks mode.

```python eval/locomo/prompts.py
ANSWER_SYSTEM_PROMPT = """
You are answering questions about a previous long conversation.
Use only the provided memory context and conversation context.
If the answer is not supported, say "I don't know".
Keep the answer short and direct.
""".strip()


def build_memblocks_answer_messages(question, retrieval, recursive_summary, memory_window):
    system_parts = [ANSWER_SYSTEM_PROMPT]

    if recursive_summary:
        system_parts.append(f"<Rolling Summary>\n{recursive_summary}\n</Rolling Summary>")

    if retrieval and not retrieval.is_empty():
        system_parts.append(retrieval.to_prompt_string())

    if memory_window:
        formatted_window = "\n".join(
            f"{m.get('role', '').upper()}: {m.get('content', '')}"
            for m in memory_window
        )
        system_parts.append(f"<Recent Conversation Window>\n{formatted_window}\n</Recent Conversation Window>")

    return [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": question},
    ]
```

Use this baseline prompt for no-memory mode.

```python eval/locomo/prompts.py
NO_MEMORY_SYSTEM_PROMPT = """
You are answering a question, but you have no access to the previous conversation.
If the answer requires previous conversation context, say "I don't know".
Keep the answer short and direct.
""".strip()


def build_no_memory_answer_messages(question):
    return [
        {"role": "system", "content": NO_MEMORY_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
```

---

## 8. Scoring

Use both automatic string metrics and an optional LLM judge.

### 8.1 Automatic metrics

Compute these for every question:

| Metric | Description |
|---|---|
| `exact_match` | normalized predicted answer exactly equals normalized gold answer |
| `token_f1` | token-level F1 between predicted and gold answer |
| `contains_gold` | normalized gold answer is a substring of normalized prediction |
| `retrieval_contains_evidence` | any retrieved semantic/core/summary text contains a gold evidence snippet or gold answer |

Normalization:

- lowercase
- remove punctuation
- remove articles `a`, `an`, `the`
- collapse whitespace

### 8.2 Main per-question score

Use this deterministic score for CI:

```text eval/locomo/formulas.txt
if exact_match:
    qa_score = 1.0
elif contains_gold:
    qa_score = 0.8
else:
    qa_score = token_f1
```

### 8.3 Optional LLM judge score

Use an LLM judge for cases where gold answers are paraphrased. The judge returns:

- `correct`: boolean
- `partial_credit`: number from `0.0` to `1.0`
- `uses_conversation_memory`: boolean
- `hallucination_detected`: boolean

Final score with judge enabled:

```text eval/locomo/formulas.txt
final_score = max(qa_score, judge.partial_credit)
```

Do not let a hallucinated answer score above `0.5` even if it has lexical overlap.

```text eval/locomo/formulas.txt
if judge.hallucination_detected:
    final_score = min(final_score, 0.5)
```

### 8.4 Aggregation by reasoning type

For every type bucket, report:

- number of questions
- mean