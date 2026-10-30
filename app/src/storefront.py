"""Storefront demo UI — a human-facing 'dummy shop' skin over the existing
cheap/medium/expensive endpoints (CLAUDE.md section 6).

This exists so flash-crowd and EDoS traffic aimed at this app has a
visible, relatable target during a live demo, instead of only showing up
as rows in a dashboard. It never reimplements application logic: every
action on the page (browse, search, checkout, "generate report") calls
the *same* /api/* endpoints Locust and the dashboard's Attack/Flash Crowd
Simulator call, so a human clicking around produces identical, real,
instrumented traffic to a synthetic run — nothing here is a client-side
fake animation.

Serves HTML/static assets only. Kept out of app_endpoint_* / traffic
metrics via middleware.py's exclusion list (page navigation is not
experiment traffic; the API calls the page makes still count normally).
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter()


@router.get("/shop", response_class=HTMLResponse)
async def shop(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "store.html")
