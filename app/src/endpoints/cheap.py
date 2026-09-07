"""Cheap endpoint class: minimal CPU, minimal payload."""
from fastapi import APIRouter, Request

from ..metrics import APP_CONVERSION_TOTAL, endpoint_class
from ..models import CheckoutResponse, HomeResponse

router = APIRouter()


@router.get("/api/home", response_model=HomeResponse)
@endpoint_class("cheap")
async def home() -> HomeResponse:
    return HomeResponse(message="Welcome to the CASCADE test application.", status="ok")


@router.post("/api/checkout", response_model=CheckoutResponse)
@endpoint_class("cheap")
async def checkout(request: Request) -> CheckoutResponse:
    """Marks a simulated conversion event. Minimal computation — classed
    'cheap' like /api/home, but tracked separately via app_conversion_total
    for the future flash-crowd/EDoS conversion-rate comparison."""
    scenario = request.headers.get("x-scenario", "unspecified")
    APP_CONVERSION_TOTAL.labels(scenario=scenario).inc()
    return CheckoutResponse(status="ok", converted=True)
