
# MemBlocks Evaluation Workflow

This document is the project-specific evaluation contract for the current `memblocks_lib` implementation. It is written against the code in `memblocks_lib/src/memblocks` and uses the exact service methods, Pydantic models, prompt payloads, and storage payloads that the library currently uses.

Use this document as the source of truth when creating evaluation datasets, running layer tests, and interpreting results.

## Table of Contents

1. [Project Data Flow and Evaluation Boundaries](#1-project-data-flow-and-evaluation-boundaries)
2. [Canonical Project Formats](#2-canonical-project-formats)
3. [Layer 1 — PS1 Semantic Memory Extraction](#3-layer-1--ps1-semantic-memory-extraction)
4. [Layer 2 — PS2 Conflict Resolution Quality](#4-layer-2--ps2-conflict-resolution-quality)
5. [Layer 3 — Retrieval Quality (RAGAS)](#5-layer-3--retrieval-quality-ragas)
6. [Layer 4 — Core Memory Update Quality](#6-layer-4--core-memory-update-quality)
7. [Layer 5 — Rolling Summary Quality (SummEval)](#7-layer-5--rolling-summary-quality-sumeval)
8. [Layer 6 — End-to-End Response Quality](#8-layer-6--end-to-end-response-quality)
9. [Score Aggregation and Composite Quality Score](#9-score-aggregation-and-composite-quality-score)
10. [CI Integration and Regression Monitoring](#10-ci-integration-and-regression-monitoring)
11. [Tooling Recommendations](#11-tooling-recommendations)
12. [Appendix — Complete Judge Prompt Templates](#appendix--complete-judge-prompt-templates)

---

## 1. Project Data Flow and Evaluation Boundaries

### 1.1 Runtime flow in `memblocks_lib`

The real application loop is:

1. Create/load a `MemBlocksClient` from `MemBlocksConfig`.
2. Create/load a `Block` for a user.
3. Create/load a `Session` attached to that block.
4. Before each assistant response, call `await block.retrieve(user_msg)`.
5. Build the conversation prompt using:
   - `RetrievalResult.to_prompt_string()`
   - `await session.get_memory_window()`
   - `await session.get_recursive_summary()`
6. Call `client.conversation_llm.chat(...)` or another conversation LLM.
7. After the response, call `await session.add(user_msg=user_msg, ai_response=ai_response)`.
8. When the session window reaches `config.memory_window_limit`, `Session.add()` trims to `config.keep_last_n` and triggers `MemoryPipeline.run(...)`, which performs:
   - PS1 semantic extraction: `SemanticMemoryService.extract(messages)`
   - PS2 conflict resolution + Qdrant writes: `SemanticMemoryService.store(memory_unit)`
   - Core memory replacement: `CoreMemoryService.update(block_id, messages)`
   - Recursive summary generation: `MemoryPipeline._generate_summary(messages, current_summary)`

### 1.2 What each evaluation layer tests

| Layer | Project method under test | Primary input | Primary output |
|---|---|---|---|
| PS1 extraction | `SemanticMemoryService.extract(messages)` | `List[Dict[str, str]]` conversation window | `List[SemanticMemoryUnit]` |
| PS2 conflict resolution | `SemanticMemoryService.store(memory_unit)` or isolated `PS2_MEMORY_UPDATE_PROMPT` call | one `SemanticMemoryUnit` + nearest Qdrant candidates | `List[MemoryOperation]` and Qdrant mutations |
| Retrieval | `Block.retrieve(query)` and `SemanticMemoryService.retrieve([query])` | user query string | `RetrievalResult` / `List[List[SemanticMemoryUnit]]` |
| Core memory | `CoreMemoryService.extract(...)` / `update(...)` | recent messages + previous `CoreMemoryUnit` | `CoreMemoryUnit` |
| Rolling summary | `MemoryPipeline._generate_summary(...)` or `Session.flush()` | messages + previous summary | summary string persisted as `recursive_summary` |
| End-to-end | full conversation loop | user message + memory context | assistant response string |

### 1.3 Judge model policy

Use a deterministic judge model with temperature `0`. The production LLM providers in `memblocks_lib` support Groq, Gemini, and OpenRouter, but evaluation may use any external judge as long as it returns valid JSON. Keep the judge independent from the candidate model where possible.

Recommended environment variables for evaluation:

```bash eval/.env.example
MONGODB_CONNECTION_STRING=mongodb://localhost:27017
MONGODB_DATABASE_NAME=memblocks_eval
QDRANT_HOST=localhost
QDRANT_PORT=6333
OLLAMA_BASE_URL=http://localhost:11434
EMBEDDINGS_MODEL=nomic-embed-text
RETRIEVAL_ENABLE_QUERY_EXPANSION=true
RETRIEVAL_ENABLE_HYPOTHETICAL_PARAGRAPHS=false
RETRIEVAL_ENABLE_RERANKING=true
RETRIEVAL_ENABLE_SPARSE=true
```

---

## 2. Canonical Project Formats

This section defines the exact shapes used by the current library. Evaluation datasets should use these shapes directly or should include enough fields to construct them without guessing.

### 2.1 Conversation message format

`Session.add()` writes messages to MongoDB with `role`, `content`, and `timestamp`. `SemanticMemoryService.extract()`, `CoreMemoryService.extract()`, and summary generation only require `role` and `content`, but your eval records should preserve `timestamp` when available.

```json eval/schemas/message.json
{
  "role": "user",
  "content": "I just moved to Berlin last week.",
  "timestamp": "2026-05-02T10:30:00.000000"
}
```

Valid `role` values used by the project are `user`, `assistant`, and optionally `system` when constructing conversation prompts. Memory extraction datasets should include only actual session messages, normally `user` and `assistant`.

### 2.2 Exact PS1 LLM input constructed by the service

`SemanticMemoryService.extract(messages)` transforms the list of message dicts into this user input for the structured LLM chain:

```text eval/formats/ps1_user_input.txt
Current time (ISO 8601): {datetime.now(timezone.utc).isoformat()}

Conversation to analyze:

USER: {messages[0].content}
ASSISTANT: {messages[1].content}
USER: {messages[2].content}

Extract structured semantic memories. Analyze each significant piece of information.
```

The system prompt is `memblocks.prompts.PS1_SEMANTIC_PROMPT`. The structured LLM output model is `SemanticMemoriesOutput`, whose root key is `memories`.

### 2.3 `SemanticMemoryUnit` after PS1 extraction

`SemanticMemoryService.extract()` converts each LLM item into this Pydantic model:

```json eval/schemas/semantic_memory_unit.json
{
  "content": "User moved to Berlin last week.",
  "type": "event",
  "memory_id": null,
  "source": "conversation",
  "confidence": 0.95,
  "memory_time": "2026-04-25T10:30:00+00:00",
  "updated_at": "2026-05-02T10:30:00+00:00",
  "meta_data": {
    "usage": ["2026-05-02T10:30:00+00:00"],
    "status": "active",
    "message_ids": []
  },
  "keywords": ["Berlin", "relocation", "last week"],
  "embedding_text": "User moved to Berlin last week.\nKeywords: Berlin, relocation, last week\nEntities: Berlin",
  "entities": ["Berlin"]
}
```

Rules enforced by the current code:

- `type` must be one of `event`, `fact`, `opinion`.
- `memory_time` is copied only when `type == "event"`; for facts and opinions the service sets it to `null`.
- `source` is set to `conversation`.
- `meta_data.usage` initially contains the extraction timestamp.
- `embedding_text` is generated exactly as `content`, then `Keywords: ...`, then `Entities: ...`.
- `memory_id` is `null` before storage and is populated from the Qdrant point ID only after retrieval.

### 2.4 PS2 input and output formats

`SemanticMemoryService.store(memory_unit)` embeds `memory_unit.embedding_text or memory_unit.content`, retrieves top 5 similar Qdrant points, maps real Qdrant IDs to simple string IDs (`"0"`, `"1"`, ...), and sends this user input to the PS2 structured chain:

```text eval/formats/ps2_user_input.txt
NEW MEMORY:
{json.dumps(new_memory_dict, indent=2, default=str)}

EXISTING MEMORIES:
{json.dumps(existing_memories_list, indent=2, default=str)}
```

Each existing candidate has this exact `ExistingSemanticMemoryUnitForPS2` shape:

```json eval/schemas/existing_semantic_memory_for_ps2.json
{
  "id": "0",
  "memory_time": null,
  "updated_at": "2026-05-01T09:00:00+00:00",
  "keywords": ["software engineer", "occupation"],
  "content": "User is a software engineer.",
  "type": "fact",
  "entities": ["software engineer"],
  "confidence": 0.8
}
```

The PS2 LLM must return `PS2MemoryUpdateOutput`:

```json eval/schemas/ps2_memory_update_output.json
{
  "new_memory_operation": {
    "operation": "NONE",
    "reason": "The new memory is covered by the updated existing memory."
  },
  "existing_memory_operations": [
    {
      "id": "0",
      "operation": "UPDATE",
      "updated_memory": {
        "id": "0",
        "memory_time": null,
        "updated_at": "2026-05-02T10:30:00+00:00",
        "keywords": ["senior software engineer", "Berlin startup", "occupation"],
        "content": "User is a senior software engineer at a Berlin-based startup.",
        "type": "fact",
        "entities": ["Berlin", "startup", "senior software engineer"],
        "confidence": 0.88
      },
      "reason": "The new memory refines the user's occupation."
    }
  ]
}
```

Valid operations are:

- New memory: `ADD` or `NONE`.
- Existing memory: `UPDATE`, `DELETE`, or `NONE`.

### 2.5 Storage payloads and `MemoryOperation`

Semantic memories are stored in Qdrant with `payload = SemanticMemoryUnit.model_dump(exclude={"memory_id"})`. The returned operation list contains `MemoryOperation` objects:

```json eval/schemas/memory_operation.json
{
  "operation": "UPDATE",
  "memory_id": "9ce5d655-60c0-4e30-bc9f-47d0d9b23e39",
  "content": "User is a senior software engineer at a Berlin-based startup.",
  "old_content": "User is a software engineer."
}
```

For `ADD`, `memory_id` may be `null` because the current `QdrantAdapter.store_vector()` generates the point ID internally and returns only `true/false`. For `UPDATE` and `DELETE`, the operation contains the real Qdrant point ID.

### 2.6 Core memory format

`CoreMemoryService.extract(messages, old_core_memory)` returns:

```json eval/schemas/core_memory_unit.json
{
  "persona_content": "The AI is concise and direct, and gives code-first answers when asked.",
  "human_content": "User is named Alice and lives in Berlin. Alice works as a senior software engineer at a startup. Alice prefers direct technical explanations."
}
```

`CoreMemoryService.save(block_id, memory_unit)` stores MongoDB document fields: `block_id`, `persona_content`, `human_content`, and `updated_at`.

### 2.7 Recursive summary format

`MemoryPipeline._generate_summary(messages, previous_summary)` returns the `summary` string from this structured output:

```json eval/schemas/summary_output.json
{
  "summary": "Alice moved to Berlin recently and is settling into a new senior software engineering role at a startup. She prefers direct technical explanations."
}
```

`Session.flush()` and `Session.add()` persist the string in MongoDB as `recursive_summary`.

### 2.8 Retrieval result format

`Block.retrieve(query)` returns `RetrievalResult`:

```json eval/schemas/retrieval_result.json
{
  "core": {
    "persona_content": "The AI is concise and direct.",
    "human_content": "User is Alice, a senior software engineer in Berlin."
  },
  "semantic": [
    {
      "content": "User moved to Berlin last week.",
      "type": "event",
      "memory_id": "9ce5d655-60c0-4e30-bc9f-47d0d9b23e39",
      "source": "conversation",
      "confidence": 0.95,
      "memory_time": "2026-04-25T10:30:00+00:00",
      "updated_at": "2026-05-02T10:30:00+00:00",
      "meta_data": {"usage": [], "status": "active", "message_ids": []},
      "keywords": ["Berlin", "relocation"],
      "embedding_text": "User moved to Berlin last week.\nKeywords: Berlin, relocation\nEntities: Berlin",
      "entities": ["Berlin"]
    }
  ],
  "resource": []
}
```

The exact prompt text injected by `RetrievalResult.to_prompt_string()` is:

```text eval/formats/retrieval_prompt_string.txt
<Core Memory>
[PERSONA]
{persona_content}

[HUMAN]
{human_content}
</Core Memory>

<Semantic Memories>
[EVENT] User moved to Berlin last week.
 Memory Updated at: 2026-05-02T10:30:00+00:00
 | Event occurance time: 2026-04-25T10:30:00+00:00 

</Semantic Memories>
```

Note the current code spells `occurrence` as `occurance`; evaluation prompt-string comparisons should match the implementation, not corrected spelling.

### 2.9 Dataset wrapper format

Use this wrapper for all eval records. Each layer then fills the relevant sub-object.

```json eval/schemas/evaluation_record.json
{
  "case_id": "ps1_001",
  "user_id": "eval_user_001",
  "block_id": "eval_block_001",
  "session_id": "eval_session_001",
  "messages": [
    {"role": "user", "content": "I moved to Berlin last week.", "timestamp": "2026-05-02T10:30:00"},
    {"role": "assistant", "content": "How are you settling in?", "timestamp": "2026-05-02T10:30:01"}
  ],
  "gold": {},
  "notes": "Optional human annotation notes."
}
```

### 2.10 Minimum layer datasets and exact harnesses

Use the following concrete records and harnesses when implementing `eval/layers/*`. These mirror the current service API and avoid guessing about hidden formats.

#### PS1 dataset record

```json eval/datasets/ps1_record.json
{
  "case_id": "ps1_001",
  "messages": [
    {"role": "user", "content": "I moved to Berlin last week."},
    {"role": "assistant", "content": "How are you settling in?"},
    {"role": "user", "content": "I start my new senior backend job on Monday."}
  ],
  "gold": {
    "semantic_memories": [
      {"content": "User moved to Berlin last week.", "type": "event", "memory_time_required": true},
      {"content": "User starts a new senior backend job on Monday.", "type": "event", "memory_time_required": true}
    ]
  }
}
```

```python eval/layers/ps1.py
async def run_ps1_case(semantic_memory_service, record):
    extracted = await semantic_memory_service.extract(record["messages"])
    return [memory.model_dump() for memory in extracted]
```

#### PS2 dataset record

```json eval/datasets/ps2_record.json
{
  "case_id": "ps2_001",
  "collection_name": "eval_ps2_001_semantic",
  "new_memory": {
    "content": "User is a senior software engineer at a Berlin-based startup.",
    "type": "fact",
    "source": "conversation",
    "confidence": 0.88,
    "memory_time": null,
    "updated_at": "2026-05-02T10:30:00+00:00",
    "meta_data": {"usage": [], "status": "active", "message_ids": []},
    "keywords": ["senior software engineer", "Berlin startup"],
    "embedding_text": "User is a senior software engineer at a Berlin-based startup.\nKeywords: senior software engineer, Berlin startup\nEntities: Berlin, startup",
    "entities": ["Berlin", "startup"]
  },
  "existing_qdrant_payloads": [
    {
      "point_id": "11111111-1111-1111-1111-111111111111",
      "payload": {
        "content": "User is a software engineer.",
        "type": "fact",
        "source": "conversation",
        "confidence": 0.8,
        "memory_time": null,
        "updated_at": "2026-05-01T09:00:00+00:00",
        "meta_data": {"usage": [], "status": "active", "message_ids": []},
        "keywords": ["software engineer"],
        "embedding_text": "User is a software engineer.\nKeywords: software engineer\nEntities: software engineer",
        "entities": ["software engineer"]
      }
    }
  ],
  "gold": {
    "expected_operations": ["UPDATE"],
    "expected_content_contains": ["senior software engineer", "Berlin", "startup"],
    "false_delete_forbidden": true
  }
}
```

```python eval/layers/ps2.py
from memblocks.models.units import SemanticMemoryUnit

async def run_ps2_case(semantic_memory_service, qdrant, embeddings, record):
    collection = record["collection_name"]
    qdrant.create_collection(collection)
    for item in record["existing_qdrant_payloads"]:
        payload = item["payload"]
        vector = embeddings.embed_text(payload.get("embedding_text") or payload["content"])
        qdrant.store_vector(collection, vector, payload, point_id=item["point_id"])

    memory = SemanticMemoryUnit(**record["new_memory"])
    operations = await semantic_memory_service.store(memory)
    final_points = qdrant.get_all_points(collection, limit=100)
    return {
        "operations": [operation.model_dump() for operation in operations],
        "final_points": final_points,
    }
```

#### Retrieval dataset record

```json eval/datasets/retrieval_record.json
{
  "case_id": "retrieval_001",
  "query": "Where did I move recently?",
  "seed_semantic_memories": [
    {
      "content": "User moved to Berlin last week.",
      "type": "event",
      "source": "conversation",
      "confidence": 0.95,
      "memory_time": "2026-04-25T10:30:00+00:00",
      "updated_at": "2026-05-02T10:30:00+00:00",
      "meta_data": {"usage": [], "status": "active", "message_ids": []},
      "keywords": ["Berlin", "relocation"],
      "embedding_text": "User moved to Berlin last week.\nKeywords: Berlin, relocation\nEntities: Berlin",
      "entities": ["Berlin"]
    }
  ],
  "gold": {"relevant_contents": ["User moved to Berlin last week."]}
}
```

```python eval/layers/retrieval.py
async def run_retrieval_case(block, record):
    result = await block.retrieve(record["query"])
    return {
        "prompt_string": result.to_prompt_string(),
        "core": result.core.model_dump() if result.core else None,
        "semantic": [memory.model_dump() for memory in result.semantic],
        "resource": [resource.model_dump() for resource in result.resource],
    }
```

#### Core memory dataset record

```json eval/datasets/core_memory_record.json
{
  "case_id": "core_001",
  "old_core_memory": {
    "persona_content": "The AI is helpful and concise.",
    "human_content": "User is named Alice and lives in Kathmandu. Alice works as a software engineer."
  },
  "messages": [
    {"role": "user", "content": "I moved to Berlin last week."},
    {"role": "user", "content": "Please be direct and code-first when I ask programming questions."}
  ],
  "gold": {
    "must_preserve": ["User is named Alice", "works as a software engineer"],
    "must_update": ["lives in Berlin", "direct and code-first programming answers"],
    "must_not_include": ["temporary mood", "assistant speculation"]
  }
}
```

```python eval/layers/core_memory.py
from memblocks.models.units import CoreMemoryUnit

async def run_core_case(core_memory_service, record):
    old = CoreMemoryUnit(**record["old_core_memory"]) if record.get("old_core_memory") else None
    new_core = await core_memory_service.extract(record["messages"], old)
    return new_core.model_dump()
```

#### Summary dataset record

```json eval/datasets/summary_record.json
{
  "case_id": "summary_001",
  "previous_summary": "Alice is a software engineer and previously lived in Kathmandu.",
  "messages": [
    {"role": "user", "content": "I moved to Berlin last week."},
    {"role": "assistant", "content": "That is a major move."},
    {"role": "user", "content": "I start a senior backend job on Monday."}
  ],
  "gold": {
    "must_preserve": ["Alice is a software engineer"],
    "must_update": ["moved to Berlin", "starts a senior backend job on Monday"],
    "must_not_include": ["unsupported reason for moving"]
  }
}
```

```python eval/layers/summary.py
async def run_summary_case(memory_pipeline, record):
    return await memory_pipeline._generate_summary(
        messages=record["messages"],
        previous_summary=record.get("previous_summary", ""),
    )
```

#### End-to-end dataset record

```json eval/datasets/e2e_record.json
{
  "case_id": "e2e_001",
  "user_message": "Can you suggest neighborhoods based on where I moved?",
  "memory_window": [],
  "recursive_summary": "Alice moved to Berlin last week.",
  "seed_core_memory": {
    "persona_content": "The AI is concise and practical.",
    "human_content": "User is Alice, a senior software engineer who recently moved to Berlin."
  },
  "seed_semantic_memories": [
    {
      "content": "User moved to Berlin last week.",
      "type": "event",
      "source": "conversation",
      "confidence": 0.95,
      "memory_time": "2026-04-25T10:30:00+00:00",
      "updated_at": "2026-05-02T10:30:00+00:00",
      "meta_data": {"usage": [], "status": "active", "message_ids": []},
      "keywords": ["Berlin", "relocation"],
      "embedding_text": "User moved to Berlin last week.\nKeywords: Berlin, relocation\nEntities: Berlin",
      "entities": ["Berlin"]
    }
  ],
  "gold": {
    "response_should_use": ["Berlin"],
    "response_must_not_claim": ["user lives in Munich"]
  }
}
```

```python eval/layers/e2e.py
async def run_e2e_case(client, block, record):
    retrieval = await block.retrieve(record["user_message"])
    system_parts = ["You are a helpful assistant."]
    if record.get("recursive_summary"):
        system_parts.append(f"<Summary>\n{record['recursive_summary']}\n</Summary>")
    if not retrieval.is_empty():
        system_parts.append(retrieval.to_prompt_string())

    messages = (
        [{"role": "system", "content": "\n\n".join(system_parts)}]
        + record.get("memory_window", [])
        + [{"role": "user", "content": record["user_message"]}]
    )
    response = await client.conversation_llm.chat(messages)
    return {"retrieval": retrieval.model_dump(), "response": response}
```

---

## 3. Layer 1 — PS1 Semantic Memory Extraction

PS1 corresponds to `SemanticMemoryService.extract()`, which calls the LLM with the raw conversation window and receives a list of `SemanticMemoryUnit` objects. This is the foundational step — any hallucinated or missed memory at this stage propagates permanently into Qdrant.

### 3.1 Failure taxonomy

### 3.2 LLM judge prompt — PS1 extraction fidelity

Use this prompt verbatim. Inject the three input fields from your test dataset. Run once per conversation window.

**SYSTEM:** You are a memory extraction evaluator for an LLM-powered memory system.
Your task is to assess the quality of memories extracted from a raw conversation window.

**INPUT:**
- CONVERSATION: `{raw_messages}`
- EXTRACTED MEMORIES: `{ps1_output_list}`
- GOLD ANNOTATIONS: `{gold_memory_list}`

**TASK 1 — Per-memory grounding score (0–5):**

For each extracted memory, score it independently:
- **5** = factually grounded in conversation, correct type (fact/event/opinion), complete content
- **4** = grounded and correct type, but slightly incomplete or minor wording issue
- **3** = grounded but missing key detail OR minor type mismatch (e.g., fact labeled event)
- **2** = partially grounded — some correct element but distorted or merged with unrelated info
- **1** = barely grounded — conclusion stretches far beyond what conversation states
- **0** = not supported by conversation at all (hallucination)

**TASK 2 — Aggregate metrics:**
- Precision = count(score >= 3) / total extracted
- Recall = count(gold memories with a matching extracted) / total gold memories
- Type F1 = F1 score on fact/event/opinion classification vs gold type labels
- Hallucination rate = count(score == 0) / total extracted

**TASK 3 — Flag:**
- List any gold memory that was not extracted at all (missed recall).
- List any extracted memory that contradicts the conversation (hard hallucination).

**OUTPUT FORMAT:** JSON

```json
{
  "per_memory": [{ "index": N, "score": N, "reason": "..." }],
  "precision": 0.0, "recall": 0.0, "type_f1": 0.0,
  "hallucination_rate": 0.0,
  "missed_memories": ["..."], "hard_hallucinations": ["..."]
}
```

### 3.3 Metrics and target thresholds

### 3.4 Implementation — DeepEval

```python
from deepeval import evaluate
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase

ps1_metric = GEval(
    name="PS1 Extraction Fidelity",
    criteria="""
    Score the memory extraction on:
    1. Precision (0-5): are extracted memories grounded in the conversation?
    2. Recall (0-5): were all important facts extracted?
    3. Hallucination: flag any memory with no grounding (score=0)
    """,
    evaluation_params=["input", "actual_output", "expected_output"],
    model="claude-sonnet-4-6",
)

test_cases = []
for record in ps1_dataset:
    # Run the MemBlocks PS1 extraction
    extracted = await semantic_memory_service.extract(record["messages"])
    test_cases.append(LLMTestCase(
        input=format_messages(record["messages"]),
        actual_output=format_memories(extracted),
        expected_output=format_memories(record["gold_memories"]),
    ))

results = evaluate(test_cases, [ps1_metric])
```

---

## 4. Layer 2 — PS2 Conflict Resolution Quality

PS2 corresponds to `SemanticMemoryService.store()`, where the LLM receives a new candidate memory alongside its K nearest neighbours from Qdrant and decides whether to ADD, UPDATE, DELETE (existing memories), or take no action (NONE). Errors here are partially irreversible — a false DELETE destroys information permanently.

### 4.1 Failure taxonomy

### 4.2 LLM judge prompt — PS2 decision correctness

**SYSTEM:** You are evaluating conflict resolution decisions in a long-term memory system.
Each decision involves a new candidate memory and a set of semantically similar existing memories.

**INPUT:**
- NEW MEMORY: `{new_memory_unit}`
- EXISTING CANDIDATES: `{existing_memories_list}`
- SYSTEM DECISION: operation=`{ADD|UPDATE|DELETE|NONE}`
- RESULTING CONTENT: `{updated_memory_content}` (null if ADD or NONE with no changes)

**TASK 1 — Operation correctness (0–5):**
- **5** = ideal operation given the semantic relationship between new and existing memories
- **4** = correct operation with minor suboptimality (e.g., updated content slightly verbose)
- **3** = defensible operation but a better choice clearly exists
- **2** = operation causes information degradation or unnecessary duplication
- **1** = wrong operation — clear semantic mismatch
- **0** = critically wrong (e.g., DELETE of an unrelated memory)

**TASK 2 — Information preservation (0–5, only for UPDATE or NONE operations):**
- **5** = updated content fully preserves all information from both old and new memory
- **4** = very minor information loss — negligible for practical use
- **3** = some information lost but core facts remain
- **2** = significant information from either old or new memory is missing
- **0** = critical information lost; the merge is worse than either original

**TASK 3 — False DELETE flag:**
Was any DELETE decision applied to a memory that contains information NOT covered by the surviving memory or the new memory?

Answer: `{ "false_delete": true/false, "lost_information": "..." }`

**TASK 4 — Confidence assessment:**
Were the confidence scores on the resulting memories reasonable?
Flag if confidence on a merged memory significantly deviates from either source.

**OUTPUT FORMAT:** JSON

```json
{
  "operation_score": N, "preservation_score": N,
  "false_delete": { "detected": bool, "lost_information": "..." },
  "confidence_ok": bool, "overall_notes": "..."
}
```

### 4.3 Metrics and target thresholds

### 4.4 The False DELETE protocol

Because false DELETEs are the highest-severity failure and are irreversible in production, they require a separate monitoring protocol beyond the standard evaluation run.

### 4.5 Implementation — custom DeepEval metric

```python
from deepeval.metrics import BaseMetric
from deepeval.test_case import LLMTestCase
import json, anthropic

class PS2ConflictMetric(BaseMetric):
    def __init__(self):
        self.threshold = 0.85
        self.name = "PS2 Conflict Resolution"
    
    def measure(self, test_case: LLMTestCase) -> float:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            temperature=0,
            messages=[{ "role": "user", "content": PS2_JUDGE_PROMPT.format(
                new_memory=test_case.input,
                existing_memories_list=test_case.context,
                operation=test_case.actual_output,
                updated_memory_content=test_case.additional_metadata["updated_content"]
            )}]
        )
        result = json.loads(response.content[0].text)
        self.false_delete_detected = result["false_delete"]["detected"]
        op_score = result["operation_score"] / 5.0
        pres_score = result.get("preservation_score", 5) / 5.0
        self.score = (op_score * 0.6 + pres_score * 0.4)
        self.is_successful = self.score >= self.threshold and not self.false_delete_detected
        return self.score
    
    def is_successful(self) -> bool:
        return self._is_successful
```

---

## 5. Layer 3 — Retrieval Quality (RAGAS)

The retrieval layer covers `SemanticMemoryService.retrieve()`, which runs: optional query expansion, optional hypothetical document embedding (HyDE), dense + sparse hybrid search via Qdrant, and optional Cohere reranking. The output is the top-K `SemanticMemoryUnit` list injected into the system prompt.

### 5.1 RAGAS metric mapping to MemBlocks

### 5.2 LLM judge prompt — retrieval fidelity

**SYSTEM:** You are evaluating the retrieval quality of a semantic memory system.

**INPUT:**
- USER QUERY: `{user_message}`
- RETRIEVED MEMORIES (top-K): `{retrieved_memory_list}`
- GROUND TRUTH RELEVANT MEMORIES: `{gold_relevant_set}`
- FINAL AI RESPONSE: `{ai_response}`

**TASK 1 — Context Precision (per retrieved memory):**
For each retrieved memory, is it genuinely useful for answering the user query?
Score: 1 (relevant) or 0 (not relevant). Precision = sum / K

**TASK 2 — Context Recall:**
Of the gold relevant memories, how many were retrieved?
Recall = count(gold found in retrieved) / total gold relevant

**TASK 3 — Faithfulness:**
For each factual claim in the AI response, is it supported by:
(a) the retrieved memories, or (b) the current conversation turn?
Flag any claim not traceable to either source.
Faithfulness = count(supported claims) / total claims

**TASK 4 — Answer Relevance:**
Does the response directly and completely address the user query?
Score 0–5: 5 = fully addresses, 0 = completely off-topic.

**TASK 5 — Memory Utilisation:**
Of the retrieved memories, how many does the response actually reference or reason from?
Utilisation rate = count(used memories) / count(retrieved memories)

**OUTPUT FORMAT:** JSON

```json
{
  "context_precision": 0.0, "context_recall": 0.0, "faithfulness": 0.0,
  "answer_relevance": N, "memory_utilisation": 0.0,
  "unsupported_claims": ["..."], "unused_retrieved_memories": [N, N]
}
```

### 5.3 Non-LLM retrieval metrics

These metrics do not require a judge call and should be computed on every evaluation run.

### 5.4 Ablation study design

MemBlocks retrieval has three toggleable features. Evaluate each in isolation to quantify individual contributions:

```python
ABLATION_CONFIGS = [
    {
        "name": "dense_only",
        "retrieval_enable_query_expansion": False,
        "retrieval_enable_hypothetical_paragraphs": False,
        "retrieval_enable_reranking": False,
        "retrieval_enable_sparse": False,
    },
    {
        "name": "hybrid_sparse",
        "retrieval_enable_query_expansion": False,
        "retrieval_enable_hypothetical_paragraphs": False,
        "retrieval_enable_reranking": False,
        "retrieval_enable_sparse": True,
    },
    {
        "name": "query_expansion",
        "retrieval_enable_query_expansion": True,
        "retrieval_enable_hypothetical_paragraphs": False,
        "retrieval_enable_reranking": False,
        "retrieval_enable_sparse": True,
    },
    {
        "name": "hyde",
        "retrieval_enable_query_expansion": False,
        "retrieval_enable_hypothetical_paragraphs": True,
        "retrieval_enable_reranking": False,
        "retrieval_enable_sparse": True,
    },
    {
        "name": "full",
        "retrieval_enable_query_expansion": True,
        "retrieval_enable_hypothetical_paragraphs": True,
        "retrieval_enable_reranking": True,
        "retrieval_enable_sparse": True,
    }
]

for config in ABLATION_CONFIGS:
    set_retrieval_config(config)
    results = evaluate_retrieval(test_queries, gold_relevant_sets)
    report_metrics(config["name"], results)
```

This ablation reveals whether each feature earns its latency cost. A feature that adds 80ms but lifts Recall@5 by only 1% may not be worth enabling in production.

### 5.5 Implementation — RAGAS integration

```python
from ragas import evaluate as ragas_evaluate
from ragas.metrics import (
    context_precision, context_recall,
    faithfulness, answer_relevancy
)
from datasets import Dataset

data = {
    "question":  [r["query"] for r in retrieval_test_set],
    "contexts":  [r["retrieved_memories_text"] for r in retrieval_test_set],
    "answer":    [r["ai_response"] for r in retrieval_test_set],
    "ground_truths": [r["gold_relevant_texts"] for r in retrieval_test_set],
}

result = ragas_evaluate(
    Dataset.from_dict(data),
    metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
    llm=AnthropicLangchain(model="claude-sonnet-4-6"),
)

print(result.to_pandas())
```

---

## 6. Layer 4 — Core Memory Update Quality

Core memory (`CoreMemoryService.update()`) maintains two persistent text fields in MongoDB: `persona_content` (the AI persona for the active block) and `human_content` (the user profile). These fields are injected into every system prompt without retrieval, so errors here affect every response the user receives.

### 6.1 Failure taxonomy

### 6.2 LLM judge prompt — profile accuracy

**SYSTEM:** You are evaluating how accurately a system updates a persistent user profile.

**INPUT:**
- RECENT CONVERSATION WINDOW: `{recent_messages}`
- PERSONA BEFORE: `{old_persona_content}`
- HUMAN PROFILE BEFORE: `{old_human_content}`
- PERSONA AFTER: `{new_persona_content}`
- HUMAN PROFILE AFTER: `{new_human_content}`

**TASK 1 — Update Relevance (0–5):**
Did the update incorporate genuinely new information that was present in the conversation and was not already captured in the profile?
- **5** = all important new information captured, no spurious additions
- **3** = some important information captured but notable omissions
- **1** = update added mostly trivial or irrelevant details
- **0** = update ignored all new information

**TASK 2 — Profile Completeness (0–5):**
Is the resulting profile complete relative to what a good assistant would need to know about this user based on the full conversation history?

**TASK 3 — Profile Drift (critical flag):**
Did any update CHANGE a fact that was previously correct?
List any factual distortions or contradictions introduced by the update.
`"drift_detected": true/false, "distortions": [{ "field": "...", "before": "...", "after": "..." }]`

**TASK 4 — Omission Rate:**
List facts explicitly stated in the conversation that were NOT captured in the updated profile.

**OUTPUT FORMAT:** JSON

```json
{
  "update_relevance": N, "completeness": N,
  "drift": { "detected": bool, "distortions": [...] },
  "omissions": ["..."]
}
```

### 6.3 Metrics and target thresholds

---

## 7. Layer 5 — Rolling Summary Quality (SummEval)

The rolling summary (generated in `MemoryPipeline.run()`) compresses older conversation messages into a compact summary stored per session in MongoDB. This summary is injected into every system prompt alongside the memory window and retrieved semantic memories. Compression errors silently destroy context that cannot be recovered from Qdrant (because conversation turns are not individually vectorised).

### 7.1 SummEval dimension mapping

### 7.2 LLM judge prompt — summary fidelity

**SYSTEM:** You are evaluating the quality of a rolling conversation summary.
The summary is produced recursively — it compresses older messages to free context window space.

**INPUT:**
- SOURCE MESSAGES: `{raw_message_window}`
- PREVIOUS SUMMARY: `{prior_summary}` (may be empty for first compression)
- NEW SUMMARY: `{new_summary}`

**TASK 1 — Factual Consistency (0–5):**
Does the new summary contain any facts that contradict the source messages or the previous summary?
- **5** = fully consistent, no contradictions
- **3** = minor imprecision but no clear contradiction
- **0** = clear factual contradiction present
List contradictions if any.

**TASK 2 — Relevance / Information Density (0–5):**
Does the summary capture the most important information from the source window?
Is filler (small talk, acknowledgments, redundant exchanges) appropriately excluded?
- **5** = all important facts preserved, filler excluded
- **3** = important facts mostly preserved with some unnecessary content
- **1** = critical information lost or summary dominated by filler

**TASK 3 — Coherence (0–5):**
Is the summary logically organized and easy to read as a standalone document?
A future LLM receiving only this summary should understand the user context clearly.

**TASK 4 — Information Density Ratio:**
Count distinct factual claims in source messages vs in new summary.
Density ratio = facts_in_summary / facts_in_source
(Higher is better up to ~0.8; near 1.0 means no compression happened)

**OUTPUT FORMAT:** JSON

```json
{
  "factual_consistency": N, "relevance": N, "coherence": N,
  "density_ratio": 0.0, "contradictions": ["..."], "missed_facts": ["..."]
}
```

### 7.3 Information density ratio computation

The density ratio provides a compression-independent quality signal. It requires a preliminary fact extraction step:

```python
# Step 1: Extract atomic facts from source messages
FACT_EXTRACT_PROMPT = """
List every distinct factual claim in the following conversation.
Output as a JSON array of strings. Only include concrete facts, not social utterances.
CONVERSATION: {messages}
"""

# Step 2: Extract atomic facts from summary
FACT_EXTRACT_PROMPT_SUMMARY = """
List every distinct factual claim in the following text.
Output as a JSON array of strings.
TEXT: {summary}
"""

# Step 3: Compute ratio
source_facts = extract_facts(source_messages)
summary_facts = extract_facts(new_summary)
# Judge which source facts are covered in summary_facts
coverage_score = judge_fact_coverage(source_facts, summary_facts)
density_ratio = coverage_score / len(source_facts)
```

### 7.4 Recursive compression degradation test

Because MemBlocks summarises recursively (each new summary may compress a prior summary), test quality across N rounds of compression to detect cumulative degradation:

```python
async def test_recursive_compression_degradation(session, rounds=5):
    """
    Flush the session N times and measure SummEval scores after each round.
    A healthy system should not degrade more than 0.2 points per round.
    """
    scores = []
    for i in range(rounds):
        await session.flush()  # triggers memory pipeline
        summary = await session.get_recursive_summary()
        score = evaluate_summary(original_messages, summary)
        scores.append(score)
    return scores  # should be approximately flat; downward trend = degradation
```

---

## 8. Layer 6 — End-to-End Response Quality

The end-to-end evaluation assesses the final assistant response as generated by the conversation LLM after memory injection. This layer tests whether the full system — retrieval + injection + generation — actually delivers personalised, grounded responses.

### 8.1 Failure taxonomy

### 8.2 LLM judge prompt — grounding and coherence

**SYSTEM:** You are evaluating an AI assistant response in a memory-augmented chat system.
The assistant has access to long-term memories injected into its system prompt.

**INPUT:**
- USER MESSAGE: `{user_message}`
- INJECTED MEMORIES (what the assistant could use):
  - Core Memory: `{core_memory_string}`
  - Semantic Memories: `{semantic_memories_list}`
  - Rolling Summary: `{rolling_summary}`
- ASSISTANT RESPONSE: `{ai_response}`

**TASK 1 — Memory Grounding Score (0–5):**
Does the response appropriately use the injected memories to personalize the answer?
- **5** = response clearly leverages relevant memories where applicable
- **3** = some memory usage but obvious relevant memories were ignored
- **0** = response completely ignores all injected memories despite clear relevance

**TASK 2 — Persona Consistency (0–5):**
Is the response consistent with the `persona_content` defined in the active memory block?
Does the assistant maintain the defined role, tone, and expertise?

**TASK 3 — Temporal Accuracy (0–5, only when event-type memories exist):**
For event-type memories with timestamps, does the response correctly handle temporal references ("last week", "recently", "before X")?

**TASK 4 — Hallucination in Response (0–1 flag):**
Does the response assert any specific fact about the user that is NOT supported by the injected memories or the current conversation turn?
List hallucinated claims.

**TASK 5 — Answer Relevance (0–5):**
Does the response directly and helpfully address the user message?

**OUTPUT FORMAT:** JSON

```json
{
  "grounding": N, "persona_consistency": N, "temporal_accuracy": N,
  "hallucination_detected": bool, "hallucinated_claims": ["..."],
  "answer_relevance": N
}
```

### 8.3 Baseline comparison protocol

The most important E2E measurement is the lift MemBlocks provides over a baseline with memory disabled. Run the full test set twice: once with retrieval enabled, once with an empty RetrievalResult. Measure the delta:

```python
async def measure_memory_lift(test_cases):
    results = {}
    for tc in test_cases:
        # With memory enabled
        retrieval = await block.retrieve(tc["user_message"])
        response_with_mem = generate_response(tc, retrieval)
        
        # Baseline: empty retrieval (no long-term memory)
        empty_retrieval = RetrievalResult(core=None, semantic=[], resource=[])
        response_no_mem = generate_response(tc, empty_retrieval)
        
        # Judge both responses
        score_with = judge_e2e(tc, response_with_mem, retrieval)
        score_without = judge_e2e(tc, response_no_mem, empty_retrieval)
        
        results[tc["id"]] = {
            "with_memory": score_with,
            "without_memory": score_without,
            "lift": score_with["answer_relevance"] - score_without["answer_relevance"]
        }
    return results
```

**Target:** memory lift on answer relevance >= +0.5 on the 0–5 scale. A system that scores equally with and without memory provides no practical benefit from the memory layer.

---

## 9. Score Aggregation and Composite Quality Score

### 9.1 Weighted composite formula

```python
def compute_composite_score(layer_scores: dict) -> float:
    """
    Weighted composite score across all six evaluation layers.
    Weights reflect both layer importance and downstream impact.
    """
    weights = {
        "ps1":       0.20,   # extraction is foundational — errors propagate downstream
        "ps2":       0.20,   # PS2 errors are partially irreversible (false DELETE)
        "retrieval": 0.25,   # retrieval gates everything that follows
        "core_mem":  0.10,   # always-present; lower weight because it changes slowly
        "summary":   0.10,   # affects episodic context; medium criticality
        "e2e":       0.15,   # user-facing quality; depends on all upstream layers
    }
    return sum(layer_scores[k] * weights[k] for k in weights)
```

### 9.2 Hard gates — deployment blockers

Before computing the composite score, evaluate these hard gates. A failure on any hard gate blocks deployment regardless of the composite score.

### 9.3 Score reporting format

Output the following JSON for each evaluation run. Store alongside the git commit hash to track regression over time:

```json
{
  "run_id": "eval_2025-05-02_abc123",
  "git_commit": "abc123",
  "hard_gates": {
    "ps1_hallucination_rate":   0.032,  "ps1_gate_passed": true,
    "ps2_false_delete_rate":    0.014,  "ps2_gate_passed": true,
    "core_drift_rate":          0.021,  "core_gate_passed": true,
    "e2e_hallucination_rate":   0.038,  "e2e_gate_passed": true,
    "retrieval_precision":      0.832,  "retrieval_gate_passed": true
  },
  "layer_scores": {
    "ps1": 0.81, "ps2": 0.87, "retrieval": 0.79,
    "core_mem": 0.84, "summary": 0.88, "e2e": 0.76
  },
  "composite_score": 0.819,
  "deployment_approved": true
}
```

---

## 10. CI Integration and Regression Monitoring

### 10.1 Evaluation loop structure

```python
# eval/run_all_layers.py
import asyncio
from eval.layers import ps1, ps2, retrieval, core_mem, summary, e2e
from eval.aggregator import compute_composite, check_hard_gates
from eval.reporter import save_report

async def run_full_eval(commit_hash: str):
    print("Running PS1 extraction evaluation...")
    ps1_scores = await ps1.evaluate(PS1_DATASET)
    
    print("Running PS2 conflict resolution evaluation...")
    ps2_scores = await ps2.evaluate(PS2_DATASET)
    
    print("Running retrieval quality evaluation (RAGAS)...")
    retrieval_scores = await retrieval.evaluate(RETRIEVAL_DATASET)
    
    print("Running core memory update evaluation...")
    core_scores = await core_mem.evaluate(CORE_MEM_DATASET)
    
    print("Running rolling summary evaluation (SummEval)...")
    summary_scores = await summary.evaluate(SUMMARY_DATASET)
    
    print("Running end-to-end response evaluation...")
    e2e_scores = await e2e.evaluate(E2E_DATASET)
    
    layer_scores = {
        "ps1": ps1_scores["composite"],
        "ps2": ps2_scores["composite"],
        "retrieval": retrieval_scores["composite"],
        "core_mem": core_scores["composite"],
        "summary": summary_scores["composite"],
        "e2e": e2e_scores["composite"],
    }
    
    gates = check_hard_gates(
        ps1_hallucination_rate=ps1_scores["hallucination_rate"],
        ps2_false_delete_rate=ps2_scores["false_delete_rate"],
        core_drift_rate=core_scores["drift_rate"],
        e2e_hallucination_rate=e2e_scores["hallucination_rate"],
        retrieval_precision=retrieval_scores["context_precision"],
    )
    
    composite = compute_composite(layer_scores)
    save_report(commit_hash, layer_scores, gates, composite)
    
    if not all(gates.values()):
        raise SystemExit("Hard gate failure — deployment blocked.")
    
    if composite < 0.75:
        raise SystemExit(f"Composite score {composite:.3f} below threshold 0.75.")
    
    print(f"Evaluation passed. Composite score: {composite:.3f}")
```

### 10.2 Recommended CI schedule

---

## 11. Tooling Recommendations

### 11.1 Environment setup

```bash
# Install all evaluation dependencies
pip install deepeval ragas anthropic langchain-anthropic datasets

# Set judge model API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Configure DeepEval
deepeval set-azure-openai ...  # or use Anthropic directly via custom metric

# Run a single layer smoke test
python -m eval.layers.ps1 --sample 5 --verbose
```

---

## Appendix — Complete Judge Prompt Templates

The following section contains all six judge prompts in their complete, copy-pasteable form. Each prompt is designed for a single judge model call at temperature 0 with JSON output mode. Inject the `{variable}` placeholders from your dataset records before calling the API.

### A. PS1 Extraction Judge Prompt

**SYSTEM:** You are a memory extraction evaluator for an LLM-powered memory system.
Your task is to assess the quality of memories extracted from a raw conversation window.

**INPUT:**
- CONVERSATION: `{raw_messages}`
- EXTRACTED MEMORIES: `{ps1_output_list}`
- GOLD ANNOTATIONS: `{gold_memory_list}`

**TASK 1 — Per-memory grounding score (0–5):**

For each extracted memory, score it independently:
- **5** = factually grounded in conversation, correct type (fact/event/opinion), complete content
- **4** = grounded and correct type, but slightly incomplete or minor wording issue
- **3** = grounded but missing key detail OR minor type mismatch (e.g., fact labeled event)
- **2** = partially grounded — some correct element but distorted or merged with unrelated info
- **1** = barely grounded — conclusion stretches far beyond what conversation states
- **0** = not supported by conversation at all (hallucination)

**TASK 2 — Aggregate metrics:**
- Precision = count(score >= 3) / total extracted
- Recall = count(gold memories with a matching extracted) / total gold memories
- Type F1 = F1 score on fact/event/opinion classification vs gold type labels
- Hallucination rate = count(score == 0) / total extracted

**TASK 3 — Flag:**
- List any gold memory that was not extracted at all (missed recall).
- List any extracted memory that contradicts the conversation (hard hallucination).

**OUTPUT FORMAT:** JSON

```json
{
  "per_memory": [{ "index": N, "score": N, "reason": "..." }],
  "precision": 0.0, "recall": 0.0, "type_f1": 0.0,
  "hallucination_rate": 0.0,
  "missed_memories": ["..."], "hard_hallucinations": ["..."]
}
```

### B. PS2 Conflict Resolution Judge Prompt

**SYSTEM:** You are evaluating conflict resolution decisions in a long-term memory system.
Each decision involves a new candidate memory and a set of semantically similar existing memories.

**INPUT:**
- NEW MEMORY: `{new_memory_unit}`
- EXISTING CANDIDATES: `{existing_memories_list}`
- SYSTEM DECISION: operation=`{ADD|UPDATE|DELETE|NONE}`
- RESULTING CONTENT: `{updated_memory_content}` (null if ADD or NONE with no changes)

**TASK 1 — Operation correctness (0–5):**
- **5** = ideal operation given the semantic relationship between new and existing memories
- **4** = correct operation with minor suboptimality (e.g., updated content slightly verbose)
- **3** = defensible operation but a better choice clearly exists
- **2** = operation causes information degradation or unnecessary duplication
- **1** = wrong operation — clear semantic mismatch
- **0** = critically wrong (e.g., DELETE of an unrelated memory)

**TASK 2 — Information preservation (0–5, only for UPDATE or NONE operations):**
- **5** = updated content fully preserves all information from both old and new memory
- **4** = very minor information loss — negligible for practical use
- **3** = some information lost but core facts remain
- **2** = significant information from either old or new memory is missing
- **0** = critical information lost; the merge is worse than either original

**TASK 3 — False DELETE flag:**
Was any DELETE decision applied to a memory that contains information NOT covered by the surviving memory or the new memory?

Answer: `{ "false_delete": true/false, "lost_information": "..." }`

**TASK 4 — Confidence assessment:**
Were the confidence scores on the resulting memories reasonable?
Flag if confidence on a merged memory significantly deviates from either source.

**OUTPUT FORMAT:** JSON

```json
{
  "operation_score": N, "preservation_score": N,
  "false_delete": { "detected": bool, "lost_information": "..." },
  "confidence_ok": bool, "overall_notes": "..."
}
```

### C. Retrieval Quality Judge Prompt

**SYSTEM:** You are evaluating the retrieval quality of a semantic memory system.

**INPUT:**
- USER QUERY: `{user_message}`
- RETRIEVED MEMORIES (top-K): `{retrieved_memory_list}`
- GROUND TRUTH RELEVANT MEMORIES: `{gold_relevant_set}`
- FINAL AI RESPONSE: `{ai_response}`

**TASK 1 — Context Precision (per retrieved memory):**
For each retrieved memory, is it genuinely useful for answering the user query?
Score: 1 (relevant) or 0 (not relevant). Precision = sum / K

**TASK 2 — Context Recall:**
Of the gold relevant memories, how many were retrieved?
Recall = count(gold found in retrieved) / total gold relevant

**TASK 3 — Faithfulness:**
For each factual claim in the AI response, is it supported by:
(a) the retrieved memories, or (b) the current conversation turn?
Flag any claim not traceable to either source.
Faithfulness = count(supported claims) / total claims

**TASK 4 — Answer Relevance:**
Does the response directly and completely address the user query?
Score 0–5: 5 = fully addresses, 0 = completely off-topic.

**TASK 5 — Memory Utilisation:**
Of the retrieved memories, how many does the response actually reference or reason from?
Utilisation rate = count(used memories) / count(retrieved memories)

**OUTPUT FORMAT:** JSON

```json
{
  "context_precision": 0.0, "context_recall": 0.0, "faithfulness": 0.0,
  "answer_relevance": N, "memory_utilisation": 0.0,
  "unsupported_claims": ["..."], "unused_retrieved_memories": [N, N]
}
```

### D. Core Memory Update Judge Prompt

**SYSTEM:** You are evaluating how accurately a system updates a persistent user profile.

**INPUT:**
- RECENT CONVERSATION WINDOW: `{recent_messages}`
- PERSONA BEFORE: `{old_persona_content}`
- HUMAN PROFILE BEFORE: `{old_human_content}`
- PERSONA AFTER: `{new_persona_content}`
- HUMAN PROFILE AFTER: `{new_human_content}`

**TASK 1 — Update Relevance (0–5):**
Did the update incorporate genuinely new information that was present in the conversation and was not already captured in the profile?
- **5** = all important new information captured, no spurious additions
- **3** = some important information captured but notable omissions
- **1** = update added mostly trivial or irrelevant details
- **0** = update ignored all new information

**TASK 2 — Profile Completeness (0–5):**
Is the resulting profile complete relative to what a good assistant would need to know about this user based on the full conversation history?

**TASK 3 — Profile Drift (critical flag):**
Did any update CHANGE a fact that was previously correct?
List any factual distortions or contradictions introduced by the update.
`"drift_detected": true/false, "distortions": [{ "field": "...", "before": "...", "after": "..." }]`

**TASK 4 — Omission Rate:**
List facts explicitly stated in the conversation that were NOT captured in the updated profile.

**OUTPUT FORMAT:** JSON

```json
{
  "update_relevance": N, "completeness": N,
  "drift": { "detected": bool, "distortions": [...] },
  "omissions": ["..."]
}
```

### E. Rolling Summary Judge Prompt

**SYSTEM:** You are evaluating the quality of a rolling conversation summary.
The summary is produced recursively — it compresses older messages to free context window space.

**INPUT:**
- SOURCE MESSAGES: `{raw_message_window}`
- PREVIOUS SUMMARY: `{prior_summary}` (may be empty for first compression)
- NEW SUMMARY: `{new_summary}`

**TASK 1 — Factual Consistency (0–5):**
Does the new summary contain any facts that contradict the source messages or the previous summary?
- **5** = fully consistent, no contradictions
- **3** = minor imprecision but no clear contradiction
- **0** = clear factual contradiction present
List contradictions if any.

**TASK 2 — Relevance / Information Density (0–5):**
Does the summary capture the most important information from the source window?
Is filler (small talk, acknowledgments, redundant exchanges) appropriately excluded?
- **5** = all important facts preserved, filler excluded
- **3** = important facts mostly preserved with some unnecessary content
- **1** = critical information lost or summary dominated by filler

**TASK 3 — Coherence (0–5):**
Is the summary logically organized and easy to read as a standalone document?
A future LLM receiving only this summary should understand the user context clearly.

**TASK 4 — Information Density Ratio:**
Count distinct factual claims in source messages vs in new summary.
Density ratio = facts_in_summary / facts_in_source
(Higher is better up to ~0.8; near 1.0 means no compression happened)

**OUTPUT FORMAT:** JSON

```json
{
  "factual_consistency": N, "relevance": N, "coherence": N,
  "density_ratio": 0.0, "contradictions": ["..."], "missed_facts": ["..."]
}
```

### F. End-to-End Response Judge Prompt

**SYSTEM:** You are evaluating an AI assistant response in a memory-augmented chat system.
The assistant has access to long-term memories injected into its system prompt.

**INPUT:**
- USER MESSAGE: `{user_message}`
- INJECTED MEMORIES (what the assistant could use):
  - Core Memory: `{core_memory_string}`
  - Semantic Memories: `{semantic_memories_list}`
  - Rolling Summary: `{rolling_summary}`
- ASSISTANT RESPONSE: `{ai_response}`

**TASK 1 — Memory Grounding Score (0–5):**
Does the response appropriately use the injected memories to personalize the answer?
- **5** = response clearly leverages relevant memories where applicable
- **3** = some memory usage but obvious relevant memories were ignored
- **0** = response completely ignores all injected memories despite clear relevance

**TASK 2 — Persona Consistency (0–5):**
Is the response consistent with the `persona_content` defined in the active memory block?
Does the assistant maintain the defined role, tone, and expertise?

**TASK 3 — Temporal Accuracy (0–5, only when event-type memories exist):**
For event-type memories with timestamps, does the response correctly handle temporal references ("last week", "recently", "before X")?

**TASK 4 — Hallucination in Response (0–1 flag):**
Does the response assert any specific fact about the user that is NOT supported by the injected memories or the current conversation turn?
List hallucinated claims.

**TASK 5 — Answer Relevance (0–5):**
Does the response directly and helpfully address the user message?

**OUTPUT FORMAT:** JSON

```json
{
  "grounding": N, "persona_consistency": N, "temporal_accuracy": N,
  "hallucination_detected": bool, "hallucinated_claims": ["..."],
  "answer_relevance": N
}
```
