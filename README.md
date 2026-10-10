# ExamGPT

ExamGPT generates ten multiple-choice practice questions from a selected topic
and, when needed, study text supplied by the learner.

## Reliable generation pipeline

- Gemini is tried first, followed by Groq. Configure provider keys in
  `backend/.env`; never put keys in frontend code or commit them.
- Each request uses JSON Schema structured outputs with `strict: true`, then
  Pydantic validates exactly ten distinct questions, A–D options, answer keys,
  and unexpected fields.
- If both providers are unavailable, the UI lets the learner paste 80–20,000
  characters of material. A no-LLM fallback creates text-completion questions
  from the supplied passage and tries DuckDuckGo search for additional
  attributed snippets; generation still works from the passage if search is
  unavailable.
- Provider-generated questions are checked against the pasted text when it is
  supplied. The local fallback cites the exact passage sentence or web result
  URL used for each question.

## Setup

1. Start PostgreSQL: `docker compose up -d`.
2. Copy `backend/.env.example` to `backend/.env`. Set `GEMINI_API_KEY` and/or
   `GROQ_API_KEY` to enable those providers. The text fallback does not require
   an API key.
3. In `backend`, run `pip install -r requirements.txt`, then `python init_db.py`
   and `uvicorn app.main:app --reload`.
4. In `frontend`, run `npm install` and `npm run dev`.

Gemini defaults to `gemini-2.5-flash`, and Groq defaults to
`openai/gpt-oss-20b`; override either model in `.env` if needed.

## Render and Vercel deployment

- In Render's backend service environment, set `GEMINI_API_KEY` and
  `GROQ_API_KEY`, then redeploy the backend.
- In Vercel's frontend project settings, set `VITE_API_URL` to the Render
  backend's public URL (for example, `https://your-service.onrender.com`) and
  redeploy the frontend. This value is embedded when Vite builds; without it,
  production must not fall back to a visitor's `localhost`.
- Set the backend's `APP_URL` to the deployed frontend origin if using a
  custom domain. Vercel preview and production domains are also allowed by CORS.
