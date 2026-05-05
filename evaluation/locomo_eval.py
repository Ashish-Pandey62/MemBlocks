"""Run MemBlocks end-to-end evaluation on normalized LOCOMO-style data.

The script expects each input record to be normalized to, or convertible into:

{
  "conversation_id": "...",
  "messages": [{"role": "user", "content": "..."}, ...],
  "qa": [{"question": "...", "answer": "...", "reasoning_type": "single-hop"}, ...]
}

It replays each conversation through the real MemBlocks runtime, asks each QA
question with retrieved memory context, and writes question-level + aggregate
reports.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import string
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from memblocks import MemBlocksClient, MemBlocksConfig


ANSWER_SYSTEM_PROMPT = """
You are answering questions about a previous long conversation.
Use only the provided memory context and conversation context.
If the answer is not supported, say "I don't know".
Keep the answer short and direct.
""".strip()

NO_MEMORY_SYSTEM_PROMPT = """
You are answering a question, but you have no access to the previous conversation.
If the answer requires previous conversation context, say "I don't know".
Keep the answer short and direct.
""".strip()

ORACLE_SYSTEM_PROMPT = """
You are answering questions about a previous long conversation.
Use only the provided gold evidence snippets.
If the answer is not supported, say "I don't know".
Keep the answer short and direct.
""".strip()

ARTICLES_RE = re.compile(r"\b(a|an|the)\b", flags=re.IGNORECASE)


# ---------------------------------------------------------------------------
# Text scoring
# ---------------------------------------------------------------------------


def normalize_text(text: str | None) -> str:
    """Lowercase, remove punctuation/articles, and collapse whitespace."""
    text = (text or "").lower()
    text = text.translate(str.maketrans("", "", string.punctuation))
    text = ARTICLES_RE.sub(" ", text)
    return " ".join(text.split())


def token_f1(prediction: str, gold: str) -> float:
    pred_tokens = normalize_text(prediction).split()
    gold_tokens = normalize_text(gold).split()

    if not pred_tokens and not gold_tokens:
        return 1.0
    if not pred_tokens or not gold_tokens:
        return 0.0

    pred_counts = Counter(pred_tokens)
    overlap = 0
    for token in gold_tokens:
        if pred_counts[token] > 0:
            overlap += 1
            pred_counts[token] -= 1

    if overlap == 0:
        return 0.0

    precision = overlap / len(pred_tokens)
    recall = overlap / len(gold_tokens)
    return (2 * precision * recall) / (precision + recall)


def automatic_score(prediction: str, gold: str) -> dict[str, Any]:
    pred_norm = normalize_text(prediction)
    gold_norm = normalize_text(gold)

    exact = bool(gold_norm) and pred_norm == gold_norm
    contains = bool(gold_norm) and gold_norm in pred_norm
    f1 = token_f1(prediction, gold)

    if exact:
        score = 1.0
    elif contains:
        score = 0.8
    else:
        score = f1

    return {
        "score": float(score),
        "exact_match": bool(exact),
        "contains_gold": bool(contains),
        "token_f1": float(f1),
    }


def text_contains_any(corpus: str, needles: Iterable[str]) -> bool:
    corpus_norm = normalize_text(corpus)
    for needle in needles:
        needle_norm = normalize_text(needle)
        if needle_norm and needle_norm in corpus_norm:
            return True
    return False


# ---------------------------------------------------------------------------
# LOCOMO normalization
# ---------------------------------------------------------------------------


def first_present(mapping: dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return default


def normalize_role(raw_role: Any, user_speaker: str | None = None) -> str:
    role = str(raw_role or "").strip().lower()
    user_speaker_norm = user_speaker.strip().lower() if user_speaker else None

    if user_speaker_norm and role == user_speaker_norm:
        return "user"

    if role in {"user", "human", "person", "speaker1", "speaker_1", "user1", "participant1", "p1"}:
        return "user"
    if role in {"assistant", "ai", "agent", "bot", "speaker2", "speaker_2", "user2", "participant2", "p2"}:
        return "assistant"

    # Conservative default: unknown primary speaker becomes user.
    return "user"


def normalize_message(raw_message: Any, user_speaker: str | None = None) -> dict[str, Any] | None:
    if isinstance(raw_message, str):
        content = raw_message.strip()
        return {"role": "user", "content": content} if content else None

    if not isinstance(raw_message, dict):
        return None

    content = first_present(
        raw_message,
        ["content", "text", "utterance", "message", "value", "body"],
        "",
    )
    content = str(content or "").strip()
    if not content:
        return None

    raw_role = first_present(
        raw_message,
        ["role", "speaker", "sender", "from", "author", "participant"],
        "user",
    )
    role = normalize_role(raw_role, user_speaker=user_speaker)

    message = {"role": role, "content": content}
    timestamp = first_present(raw_message, ["timestamp", "time", "created_at", "date"])
    if timestamp is not None:
        message["timestamp"] = str(timestamp)
    return message


def normalize_reasoning_type(raw_type: Any) -> str:
    if raw_type is None:
        return "other"

    if isinstance(raw_type, list):
        labels = " ".join(str(item).lower() for item in raw_type)
    else:
        labels = str(raw_type).lower()

    if any(term in labels for term in ["temporal", "time", "chronological", "before", "after"]):
        return "temporal"
    if any(term in labels for term in ["multi", "2-hop", "two-hop", "compositional"]):
        return "multi-hop"
    if any(term in labels for term in ["preference", "like", "dislike", "habit"]):
        return "preference"
    if any(term in labels for term in ["attribute", "profile", "fact", "persona", "identity"]):
        return "attribute"
    if any(term in labels for term in ["single", "1-hop", "one-hop"]):
        return "single-hop"
    if any(term in labels for term in ["open", "knowledge"]):
        return "open-domain"
    return "other"


def normalize_qa(raw_qa: dict[str, Any], index: int, conversation_id: str) -> dict[str, Any] | None:
    question = first_present(raw_qa, ["question", "query", "q", "input"])
    answer = first_present(raw_qa, ["answer", "gold_answer", "target", "output", "a"])

    if isinstance(answer, list):
        answer = answer[0] if answer else ""

    question = str(question or "").strip()
    answer = str(answer or "").strip()
    if not question or not answer:
        return None

    raw_type = first_present(
        raw_qa,
        ["reasoning_type", "type", "category", "question_type", "qa_type", "label"],
    )
    evidence = first_present(raw_qa, ["evidence", "evidences", "supporting_facts", "support"], [])
    if isinstance(evidence, str):
        evidence = [evidence]
    if not isinstance(evidence, list):
        evidence = []

    return {
        "question_id": str(first_present(raw_qa, ["question_id", "qid", "id"], f"{conversation_id}_q{index:04d}")),
        "question": question,
        "answer": answer,
        "reasoning_type": normalize_reasoning_type(raw_type),
        "evidence": [str(item) for item in evidence if str(item).strip()],
        "metadata": {k: v for k, v in raw_qa.items() if k not in {"question", "answer"}},
    }


def normalize_record(raw_record: dict[str, Any], index: int, user_speaker: str | None = None) -> dict[str, Any] | None:
    conversation_id = str(
        first_present(
            raw_record,
            ["conversation_id", "conversationId", "dialogue_id", "dialog_id", "id"],
            f"locomo_{index:05d}",
        )
    )

    raw_messages = first_present(
        raw_record,
        ["messages", "conversation", "dialogue", "dialog", "turns", "transcript"],
        [],
    )
    if isinstance(raw_messages, dict):
        raw_messages = first_present(raw_messages, ["messages", "turns", "dialogue"], [])

    messages = []
    if isinstance(raw_messages, list):
        for raw_message in raw_messages:
            message = normalize_message(raw_message, user_speaker=user_speaker)
            if message:
                messages.append(message)

    raw_qas = first_present(raw_record, ["qa", "qas", "questions", "question_answers"], [])
    if isinstance(raw_qas, dict):
        raw_qas = list(raw_qas.values())

    qas = []
    if isinstance(raw_qas, list):
        for qa_index, raw_qa in enumerate(raw_qas, start=1):
            if isinstance(raw_qa, dict):
                qa = normalize_qa(raw_qa, qa_index, conversation_id)
                if qa:
                    qas.append(qa)

    if not messages or not qas:
        return None

    return {"conversation_id": conversation_id, "messages": messages, "qa": qas}


def load_json_or_jsonl(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ["records", "data", "conversations", "items"]:
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    raise ValueError(f"Unsupported dataset JSON shape in {path}")


def load_hf_dataset(dataset_name: str, split: str, config_name: str | None = None) -> list[dict[str, Any]]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Install HuggingFace datasets with: uv pip install datasets") from exc

    if config_name:
        dataset = load_dataset(dataset_name, config_name, split=split)
    else:
        dataset = load_dataset(dataset_name, split=split)
    return [dict(row) for row in dataset]


def load_records(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.dataset_path:
        raw_records = load_json_or_jsonl(Path(args.dataset_path))
    elif args.hf_dataset:
        raw_records = load_hf_dataset(args.hf_dataset, args.hf_split, args.hf_config)
    else:
        raise ValueError("Provide either --dataset-path or --hf-dataset")

    normalized = []
    for index, raw_record in enumerate(raw_records, start=1):
        record = normalize_record(raw_record, index, user_speaker=args.user_speaker)
        if record:
            normalized.append(record)

    if args.limit_conversations:
        normalized = normalized[: args.limit_conversations]

    if not normalized:
        raise ValueError("No valid LOCOMO records found after normalization")
    return normalized


# ---------------------------------------------------------------------------
# MemBlocks prompt construction and replay
# ---------------------------------------------------------------------------


def build_memblocks_answer_messages(question: str, retrieval: Any, recursive_summary: str, memory_window: list[dict[str, Any]]) -> list[dict[str, str]]:
    system_parts = [ANSWER_SYSTEM_PROMPT]

    if recursive_summary:
        system_parts.append(f"<Rolling Summary>\n{recursive_summary}\n</Rolling Summary>")

    if retrieval and not retrieval.is_empty():
        system_parts.append(retrieval.to_prompt_string())

    if memory_window:
        formatted_window = "\n".join(
            f"{message.get('role', '').upper()}: {message.get('content', '')}"
            for message in memory_window
        )
        system_parts.append(
            f"<Recent Conversation Window>\n{formatted_window}\n</Recent Conversation Window>"
        )

    return [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": question},
    ]


def build_no_memory_answer_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": NO_MEMORY_SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]


def build_oracle_answer_messages(question: str, evidence: list[str]) -> list[dict[str, str]]:
    evidence_text = "\n".join(f"- {item}" for item in evidence) or "No evidence provided."
    return [
        {
            "role": "system",
            "content": f"{ORACLE_SYSTEM_PROMPT}\n\n<Gold Evidence>\n{evidence_text}\n</Gold Evidence>",
        },
        {"role": "user", "content": question},
    ]


def compact_adjacent_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent same-role messages so replay can form clean turns."""
    compacted: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role") or "user"
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        if compacted and compacted[-1]["role"] == role:
            compacted[-1]["content"] = compacted[-1]["content"] + "\n" + content
        else:
            compacted.append({"role": role, "content": content})
    return compacted


