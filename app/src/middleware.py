"""ASGI middleware: request metrics recording and session cookie tracking."""
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from .metrics import (
    APP_ENDPOINT_DURATION_SECONDS,
    APP_ENDPOINT_REQUESTS_TOTAL,
    HTTP_REQUEST_DURATION_SECONDS,
    HTTP_REQUESTS_TOTAL,
)
from .sessions import SessionTracker

# Infrastructure endpoints (Kubernetes probes, Prometheus scraping itself)
# and the storefront demo UI's own page/asset requests are excluded from
# traffic/session instrumentation — none of these are application traffic
# and would otherwise inflate http_requests_total and app_active_sessions
# with probe noise (observed: kubelet's probes, sent without cookies, were
# minting a "new session" every 5s) or with page-load noise from a human
# browsing the storefront (see storefront.py). The /api/* calls that page
# makes are NOT excluded — those are real, instrumented traffic exactly
# like any Locust-generated request.
_EXCLUDED_PATHS = frozenset({"/healthz", "/metrics", "/shop"})
_EXCLUDED_PREFIXES = ("/static/",)


def _is_excluded(path: str) -> bool:
    return path in _EXCLUDED_PATHS or path.startswith(_EXCLUDED_PREFIXES)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Records http_* metrics for every request, and app_endpoint_* metrics
    for requests that hit a route tagged via @endpoint_class (see metrics.py).
    """

    async def dispatch(self, request: Request, call_next):
        if _is_excluded(request.url.path):
            return await call_next(request)

        start = time.perf_counter()
        scenario = request.headers.get("x-scenario", "unspecified")

        response = await call_next(request)

        duration = time.perf_counter() - start
        method = request.method
        status_class = f"{response.status_code // 100}xx"

        HTTP_REQUESTS_TOTAL.labels(method=method, status_class=status_class, scenario=scenario).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(method=method, scenario=scenario).observe(duration)

        route = request.scope.get("route")
        cls = getattr(getattr(route, "endpoint", None), "endpoint_class", None)
        if cls:
            APP_ENDPOINT_REQUESTS_TOTAL.labels(endpoint_class=cls, status_class=status_class, scenario=scenario).inc()
            APP_ENDPOINT_DURATION_SECONDS.labels(endpoint_class=cls, scenario=scenario).observe(duration)

        return response


class SessionTrackingMiddleware(BaseHTTPMiddleware):
    """Simulates session continuity via an opaque cookie (never used as a
    metric label) and keeps app_active_sessions current.
    """

    COOKIE_NAME = "cascade_session"

    def __init__(self, app, tracker: SessionTracker):
        super().__init__(app)
        self._tracker = tracker

    async def dispatch(self, request: Request, call_next):
        if _is_excluded(request.url.path):
            return await call_next(request)

        session_id = request.cookies.get(self.COOKIE_NAME)
        session_id = self._tracker.touch(session_id)

        response = await call_next(request)

        response.set_cookie(
            self.COOKIE_NAME,
            session_id,
            max_age=int(self._tracker.ttl_seconds),
            httponly=True,
        )
        return response
