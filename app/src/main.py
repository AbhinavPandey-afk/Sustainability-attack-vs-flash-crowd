"""CASCADE Phase 2 — FastAPI test application.

Implements the cheap/medium/expensive endpoint classes (CLAUDE.md section
6), application-level Prometheus metrics exposition (section 7), and a
minimal session/conversion simulation. This app is intentionally NOT yet
deployed to Kubernetes, has no HPA, and is not scraped by a running
Prometheus server — those are later phases.
"""
from fastapi import FastAPI
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from .config import settings
from .endpoints import cheap, expensive, medium
from .middleware import MetricsMiddleware, SessionTrackingMiddleware
from .models import HealthResponse
from .sessions import SessionTracker

app = FastAPI(title="CASCADE Test Application", version="0.2.0")

_session_tracker = SessionTracker(ttl_seconds=settings.SESSION_TTL_SECONDS)

app.add_middleware(MetricsMiddleware)
app.add_middleware(SessionTrackingMiddleware, tracker=_session_tracker)

app.include_router(cheap.router)
app.include_router(medium.router)
app.include_router(expensive.router)


@app.get("/healthz", response_model=HealthResponse)
async def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/metrics")
async def metrics() -> Response:
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
