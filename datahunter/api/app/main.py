from __future__ import annotations

from fastapi import FastAPI

from api.app.jobs import router as jobs_router

app = FastAPI(
    title="datahunter API",
    version="0.1.0",
    description="Job management API for dispatching and monitoring scraping tasks.",
)

app.include_router(jobs_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Liveness probe — returns ok when the API process is running."""
    return {"status": "ok"}
