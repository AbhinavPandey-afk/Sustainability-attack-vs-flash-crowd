"""Application-behaviour features — CLAUDE.md section 14.4 (core proposed
features). Computed from cumulative endpoint-class/cache/conversion
counters, the app_session_duration_seconds histogram, and the
active-sessions gauge, within a window.

Two features are session-based PROXIES rather than true client-identity
measurements — the app deliberately does not track client IPs (CLAUDE.md
section 7 warns against unbounded labels such as raw user/session IDs):

  unique_client_ratio   uses mean active sessions as a stand-in for
                         distinct actors (not verified against real
                         client identity).
  requests_per_session   divides by that same proxy.

This is a documented limitation, not an unstated assumption — see
docs/feature_dictionary.md's "Potential leakage" field for each.
"""
from __future__ import annotations

import math

import pandas as pd

EMPTY = {
    "endpoint_diversity": 0.0,
    "unique_endpoint_ratio": 0.0,
    "expensive_endpoint_ratio": 0.0,
    "cheap_endpoint_ratio": 0.0,
    "search_ratio": 0.0,
    "report_generation_ratio": 0.0,
    "requests_per_session": 0.0,
    "session_duration": 0.0,
    "unique_client_ratio": 0.0,
    "cache_hit_rate": 0.0,
    "cache_miss_rate": 0.0,
    "conversion_rate": 0.0,
}


def compute(window: pd.DataFrame, request_count: float) -> dict:
    if len(window) < 2:
        return dict(EMPTY)

    def delta(col: str) -> float:
        return max(float(window[col].iloc[-1] - window[col].iloc[0]), 0.0)

    cheap = delta("cheap_count")
    medium = delta("medium_count")
    expensive = delta("expensive_count")
    cache_hits = delta("cache_hits")
    cache_misses = delta("cache_misses")
    conversions = delta("conversions")
    duration_sum = delta("session_duration_sum")
    duration_count = delta("session_duration_count")

    class_counts = {"cheap": cheap, "medium": medium, "expensive": expensive}
    unique_endpoint_ratio = sum(1 for v in class_counts.values() if v > 0) / 3.0

    total_class_requests = cheap + medium + expensive
    if total_class_requests > 0:
        proportions = [v / total_class_requests for v in class_counts.values() if v > 0]
        entropy = -sum(p * math.log(p) for p in proportions)
        # log(3) normalizes to [0, 1]: 0 = concentrated on one class
        # (the EDoS signature), 1 = perfectly spread across all three.
        endpoint_diversity = entropy / math.log(3)
    else:
        endpoint_diversity = 0.0

    expensive_endpoint_ratio = (expensive / request_count) if request_count > 0 else 0.0
    cheap_endpoint_ratio = (cheap / request_count) if request_count > 0 else 0.0
    # 'search' is currently the only medium-class endpoint in the app.
    search_ratio = (medium / request_count) if request_count > 0 else 0.0
    # 'generate-report' is currently the only expensive-class endpoint.
    report_generation_ratio = expensive_endpoint_ratio

    mean_active_sessions = float(window["active_sessions"].mean())
    requests_per_session = (request_count / mean_active_sessions) if mean_active_sessions > 0 else 0.0
    unique_client_ratio = (mean_active_sessions / request_count) if request_count > 0 else 0.0

    session_duration = (duration_sum / duration_count) if duration_count > 0 else 0.0

    cache_total = cache_hits + cache_misses
    cache_hit_rate = (cache_hits / cache_total) if cache_total > 0 else 0.0
    cache_miss_rate = (cache_misses / cache_total) if cache_total > 0 else 0.0

    conversion_rate = (conversions / request_count) if request_count > 0 else 0.0

    return {
        "endpoint_diversity": endpoint_diversity,
        "unique_endpoint_ratio": unique_endpoint_ratio,
        "expensive_endpoint_ratio": expensive_endpoint_ratio,
        "cheap_endpoint_ratio": cheap_endpoint_ratio,
        "search_ratio": search_ratio,
        "report_generation_ratio": report_generation_ratio,
        "requests_per_session": requests_per_session,
        "session_duration": session_duration,
        "unique_client_ratio": unique_client_ratio,
        "cache_hit_rate": cache_hit_rate,
        "cache_miss_rate": cache_miss_rate,
        "conversion_rate": conversion_rate,
    }
