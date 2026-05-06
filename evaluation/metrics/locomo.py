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
        """Evaluate using an LLM judge (stub for future implementation).
        
        This would call the configured judge_model with strict instructions
        to return ONLY 'Pass' or 'Fail' without Chain of Thought.
        
        Returns:
            "Pass" or "Fail" from the judge.
        """
        # Stub: use the simple matching for now
        return self.evaluate_answer(question, expected_answer, actual_answer)