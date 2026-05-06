# Current Evaluation Flow Analysis

This document provides a highly detailed, step-by-step breakdown of the execution flow in the current `evaluation/` directory. It explains exactly which components are used, what they do, and how they interact with each other and the `memblocks` SDK.

---

## High-Level Execution Pipeline

1. **Configuration Parsing:** `eval.py`
2. **Dataset Loading:** `LocomoDataset` (`evaluation/datasets/locomo.py`)
3. **Execution Runner:** `LocomoRunner` (`evaluation/runners/locomo.py`)
    - **Step 3.1:** Session Ingestion
    - **Step 3.2:** Context Retrieval
    - **Step 3.3:** QA Generation
    - **Step 3.4:** Judging
4. **Result Reporting:** `Reporter` (`evaluation/metrics/reporter.py`)

---

## Detailed Component Breakdown

### 1. Configuration & Entry Point (`eval.py`)
- **Execution:** The script is triggered via the CLI (e.g., `python evaluation/eval.py --config configs/quicktest_config.yaml`).
- **Flow:**
  - The `main()` function parses the `--config` argument.
  - It calls `run_evaluation(config_path)`.
  - `load_config()` (from `evaluation.core.config`) parses the YAML file into an `EvalConfig` Pydantic model.
  - For each `run` defined in the config:
    - `create_output_dir()` generates a timestamped folder in `evaluation/runs/`.
    - It instantiates a dataset class (`LocomoDataset`).
    - It instantiates a runner class (`LocomoRunner`).
    - It calls `runner.run(output_dir)`.

### 2. Dataset Loading (`LocomoDataset` in `evaluation/datasets/locomo.py`)
- **Component:** `LocomoDataset` (inherits from `BaseDataset`)
- **Flow:**
  - `load()` method is called by the runner.
  - It attempts to load `locomo10.json` from local directories. If not found, it falls back to downloading it via `urllib.request` from the `snap-research/locomo` GitHub repository.
  - It parses the raw JSON into three nested Pydantic-like dataclasses:
    - `LocomoMessage`: Contains `role` ("user" or "assistant") and `content` (prepended with `[SpeakerA]: ` or `[SpeakerB]: `).
    - `LocomoQuestion`: Contains the `question`, expected `answer`, and `category`.
    - `LocomoSession`: Wraps a `session_id`, a list of `LocomoMessage`s, and a list of `LocomoQuestion`s.
  - It truncates the number of sessions and questions based on `max_sessions` and `max_questions_per_session` from the config.
  - Returns a `List[LocomoSession]`.

### 3. The Runner Loop (`LocomoRunner` in `evaluation/runners/locomo.py`)
- **Component:** `LocomoRunner` (inherits from `BaseRunner`)
- **Flow:**
  - `run(output_dir)` sets up the asyncio event loop and executes `await self._run_async(output_dir)`.
  - `_run_async()` loads the dataset (`self.dataset.load()`) and a text-based QA prompt template (`QA_TEMPLATE_PATH`).
  - It iterates over every `LocomoSession`.

#### 3.1 Session Ingestion (How `memblocks` is called)
- **Goal:** Feed the conversation messages into the memory system.
- **Component Flow & SDK Misuse:**
  - The runner attempts to create a unique block ID: `block_id = f"locomo-session-{session.session_id}"`.
  - **SDK Call 1 (Broken):** `block_config = MemBlocksConfig(block_id=block_id)`
    - *What it does:* Tries to instantiate the library configuration.
    - *Why it fails:* `MemBlocksConfig` has no `block_id` argument in the real SDK.
  - **SDK Call 2:** `block_client = MemBlocksClient(config=block_config)`
    - *What it does:* Instantiates the main entry-point client.
  - The runner iterates over `session.messages`:
    - **SDK Call 3 (Broken):** `block_client.session.add(message)`
      - *What it does:* Attempts to add a single message to a session.
      - *Why it fails:* The `MemBlocksClient` object does not expose a `.session` property. Sessions must be created via `await client.create_session(...)`. Furthermore, `Session.add()` expects `user_msg` and `ai_response` as separate kwargs, not a single `message` object. It also requires an `await`.
    - **SDK Call 4 (Broken):** `block_client.session.flush()`
      - *Why it fails:* The method does not exist.
  - **The Fallback Mechanism:**
    - Because the above code inevitably throws an `AttributeError` or `TypeError`, the entire block is caught by a broad `except Exception as e:` block.
    - The runner sets `session_results["ingestion_status"] = f"failed: {str(e)}"`.
    - It then abandons the `memblocks` SDK entirely and instantiates an internal dummy class: `block_client = _InMemoryBlockClient()`.
    - It iterates over the messages again and adds them to `_InMemoryBlockClient.session.messages` (a simple python `list`).

