"""LoCoMo dataset loader for evaluation framework."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from evaluation.core.config import DatasetConfig
from evaluation.datasets.base import BaseDataset


@dataclass
class LocomoMessage:
    """A single message in a LoCoMo conversation."""
    role: str
    content: str


@dataclass
class LocomoQuestion:
    """A multiple choice question from LoCoMo."""
    question: str
    choices: List[str]
    answer_idx: int
    reasoning_type: str


@dataclass
class LocomoSession:
    """A complete LoCoMo conversation session."""
    session_id: str
    messages: List[LocomoMessage]
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

    def _load_from_local(self, base_path: Path) -> List[dict]:
        """Load dataset from local file."""
        dataset_path = base_path / "locomo10.json"
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

            # Messages from all sessions in the conversation
            messages = []
            for key, value in conversation.items():
                if key.startswith("session_") and not key.endswith(("_date_time", "_summary", "_observation")):
                    if isinstance(value, list):
                        for msg in value:
                            speaker = msg.get("speaker", "")
                            text = msg.get("text", "")

                            # Map speaker to role
                            if speaker == speaker_a:
                                role = "user"
                                character = speaker_a
                            elif speaker == speaker_b:
                                role = "assistant"
                                character = speaker_b
                            else:
                                role = "unknown"
                                character = speaker

                            # Prepend character tag to content
                            content_with_tag = f"[{character}]: {text}"
                            messages.append(LocomoMessage(role=role, content=content_with_tag))

            # Build questions from QA annotations
            questions = []
            qa_list = sample.get("qa", [])
            for qa in qa_list:
                question = LocomoQuestion(
                    question=qa.get("question", ""),
                    choices=[],
                    answer_idx=-1,
                    reasoning_type=qa.get("category", "")
                )
                questions.append(question)

            sessions.append(
                LocomoSession(
                    session_id=sample_id,
                    messages=messages,
                    questions=questions
                )
            )

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