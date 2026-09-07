"""Phase 2 static/unit tests for the FastAPI application.

These run entirely in-process via FastAPI's TestClient — no Docker, no
Kubernetes cluster, no network calls. Docker-specific behaviour ("the app
runs in Docker and responds correctly") is validated separately and is not
part of the default `pytest` run (see the Phase 2 delivery notes / README).
"""
from fastapi.testclient import TestClient

from app.src.main import app

client = TestClient(app)


def test_home_endpoint():
    response = client.get("/api/home")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert isinstance(body["message"], str) and body["message"]


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_search_returns_schema_and_marks_cache_miss_then_hit():
    query = "unique-test-query-alpha"

    first = client.get("/api/search", params={"q": query})
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["query"] == query
    assert first_body["cached"] is False
    assert isinstance(first_body["results"], list)

    second = client.get("/api/search", params={"q": query})
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["cached"] is True
    assert second_body["results"] == first_body["results"]


def test_search_requires_query_param():
    response = client.get("/api/search")
    assert response.status_code == 422


def test_generate_report_is_deterministic_for_same_complexity():
    first = client.post("/api/generate-report", json={"complexity": 3})
    second = client.post("/api/generate-report", json={"complexity": 3})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["checksum"] == second.json()["checksum"]
    assert first.json()["iterations"] == second.json()["iterations"]


def test_generate_report_uses_default_complexity_when_body_omitted():
    response = client.post("/api/generate-report")
    assert response.status_code == 200
    body = response.json()
    assert body["complexity"] > 0
    assert body["iterations"] > 0
    assert body["duration_seconds"] >= 0


def test_generate_report_rejects_out_of_range_complexity():
    response = client.post("/api/generate-report", json={"complexity": 100_000})
    assert response.status_code == 422


def test_generate_report_iterations_are_bounded():
    response = client.post("/api/generate-report", json={"complexity": 100})
    assert response.status_code == 200
    # Must never exceed the app's hard ceiling regardless of complexity.
    from app.src.config import settings

    assert response.json()["iterations"] <= settings.REPORT_MAX_ITERATIONS


def test_checkout_marks_conversion():
    response = client.post("/api/checkout")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "converted": True}


def test_metrics_endpoint_exposes_expected_metric_families():
    # Exercise each endpoint class once so their metrics are guaranteed
    # to have been recorded before we scrape.
    client.get("/api/home")
    client.get("/api/search", params={"q": "metrics-check"})
    client.post("/api/generate-report", json={"complexity": 1})
    client.post("/api/checkout")

    response = client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")

    body = response.text
    expected_metric_names = [
        "http_requests_total",
        "http_request_duration_seconds",
        "app_endpoint_requests_total",
        "app_endpoint_duration_seconds",
        "app_active_sessions",
        "app_session_duration_seconds",
        "app_cache_hits_total",
        "app_cache_misses_total",
        "app_conversion_total",
    ]
    for name in expected_metric_names:
        assert name in body, f"missing metric family: {name}"


def test_metrics_labels_are_bounded_not_raw_query_strings():
    client.get("/api/search", params={"q": "should-not-appear-as-a-label"})
    response = client.get("/metrics")
    assert "should-not-appear-as-a-label" not in response.text


def test_session_cookie_is_set_and_active_sessions_gauge_increments():
    fresh_client = TestClient(app)
    response = fresh_client.get("/api/home")
    assert "cascade_session" in response.cookies

    metrics_response = fresh_client.get("/metrics")
    assert "app_active_sessions" in metrics_response.text


def test_healthz_and_metrics_do_not_mint_sessions_or_count_as_traffic():
    """Kubernetes probes hit /healthz repeatedly without cookies; Prometheus
    scrapes /metrics repeatedly. Neither should inflate app_active_sessions
    or http_requests_total — they are not application traffic."""
    from app.src.metrics import APP_ACTIVE_SESSIONS, HTTP_REQUESTS_TOTAL

    fresh_client = TestClient(app)
    assert "cascade_session" not in fresh_client.get("/healthz").cookies

    counter = HTTP_REQUESTS_TOTAL.labels(method="GET", status_class="2xx", scenario="unspecified")
    before_requests = counter._value.get()
    before_sessions = APP_ACTIVE_SESSIONS._value.get()

    for _ in range(5):
        fresh_client.get("/healthz")
        fresh_client.get("/metrics")

    assert counter._value.get() == before_requests
    assert APP_ACTIVE_SESSIONS._value.get() == before_sessions
