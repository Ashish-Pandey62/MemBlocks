"""LoCoMo dataset loader for evaluation framework."""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from evaluation.core.config import DatasetConfig
from evaluation.datasets.base import BaseDataset


def _parse_locomo_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Parse a LoCoMo date-time string like '1:56 pm on 8 May, 2023'."""
    if not raw:
        return None
    try:
        normalized = raw.strip().replace(" am ", " AM ").replace(" pm ", " PM ")
        return datetime.strptime(normalized, "%I:%M %p on %d %B, %Y")
    except ValueError:
        return None


@dataclass
class LocomoMessage:
    """A single message in a LoCoMo conversation."""
    role: str
    content: str


@dataclass
class LocomoChatSession:
    """One session_X block within a LoCoMo conversation, with its own timestamp."""
    session_key: str          # e.g. "session_1"
    date_time: Optional[datetime]
    messages: List[LocomoMessage]


@dataclass
class LocomoQuestion:
    """A question from LoCoMo.

    In the original dataset, questions are mostly open-ended generation tasks,
    not multiple-choice (unless they have distractors explicitly provided).
    """
    question: str
    answer: str
    category: int
    adversarial_answer: Optional[str] = None


@dataclass
class LocomoSession:
    """A complete LoCoMo conversation (one sample), containing multiple chat sessions."""
    session_id: str
    sub_sessions: List[LocomoChatSession]
    questions: List[LocomoQuestion]


class LocomoDataset(BaseDataset):
    """Dataset loader for the LoCoMo dataset.

    Loads the original LoCoMo dataset from local JSON file or GitHub.
    Expected JSON format from snap-research/locomo.
    """

    def __init__(self, config: DatasetConfig) -> None:
        """Initialize the LoCoMo dataset with configuration."""
        super().__init__(config)

    def _load_from_github(self) -> List[dict]:
        """Load dataset from GitHub raw URL."""
        import urllib.request
        url = "https://raw.githubusercontent.com/snap-research/locomo/main/data/locomo10.json"
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data

    def _load_from_local(self, dataset_path: Path) -> List[dict]:
        """Load dataset from local file."""
        if not dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found at {dataset_path}")

        with open(dataset_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data

    def load(self) -> List[LocomoSession]:
        """Load the LoCoMo dataset.

        Returns:
            List of LocomoSession objects.

        Raises:
            FileNotFoundError: If dataset cannot be loaded.
        """
        # Try loading from local paths first
        possible_paths = [
            Path.cwd() / "evaluation" / "data" / "locomo10.json",
            Path.cwd() / "data" / "locomo10.json",
            Path.cwd() / "locomo10.json",
        ]

        data = None
        for path in possible_paths:
            try:
                data = self._load_from_local(path)
                break
            except FileNotFoundError:
                continue

        # Fall back to GitHub
        if data is None:
            try:
                data = self._load_from_github()
            except Exception as e:
                raise FileNotFoundError(
                    f"Could not load LoCoMo dataset. "
                    f"Please download from https://github.com/snap-research/locomo/blob/main/data/locomo10.json "
                    f"and place in evaluation/data/ or data/ directory. Error: {e}"
                )

        sessions = []
        for sample in data:
            sample_id = sample.get("sample_id", "")
            conversation = sample.get("conversation", {})
            speaker_a = conversation.get("speaker_a", "SpeakerA")
            speaker_b = conversation.get("speaker_b", "SpeakerB")

            # Build one LocomoChatSession per session_X key in the conversation.
            # session_X_date_time entries without a matching session_X list are skipped.
            sub_sessions: List[LocomoChatSession] = []
            for key, value in conversation.items():
                if not (key.startswith("session_") and not key.endswith(("_date_time", "_summary", "_observation"))):
                    continue
                if not isinstance(value, list):
                    continue

                session_dt = _parse_locomo_datetime(conversation.get(f"{key}_date_time"))
                messages: List[LocomoMessage] = []
                for msg in value:
                    speaker = msg.get("speaker", "")
                    text = msg.get("text", "")

                    if speaker == speaker_a:
                        role = "user"
                        character = speaker_a
                    elif speaker == speaker_b:
                        role = "assistant"
                        character = speaker_b
                    else:
                        role = "unknown"
                        character = speaker

                    messages.append(LocomoMessage(role=role, content=f"[{character}]: {text}"))

                if messages:
                    sub_sessions.append(LocomoChatSession(
                        session_key=key,
                        date_time=session_dt,
                        messages=messages,
                    ))

            # Build questions from QA annotations
            questions: List[LocomoQuestion] = []
            for qa in sample.get("qa", []):
                questions.append(LocomoQuestion(
                    question=qa.get("question", ""),
                    answer=qa.get("answer", ""),
                    category=qa.get("category", 0),
                    adversarial_answer=qa.get("adversarial_answer"),
                ))

            sessions.append(LocomoSession(
                session_id=sample_id,
                sub_sessions=sub_sessions,
                questions=questions,
            ))

        # Apply subsetting limits if configured
        if self.config.max_sessions is not None:
            sessions = sessions[:self.config.max_sessions]

        for session in sessions:
            if self.config.max_questions_per_session is not None:
                session.questions = session.questions[:self.config.max_questions_per_session]

        return sessions


# Register the dataset
from evaluation.core.registry import get_registry
get_registry().register_dataset("locomo", LocomoDataset)
