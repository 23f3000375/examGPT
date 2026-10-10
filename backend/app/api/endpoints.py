"""
ExamGPT — API Endpoints

Three routes that connect the AI Factory and SQLAlchemy ORM to the web:

  POST /api/generate-question  — Generate & persist an AI-validated MCQ
  POST /api/submit-answer      — Record a user's answer and grade it
  GET  /api/weakest-topic/{id} — Identify the user's weakest sub-topic
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import cast, func, Float as SAFloat
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Question, UserPerformance
from app.schemas.schemas import (
    AnswerResponse,
    AnswerSubmission,
    QuestionRequest,
    WeakestTopicResponse,
)
from app.services.ai_factory import GenerationError, generate_validated_questions, generate_validated_questions_stream
from app.services.pdf_extractor import PdfExtractionError, extract_pdf_text
import json
try:
    from sse_starlette.sse import EventSourceResponse
except ImportError:
    pass

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api", tags=["ExamGPT"])


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POST /api/generate-question
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@api_router.post("/generate-question", status_code=status.HTTP_201_CREATED)
async def generate_question(
    body: QuestionRequest,
    db: Session = Depends(get_db),
):
    """Generate and persist a schema-valid batch grounded in study_text."""

    # 1. Run the Generator loop
    try:
        batch, provider = await generate_validated_questions(study_text=body.study_text)
    except GenerationError as exc:
        logger.error("Question generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Question generation is temporarily unavailable. Please try again shortly.",
        )
    except Exception as exc:
        logger.exception("Unexpected error in AI Factory: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while generating questions. Please try again.",
        )

    return _persist_questions(db, batch, provider)


@api_router.post("/generate-question-stream")
async def generate_question_stream(
    body: QuestionRequest,
    db: Session = Depends(get_db),
):
    """Generate questions with SSE streaming for progress updates."""
    
    async def event_generator():
        try:
            async for event in generate_validated_questions_stream(study_text=body.study_text):
                if event["status"] == "complete":
                    # We have the final batch, persist it
                    from app.schemas.schemas import QuestionBatch
                    batch = QuestionBatch(**event["batch"])
                    persisted_output = _persist_questions(db, batch, event["provider"])
                    event["batch"] = persisted_output
                
                yield {
                    "event": "message",
                    "data": json.dumps(event)
                }
        except GenerationError as exc:
            logger.error("Question stream failed: %s", exc)
            yield {
                "event": "error",
                "data": json.dumps({"detail": str(exc)})
            }
        except Exception as exc:
            logger.exception("Unexpected error in stream: %s", exc)
            yield {
                "event": "error",
                "data": json.dumps({"detail": "An unexpected error occurred."})
            }
            
    return EventSourceResponse(event_generator())


@api_router.post("/generate-question-from-pdf", status_code=status.HTTP_201_CREATED)
async def generate_question_from_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Extract a bounded text PDF in memory and generate grounded questions."""
    try:
        study_text = await extract_pdf_text(file)
        batch, provider = await generate_validated_questions(study_text=study_text)
    except PdfExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except GenerationError as exc:
        logger.error("PDF question generation failed: %s", exc)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Question generation is temporarily unavailable. Please try again shortly.")
    return _persist_questions(db, batch, provider)


def _persist_questions(db: Session, batch, provider: str):
    """Persist a validated batch while retaining the format consumed by the UI."""
    db_questions = []
    
    # 2. Build and persist ORM objects
    for generated in batch.questions:
        options = {option.id: option.text for option in generated.options}
        db_question = Question(
            topic="User-provided material",
            sub_topic=None,
            difficulty=generated.difficulty,
            question_text=generated.question,
            options=options,
            correct_answer=generated.correct_option_id,
            explanation=generated.explanation,
        )
        db.add(db_question)
        db_questions.append((db_question, generated))
        
    db.commit()

    output = []
    for db_q, generated in db_questions:
        db.refresh(db_q)
        output.append({
            "id": db_q.id,
            "topic": db_q.topic,
            "sub_topic": db_q.sub_topic,
            "difficulty": db_q.difficulty,
            "type": generated.type,
            "question": db_q.question_text,
            "options": [option.model_dump() for option in generated.options],
            "correct_option_id": db_q.correct_answer,
            "explanation": db_q.explanation,
            "source_reference": generated.source_reference,
            "ai_metadata": {"provider": provider, "is_valid": True},
        })

    logger.info("Persisted %d grounded questions via %s", len(output), provider)

    return output


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  POST /api/submit-answer
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@api_router.post("/submit-answer", response_model=AnswerResponse)
def submit_answer(
    body: AnswerSubmission,
    db: Session = Depends(get_db),
):
    """Grade a user's answer against the stored correct answer,
    then record the attempt in user_performances."""

    # 1. Fetch the question
    question = db.get(Question, body.question_id)
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Question with id {body.question_id} not found.",
        )

    # 2. Grade
    is_correct = body.chosen_option == question.correct_answer

    # 3. Persist the attempt
    performance = UserPerformance(
        user_id=body.user_id,
        question_id=body.question_id,
        chosen_option=body.chosen_option,
        is_correct=is_correct,
        time_taken_seconds=body.time_taken_seconds,
    )
    db.add(performance)
    db.commit()

    logger.info(
        "Answer recorded: user=%d question=%d correct=%s",
        body.user_id,
        body.question_id,
        is_correct,
    )

    return AnswerResponse(
        is_correct=is_correct,
        correct_answer=question.correct_answer,
        explanation=question.explanation,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  GET /api/weakest-topic/{user_id}
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@api_router.get("/weakest-topic/{user_id}", response_model=WeakestTopicResponse)
def get_weakest_topic(
    user_id: int,
    db: Session = Depends(get_db),
):
    """Identify the user's weakest sub-topic by computing per-sub-topic
    accuracy from the user_performances + questions join.

    SQL equivalent:
        SELECT q.sub_topic,
               AVG(CAST(up.is_correct AS FLOAT)) * 100  AS accuracy,
               COUNT(*)                                   AS total_attempts
        FROM   user_performances up
        JOIN   questions q ON q.id = up.question_id
        WHERE  up.user_id = :user_id
        GROUP  BY q.sub_topic
        ORDER  BY accuracy ASC
        LIMIT  1;
    """

    # ── The raw SQLAlchemy query ──────────────────────────────
    accuracy_expr = func.avg(cast(UserPerformance.is_correct, SAFloat)) * 100
    attempts_expr = func.count()

    row = (
        db.query(
            Question.sub_topic,
            accuracy_expr.label("accuracy"),
            attempts_expr.label("total_attempts"),
        )
        .join(Question, Question.id == UserPerformance.question_id)
        .filter(UserPerformance.user_id == user_id)
        .group_by(Question.sub_topic)
        .order_by(accuracy_expr.asc())
        .first()
    )

    # No data yet for this user
    if row is None:
        return WeakestTopicResponse(
            user_id=user_id,
            weakest_sub_topic=None,
            accuracy=0.0,
            total_attempts=0,
        )

    return WeakestTopicResponse(
        user_id=user_id,
        weakest_sub_topic=row.sub_topic,
        accuracy=round(row.accuracy, 2),
        total_attempts=row.total_attempts,
    )
