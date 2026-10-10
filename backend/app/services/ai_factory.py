"""Reliable, grounded question generation with provider failover and parallel chunks."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, AsyncGenerator

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.schemas import Difficulty, QuestionBatch, QuestionChunk
from app.services.web_search_fallback import fallback_generate_questions

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


def get_system_prompt(chunk_size: int, chunk_index: int, topic: str, sub_topic: str, difficulty: str, has_study_text: bool) -> str:
    if has_study_text:
        return f"""You are ExamGPT's assessment author. Create exam-quality MCQs
using ONLY the STUDY TEXT supplied by the user. Do not use background knowledge,
make up facts, or ask about material absent from that text.

Return exactly {chunk_size} distinct multiple-choice questions with a mix of easy, medium, and hard difficulty.
Infer the subject from the study text; do not require or invent external topic metadata.
Each question must have four plausible options A through D, exactly one correct
option, a self-contained explanation, and a source_reference copied verbatim from
the study text. The source_reference must be the smallest direct snippet that proves
the answer. Do not include markdown, commentary, citations outside source_reference,
or fields not present in the supplied JSON Schema.

For this batch, use IDs starting from q{(chunk_index * chunk_size) + 1} to q{(chunk_index + 1) * chunk_size}.

Example shape:
{{"questions":[{{"id":"q1","type":"multiple_choice","difficulty":"medium","question":"Clear question purely on context?","options":[{{"id":"A","text":"Distractor 1"}},{{"id":"B","text":"Correct Answer"}},{{"id":"C","text":"Distractor 2"}},{{"id":"D","text":"Distractor 3"}}],"correct_option_id":"B","explanation":"B follows from the text.","source_reference":"Exact supporting sentence."}}]}}"""
    else:
        return f"""You are ExamGPT's assessment author. Create exam-quality MCQs
about the topic '{topic}' and specifically the sub-topic '{sub_topic}'.

Return exactly {chunk_size} distinct multiple-choice questions at a '{difficulty}' difficulty level.
Each question must have four plausible options A through D, exactly one correct
option, a self-contained explanation, and a source_reference (can just be "General Knowledge").
Do not include markdown, commentary, citations outside source_reference,
or fields not present in the supplied JSON Schema.

For this batch, use IDs starting from q{(chunk_index * chunk_size) + 1} to q{(chunk_index + 1) * chunk_size}."""


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _grounding_errors(chunk: QuestionChunk, study_text: str) -> list[str]:
    """Apply deterministic checks that API-level JSON schema cannot express."""
    context = _normalise(study_text).casefold()
    errors: list[str] = []
    
    if len(chunk.questions) != settings.CHUNK_SIZE:
        errors.append(f"chunk must contain exactly {settings.CHUNK_SIZE} questions")
        
    for question in chunk.questions:
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
    if settings.GEMINI_API_KEY:
        providers.append(Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", settings.GEMINI_API_KEY, settings.GEMINI_MODEL, {}))
    if settings.GROQ_API_KEY:
        providers.append(Provider("groq", "https://api.groq.com/openai/v1/chat/completions", settings.GROQ_API_KEY, settings.GROQ_MODEL, {}))
    return providers


async def _call_provider(provider: Provider, messages: list[dict[str, str]]) -> QuestionChunk:
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": 0,
        "stream": False,
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "examgpt_question_chunk", "strict": True, "schema": QuestionChunk.model_json_schema()},
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
        return QuestionChunk.model_validate_json(_extract_json(content))
    except (ValidationError, json.JSONDecodeError, GenerationError) as exc:
        raise GenerationError(f"{provider.name} response failed schema validation: {exc}") from exc


async def _fallback_providers(chunk_index: int, study_text: str, topic: str, sub_topic: str, difficulty: str, providers: list[Provider]) -> tuple[QuestionChunk, str]:
    """Try providers sequentially. Return the first valid chunk."""
    has_study_text = bool(study_text and study_text.strip())
    system_prompt = get_system_prompt(settings.CHUNK_SIZE, chunk_index, topic, sub_topic, difficulty, has_study_text)
    
    if has_study_text:
        user_prompt = f"STUDY TEXT START\n{study_text.strip()}\nSTUDY TEXT END"
    else:
        user_prompt = f"Topic: {topic}\nSub-topic: {sub_topic}\nDifficulty: {difficulty}"
        
    messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]

    for provider in providers:
        try:
            chunk = await _call_provider(provider, messages)
            if has_study_text:
                errors = _grounding_errors(chunk, study_text)
            else:
                errors = [] # No strict grounding check if no text provided
            
            if not errors:
                return chunk, provider.name
            else:
                logger.warning("Provider %s generated chunk with errors: %s", provider.name, "; ".join(errors))
        except Exception as exc:
            logger.warning("Provider %s failed: %s", provider.name, exc)

    raise GenerationError(f"All LLM providers failed for chunk {chunk_index}.")


async def generate_validated_questions_stream(topic: str, sub_topic: str, difficulty: str, study_text: str = "") -> AsyncGenerator[dict[str, Any], None]:
    """Generate 10 questions in 2 chunks, trying providers sequentially. Yields progress dicts."""
    providers = _providers()
    
    total_chunks = 2
    all_questions = []

    for chunk_index in range(total_chunks):
        yield {"status": "generating", "chunk": chunk_index + 1, "total_chunks": total_chunks, "provider": "searching..."}
        
        try:
            if not providers:
                raise GenerationError("No LLM providers configured.")
                
            chunk, provider_name = await _fallback_providers(chunk_index, study_text, topic, sub_topic, difficulty, providers)
            all_questions.extend(chunk.questions)
            yield {"status": "progress", "chunk": chunk_index + 1, "total_chunks": total_chunks, "provider": provider_name}
            
        except GenerationError as exc:
            logger.warning("Chunk %d failed via LLMs, falling back to web search: %s", chunk_index + 1, exc)
            yield {"status": "progress", "chunk": chunk_index + 1, "total_chunks": total_chunks, "provider": "web search fallback"}
            
            # Fallback
            try:
                chunk = await fallback_generate_questions(study_text, topic, sub_topic, difficulty, chunk_index, settings.CHUNK_SIZE)
            except Exception as e:
                raise GenerationError(str(e)) from e
                
            all_questions.extend(chunk.questions)

    # Final validation as a full batch (ensures distinct questions etc.)
    batch = QuestionBatch(questions=all_questions)
    yield {"status": "complete", "batch": batch.model_dump(), "provider": "mixed"}


async def generate_validated_questions(*, topic: str, sub_topic: str, difficulty: str, study_text: str = "") -> tuple[QuestionBatch, str]:
    """Backward compatible synchronous-style wrapper that consumes the stream and returns the final batch."""
    final_batch = None
    final_provider = "mixed"
    
    async for event in generate_validated_questions_stream(topic, sub_topic, difficulty, study_text):
        if event["status"] == "complete":
            final_batch = QuestionBatch(**event["batch"])
            final_provider = event["provider"]
            
    if not final_batch:
        raise GenerationError("Generation stream ended without completing.")
        
    return final_batch, final_provider
