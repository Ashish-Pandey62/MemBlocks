"""LoCoMo dataset loader for evaluation framework."""

from dataclasses import dataclass
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
    """Dataset loader for the LoCoMo multiple choice dataset.

    Loads and parses the locomo-mc10 dataset from HuggingFace.
    """

    def __init__(self, config: DatasetConfig) -> None:
        """Initialize the LoCoMo dataset with configuration."""
        super().__init__(config)

    def load(self) -> List[LocomoSession]:
        """Load the LoCoMo dataset from HuggingFace.

        Returns:
            List of LocomoSession objects.

        Raises:
            ImportError: If the datasets library is not installed.
        """
        # Import here to allow graceful handling if not installed
        from datasets import load_dataset

        # Load the dataset from HuggingFace
        hf_dataset = load_dataset("bdsaglam/locomo-mc10", split="test")

        # Group items by haystack_session
        session_groups: dict = {}
        for item in hf_dataset:
            session_id = item["haystack_session"]
            if session_id not in session_groups:
                session_groups[session_id] = []
            session_groups[session_id].append(item)

        # Convert to LocomoSession objects
        sessions = []
        for session_id, items in session_groups.items():
            messages = []
            questions = []

            for item in items:
                # Build message from conversation
                role = "user" if item["role"] == "user" else "assistant"
                character = item.get("character", "")
                content = f"[{character}]: {item['message']}"

                messages.append(LocomoMessage(role=role, content=content))

                # Build question
                choices = []
                for i in range(1, 11):
                    choice_key = f"choice_{i}"
                    if choice_key in item:
                        choices.append(item[choice_key])

                question = LocomoQuestion(
                    question=item.get("question", ""),
                    choices=choices,
                    answer_idx=item.get("answer_idx", 0),
                    reasoning_type=item.get("type", "")
                )
                questions.append(question)

            sessions.append(
                LocomoSession(
                    session_id=session_id,
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