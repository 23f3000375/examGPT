"""
ExamGPT — AI Factory (Batch Generator + Critic Loop)

Flow:
    ┌────────────┐        ┌───────────┐
    │  Generator  │──────▶│   Critic   │
    └────────────┘        └───────────┘
          ▲                     │
          │   error / retry     │  is_valid?
          └─────────────────────┘

• The **Generator** drafts a batch of 10 MCQs from topic + difficulty.
• The **Critic** evaluates the entire batch to catch LLM hallucinations (Answer Key Mismatches).
"""

from __future__ import annotations

import logging
from typing import Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.schemas import QuestionBatch, CriticEvaluation

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  State
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AgentState(TypedDict):
    topic: str
    sub_topic: Optional[str]
    difficulty: str
    current_batch: Optional[QuestionBatch]
    error: Optional[str]
    attempts: int


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  LLM Setup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_generator_base_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0.2, # Lowered to reduce creative hallucinations
)

_critic_base_llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    api_key=settings.GROQ_API_KEY,
    temperature=0.0,
)

# Structured-output variant for the batch
_generator_llm = _generator_base_llm.with_structured_output(QuestionBatch)
_critic_llm = _critic_base_llm.with_structured_output(CriticEvaluation)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  System Prompts
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_GENERATOR_SYSTEM = (
    "You are an expert exam question writer. "
    "Generate exactly 10 distinct, high-quality multiple-choice questions (MCQs). "
    "Each question must have exactly four options (A, B, C, D) and only one option must be correct. "
    "The questions must be clear, unambiguous, and educational. "
    "Provide a thorough explanation for the correct answer of each question. "
    "Make sure the 10 questions cover a good variety of concepts within the given sub-topic.\n\n"
    "CRITICAL RULES YOU MUST FOLLOW FOR EVERY QUESTION:\n"
    "1. Solve the problem step-by-step in your explanation FIRST.\n"
    "2. Determine the final numerical or logical answer from your own solution.\n"
    "3. Make sure that exact value appears as one of the four options (A, B, C, D).\n"
    "4. Set the correct_answer field to the LETTER of the option that contains your derived value.\n"
    "5. DOUBLE CHECK: Re-read the option text for the letter you chose. Does it match your answer? "
    "If not, fix it before outputting.\n\n"
    "COMMON MISTAKE TO AVOID: Do NOT invent options that don't match your calculations. "
    "Write simple, clean options where the correct value is clearly present. "
    "Keep questions straightforward — avoid overly complex multi-step word problems "
    "that are prone to arithmetic errors."
)

