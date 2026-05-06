"""Locomo evaluation metrics with token tracking."""

from typing import Dict, Optional
from enum import Enum

from pydantic import BaseModel, Field

from evaluation.core.config import RunnerConfig


class PipelineStage(str, Enum):
    """Pipeline stages for token tracking."""
    RETRIEVAL = "retrieval"
    EXTRACTION = "extraction"
    CONFLICT_MANAGEMENT = "conflict_management"
    SUMMARY_GENERATION = "summary_generation"
    CORE_MEMORY_GENERATION = "core_memory_generation"
    QA = "qa"
    JUDGE = "judge"


class StageTokenUsage(BaseModel):
    """Token usage for a single pipeline stage."""
    stage: PipelineStage = Field(..., description="Pipeline stage name")
    prompt_tokens: int = Field(default=0, description="Number of prompt tokens")
    completion_tokens: int = Field(default=0, description="Number of completion tokens")
    total_tokens: int = Field(default=0, description="Total tokens (prompt + completion)")


class TokenTracker:
    """Tracks token usage per pipeline stage."""
    
    def __init__(self):
        self._usage: Dict[PipelineStage, StageTokenUsage] = {}
    
    def add_usage(self, stage: PipelineStage, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        """Add token usage for a stage."""
        total = prompt_tokens + completion_tokens
        if stage in self._usage:
            existing = self._usage[stage]
            self._usage[stage] = StageTokenUsage(
                stage=stage,
                prompt_tokens=existing.prompt_tokens + prompt_tokens,
                completion_tokens=existing.completion_tokens + completion_tokens,
                total_tokens=existing.total_tokens + total,
            )
        else:
            self._usage[stage] = StageTokenUsage(
                stage=stage,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total,
            )
    
    def get_usage(self, stage: PipelineStage) -> Optional[StageTokenUsage]:
        """Get token usage for a stage."""
        return self._usage.get(stage)
    
    def get_all_usage(self) -> Dict[PipelineStage, StageTokenUsage]:
        """Get all token usage."""
        return self._usage.copy()
    
    def total_tokens(self) -> int:
        """Get total tokens across all stages."""
        return sum(u.total_tokens for u in self._usage.values())


class LocomoEvaluator:
    """Locomo evaluation metric - LLM-as-a-Judge for pass/fail accuracy."""
    
    def __init__(self, config: Optional[RunnerConfig] = None):
        """Initialize with optional RunnerConfig."""
        self._judge_model = config.judge_model if config else None
        self._token_tracker = TokenTracker()
    
    @property
    def judge_model(self) -> Optional[str]:
        """Get the configured judge model."""
        return self._judge_model
    
    @property
    def token_tracker(self) -> TokenTracker:
        """Get the token tracker."""
        return self._token_tracker
    
    def evaluate_answer(
        self,
        question: str,
        expected_answer: str,
        actual_answer: str,
    ) -> str:
        """Evaluate if actual_answer matches expected_answer.
        
        This is a stub implementation that performs exact/contains matching.
        In production, this would call an LLM judge with strict prompting.
        
        Returns:
            "Pass" if the answer is factually correct, "Fail" otherwise.
        """
        expected = str(expected_answer or "").strip().lower()
        actual = str(actual_answer or "").strip().lower()
        if not expected or not actual:
            return "Fail"

        # Strict matching: pass if actual contains expected or matches exactly.
        if expected in actual or actual in expected:
            return "Pass"
        return "Fail"
    
    def evaluate_with_judge(
        self,
        question: str,
        expected_answer: str,
        actual_answer: str,
    ) -> str:
        """Evaluate using the configured Ollama LLM judge.

        Falls back to string matching when no real judge model is configured.

        Returns:
            "Pass" or "Fail" from the judge.
        """
        stub_names = {None, "stub-judge", "default", ""}
        if self._judge_model in stub_names:
            return self.evaluate_answer(question, expected_answer, actual_answer)

        import requests

        judge_prompt = (
            f"You are a strict evaluator.\n\n"
            f"Question: {question}\n"
            f"Expected Answer: {expected_answer}\n"
            f"Actual Answer: {actual_answer}\n\n"
            f"Rules:\n"
            f"- Respond Pass ONLY if the actual answer contains the key facts from the expected answer.\n"
            f"- Respond Fail if the actual answer says 'I cannot answer', 'I don't know', refuses to answer, gives wrong facts, or omits the key information.\n"
            f"Respond with ONLY the single word Pass or Fail — nothing else."
        )
        try:
            response = requests.post(
                "http://localhost:11435/api/generate",
                json={
                    "model": self._judge_model,
                    "prompt": judge_prompt,
                    "stream": False,
                    "options": {"temperature": 0},
                },
                timeout=120,
            )
            text = response.json().get("response", "").strip()
            if "pass" in text.lower():
                return "Pass"
            return "Fail"
        except Exception:
            return self.evaluate_answer(question, expected_answer, actual_answer)