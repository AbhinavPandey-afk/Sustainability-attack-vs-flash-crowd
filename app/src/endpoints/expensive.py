"""Expensive endpoint class: deliberately CPU-intensive, deterministic,
local-only computation with a hard bound on maximum work performed.
"""
import hashlib
import time

from fastapi import APIRouter

from ..config import settings
from ..metrics import endpoint_class
from ..models import ReportRequest, ReportResponse

router = APIRouter()


@router.post("/api/generate-report", response_model=ReportResponse)
@endpoint_class("expensive")
async def generate_report(payload: ReportRequest | None = None) -> ReportResponse:
    complexity = (
        payload.complexity
        if payload is not None and payload.complexity is not None
        else settings.REPORT_DEFAULT_COMPLEXITY
    )

    # Hard ceiling regardless of complexity/config, so this endpoint always
    # has a bounded maximum execution time (CLAUDE.md section 6).
    iterations = min(complexity * settings.REPORT_ITERATIONS_PER_COMPLEXITY, settings.REPORT_MAX_ITERATIONS)

    start = time.perf_counter()
    # Deterministic: a fixed seed and a pure function of `iterations` means
    # the same complexity always reproduces the same checksum.
    digest = hashlib.sha256(b"cascade-report-seed")
    for i in range(iterations):
        digest.update(str(i).encode())
    checksum = digest.hexdigest()
    duration = time.perf_counter() - start

    return ReportResponse(
        complexity=complexity,
        iterations=iterations,
        duration_seconds=duration,
        checksum=checksum,
    )
