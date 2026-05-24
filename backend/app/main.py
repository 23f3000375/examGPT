"""
ExamGPT — FastAPI Application Entry Point

Run with:
    uvicorn app.main:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import api_router
from app.core.config import settings

# ── Application ───────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Adaptive test-generation engine powered by AI.",
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ──────────────────────────────────────────
app.include_router(api_router)


# ── Root Health-Check ─────────────────────────────────────────
@app.get("/")
def health_check():
    """Simple liveness probe."""
    return {
        "status": "success",
        "message": "The ExamGPT Engine is running flawlessly!",
    }