def messages_to_turns(messages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Convert user/assistant messages into Session.add(user_msg, ai_response) turns."""
    compacted = compact_adjacent_messages(messages)
    turns: list[tuple[str, str]] = []
    pending_user: str | None = None

    for message in compacted:
        role = message.get("role")
        content = str(message.get("content") or "").strip()
        if not content:
            continue

        if role == "user":
            if pending_user is not None:
                turns.append((pending_user, ""))
            pending_user = content
        else:
            if pending_user is None:
                pending_user = ""
            turns.append((pending_user, content))
            pending_user = None

    if pending_user is not None:
        turns.append((pending_user, ""))

    return turns


def retrieval_to_text(retrieval: Any, summary: str, window: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    if summary:
        parts.append(summary)
    if retrieval:
        parts.append(retrieval.to_prompt_string())
    if window:
        parts.extend(str(message.get("content", "")) for message in window)
    return "\n".join(parts)


async def replay_conversation(session: Any, messages: list[dict[str, Any]], flush_every: int | None = None) -> None:
    turns = messages_to_turns(messages)
    for turn_index, (user_msg, ai_response) in enumerate(turns, start=1):
        await session.add(user_msg=user_msg, ai_response=ai_response)
        if flush_every and turn_index % flush_every == 0:
            await session.flush()
    await session.flush()


# ---------------------------------------------------------------------------
# Optional judge
# ---------------------------------------------------------------------------


JUDGE_PROMPT_TEMPLATE = """
You are evaluating an answer to a question about a previous conversation.

QUESTION:
{question}

GOLD ANSWER:
{gold_answer}

PREDICTED ANSWER:
{predicted_answer}

GOLD EVIDENCE SNIPPETS:
{evidence}

Return strict JSON with this schema:
{{
  "correct": true/false,
  "partial_credit": 0.0,
  "hallucination_detected": true/false,
  "reason": "short explanation"
}}

Scoring rules:
- 1.0 means semantically correct.
- 0.5 means partially correct but incomplete.
- 0.0 means wrong or unsupported.
- Mark hallucination_detected=true if the prediction asserts a specific fact contradicted by the gold answer/evidence.
""".strip()


async def judge_with_anthropic(question: str, gold_answer: str, predicted_answer: str, evidence: list[str], model: str) -> dict[str, Any]:
    try:
        import anthropic
    except ImportError as exc:
        raise RuntimeError("Install anthropic with: uv pip install anthropic") from exc

    client = anthropic.AsyncAnthropic()
    response = await client.messages.create(
        model=model,
        max_tokens=512,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": JUDGE_PROMPT_TEMPLATE.format(
                    question=question,
                    gold_answer=gold_answer,
                    predicted_answer=predicted_answer,
                    evidence=json.dumps(evidence, ensure_ascii=False),
                ),
            }
        ],
    )
    raw_text = response.content[0].text
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


# ---------------------------------------------------------------------------
# Evaluation loop
# ---------------------------------------------------------------------------


async def answer_question(
    client: MemBlocksClient,
    mode: str,
    question: str,
    evidence: list[str],
    retrieval: Any = None,
    summary: str = "",
    window: list[dict[str, Any]] | None = None,
) -> str:
    if mode == "memblocks":
        messages = build_memblocks_answer_messages(question, retrieval, summary, window or [])
    elif mode == "baseline":
        messages = build_no_memory_answer_messages(question)
    elif mode == "oracle":
        messages = build_oracle_answer_messages(question, evidence)
    else:
        raise ValueError(f"Unknown mode: {mode}")
    return await client.conversation_llm.chat(messages, temperature=0.0)


async def evaluate_record(client: MemBlocksClient, record: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    conversation_id = record["conversation_id"]
    unique_suffix = uuid.uuid4().hex[:8]
    user_id = f"locomo_user_{conversation_id}_{unique_suffix}"

    await client.get_or_create_user(user_id)
    block = await client.create_block(user_id=user_id, name=f"LOCOMO {conversation_id}")
    session = await client.create_session(user_id=user_id, block_id=block.id)

    await replay_conversation(session, record["messages"], flush_every=args.flush_every)

    rows: list[dict[str, Any]] = []
    qas = record["qa"][: args.limit_questions_per_conversation] if args.limit_questions_per_conversation else record["qa"]

    for qa in qas:
        question = qa["question"]
        gold_answer = qa["answer"]
        evidence = qa.get("evidence", [])

        retrieval = await block.retrieve(question)
        summary = await session.get_recursive_summary()
        window = await session.get_memory_window()
        context_text = retrieval_to_text(retrieval, summary, window)

        modes = ["memblocks"]
        if args.run_baseline:
            modes.append("baseline")
        if args.run_oracle:
            modes.append("oracle")

        for mode in modes:
            start = time.perf_counter()
            answer = await answer_question(
                client=client,
                mode=mode,
                question=question,
                evidence=evidence,
                retrieval=retrieval if mode == "memblocks" else None,
                summary=summary if mode == "memblocks" else "",
                window=window if mode == "memblocks" else [],
            )
            latency_ms = int((time.perf_counter() - start) * 1000)

            score_data = automatic_score(answer, gold_answer)
            judge_data: dict[str, Any] | None = None
            final_score = score_data["score"]

            if args.judge and mode in {"memblocks", "oracle"}:
                judge_data = await judge_with_anthropic(
                    question=question,
                    gold_answer=gold_answer,
                    predicted_answer=answer,
                    evidence=evidence,
                    model=args.judge_model,
                )
                partial_credit = float(judge_data.get("partial_credit", 0.0))
                final_score = max(final_score, partial_credit)
                if judge_data.get("hallucination_detected"):
                    final_score = min(final_score, 0.5)

            semantic = retrieval.semantic if retrieval and mode == "memblocks" else []
            row = {
                "conversation_id": conversation_id,
                "question_id": qa["question_id"],
                "reasoning_type": qa["reasoning_type"],
                "mode": mode,
                "question": question,
                "gold_answer": gold_answer,
                "predicted_answer": answer,
                "score": float(final_score),
                "automatic_score": float(score_data["score"]),
                "exact_match": score_data["exact_match"],
                "contains_gold": score_data["contains_gold"],
                "token_f1": score_data["token_f1"],
                "retrieval_contains_gold": text_contains_any(context_text, [gold_answer]) if mode == "memblocks" else False,
                "retrieval_contains_evidence": text_contains_any(context_text, evidence) if mode == "memblocks" and evidence else False,
                "retrieved_semantic_count": len(semantic),
                "retrieved_semantic_contents": [memory.content for memory in semantic],
                "recursive_summary_chars": len(summary or "") if mode == "memblocks" else 0,
                "memory_window_messages": len(window or []) if mode == "memblocks" else 0,
                "latency_ms": latency_ms,
                "judge": judge_data,
            }
            rows.append(row)

    return rows


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def aggregate_rows(rows: list[dict[str, Any]], run_id: str, git_commit: str | None) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_mode[row["mode"]].append(row)

    def summarize(subset: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "count": len(subset),
            "mean_score": mean([row["score"] for row in subset]),
            "exact_match": mean([1.0 if row["exact_match"] else 0.0 for row in subset]),
            "contains_gold": mean([1.0 if row["contains_gold"] else 0.0 for row in subset]),
            "token_f1": mean([row["token_f1"] for row in subset]),
        }

    memblocks_rows = by_mode.get("memblocks", [])
    baseline_rows = by_mode.get("baseline", [])

    by_reasoning_type: dict[str, Any] = {}
    for reasoning_type in sorted({row["reasoning_type"] for row in memblocks_rows}):
        subset = [row for row in memblocks_rows if row["reasoning_type"] == reasoning_type]
        by_reasoning_type[reasoning_type] = summarize(subset)

    memblocks_mean = mean([row["score"] for row in memblocks_rows])
    baseline_mean = mean([row["score"] for row in baseline_rows]) if baseline_rows else None

    report = {
        "run_id": run_id,
        "git_commit": git_commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_size": {
            "conversations": len({row["conversation_id"] for row in rows}),
            "questions": len({(row["conversation_id"], row["question_id"]) for row in rows}),
            "rows": len(rows),
        },
        "overall_by_mode": {mode: summarize(mode_rows) for mode, mode_rows in sorted(by_mode.items())},
        "overall": {
            "memblocks_mean_score": memblocks_mean,
            "baseline_mean_score": baseline_mean,
            "memory_lift": (memblocks_mean - baseline_mean) if baseline_mean is not None else None,
        },
        "by_reasoning_type": by_reasoning_type,
        "retrieval_diagnostics": {
            "retrieval_contains_gold_rate": mean([1.0 if row["retrieval_contains_gold"] else 0.0 for row in memblocks_rows]),
            "retrieval_contains_evidence_rate": mean([1.0 if row["retrieval_contains_evidence"] else 0.0 for row in memblocks_rows]),
            "avg_retrieved_semantic_count": mean([row["retrieved_semantic_count"] for row in memblocks_rows]),
        },
    }
    return report


def get_git_commit() -> str | None:
    try:
        import subprocess

        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


async def run(args: argparse.Namespace) -> None:
    records = load_records(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = args.run_id or f"locomo_eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    rows_path = output_dir / f"{run_id}_rows.jsonl"
    report_path = output_dir / f"{run_id}_report.json"

    config = MemBlocksConfig()
    client = MemBlocksClient(config)

    all_rows: list[dict[str, Any]] = []
    try:
        for record in records:
            print(f"Evaluating conversation {record['conversation_id']} with {len(record['qa'])} questions")
            rows = await evaluate_record(client, record, args)
            all_rows.extend(rows)
            with rows_path.open("a", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

        report = aggregate_rows(all_rows, run_id=run_id, git_commit=get_git_commit())
        with report_path.open("w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, default=str)

        print(f"\nWrote rows: {rows_path}")
        print(f"Wrote report: {report_path}")
        print(json.dumps(report["overall"], indent=2))
    finally:
        await client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate MemBlocks on LOCOMO-style long-conversation QA")
    parser.add_argument("--dataset-path", help="Path to local JSON/JSONL LOCOMO-style dataset")
    parser.add_argument("--hf-dataset", help="Optional HuggingFace dataset name")