"""Live 'impact strip' data for the storefront demo UI (app/src/storefront.py).

Aggregates the same real signals the rest of this dashboard already reads
— Kubernetes replica/CPU state (system_status.check_kubernetes) and
Prometheus request-rate queries — into one compact endpoint the storefront
page polls every couple of seconds, plus a running cost accrual computed
with the same replica-minute formula as app/src/cost.py / CLAUDE.md
section 10 (replica_cost_per_minute x active_minutes), integrated over
wall-clock time since this backend process started.

Everything returned is either a live read, a formula applied to a real
live-read replica count, or a per-poll delta of a real Prometheus counter
— nothing here is a fabricated or precomputed number. When Kubernetes/
Prometheus aren't reachable, the corresponding fields come back as
None/False rather than a guessed value (see system_status.py's docstring:
"never claim a component healthy without an actual live check").

expensive_endpoint_ratio here is a live, single-window echo of the same
named feature computed properly (over a configurable rolling window, with
history) by feature_engineering/behaviour_features.py for the trained
model — this one is for the storefront's descriptive banner only, not a
model prediction (see store.js's renderBanner comment).
"""
from __future__ import annotations

import time

import httpx

import system_status
from config import DEFAULT_PROMETHEUS_URL, DEFAULT_REPLICA_COST_PER_MINUTE

_ENDPOINT_CLASSES = ("cheap", "medium", "expensive")

# In-memory running-cost accumulator for this backend process's lifetime.
# This is a live demo counter for the storefront strip, not a persisted
# experiment result — real experiment cost is computed from recorded
# replica-interval samples by feature_engineering/cost_features.py and
# written under data/experiments/<id>/, independently of this module.
_accrual_state = {"last_ts": None, "total_cost": 0.0}

# In-memory previous-poll counters, used only to derive per-poll request
# deltas for the storefront's live feed (store.js). Also process-lifetime
# state, not a persisted artifact.
_delta_state: dict = {"last_counts": None}


def _accrue_cost(replicas: int | None) -> float:
    now = time.monotonic()
    last_ts = _accrual_state["last_ts"]
    if last_ts is not None:
        elapsed_minutes = max(now - last_ts, 0.0) / 60.0
        _accrual_state["total_cost"] += (replicas or 0) * DEFAULT_REPLICA_COST_PER_MINUTE * elapsed_minutes
    _accrual_state["last_ts"] = now
    return _accrual_state["total_cost"]


def _query_prometheus_scalar(query: str, base_url: str) -> float | None:
    try:
        resp = httpx.get(f"{base_url}/api/v1/query", params={"query": query}, timeout=2.0)
        resp.raise_for_status()
        result = resp.json()["data"]["result"]
        if not result:
            return 0.0
        return float(result[0]["value"][1])
    except Exception:  # noqa: BLE001 - unreachable/misconfigured Prometheus, report unavailable
        return None


def _query_prometheus_by_class(query: str, base_url: str) -> dict[str, float] | None:
    try:
        resp = httpx.get(f"{base_url}/api/v1/query", params={"query": query}, timeout=2.0)
        resp.raise_for_status()
        result = resp.json()["data"]["result"]
        counts = {item["metric"].get("endpoint_class", "unknown"): float(item["value"][1]) for item in result}
        return {cls: counts.get(cls, 0.0) for cls in _ENDPOINT_CLASSES}
    except Exception:  # noqa: BLE001 - unreachable/misconfigured Prometheus, report unavailable
        return None


def _compute_request_deltas(base_url: str) -> dict[str, float] | None:
    """Real per-poll delta of app_endpoint_requests_total (a cumulative
    Prometheus counter), by endpoint class. Returns None on the first call
    after a backend restart (no prior sample to diff against yet) or when
    Prometheus is unreachable — never a guessed delta."""
    counts = _query_prometheus_by_class("sum by (endpoint_class) (app_endpoint_requests_total)", base_url)
    if counts is None:
        return None
    previous = _delta_state["last_counts"]
    _delta_state["last_counts"] = counts
    if previous is None:
        return None
    return {cls: max(0.0, counts[cls] - previous.get(cls, 0.0)) for cls in _ENDPOINT_CLASSES}


def get_live_impact() -> dict:
    k8s = system_status.check_kubernetes()
    replicas = k8s.get("replicas")
    cpu_pct = k8s.get("current_cpu_utilization_pct")
    kubernetes_available = k8s.get("status") != system_status.STATUS_UNAVAILABLE

    request_rate_total = _query_prometheus_scalar("sum(rate(http_requests_total[30s]))", DEFAULT_PROMETHEUS_URL)
    request_rate_by_class = {
        endpoint_class: _query_prometheus_scalar(
            f'sum(rate(app_endpoint_requests_total{{endpoint_class="{endpoint_class}"}}[30s]))',
            DEFAULT_PROMETHEUS_URL,
        )
        for endpoint_class in _ENDPOINT_CLASSES
    }
    request_delta_by_class = _compute_request_deltas(DEFAULT_PROMETHEUS_URL)

    expensive_rate = request_rate_by_class.get("expensive")
    expensive_endpoint_ratio = (
        (expensive_rate / request_rate_total) if request_rate_total and expensive_rate is not None else None
    )

    cost_rate_per_minute = (replicas or 0) * DEFAULT_REPLICA_COST_PER_MINUTE
    estimated_cost_session = _accrue_cost(replicas)

    return {
        "kubernetes_available": kubernetes_available,
        "replicas": replicas,
        "min_replicas": k8s.get("min_replicas"),
        "max_replicas": k8s.get("max_replicas"),
        "cpu_utilization_pct": cpu_pct,
        "prometheus_available": request_rate_total is not None,
        "request_rate_total": request_rate_total,
        "request_rate_by_class": request_rate_by_class,
        "request_delta_by_class": request_delta_by_class,
        "expensive_endpoint_ratio": expensive_endpoint_ratio,
        "cost_rate_per_minute": cost_rate_per_minute,
        "estimated_cost_session": round(estimated_cost_session, 4),
        "replica_cost_per_minute": DEFAULT_REPLICA_COST_PER_MINUTE,
    }
