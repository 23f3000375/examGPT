"""Generate grounded multiple-choice questions without an LLM provider."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from html import unescape
from typing import Iterable
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

from app.schemas.schemas import GeneratedQuestion, QuestionChunk, QuestionOption

logger = logging.getLogger(__name__)

_WORD = re.compile(r"\b[A-Za-z][A-Za-z'-]{3,}\b")
_STOP_WORDS = {
    "about", "after", "again", "also", "among", "because", "before",
    "being", "between", "could", "during", "first", "found", "from",
    "have", "into", "itself", "known", "more", "most", "other", "over",
    "same", "should", "some", "such", "than", "that", "their", "there",
    "these", "they", "this", "those", "through", "under", "using", "very",
    "were", "which", "while", "where", "with", "would",
}
_GENERIC_DISTRACTORS = (
    "The source does not provide this term",
    "All of the listed terms",
    "None of the listed terms",
)


@dataclass(frozen=True)
class Source:
    text: str
    reference: str
    label: str


def extract_keywords(study_text: str, max_words: int = 5) -> str:
    """Extract frequent non-stopwords to form a short web-search query."""
    words = [
        word.casefold()
        for word in _WORD.findall(study_text)
        if word.casefold() not in _STOP_WORDS
    ]
    frequencies: dict[str, int] = {}
    for word in words:
        frequencies[word] = frequencies.get(word, 0) + 1
    ranked = sorted(frequencies, key=lambda word: (-frequencies[word], word))
    return " ".join(ranked[:max_words]) or "study material"


def _sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+|[\r\n]+", text):
        sentence = sentence.strip(" \t\r\n-•")
        start = 0
        while start < len(sentence):
            end = min(start + 400, len(sentence))
            if end < len(sentence):
                boundary = sentence.rfind(" ", start, end)
                if boundary > start:
                    end = boundary
            segment = sentence[start:end].strip()
            if len(segment) >= 25:
                sentences.append(segment)
            start = end
            while start < len(sentence) and sentence[start].isspace():
                start += 1
    return sentences


def _unwrap_search_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com"):
        target = parse_qs(parsed.query).get("uddg", [])
        if target:
            return target[0]
    return url


async def _search_web(query: str) -> list[Source]:
    """Get short, attributed search snippets; search is best-effort."""
    try:
        async with httpx.AsyncClient(
            timeout=6.0,
            follow_redirects=True,
            headers={"User-Agent": "ExamGPT/1.0 (study question search)"},
        ) as client:
            response = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Web search unavailable; using pasted text only: %s", exc)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results: list[Source] = []
    for link in soup.select("a.result__a"):
        snippet_node = link.find_next(class_="result__snippet")
        if snippet_node is None:
            continue
        title = " ".join(link.get_text(" ", strip=True).split())
        snippet = " ".join(snippet_node.get_text(" ", strip=True).split())
        url = _unwrap_search_url(str(link.get("href", "")))
        if title and snippet and url.startswith(("http://", "https://")):
            results.append(
                Source(
                    text=unescape(snippet),
                    reference=f"Web search: {url}",
                    label=f'web result "{title[:100]}"',
                )
            )
        if len(results) == 6:
            break
    return results


def _terms(texts: Iterable[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for text in texts:
        for match in _WORD.finditer(text):
            term = match.group(0).strip("'-")
            key = term.casefold()
            if key in _STOP_WORDS or len(key) < 4 or len(key) > 80 or key in seen:
                continue
            seen.add(key)
            terms.append(term)
    return terms


def _masked_candidates(sources: list[Source]) -> list[tuple[Source, str, str]]:
    candidates: list[tuple[Source, str, str]] = []
    seen: set[str] = set()
    for source in sources:
        for sentence in _sentences(source.text):
            words = [
                match
                for match in _WORD.finditer(sentence)
                if match.group(0).casefold() not in _STOP_WORDS
                and len(match.group(0)) <= 80
            ]
            # A single long passage may be the only input, so offer distinct
            # completion questions for its content terms rather than requiring
            # ten separate sentences.
            words.sort(key=lambda match: (-len(match.group(0)), match.start()))
            for target in words:
                term = target.group(0)
                key = f"{sentence.casefold()}|{term.casefold()}"
                if key in seen:
                    continue
                seen.add(key)
                masked = sentence[: target.start()] + "_____" + sentence[target.end() :]
                citation = (
                    Source(sentence, sentence, source.label)
                    if source.label == "study text"
                    else source
                )
                candidates.append((citation, masked, term))
                if len(candidates) >= 50:
                    return candidates
    return candidates


def _make_options(answer: str, term_pool: list[str], index: int) -> list[QuestionOption]:
    distractors: list[str] = []
    for offset in range(len(term_pool)):
        candidate = term_pool[(index + offset) % len(term_pool)]
        if candidate.casefold() != answer.casefold() and candidate.casefold() not in {
            value.casefold() for value in distractors
        }:
            distractors.append(candidate)
        if len(distractors) == 3:
            break
    for generic in _GENERIC_DISTRACTORS:
        if len(distractors) == 3:
            break
        distractors.append(generic)

    choices = [answer, *distractors]
    correct_index = index % 4
    choices[0], choices[correct_index] = choices[correct_index], choices[0]
    return [
        QuestionOption(id=option_id, text=text)
        for option_id, text in zip(("A", "B", "C", "D"), choices)
    ]


async def fallback_generate_questions(
    study_text: str,
    topic: str,
    sub_topic: str,
    difficulty: str,
    chunk_index: int,
    chunk_size: int,
) -> QuestionChunk:
    """Create text-completion MCQs from study text, enriched with web snippets."""
    if len(study_text.strip()) < 80:
        raise ValueError("Paste at least 80 characters of study text to use offline generation.")

    search_sources = await _search_web(f"{extract_keywords(study_text)} {topic} {sub_topic}")
    text_source = Source(
        text=study_text.strip(),
        reference="Study text supplied by the learner",
        label="study text",
    )
    sources = [text_source, *search_sources]
    text_candidates = _masked_candidates([text_source])
    web_candidates = _masked_candidates(search_sources)
    candidates: list[tuple[Source, str, str]] = []
    for index in range(max(len(text_candidates), len(web_candidates))):
        if index < len(text_candidates):
            candidates.append(text_candidates[index])
        if index < len(web_candidates):
            candidates.append(web_candidates[index])
        if len(candidates) >= 50:
            break
    required_candidates = (chunk_index + 1) * chunk_size
    if len(candidates) < required_candidates:
        raise ValueError(
            f"Only {len(candidates)} distinct statements were found; "
            f"{required_candidates} are needed. Paste a longer or more detailed "
            "passage and try again."
        )

    term_pool = _terms(source.text for source in sources)
    selected = candidates[chunk_index * chunk_size : (chunk_index + 1) * chunk_size]

    questions: list[GeneratedQuestion] = []
    for offset, (source, masked, answer) in enumerate(selected):
        index = chunk_index * chunk_size + offset
        source_name = "the study text" if source.label == "study text" else source.label
        questions.append(
            GeneratedQuestion(
                id=f"q{index + 1}",
                type="multiple_choice",
                difficulty=difficulty,
                question=(
                    f'Which term completes this statement from {source_name}? "{masked}"'
                ),
                options=_make_options(answer, term_pool, index),
                correct_option_id=("A", "B", "C", "D")[index % 4],
                explanation=(
                    f'The {source_name} states: "{masked.replace("_____", answer)}" '
                    f"The missing term is {answer}."
                ),
                source_reference=source.reference,
            )
        )

    return QuestionChunk(questions=questions)
