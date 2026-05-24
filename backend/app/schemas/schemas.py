"""
ExamGPT — Pydantic Data Contracts

Strict schemas used to validate structured output from the LLM,
and request/response models for the API layer.
"""

from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LLM Structured-Output Contracts
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class QuestionOptions(BaseModel):
    A: str
    B: str
    C: str
    D: str

class GeneratedQuestion(BaseModel):
    """Schema for a single MCQ produced by the Generator agent."""

    question_text: str = Field(
        ...,
        description="The full text of the multiple-choice question.",
    )
    options: QuestionOptions = Field(
        ...,
        description="The four options for the multiple-choice question.",
    )
    correct_answer: Literal["A", "B", "C", "D"] = Field(
        ...,
        description="The letter key of the correct option.",
    )
    explanation: str = Field(
        ...,
        description="A clear, concise explanation of why the correct answer is right.",
    )

class QuestionBatch(BaseModel):
    """Schema for a batch of MCQs produced by the Generator agent."""
    questions: list[GeneratedQuestion] = Field(
        ...,
        description="A list of 10 distinct, high-quality multiple-choice questions.",
    )


class CriticEvaluation(BaseModel):
    """Schema for the Critic agent's verdict on a generated question."""

    is_valid: bool = Field(
        ...,
        description=(
            "True if the question is logically sound, unambiguous, "
            "and has exactly one correct answer.  False otherwise."
        ),
    )
    feedback: str = Field(
        ...,
        description=(
            "Actionable feedback explaining what is wrong with the question, "
            "or a short confirmation that it passes all checks."
        ),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  API Request Schemas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class QuestionRequest(BaseModel):
    """POST /api/generate-question request body."""

    topic: str = Field(..., min_length=1, description="Subject area, e.g. 'Python'.")
    sub_topic: str = Field(..., min_length=1, description="Narrower focus, e.g. 'List Comprehensions'.")
    difficulty: str = Field(..., description="One of 'easy', 'medium', or 'hard'.")


class AnswerSubmission(BaseModel):
    """POST /api/submit-answer request body."""

    user_id: int = Field(..., gt=0)
    question_id: int = Field(..., gt=0)
    chosen_option: Literal["A", "B", "C", "D"]
    time_taken_seconds: float = Field(..., ge=0)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  API Response Schemas
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AnswerResponse(BaseModel):
    """POST /api/submit-answer response body."""

    is_correct: bool
    correct_answer: str
    explanation: Optional[str]


class WeakestTopicResponse(BaseModel):
    """GET /api/weakest-topic/{user_id} response body."""

    user_id: int
    weakest_sub_topic: Optional[str] = Field(
        None,
        description="The sub-topic with the lowest accuracy, or null if no data.",
    )
    accuracy: Optional[float] = Field(
        None,
        description="The accuracy percentage (0–100) for the weakest sub-topic.",
    )
    total_attempts: Optional[int] = Field(
        None,
        description="Number of questions attempted in that sub-topic.",
    )
