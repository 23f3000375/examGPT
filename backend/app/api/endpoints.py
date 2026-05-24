"""
ExamGPT — API Endpoints

Three routes that connect the AI Factory and SQLAlchemy ORM to the web:

  POST /api/generate-question  — Generate & persist an AI-validated MCQ
  POST /api/submit-answer      — Record a user's answer and grade it
  GET  /api/weakest-topic/{id} — Identify the user's weakest sub-topic
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
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
from app.services.ai_factory import generate_validated_question

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
    """Call the AI Factory to generate a batch of 10 MCQs,
    persist them in the database, and return the new records."""

    # 1. Run the Generator loop
    results = await generate_validated_question(
        topic=body.topic,
        sub_topic=body.sub_topic,
        difficulty=body.difficulty,
    )

    db_questions = []
    
    # 2. Build and persist ORM objects
    for res in results:
        db_question = Question(
            topic=body.topic,
            sub_topic=body.sub_topic,
            difficulty=body.difficulty,
            question_text=res["question_text"],
            options=res["options"],
            correct_answer=res["correct_answer"],
            explanation=res["explanation"],
        )
        db.add(db_question)
        db_questions.append((db_question, res))
        
    db.commit()

    output = []
    for db_q, res in db_questions:
        db.refresh(db_q)
        output.append({
            "id": db_q.id,
            "topic": db_q.topic,
            "sub_topic": db_q.sub_topic,
            "difficulty": db_q.difficulty,
            "question_text": db_q.question_text,
            "options": db_q.options,
            "correct_answer": db_q.correct_answer,
            "explanation": db_q.explanation,
            "ai_metadata": {
                "attempts": res["attempts"],
                "is_valid": res["is_valid"],
            },
        })

    logger.info("Persisted %d questions for [%s / %s / %s]", len(output), body.topic, body.sub_topic, body.difficulty)

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
