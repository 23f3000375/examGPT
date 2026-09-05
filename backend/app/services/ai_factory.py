"""Reliable, grounded question generation with provider failover.

One schema-constrained LLM request plus local semantic validation is faster and
more predictable than the former generator/critic loop.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.schemas import Difficulty, QuestionBatch

logger = logging.getLogger(__name__)


class GenerationError(RuntimeError):
    """No configured provider returned a valid, grounded question batch."""


@dataclass(frozen=True)
class Provider:
    name: str
    url: str
    api_key: str
    model: str
    headers: dict[str, str]


SYSTEM_PROMPT = """You are ExamGPT's assessment author. Create exam-quality MCQs
using ONLY the STUDY TEXT supplied by the user. Do not use background knowledge,
make up facts, or ask about material absent from that text.

Return exactly 10 distinct multiple-choice questions: three easy, four medium,
and three hard. Infer the subject from the study text; do not require or invent
external topic metadata.
Each question must have four plausible options A through D, exactly one correct
option, a self-contained explanation, and a source_reference copied verbatim from
the study text. The source_reference must be the smallest direct snippet that proves
the answer. Do not include markdown, commentary, citations outside source_reference,
or fields not present in the supplied JSON Schema.

Difficulty guide: easy = direct recall or a single explicit inference; medium =
connect two or more statements in the text; hard = careful comparison, application,
or multi-step reasoning strictly justified by the text.

Example shape (values are illustrative only):
{"questions":[{"id":"q1","type":"multiple_choice","difficulty":"medium","question":"Clear question based purely on context?","options":[{"id":"A","text":"Distractor 1"},{"id":"B","text":"Correct Answer"},{"id":"C","text":"Distractor 2"},{"id":"D","text":"Distractor 3"}],"correct_option_id":"B","explanation":"B follows from the supplied text.","source_reference":"Exact supporting sentence from the study text."}]}"""


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _grounding_errors(batch: QuestionBatch, study_text: str) -> list[str]:
    """Apply deterministic checks that API-level JSON schema cannot express."""
    context = _normalise(study_text).casefold()
    errors: list[str] = []
    difficulties = [question.difficulty for question in batch.questions]
    if difficulties.count("easy") != 3 or difficulties.count("medium") != 4 or difficulties.count("hard") != 3:
        errors.append("batch must contain three easy, four medium, and three hard questions")
    for question in batch.questions:
        reference = _normalise(question.source_reference).casefold()
        if reference not in context:
            errors.append(f"{question.id}: source_reference is not a verbatim study-text snippet")
        correct_text = next(option.text for option in question.options if option.id == question.correct_option_id)
        explanation = _normalise(question.explanation).casefold()
        if (_normalise(correct_text).casefold() not in explanation and question.correct_option_id.casefold() not in explanation):
            errors.append(f"{question.id}: explanation does not identify the selected answer")
    return errors


def _extract_json(content: Any) -> str:
    """Recover JSON from an imperfect provider response before validation."""
    if isinstance(content, (dict, list)):
        return json.dumps(content)
    if not isinstance(content, str) or not content.strip():
        raise GenerationError("provider returned an empty response")
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise GenerationError("provider response did not contain a JSON object")
    return candidate[start : end + 1]


def _providers() -> list[Provider]:
    providers: list[Provider] = []
    if settings.GROQ_API_KEY:
        providers.append(Provider("groq", "https://api.groq.com/openai/v1/chat/completions", settings.GROQ_API_KEY, settings.GROQ_MODEL, {}))
    if settings.OPENROUTER_API_KEY:
        providers.append(Provider("openrouter", "https://openrouter.ai/api/v1/chat/completions", settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL, {"HTTP-Referer": settings.APP_URL, "X-Title": settings.APP_NAME}))
    return providers


async def _call_provider(provider: Provider, messages: list[dict[str, str]]) -> QuestionBatch:
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": 0,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "examgpt_question_batch", "strict": True, "schema": QuestionBatch.model_json_schema()},
        },
    }
    headers = {"Authorization": f"Bearer {provider.api_key}", "Content-Type": "application/json", **provider.headers}
    async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
        response = await client.post(provider.url, json=payload, headers=headers)
        response.raise_for_status()
    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise GenerationError(f"{provider.name} returned an unexpected response envelope") from exc
    try:
        return QuestionBatch.model_validate_json(_extract_json(content))
    except (ValidationError, json.JSONDecodeError, GenerationError) as exc:
        raise GenerationError(f"{provider.name} response failed schema validation: {exc}") from exc


async def generate_validated_questions(*, study_text: str) -> tuple[QuestionBatch, str]:
    """Return a schema-valid, source-grounded batch, trying each configured provider."""
    providers = _providers()
    if not providers:
        raise GenerationError("No LLM provider is configured. Set GROQ_API_KEY or OPENROUTER_API_KEY.")

    user_prompt = f"STUDY TEXT START\n{study_text.strip()}\nSTUDY TEXT END"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}]
    failures: list[str] = []
    for provider in providers:
        try:
            batch = await _call_provider(provider, messages)
            grounding_errors = _grounding_errors(batch, study_text)
            if grounding_errors:
                raise GenerationError("; ".join(grounding_errors))
            logger.info("Generated grounded batch through %s", provider.name)
            return batch, provider.name
        except (httpx.HTTPError, GenerationError) as exc:
            logger.warning("Question generation via %s failed: %s", provider.name, exc)
            failures.append(f"{provider.name}: {exc}")
    raise GenerationError("All LLM providers failed validation. " + " | ".join(failures))
