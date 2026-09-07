"""Prometheus metric definitions for the CASCADE test application.

Metric names and label sets follow CLAUDE.md section 7. Labels are kept
intentionally bounded (endpoint class, HTTP method, status class, scenario)
— no raw URLs, query strings, or session IDs are ever used as label values.

This module only *defines* metrics and exposes them for scraping via
/metrics. Deploying an actual Prometheus server to scrape them is a later
phase (Kubernetes/Prometheus deployment, CLAUDE.md Phase 3).
"""
from prometheus_client import Counter, Gauge, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests received, across all routes.",
    ["method", "status_class", "scenario"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds, across all routes.",
    ["method", "scenario"],
)

APP_ENDPOINT_REQUESTS_TOTAL = Counter(
    "app_endpoint_requests_total",
    "Total requests per application endpoint class (cheap/medium/expensive).",
    ["endpoint_class", "status_class", "scenario"],
)

APP_ENDPOINT_DURATION_SECONDS = Histogram(
    "app_endpoint_duration_seconds",
    "Request duration per application endpoint class, in seconds.",
    ["endpoint_class", "scenario"],
)

APP_ACTIVE_SESSIONS = Gauge(
    "app_active_sessions",
    "Number of currently active simulated sessions.",
)

APP_SESSION_DURATION_SECONDS = Histogram(
    "app_session_duration_seconds",
    "Observed lifetime of a simulated session, recorded when it expires.",
    buckets=(5, 15, 30, 60, 120, 300, 600, 1800, 3600),
)

APP_CACHE_HITS_TOTAL = Counter(
    "app_cache_hits_total",
    "Total cache hits, by endpoint class.",
    ["endpoint_class"],
)

APP_CACHE_MISSES_TOTAL = Counter(
    "app_cache_misses_total",
    "Total cache misses, by endpoint class.",
    ["endpoint_class"],
)

APP_CONVERSION_TOTAL = Counter(
    "app_conversion_total",
    "Total simulated conversion events.",
    ["scenario"],
)


def endpoint_class(name: str):
    """Tag a route handler with its endpoint class for MetricsMiddleware.

    Applied *under* the router decorator so the attribute survives on the
    same function object FastAPI registers as the route endpoint:

        @router.get(...)
        @endpoint_class("cheap")
        async def handler(): ...
    """

    def decorator(func):
        func.endpoint_class = name
        return func

    return decorator