#### 3.2 Context Retrieval
- **Goal:** For each question in the session, retrieve context from memory.
- **Component Flow & SDK Misuse:**
  - Iterates over `session.questions`.
  - Calls `self._retrieve_context(question.question, block_client, strategy)` for three strategies: `"semantic"`, `"core"`, and `"hybrid"`.
  - **SDK Call 5 (Broken):** Inside `_retrieve_context`, it calls `block_client.retrieve(question_text, strategy=strategy, top_k=5)`.
    - *Why it fails (if it were real):* `MemBlocksClient` does not have a `.retrieve()` method. This method belongs to the `Block` class (`await block.retrieve(...)`). Also, `strategy` and `top_k` are not valid arguments for the generic retrieve method.
    - *What actually happens:* Because ingestion failed, `block_client` is actually the `_InMemoryBlockClient`. The dummy `_InMemoryBlockClient.retrieve()` method ignores the `strategy` string and performs a rudimentary naive-keyword overlap search against the python list of messages. It returns a formatted string: `[<strategy> retrieval — top 5 ...] \n <context>`.

#### 3.3 QA Generation (Bypassing `memblocks` entirely)
- **Goal:** Ask the LLM to answer the question using the retrieved context.
- **Component Flow:**
  - It loops over the three generated contexts (semantic, core, hybrid).
  - `self._fill_qa_prompt(template, context, question)` injects the retrieved context and question text into the raw string template.
  - `self._call_llm(prompt)` is invoked.
    - *What it does:* Instead of using `memblocks.llm` providers, it explicitly hardcodes an HTTP POST request via the `requests` library to an Ollama server running at `http://localhost:11435/api/generate`.
    - It returns the raw string answer from the LLM. If the request fails, it catches the exception and returns the string `"LLM call failed: <error>"`.

#### 3.4 Judging & Metrics (`LocomoEvaluator` in `evaluation/metrics/locomo.py`)
- **Goal:** Score the actual answer against the expected answer.
- **Component Flow:**
  - For the `"hybrid"` strategy *only*, it instantiates `LocomoEvaluator(self.config)`.
  - It calls `evaluator.evaluate_with_judge(question.question, question.answer, answer)`.
  - `evaluate_with_judge()`:
    - Constructs a strict grading prompt telling the LLM to output exactly "Pass" or "Fail".
    - Makes *another* raw HTTP POST request to `http://localhost:11435/api/generate`.
    - If the LLM returns a string containing "pass", it returns `"Pass"`. Otherwise, `"Fail"`.
    - If the `judge_model` is missing or the network request fails, it falls back to `evaluate_answer()`.
  - `evaluate_answer()` (Fallback Judge):
    - Simply checks if the expected answer string exists inside the actual answer string (`if expected in actual or actual in expected`).
  - **Fake Telemetry:** The runner hardcodes a fake `eval_result["tokens"]` dictionary containing dummy integer values (e.g., 50 prompt tokens, 20 completion tokens) for `StageTokenUsage` metrics, completely ignoring actual telemetry from `memblocks` or the local LLM.

#### 3.5 Aggregation
- **Component Flow:**
  - `self._aggregate_metrics(results)` calculates total passes, total questions, overall accuracy, and groups accuracy by the question's `category`.
  - It sums up the hardcoded dummy tokens.

### 4. Reporting (`Reporter` in `evaluation/metrics/reporter.py`)
- **Component:** `Reporter`
- **Flow:**
  - `runner.run()` passes the giant aggregated `results` dictionary to the `Reporter`.
  - `save_json()`: Dumps the raw dictionary to `report.json`.
  - `save_csv()`: Flattens the nested evaluations and writes `session_id`, `question`, `expected_answer`, `actual_answer` (hybrid only), `score`, and `category` to `report.csv`.
  - `save_run_info()`: Dumps the `RunConfig` (causing a type mismatch hint warning, as it expects `EvalConfig`) to `run_info.json`.
  - `print_summary()`: Outputs the formatted metrics (Accuracy, By Reasoning Type, Token Usage) to the terminal console.

---

## Summary of the Flow's Fatal Flaw

Because the `LocomoRunner` was seemingly written against a non-existent or heavily outdated version of the `memblocks` SDK (attempting to use a synchronous client, `.session` attributes, and `block_client.retrieve`), the `try/except` block on **Line 114 of `locomo.py`** traps the inevitable crash. 

The script then silently shifts all operations to `_InMemoryBlockClient`, meaning **the entire evaluation suite is evaluating a dummy python list keyword search, completely bypassing the actual `memblocks` vector DB, core memory updates, recursive summaries, and retrieval pipelines.**