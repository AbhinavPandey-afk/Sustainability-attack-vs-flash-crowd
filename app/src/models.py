"""Pydantic request/response schemas for the CASCADE test application."""
from pydantic import BaseModel, Field

from .config import settings


class HomeResponse(BaseModel):
    message: str
    status: str


class SearchResult(BaseModel):
    id: int
    title: str
    snippet: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    cached: bool


class ReportRequest(BaseModel):
    complexity: int | None = Field(
        default=None,
        ge=settings.REPORT_MIN_COMPLEXITY,
        le=settings.REPORT_MAX_COMPLEXITY,
        description="Workload complexity; higher values do proportionally more CPU work.",
    )


class ReportResponse(BaseModel):
    complexity: int
    iterations: int
    duration_seconds: float
    checksum: str


class CheckoutResponse(BaseModel):
    status: str
    converted: bool


class HealthResponse(BaseModel):
    status: str
