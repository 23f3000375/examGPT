# ExamGPT

ExamGPT generates ten multiple-choice practice questions grounded exclusively in
study text supplied by the learner.

## Reliable generation pipeline

- The API requires `study_text` (80–20,000 characters); there is no ungrounded
  topic-only generation path.
- Groq is the primary OpenAI-compatible provider and OpenRouter is attempted if
  Groq fails or returns an invalid response.
- Each request uses JSON Schema structured outputs with `strict: true`, then
  Pydantic validates exactly ten distinct questions, A–D options, answer keys,
  and unexpected fields.
- A local grounding gate rejects batches unless every `source_reference` is a
  verbatim snippet of the submitted study text and each explanation names its
  correct option.

## Setup

1. Start PostgreSQL: `docker compose up -d`.
2. Copy `backend/.env.example` to `backend/.env` and set at least one API key.
3. In `backend`, run `pip install -r requirements.txt`, then `python init_db.py`
   and `uvicorn app.main:app --reload`.
4. In `frontend`, run `npm install` and `npm run dev`.

The Groq model must support strict JSON Schema structured outputs. The default
`openai/gpt-oss-20b` is selected for that capability; override it in `.env` if
your account uses another supported model.