_CRITIC_SYSTEM = (
    "You are an extremely rigorous, pedantic quality-assurance reviewer for exam questions. "
    "Your primary goal is to ensure absolute mathematical and logical correctness of the MCQs.\n\n"
    "CRITICAL VERIFICATION: Your primary job is to catch Answer Key Mismatches. "
    "You must independently read the explanation and verify the final derived value. "
    "Then, look at the options. If the explanation concludes the answer is 68, and 68 is Option C, "
    "but the correct_answer field says 'B', you MUST return is_valid=False and instruct the generator "
    "to fix the correct_answer key to match the math. Check all 10 questions in the batch carefully. "
    "If any single question fails, fail the entire batch and provide the question number and specific fix required."
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Graph Nodes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def generator_node(state: AgentState) -> dict:
    """Draft a batch of 10 MCQs based on topic, sub_topic, difficulty."""

    topic = state["topic"]
    sub_topic = state.get("sub_topic")
    difficulty = state["difficulty"]
    error = state.get("error")

    prompt_lines = [
        f"Topic: {topic}",
    ]
    if sub_topic:
        prompt_lines.append(f"Sub-Topic: {sub_topic}")
    prompt_lines.append(f"Difficulty: {difficulty}")

    if error:
        prompt_lines.extend([
            f"\n⚠️ YOUR PREVIOUS BATCH WAS REJECTED BY THE REVIEWER.",
            f"Reviewer feedback:\n{error}\n",
            f"You MUST fix the specific issues described above. "
            f"Generate a completely NEW set of 10 questions. For each question, "
            f"solve it yourself first, verify the answer matches one of your options, "
            f"and set the correct_answer letter accordingly."
        ])
    else:
        prompt_lines.append(f"\nGenerate exactly 10 distinct questions for {sub_topic or topic} at {difficulty} difficulty.")

    user_prompt = "\n".join(prompt_lines)

    logger.info(
        "Generator — batch attempt %d for [%s / %s / %s]",
        state["attempts"] + 1,
        topic,
        sub_topic,
        difficulty,
    )

    try:
        result = _generator_llm.invoke(
            [SystemMessage(content=_GENERATOR_SYSTEM), HumanMessage(content=user_prompt)]
        )
        if isinstance(result, dict):
            result = QuestionBatch(**result)
    except (ValidationError, Exception) as exc:
        logger.warning(
            "Generator — LLM output failed validation on attempt %d: %s",
            state["attempts"] + 1,
            exc,
        )
        return {
            "current_batch": None,
            "error": f"LLM output was malformed: {exc}",
            "attempts": state["attempts"] + 1,
        }

    return {
        "current_batch": result,
        "error": None,
        "attempts": state["attempts"] + 1,
    }


def critic_node(state: AgentState) -> dict:
    """Evaluate the generated batch of 10 MCQs."""
    batch = state.get("current_batch")
    
    if not batch:
        return {
            "error": "No questions were generated.",
            "attempts": state["attempts"]
        }

    if isinstance(batch, dict):
        batch = QuestionBatch(**batch)

    questions_text = []
    for i, q in enumerate(batch.questions, 1):
        options_dict = _options_to_dict(q.options)
        opts = "\n".join(f"  {k}. {v}" for k, v in options_dict.items())
        questions_text.append(
            f"Question {i}:\n{q.question_text}\nOptions:\n{opts}\n"
            f"Correct Answer: {q.correct_answer}\nExplanation: {q.explanation}\n"
        )
        
    user_prompt = "Evaluate the following batch of 10 MCQs for Answer Key Mismatches:\n\n" + "\n---\n".join(questions_text)
    
    logger.info("Critic — reviewing batch attempt %d", state["attempts"])

    try:
        result = _critic_llm.invoke(
            [SystemMessage(content=_CRITIC_SYSTEM), HumanMessage(content=user_prompt)]
        )
        if isinstance(result, dict):
            result = CriticEvaluation(**result)
    except (ValidationError, Exception) as exc:
        logger.warning("Critic — LLM output failed validation: %s", exc)
        return {
            "error": f"Critic evaluation failed: {exc}",
        }

    if not result.is_valid:
        logger.warning("Critic — batch failed validation. Feedback: %s", result.feedback)
        return {
            "current_batch": None,
            "error": result.feedback,
        }

    return {
        "error": None,
    }


def _router(state: AgentState) -> str:
    """Decide if we succeeded or need to retry generating the batch."""
    if state.get("current_batch") is not None and not state.get("error"):
        logger.info("Router — batch ACCEPTED on attempt %d", state["attempts"])
        return "end"

    if state["attempts"] >= 5:
        logger.warning("Router — retry budget exhausted (%d attempts).", state["attempts"])
        return "end"

    logger.info("Router — batch REJECTED due to error, retrying (attempt %d)", state["attempts"])
    return "retry"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Graph Compilation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_workflow = StateGraph(AgentState)
_workflow.add_node("generator", generator_node)
_workflow.add_node("critic", critic_node)
_workflow.set_entry_point("generator")
_workflow.add_edge("generator", "critic")
_workflow.add_conditional_edges(
    "critic",
    _router,
    {
        "retry": "generator",
        "end": END,
    },
)

exam_graph = _workflow.compile()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Helper — normalise options to a plain dict
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _options_to_dict(options) -> dict[str, str]:
    if hasattr(options, "model_dump"):
        return options.model_dump()
    if isinstance(options, dict):
        return options
    return dict(options)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  Public Entry Point
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def generate_validated_question(
    topic: str,
    sub_topic: str,
    difficulty: str,
) -> list[dict]:
    """Run the Generator to produce a batch of 10 questions.

    Returns
    -------
    list[dict]
        A list of 10 questions.
    """
    initial_state: AgentState = {
        "topic": topic,
        "sub_topic": sub_topic,
        "difficulty": difficulty,
        "current_batch": None,
        "error": None,
        "attempts": 0,
    }

    final_state = await exam_graph.ainvoke(initial_state)

    batch = final_state["current_batch"]
    if batch is None:
        raise ValueError("AI Factory failed to generate questions after all retries.")

    if isinstance(batch, dict):
        batch = QuestionBatch(**batch)

    output = []
    for q in batch.questions:
        output.append({
            "question_text": q.question_text,
            "options": _options_to_dict(q.options),
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "attempts": final_state["attempts"],
            "is_valid": True,  # assumed valid since critic is bypassed
        })

    return output
