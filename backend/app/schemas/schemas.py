"""Pydantic contracts for ExamGPT's public API and LLM output."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    """Reject invented fields from an LLM instead of silently ignoring them."""

    model_config = ConfigDict(extra="forbid")


Difficulty = Literal["easy", "medium", "hard"]
OptionId = Literal["A", "B", "C", "D"]


class QuestionOption(StrictModel):
    id: OptionId
    text: str = Field(min_length=1, max_length=500)


class GeneratedQuestion(StrictModel):
    """One grounded MCQ. This is also the JSON Schema sent to providers."""

    id: str = Field(pattern=r"^q(?:[1-9]|10)$")
    type: Literal["multiple_choice"]
    difficulty: Difficulty
    question: str = Field(min_length=8, max_length=1_200)
    options: list[QuestionOption] = Field(min_length=4, max_length=4)
    correct_option_id: OptionId
    explanation: str = Field(min_length=20, max_length=2_000)
    source_reference: str = Field(min_length=8, max_length=700)

    @model_validator(mode="after")
    def options_are_complete_and_answerable(self) -> "GeneratedQuestion":
        option_ids = [option.id for option in self.options]
        if set(option_ids) != {"A", "B", "C", "D"} or len(set(option_ids)) != 4:
            raise ValueError("options must contain A, B, C, and D exactly once")
        if self.correct_option_id not in option_ids:
            raise ValueError("correct_option_id must refer to one of the options")
        return self


class QuestionChunk(StrictModel):
    """A chunk of questions from a single LLM call."""
    questions: list[GeneratedQuestion]

    @model_validator(mode="after")
    def questions_are_distinct(self) -> "QuestionChunk":
        ids = [question.id for question in self.questions]
        prompts = [question.question.casefold().strip() for question in self.questions]
        if len(set(ids)) != len(self.questions):
            raise ValueError("question ids must be unique within chunk")
        if len(set(prompts)) != len(self.questions):
            raise ValueError("questions must be distinct within chunk")
        return self


class QuestionBatch(StrictModel):
    questions: list[GeneratedQuestion] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def questions_are_distinct(self) -> "QuestionBatch":
        ids = [question.id for question in self.questions]
        prompts = [question.question.casefold().strip() for question in self.questions]
        if len(set(ids)) != len(self.questions):
            raise ValueError("question ids must be unique")
        if len(set(prompts)) != len(self.questions):
            raise ValueError("questions must be distinct")
        return self


class QuestionRequest(StrictModel):
    """A question-generation request; study text is needed for local fallback."""

    topic: str = Field(min_length=1, max_length=120)
    sub_topic: str = Field(min_length=1, max_length=120)
    difficulty: Difficulty
    study_text: str = Field(default="", max_length=20_000)

    @model_validator(mode="after")
    def study_text_is_bounded_when_provided(self) -> "QuestionRequest":
        if self.study_text.strip() and len(self.study_text.strip()) < 80:
            raise ValueError("study_text must contain at least 80 non-whitespace characters")
        return self


class AnswerSubmission(StrictModel):
    user_id: int = Field(gt=0)
    question_id: int = Field(gt=0)
    chosen_option: OptionId
    time_taken_seconds: float = Field(ge=0)


class AnswerResponse(StrictModel):
    is_correct: bool
    correct_answer: str
    explanation: Optional[str]


class WeakestTopicResponse(StrictModel):
    user_id: int
    weakest_sub_topic: Optional[str] = None
    accuracy: Optional[float] = None
    total_attempts: Optional[int] = None
